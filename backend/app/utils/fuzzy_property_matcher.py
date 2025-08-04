"""
ファジーマッチングによる物件重複判定ユーティリティ

物件の自動重複判定精度を向上させるための高度なマッチングロジック
"""

import re
from typing import Optional, Tuple, List, Dict, Any
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class FuzzyPropertyMatcher:
    """ファジーマッチングによる物件重複判定クラス"""
    
    def __init__(self):
        # 許容誤差の設定
        self.area_tolerance = 0.5  # 面積の許容誤差（㎡）
        self.floor_tolerance = 0   # 階数の許容誤差（基本は完全一致）
        
        # 類似度の閾値
        self.high_confidence_threshold = 0.95  # 高確度閾値
        self.medium_confidence_threshold = 0.85  # 中確度閾値
        self.low_confidence_threshold = 0.75   # 低確度閾値
        
        # 方角の正規化マップ
        self.direction_map = {
            # 基本方角
            '東': ['東', 'E', 'EAST', '東向き'],
            '西': ['西', 'W', 'WEST', '西向き'],
            '南': ['南', 'S', 'SOUTH', '南向き'],
            '北': ['北', 'N', 'NORTH', '北向き'],
            # 複合方角
            '南東': ['南東', 'SE', 'SOUTHEAST', '東南'],
            '南西': ['南西', 'SW', 'SOUTHWEST', '西南'],
            '北東': ['北東', 'NE', 'NORTHEAST', '東北'],
            '北西': ['北西', 'NW', 'NORTHWEST', '西北'],
        }
        
        # 間取りの正規化パターン
        self.layout_patterns = {
            # 数字+LDKパターン
            r'(\d+)LDK\+S': r'\1SLDK',  # 1LDK+S → 1SLDK
            r'(\d+)LDK\+WIC': r'\1LDK',  # WICは無視
            r'(\d+)LDK\+SIC': r'\1LDK',  # SICは無視
            r'(\d+)LDK\+N': r'\1LDK',    # 納戸は無視
            # スペースの統一
            r'(\d+)\s*LDK': r'\1LDK',
            r'(\d+)\s*DK': r'\1DK',
            r'(\d+)\s*K': r'\1K',
            r'(\d+)\s*R': r'\1R',
            # ワンルームの統一
            r'ワンルーム': '1R',
            r'1ルーム': '1R',
            r'1ROOM': '1R',
            # スタジオタイプ
            r'スタジオ': '1R',
            r'STUDIO': '1R',
        }
    
    def normalize_direction(self, direction: Optional[str]) -> Optional[str]:
        """方角を正規化"""
        if not direction:
            return None
            
        direction = direction.strip()
        
        # 正規化マップから検索
        for normalized, variations in self.direction_map.items():
            if direction in variations:
                return normalized
                
        # マッチしない場合は元の値を返す
        return direction
    
    def normalize_layout(self, layout: Optional[str]) -> Optional[str]:
        """間取りを正規化"""
        if not layout:
            return None
            
        layout = layout.strip().upper()
        
        # パターンマッチングで正規化
        for pattern, replacement in self.layout_patterns.items():
            layout = re.sub(pattern, replacement, layout, flags=re.IGNORECASE)
            
        return layout
    
    def calculate_property_similarity(
        self,
        prop1: Dict[str, Any],
        prop2: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """
        2つの物件の類似度を計算
        
        Returns:
            (類似度スコア, 一致した特徴のリスト)
        """
        score = 0.0
        max_score = 0.0
        matched_features = []
        
        # 1. 建物IDチェック（必須）
        if prop1.get('building_id') != prop2.get('building_id'):
            return 0.0, []
        
        # 2. 階数チェック（重要度: 高）
        max_score += 30
        floor1 = prop1.get('floor_number')
        floor2 = prop2.get('floor_number')
        
        if floor1 is not None and floor2 is not None:
            if abs(floor1 - floor2) <= self.floor_tolerance:
                score += 30
                matched_features.append(f"階数一致: {floor1}階")
            else:
                # 階数が異なる場合は別物件の可能性が高い
                return score / 100, matched_features
        elif floor1 is None or floor2 is None:
            # 片方が不明の場合は部分点
            score += 15
            matched_features.append("階数: 片方不明")
        
        # 3. 面積チェック（重要度: 高）
        max_score += 30
        area1 = prop1.get('area')
        area2 = prop2.get('area')
        
        if area1 is not None and area2 is not None:
            area_diff = abs(area1 - area2)
            if area_diff <= self.area_tolerance:
                score += 30
                matched_features.append(f"面積一致: {area1}㎡")
            elif area_diff <= 1.0:
                # 1㎡以内の差は部分点
                score += 20
                matched_features.append(f"面積近似: {area1}㎡と{area2}㎡")
            else:
                # 面積が大きく異なる場合も別物件の可能性
                score += 5
        elif area1 is None or area2 is None:
            score += 15
            matched_features.append("面積: 片方不明")
        
        # 4. 間取りチェック（重要度: 高）
        max_score += 25
        layout1 = self.normalize_layout(prop1.get('layout'))
        layout2 = self.normalize_layout(prop2.get('layout'))
        
        if layout1 and layout2:
            if layout1 == layout2:
                score += 25
                matched_features.append(f"間取り一致: {layout1}")
            else:
                # 類似間取りチェック（例: 1LDKと1SLDK）
                if self._are_layouts_similar(layout1, layout2):
                    score += 15
                    matched_features.append(f"間取り類似: {layout1}と{layout2}")
        elif layout1 is None or layout2 is None:
            score += 12
            matched_features.append("間取り: 片方不明")
        
        # 5. 方角チェック（重要度: 中）
        max_score += 15
        dir1 = self.normalize_direction(prop1.get('direction'))
        dir2 = self.normalize_direction(prop2.get('direction'))
        
        if dir1 and dir2:
            if dir1 == dir2:
                score += 15
                matched_features.append(f"方角一致: {dir1}")
            elif self._are_directions_similar(dir1, dir2):
                score += 10
                matched_features.append(f"方角類似: {dir1}と{dir2}")
        elif dir1 is None or dir2 is None:
            # 方角は不明でも許容
            score += 10
            matched_features.append("方角: 片方不明")
        
        # 6. 部屋番号チェック（あれば確実性UP）
        room1 = prop1.get('room_number')
        room2 = prop2.get('room_number')
        
        if room1 and room2:
            if room1 == room2:
                # ボーナス点
                score += 20
                matched_features.append(f"部屋番号一致: {room1}")
            else:
                # 部屋番号が異なる場合は減点
                score -= 10
        
        # 7. バルコニー面積チェック（補助的）
        balcony1 = prop1.get('balcony_area')
        balcony2 = prop2.get('balcony_area')
        
        if balcony1 is not None and balcony2 is not None:
            if abs(balcony1 - balcony2) <= 0.5:
                score += 5
                matched_features.append(f"バルコニー面積一致: {balcony1}㎡")
        
        # 最終スコア計算（0-1の範囲に正規化）
        final_score = min(score / max_score, 1.0)
        
        return final_score, matched_features
    
    def _are_layouts_similar(self, layout1: str, layout2: str) -> bool:
        """間取りが類似しているかチェック"""
        # 数字部分を抽出
        num1 = re.search(r'(\d+)', layout1)
        num2 = re.search(r'(\d+)', layout2)
        
        if num1 and num2 and num1.group(1) == num2.group(1):
            # 同じ部屋数で微妙な違い（1LDKと1SLDK等）
            return True
            
        # 文字列の類似度チェック
        return SequenceMatcher(None, layout1, layout2).ratio() > 0.8
    
    def _are_directions_similar(self, dir1: str, dir2: str) -> bool:
        """方角が類似しているかチェック"""
        # 隣接する方角は類似とみなす
        adjacent_directions = {
            '東': ['南東', '北東'],
            '西': ['南西', '北西'],
            '南': ['南東', '南西'],
            '北': ['北東', '北西'],
            '南東': ['東', '南'],
            '南西': ['西', '南'],
            '北東': ['東', '北'],
            '北西': ['西', '北'],
        }
        
        return dir2 in adjacent_directions.get(dir1, [])
    
    def find_duplicate_candidates(
        self,
        target_property: Dict[str, Any],
        candidate_properties: List[Dict[str, Any]],
        confidence_level: str = 'medium'
    ) -> List[Tuple[Dict[str, Any], float, List[str]]]:
        """
        重複候補を検索
        
        Args:
            target_property: 対象物件
            candidate_properties: 候補物件リスト
            confidence_level: 'high', 'medium', 'low'
            
        Returns:
            [(候補物件, 類似度スコア, 一致特徴リスト), ...]
        """
        threshold_map = {
            'high': self.high_confidence_threshold,
            'medium': self.medium_confidence_threshold,
            'low': self.low_confidence_threshold,
        }
        threshold = threshold_map.get(confidence_level, self.medium_confidence_threshold)
        
        results = []
        
        for candidate in candidate_properties:
            # 自分自身はスキップ
            if candidate.get('id') == target_property.get('id'):
                continue
                
            score, features = self.calculate_property_similarity(
                target_property,
                candidate
            )
            
            if score >= threshold:
                results.append((candidate, score, features))
        
        # スコアの高い順にソート
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def get_merge_recommendation(
        self,
        score: float,
        matched_features: List[str]
    ) -> Dict[str, Any]:
        """
        統合推奨度を判定
        
        Returns:
            {
                'should_merge': bool,
                'confidence': str,  # 'high', 'medium', 'low'
                'reason': str
            }
        """
        if score >= self.high_confidence_threshold:
            return {
                'should_merge': True,
                'confidence': 'high',
                'reason': f"高い類似度（{score:.1%}）: " + ", ".join(matched_features)
            }
        elif score >= self.medium_confidence_threshold:
            # 重要な特徴が一致しているかチェック
            important_features = ['階数一致', '面積一致', '間取り一致']
            matched_important = sum(
                1 for feature in matched_features 
                if any(imp in feature for imp in important_features)
            )
            
            if matched_important >= 2:
                return {
                    'should_merge': True,
                    'confidence': 'medium',
                    'reason': f"中程度の類似度（{score:.1%}）: " + ", ".join(matched_features)
                }
            else:
                return {
                    'should_merge': False,
                    'confidence': 'medium',
                    'reason': f"類似度は中程度（{score:.1%}）だが、重要な特徴の一致が不足"
                }
        else:
            return {
                'should_merge': False,
                'confidence': 'low',
                'reason': f"類似度が低い（{score:.1%}）"
            }