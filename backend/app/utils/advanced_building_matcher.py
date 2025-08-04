"""
高度な建物マッチングユーティリティ

建物の自動重複判定精度を向上させるための高度なマッチングロジック
"""

import re
from typing import Optional, Tuple, List, Dict, Any, Set
from difflib import SequenceMatcher
import logging
from collections import Counter

logger = logging.getLogger(__name__)


class AdvancedBuildingMatcher:
    """高度な建物マッチングクラス"""
    
    def __init__(self):
        # 類似度の閾値
        self.high_confidence_threshold = 0.90
        self.medium_confidence_threshold = 0.80
        self.low_confidence_threshold = 0.70
        
        # 住所の重み
        self.address_weight = 0.4
        self.name_weight = 0.6
        
        # よくある建物名の省略パターン
        self.abbreviation_patterns = {
            # 英語の省略
            'MS': ['マンション', 'MANSION'],
            'BLD': ['ビルディング', 'BUILDING'],
            'BLDG': ['ビルディング', 'BUILDING'],
            'RES': ['レジデンス', 'RESIDENCE'],
            'CT': ['コート', 'COURT'],
            'HTS': ['ハイツ', 'HEIGHTS'],
            'HSE': ['ハウス', 'HOUSE'],
            'PL': ['プレイス', 'PLACE'],
            'SQ': ['スクエア', 'SQUARE'],
            # 日本語の省略
            'マン': ['マンション'],
            'レジ': ['レジデンス'],
            'アパ': ['アパート'],
        }
        
        # 建物名の同義語辞書
        self.synonyms = {
            'アパートメント': 'アパート',
            'マンション': 'マンション',
            'レジデンス': 'レジデンス',
            'ハイツ': 'ハイツ',
            'コーポ': 'コーポ',
            'メゾン': 'メゾン',
            'ヴィラ': 'ヴィラ',
            'ビラ': 'ヴィラ',
            'プラザ': 'プラザ',
            'タワー': 'タワー',
            'コート': 'コート',
            'パレス': 'パレス',
            'ハウス': 'ハウス',
            'ホーム': 'ホーム',
            'ガーデン': 'ガーデン',
            'パーク': 'パーク',
            'ヒルズ': 'ヒルズ',
            'テラス': 'テラス',
            'フラッツ': 'フラッツ',
            'アネックス': 'アネックス',
            'ウィング': 'ウィング',
        }
        
        # 数字の表記ゆれ辞書
        self.number_variations = {
            '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
            '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
            '１': '1', '２': '2', '３': '3', '４': '4', '５': '5',
            '６': '6', '７': '7', '８': '8', '９': '9', '０': '0',
            'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4', 'Ⅴ': '5',
            'Ⅵ': '6', 'Ⅶ': '7', 'Ⅷ': '8', 'Ⅸ': '9', 'Ⅹ': '10',
            'ⅰ': '1', 'ⅱ': '2', 'ⅲ': '3', 'ⅳ': '4', 'ⅴ': '5',
        }
    
    def expand_abbreviations(self, name: str) -> List[str]:
        """略語を展開して複数の候補を生成"""
        candidates = [name]
        
        # 大文字小文字を統一
        upper_name = name.upper()
        
        # 略語パターンをチェック
        for abbr, expansions in self.abbreviation_patterns.items():
            if abbr in upper_name:
                for expansion in expansions:
                    # 略語を展開した候補を追加
                    expanded = upper_name.replace(abbr, expansion)
                    candidates.append(expanded)
        
        return list(set(candidates))
    
    def normalize_numbers(self, text: str) -> str:
        """数字の表記を統一"""
        normalized = text
        
        # 数字の変換
        for old, new in self.number_variations.items():
            normalized = normalized.replace(old, new)
        
        # 連続する数字の処理（例: "2 3" → "23"）
        normalized = re.sub(r'(\d)\s+(\d)', r'\1\2', normalized)
        
        return normalized
    
    def extract_address_components(self, address: str) -> Dict[str, str]:
        """住所を構成要素に分解"""
        components = {
            'prefecture': '',
            'city': '',
            'ward': '',
            'town': '',
            'block': '',
            'building_number': ''
        }
        
        if not address:
            return components
        
        # 都道府県
        pref_match = re.search(r'(東京都|.*?[都道府県])', address)
        if pref_match:
            components['prefecture'] = pref_match.group(1)
            address = address[len(pref_match.group(1)):]
        
        # 市区町村
        city_match = re.search(r'^(.*?[市区町村])', address)
        if city_match:
            components['city'] = city_match.group(1)
            address = address[len(city_match.group(1)):]
        
        # 町名・番地
        # より柔軟なパターンマッチング
        block_match = re.search(r'(\d+[-－丁目]*\d*[-－]*\d*)', address)
        if block_match:
            components['block'] = block_match.group(1)
            components['town'] = address[:block_match.start()].strip()
        else:
            components['town'] = address.strip()
        
        return components
    
    def calculate_address_similarity(self, addr1: str, addr2: str) -> float:
        """住所の類似度を計算"""
        if not addr1 or not addr2:
            return 0.0
        
        # 住所を構成要素に分解
        comp1 = self.extract_address_components(addr1)
        comp2 = self.extract_address_components(addr2)
        
        # 各要素の一致度を計算
        scores = []
        weights = {
            'prefecture': 0.1,
            'city': 0.2,
            'ward': 0.2,
            'town': 0.3,
            'block': 0.2
        }
        
        for key, weight in weights.items():
            if comp1[key] and comp2[key]:
                if comp1[key] == comp2[key]:
                    scores.append(weight)
                else:
                    # 部分一致も考慮
                    similarity = SequenceMatcher(None, comp1[key], comp2[key]).ratio()
                    scores.append(weight * similarity)
        
        return sum(scores)
    
    def tokenize_building_name(self, name: str) -> List[str]:
        """建物名をトークンに分割"""
        # 正規化
        name = self.normalize_numbers(name)
        
        # 特殊文字で分割
        tokens = re.split(r'[\s\-・＿_－【】\[\]（）\(\)]+', name)
        
        # 空のトークンを除去
        tokens = [t for t in tokens if t]
        
        # 各トークンを正規化
        normalized_tokens = []
        for token in tokens:
            # 同義語変換
            normalized = self.synonyms.get(token, token)
            normalized_tokens.append(normalized)
        
        return normalized_tokens
    
    def calculate_token_similarity(self, tokens1: List[str], tokens2: List[str]) -> float:
        """トークンベースの類似度計算"""
        if not tokens1 or not tokens2:
            return 0.0
        
        # トークンの集合を作成
        set1 = set(tokens1)
        set2 = set(tokens2)
        
        # Jaccard係数
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        jaccard = intersection / union
        
        # 順序も考慮した類似度
        sequence_similarity = SequenceMatcher(None, tokens1, tokens2).ratio()
        
        # 重み付け平均
        return jaccard * 0.6 + sequence_similarity * 0.4
    
    def detect_building_variants(self, name: str) -> List[str]:
        """建物名のバリエーションを検出"""
        variants = [name]
        
        # 棟の表記バリエーション
        unit_patterns = [
            (r'([A-Z])棟', r'\1'),  # A棟 → A
            (r'第(\d+)棟', r'\1棟'),  # 第1棟 → 1棟
            (r'(\d+)号棟', r'\1棟'),  # 1号棟 → 1棟
            (r'(東|西|南|北)棟', r'\1'),  # 東棟 → 東
            (r'(EAST|WEST|SOUTH|NORTH)', r'\1棟'),  # EAST → EAST棟
        ]
        
        for pattern, replacement in unit_patterns:
            variant = re.sub(pattern, replacement, name)
            if variant != name:
                variants.append(variant)
        
        # 括弧内の情報の有無
        no_paren = re.sub(r'\([^)]*\)', '', name).strip()
        if no_paren != name:
            variants.append(no_paren)
        
        return list(set(variants))
    
    def calculate_building_similarity(
        self,
        building1: Dict[str, Any],
        building2: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        2つの建物の類似度を計算
        
        Returns:
            (類似度スコア, 詳細情報)
        """
        details = {
            'name_score': 0.0,
            'address_score': 0.0,
            'matched_features': [],
            'confidence': 'low',
            'variants_checked': []
        }
        
        name1 = building1.get('normalized_name', '')
        name2 = building2.get('normalized_name', '')
        addr1 = building1.get('address', '')
        addr2 = building2.get('address', '')
        
        # 建物名のバリエーションを生成
        variants1 = self.detect_building_variants(name1)
        variants2 = self.detect_building_variants(name2)
        details['variants_checked'] = {
            'building1': variants1,
            'building2': variants2
        }
        
        # 最も高い類似度を採用
        max_name_score = 0.0
        
        for v1 in variants1:
            for v2 in variants2:
                # 略語展開
                expanded1 = self.expand_abbreviations(v1)
                expanded2 = self.expand_abbreviations(v2)
                
                for e1 in expanded1:
                    for e2 in expanded2:
                        # トークン化
                        tokens1 = self.tokenize_building_name(e1)
                        tokens2 = self.tokenize_building_name(e2)
                        
                        # トークンベースの類似度
                        token_score = self.calculate_token_similarity(tokens1, tokens2)
                        
                        # 文字列全体の類似度
                        string_score = SequenceMatcher(None, e1, e2).ratio()
                        
                        # 組み合わせ
                        combined_score = token_score * 0.7 + string_score * 0.3
                        
                        if combined_score > max_name_score:
                            max_name_score = combined_score
                            details['matched_features'] = [
                                f"名前類似: {v1} ≈ {v2} (トークン一致: {token_score:.1%})"
                            ]
        
        details['name_score'] = max_name_score
        
        # 住所の類似度
        if addr1 and addr2:
            address_score = self.calculate_address_similarity(addr1, addr2)
            details['address_score'] = address_score
            
            if address_score > 0.8:
                details['matched_features'].append(f"住所一致度: {address_score:.1%}")
        
        # 総合スコア
        if addr1 and addr2:
            # 住所がある場合は名前と住所の重み付け平均
            total_score = (
                max_name_score * self.name_weight +
                address_score * self.address_weight
            )
        else:
            # 住所がない場合は名前のみ
            total_score = max_name_score
        
        # 築年数が近いかチェック（補助的）
        year1 = building1.get('built_year')
        year2 = building2.get('built_year')
        
        if year1 and year2:
            year_diff = abs(year1 - year2)
            if year_diff <= 1:
                total_score += 0.05  # ボーナス
                details['matched_features'].append(f"築年近似: {year1}年と{year2}年")
            elif year_diff > 5:
                total_score -= 0.05  # ペナルティ
        
        # 総階数が近いかチェック（補助的）
        floors1 = building1.get('total_floors')
        floors2 = building2.get('total_floors')
        
        if floors1 and floors2:
            floor_diff = abs(floors1 - floors2)
            if floor_diff == 0:
                total_score += 0.05  # ボーナス
                details['matched_features'].append(f"総階数一致: {floors1}階")
            elif floor_diff > 3:
                total_score -= 0.05  # ペナルティ
        
        # スコアを0-1の範囲に制限
        total_score = max(0.0, min(1.0, total_score))
        
        # 信頼度の判定
        if total_score >= self.high_confidence_threshold:
            details['confidence'] = 'high'
        elif total_score >= self.medium_confidence_threshold:
            details['confidence'] = 'medium'
        else:
            details['confidence'] = 'low'
        
        return total_score, details
    
    def find_duplicate_buildings(
        self,
        target_building: Dict[str, Any],
        candidate_buildings: List[Dict[str, Any]],
        min_confidence: str = 'medium'
    ) -> List[Tuple[Dict[str, Any], float, Dict[str, Any]]]:
        """
        重複建物候補を検索
        
        Returns:
            [(候補建物, 類似度スコア, 詳細情報), ...]
        """
        threshold_map = {
            'high': self.high_confidence_threshold,
            'medium': self.medium_confidence_threshold,
            'low': self.low_confidence_threshold,
        }
        threshold = threshold_map.get(min_confidence, self.medium_confidence_threshold)
        
        results = []
        
        for candidate in candidate_buildings:
            # 自分自身はスキップ
            if candidate.get('id') == target_building.get('id'):
                continue
            
            score, details = self.calculate_building_similarity(
                target_building,
                candidate
            )
            
            if score >= threshold:
                results.append((candidate, score, details))
        
        # スコアの高い順にソート
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def get_merge_recommendation(
        self,
        score: float,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        統合推奨度を判定
        
        Returns:
            {
                'should_merge': bool,
                'confidence': str,
                'reason': str,
                'warnings': List[str]
            }
        """
        warnings = []
        
        # 名前と住所のスコアをチェック
        name_score = details.get('name_score', 0)
        address_score = details.get('address_score', 0)
        
        if details['confidence'] == 'high':
            # 高信頼度でも追加チェック
            if name_score < 0.7:
                warnings.append("建物名の類似度がやや低い")
            if address_score > 0 and address_score < 0.7:
                warnings.append("住所の一致度がやや低い")
            
            return {
                'should_merge': True,
                'confidence': 'high',
                'reason': f"高い類似度（{score:.1%}）",
                'warnings': warnings
            }
            
        elif details['confidence'] == 'medium':
            # 中信頼度の場合は詳細をチェック
            if name_score >= 0.85 and address_score >= 0.85:
                return {
                    'should_merge': True,
                    'confidence': 'medium',
                    'reason': "名前と住所の両方が高い一致度",
                    'warnings': warnings
                }
            elif name_score >= 0.9:
                warnings.append("住所情報での確認が推奨される")
                return {
                    'should_merge': True,
                    'confidence': 'medium',
                    'reason': "建物名が非常に類似",
                    'warnings': warnings
                }
            else:
                return {
                    'should_merge': False,
                    'confidence': 'medium',
                    'reason': "確実な一致とは言えない",
                    'warnings': ['手動確認を推奨']
                }
                
        else:
            return {
                'should_merge': False,
                'confidence': 'low',
                'reason': f"類似度が低い（{score:.1%}）",
                'warnings': []
            }