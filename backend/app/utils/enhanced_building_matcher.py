"""
高度な建物マッチングユーティリティ（統合版）

既存のマッチングユーティリティを統合し、
より高精度な建物重複検出を実現します。
"""

import re
from typing import Dict, Optional, Tuple, List, Any
from difflib import SequenceMatcher
import logging

from .address_normalizer import AddressNormalizer
from .building_normalizer import BuildingNameNormalizer
from .advanced_building_matcher import AdvancedBuildingMatcher
from .katakana_converter import english_to_katakana

logger = logging.getLogger(__name__)


class EnhancedBuildingMatcher:
    """統合型建物マッチャークラス"""
    
    def __init__(self):
        self.address_normalizer = AddressNormalizer()
        self.building_normalizer = BuildingNameNormalizer()
        self.advanced_matcher = AdvancedBuildingMatcher()
        
        # デバッグ情報を保存
        self.last_debug_info = {}
    
    def calculate_comprehensive_similarity(self, building1: Any, building2: Any) -> float:
        """総合的な類似度を計算
        
        Args:
            building1: 建物1のオブジェクト（Building model）
            building2: 建物2のオブジェクト（Building model）
            
        Returns:
            類似度スコア（0.0-1.0）
        """
        # デバッグ情報をリセット
        self.last_debug_info = {
            'building1_id': building1.id,
            'building2_id': building2.id,
            'building1_name': building1.normalized_name,
            'building2_name': building2.normalized_name,
            'scores': {}
        }
        
        # 1. 住所の類似度（正規化後）
        addr_score = self._calculate_address_similarity(
            building1.address, building2.address
        )
        self.last_debug_info['scores']['address'] = addr_score
        
        # 2. 建物名の類似度（複数の手法を組み合わせ）
        name_score = self._calculate_name_similarity(
            building1.normalized_name, building2.normalized_name
        )
        self.last_debug_info['scores']['name'] = name_score
        
        # 3. 属性の一致度（築年月、総階数）
        attr_score = self._calculate_attribute_similarity(
            building1, building2
        )
        self.last_debug_info['scores']['attributes'] = attr_score
        
        # 4. 総合スコア計算
        final_score = self._calculate_final_score(
            addr_score, name_score, attr_score
        )
        self.last_debug_info['final_score'] = final_score
        
        return final_score
    
    def _calculate_address_similarity(self, addr1: Optional[str], addr2: Optional[str]) -> float:
        """住所の類似度を計算（正規化後）"""
        if not addr1 or not addr2:
            return 0.0
        
        # 住所を正規化
        norm_addr1 = self.address_normalizer.normalize(addr1)
        norm_addr2 = self.address_normalizer.normalize(addr2)
        
        # デバッグ情報
        self.last_debug_info['normalized_addresses'] = {
            'addr1': norm_addr1,
            'addr2': norm_addr2
        }
        
        # 完全一致の場合
        if norm_addr1 == norm_addr2:
            return 1.0
        
        # 構成要素に分解
        comp1 = self.address_normalizer.extract_components(norm_addr1)
        comp2 = self.address_normalizer.extract_components(norm_addr2)
        
        # デバッグ情報
        self.last_debug_info['address_components'] = {
            'comp1': comp1,
            'comp2': comp2
        }
        
        # 番地レベルまで比較（部分一致を考慮）
        if comp1['block'] and comp2['block']:
            # 番地を数値配列に分解（例：「1-9-18」→[1, 9, 18]）
            nums1 = self.address_normalizer.extract_block_numbers(comp1['block'])
            nums2 = self.address_normalizer.extract_block_numbers(comp2['block'])
            
            if nums1 and nums2:
                # 短い方の長さで比較（部分一致の判定）
                min_len = min(len(nums1), len(nums2))
                
                # 最初の要素（丁目）が異なる場合は明確に別住所
                if nums1[0] != nums2[0]:
                    # 町名までが一致している場合のみ部分点
                    if (comp1['prefecture'] == comp2['prefecture'] and
                        comp1['city'] == comp2['city'] and
                        comp1['area'] == comp2['area']):
                        return 0.3  # 同じ地域だが丁目が違う（別住所の可能性高）
                    else:
                        return 0.1  # 完全に異なる
                
                # 丁目が一致する場合、共通部分をチェック
                matches = sum(1 for i in range(min_len) if nums1[i] == nums2[i])
                
                if matches == min_len:
                    # 片方が他方の部分集合（例：「1-9-18」と「1-9」または「1」）
                    if len(nums1) == len(nums2):
                        return 0.95  # 完全一致
                    else:
                        # 部分一致（片方が省略形の可能性）
                        if min_len == 1:
                            return 0.85  # 丁目のみ一致
                        elif min_len == 2:
                            return 0.90  # 番地まで一致
                        else:
                            return 0.93  # より詳細まで一致
                else:
                    # 途中から異なる（例：「1-9-18」と「1-10-5」）
                    if matches >= 1:
                        # 丁目は一致するが番地以降が異なる
                        return 0.4  # 同じ丁目だが別の番地
                    else:
                        return 0.2  # 異なる住所
            else:
                # 番地が文字列として一致するかチェック
                if comp1['block'] == comp2['block']:
                    return 0.95
                else:
                    return 0.4
        
        # 片方にのみ番地情報がある場合
        if comp1['block'] or comp2['block']:
            # 番地以外の部分が一致するかチェック
            if (comp1['prefecture'] == comp2['prefecture'] and
                comp1['city'] == comp2['city'] and
                comp1['area'] == comp2['area']):
                # 同じ地域で、片方のみ番地情報がある（省略の可能性）
                return 0.75  # 高い類似度だが、完全一致ではない
            else:
                # 地域も異なる
                return 0.3
        
        # 両方とも番地情報がない場合は文字列類似度で判定
        return SequenceMatcher(None, norm_addr1, norm_addr2).ratio()
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """建物名の類似度を計算（英字/カタカナ変換含む）"""
        if not name1 or not name2:
            return 0.0
        
        # 1. 基本的な正規化
        norm1 = self.building_normalizer.normalize(name1)
        norm2 = self.building_normalizer.normalize(name2)
        
        # 完全一致の場合
        if norm1 == norm2:
            return 1.0
        
        # 2. 名前のバリエーションを生成
        variations1 = self._generate_name_variations(name1)
        variations2 = self._generate_name_variations(name2)
        
        # デバッグ情報
        self.last_debug_info['name_variations'] = {
            'name1': list(variations1),
            'name2': list(variations2)
        }
        
        # 3. 全ての組み合わせで最高スコアを採用
        max_score = 0.0
        best_pair = None
        
        for v1 in variations1:
            for v2 in variations2:
                # 正規化してから比較
                norm_v1 = self.building_normalizer.normalize(v1)
                norm_v2 = self.building_normalizer.normalize(v2)
                
                # 構造化比較も試みる
                score = self.building_normalizer.calculate_similarity(v1, v2)
                
                if score > max_score:
                    max_score = score
                    best_pair = (v1, v2)
        
        # デバッグ情報
        if best_pair:
            self.last_debug_info['best_name_match'] = {
                'pair': best_pair,
                'score': max_score
            }
        
        return max_score
    
    def _generate_name_variations(self, name: str) -> List[str]:
        """英字/カタカナ/略語の変換候補を生成"""
        variations = {name}  # setで重複を避ける
        
        # 1. 英語→カタカナ変換
        if self._is_english(name):
            try:
                katakana = english_to_katakana(name)
                if katakana:
                    variations.add(katakana)
                    # スペースなしバージョンも追加
                    variations.add(katakana.replace(' ', '').replace('　', ''))
                    # 中点ありバージョンも追加
                    variations.add(katakana.replace(' ', '・').replace('　', '・'))
            except Exception as e:
                logger.debug(f"カタカナ変換エラー: {e}")
        
        # 2. カタカナ→英語変換（逆変換は現在の辞書では対応できないのでスキップ）
        # TODO: カタカナ→英語の逆変換辞書を作成する
        
        # 3. 略語展開
        expanded = self.advanced_matcher.expand_abbreviations(name)
        variations.update(expanded)
        
        # 4. 一般的な表記ゆれパターン
        for var in list(variations):
            # 「ザ・」「THE」のバリエーション
            if 'ザ・' in var:
                variations.add(var.replace('ザ・', 'THE '))
                variations.add(var.replace('ザ・', ''))
            if 'THE ' in var:
                variations.add(var.replace('THE ', 'ザ・'))
                variations.add(var.replace('THE ', ''))
            
            # 中点の有無
            if '・' in var:
                variations.add(var.replace('・', ''))
            elif ' ' in var:
                variations.add(var.replace(' ', '・'))
        
        return list(variations)
    
    def _is_english(self, text: str) -> bool:
        """英語を含むかチェック"""
        # アルファベットが全体の50%以上なら英語とみなす
        alpha_count = sum(1 for c in text if c.isalpha() and ord(c) < 128)
        return alpha_count > len(text) * 0.5
    
    def _is_katakana(self, text: str) -> bool:
        """カタカナを含むかチェック"""
        # カタカナが全体の50%以上ならカタカナとみなす
        katakana_count = sum(1 for c in text if 'ァ' <= c <= 'ヶ')
        return katakana_count > len(text) * 0.5
    
    def _calculate_attribute_similarity(self, building1: Any, building2: Any) -> float:
        """築年月、総階数の一致度を計算"""
        scores = []
        weights = []
        
        # 築年月の一致（厳格な判定 - 同一建物なら一致するはず）
        if building1.built_year and building2.built_year:
            # 築月情報の取得
            month1 = getattr(building1, 'built_month', None)
            month2 = getattr(building2, 'built_month', None)
            
            year_diff = abs(building1.built_year - building2.built_year)
            
            if year_diff == 0:
                # 年が完全一致する場合
                if month1 and month2:
                    # 両方とも月情報がある場合
                    if month1 == month2:
                        scores.append(1.0)  # 年月とも完全一致
                    else:
                        # 月が異なる = 誤表記または別建物の可能性
                        scores.append(0.3)  # 低い類似度
                else:
                    # 片方または両方の月情報がない場合
                    scores.append(0.7)  # 年のみで比較（月情報が不完全）
            elif year_diff == 1:
                # 1年差の場合（誤表記の可能性はあるが低い）
                scores.append(0.2)  # かなり低い類似度
            elif year_diff == 2:
                # 2年差（誤表記の可能性は極めて低い）
                scores.append(0.1)  # 非常に低い類似度
            else:
                # 3年以上の差は別建物
                scores.append(0.0)
            
            weights.append(2.0)  # 築年月は重要度高
        
        # 総階数の一致（段階的な類似度判定）
        if building1.total_floors and building2.total_floors:
            floor_diff = abs(building1.total_floors - building2.total_floors)
            
            if floor_diff == 0:
                scores.append(1.0)  # 完全一致
            elif floor_diff == 1:
                scores.append(0.5)  # 1階差は中程度の類似度（完全一致に比べて可能性が下がる）
            elif floor_diff == 2:
                scores.append(0.3)  # 2階差は低い類似度
            else:
                scores.append(0.0)  # 3階以上の差は別建物とみなす
            
            weights.append(1.5)  # 階数も重要
        
        # 構造の一致（もしあれば）
        if (hasattr(building1, 'construction_type') and 
            hasattr(building2, 'construction_type') and
            building1.construction_type and building2.construction_type):
            if building1.construction_type == building2.construction_type:
                scores.append(1.0)
            else:
                scores.append(0.5)  # 異なる構造
            weights.append(0.5)  # 構造は参考程度
        
        # デバッグ情報
        self.last_debug_info['attribute_details'] = {
            'built_year1': building1.built_year,
            'built_year2': building2.built_year,
            'built_month1': getattr(building1, 'built_month', None),
            'built_month2': getattr(building2, 'built_month', None),
            'total_floors1': building1.total_floors,
            'total_floors2': building2.total_floors,
        }
        
        # 重み付き平均を計算
        if weights:
            return sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            return 0.5  # 属性情報がない場合は中立的なスコア
    
    def _calculate_final_score(self, addr_score: float, name_score: float, attr_score: float) -> float:
        """最終的な類似度スコアを計算"""
        
        # ケース1: 住所・属性が高一致
        # → 建物名が異なっても同一建物の可能性が高い（英字/カタカナの違い等）
        if addr_score >= 0.95 and attr_score >= 0.9:
            # 建物名が極端に低い場合でも高スコア
            if name_score < 0.3:
                self.last_debug_info['match_reason'] = '住所と属性が完全一致（建物名は異なる）'
                return 0.92
            else:
                self.last_debug_info['match_reason'] = '住所と属性が完全一致'
                return 0.95
        
        # ケース2: 建物名が高一致で、住所も一致
        if name_score >= 0.85 and addr_score >= 0.8:
            self.last_debug_info['match_reason'] = '建物名と住所が高一致'
            return max(name_score, addr_score)
        
        # ケース3: 建物名は低いが、住所と属性が一致
        # → 英字/カタカナの表記違いの可能性
        if name_score < 0.5 and addr_score >= 0.9 and attr_score >= 0.8:
            self.last_debug_info['match_reason'] = '住所一致・属性一致（建物名の表記違いの可能性）'
            return 0.85
        
        # ケース4: 住所が不明だが、建物名と属性が高一致
        if addr_score == 0.0 and name_score >= 0.9 and attr_score >= 0.8:
            self.last_debug_info['match_reason'] = '建物名と属性が高一致（住所情報なし）'
            return 0.85
        
        # ケース5: 通常の重み付け計算
        # 住所がある場合とない場合で重みを調整
        if addr_score > 0:
            # 住所情報がある場合
            score = (
                name_score * 0.35 +
                addr_score * 0.40 +
                attr_score * 0.25
            )
            self.last_debug_info['match_reason'] = '総合判定（住所情報あり）'
        else:
            # 住所情報がない場合は建物名と属性を重視
            score = (
                name_score * 0.65 +
                attr_score * 0.35
            )
            self.last_debug_info['match_reason'] = '総合判定（住所情報なし）'
        
        return score
    
    def get_debug_info(self) -> Dict[str, Any]:
        """最後の比較のデバッグ情報を取得"""
        return self.last_debug_info.copy()