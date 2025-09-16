"""
物件マッチングコンポーネント

物件の類似度計算とマッチング処理を担当するコンポーネント
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from ...utils.fuzzy_property_matcher import FuzzyPropertyMatcher as BaseMatcher


class PropertyMatcherComponent:
    """物件マッチングコンポーネント"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
        self.matcher = BaseMatcher()
    
    def find_similar_property(
        self,
        property_data: Dict[str, Any],
        existing_properties: List[Dict[str, Any]],
        threshold: float = 0.85
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        類似物件を検索
        
        Args:
            property_data: 検索対象の物件データ
            existing_properties: 既存物件のリスト
            threshold: 類似度の閾値
            
        Returns:
            最も類似度の高い物件と類似度のタプル（該当なしの場合None）
        """
        if not existing_properties:
            return None
        
        try:
            best_match = None
            best_score = 0.0
            
            for existing in existing_properties:
                score = self.calculate_similarity(property_data, existing)
                if score > best_score and score >= threshold:
                    best_match = existing
                    best_score = score
            
            if best_match:
                self.logger.debug(
                    f"類似物件発見: スコア={best_score:.2f}, "
                    f"建物名={best_match.get('building_name')}"
                )
                return best_match, best_score
            
            return None
            
        except Exception as e:
            self.logger.error(f"物件マッチングエラー: {e}")
            return None
    
    def calculate_similarity(
        self,
        property1: Dict[str, Any],
        property2: Dict[str, Any]
    ) -> float:
        """
        2つの物件の類似度を計算
        
        Args:
            property1: 物件データ1
            property2: 物件データ2
            
        Returns:
            類似度スコア（0.0-1.0）
        """
        try:
            # 基本的な属性の重み
            weights = {
                'building_name': 0.3,
                'floor_number': 0.2,
                'area': 0.2,
                'layout': 0.15,
                'direction': 0.15
            }
            
            total_score = 0.0
            total_weight = 0.0
            
            for field, weight in weights.items():
                if field in property1 and field in property2:
                    score = self._calculate_field_similarity(
                        field, 
                        property1[field],
                        property2[field]
                    )
                    total_score += score * weight
                    total_weight += weight
            
            # 重みの合計で正規化
            if total_weight > 0:
                return total_score / total_weight
            
            return 0.0
            
        except Exception as e:
            self.logger.error(f"類似度計算エラー: {e}")
            return 0.0
    
    def _calculate_field_similarity(
        self,
        field: str,
        value1: Any,
        value2: Any
    ) -> float:
        """
        フィールドごとの類似度を計算
        
        Args:
            field: フィールド名
            value1: 値1
            value2: 値2
            
        Returns:
            類似度スコア（0.0-1.0）
        """
        if value1 is None or value2 is None:
            return 0.0
        
        if field == 'building_name':
            # 建物名は文字列の類似度
            from difflib import SequenceMatcher
            return SequenceMatcher(None, str(value1), str(value2)).ratio()
        
        elif field == 'floor_number':
            # 階数は完全一致
            return 1.0 if value1 == value2 else 0.0
        
        elif field == 'area':
            # 面積は許容誤差0.5㎡
            diff = abs(float(value1) - float(value2))
            return 1.0 if diff <= 0.5 else 0.0
        
        elif field == 'layout':
            # 間取りは完全一致
            return 1.0 if value1 == value2 else 0.0
        
        elif field == 'direction':
            # 方角は完全一致
            return 1.0 if value1 == value2 else 0.0
        
        else:
            # その他は文字列比較
            return 1.0 if str(value1) == str(value2) else 0.0
    
    def is_duplicate(
        self,
        property1: Dict[str, Any],
        property2: Dict[str, Any]
    ) -> bool:
        """
        2つの物件が重複かどうか判定
        
        Args:
            property1: 物件データ1
            property2: 物件データ2
            
        Returns:
            重複の場合True
        """
        # 必須フィールドのチェック
        required_fields = ['building_id', 'floor_number', 'area', 'layout']
        
        for field in required_fields:
            if field not in property1 or field not in property2:
                return False
        
        # 建物IDが異なれば重複ではない
        if property1.get('building_id') != property2.get('building_id'):
            return False
        
        # 階数、面積、間取りで判定
        return (
            property1.get('floor_number') == property2.get('floor_number') and
            abs(float(property1.get('area', 0)) - float(property2.get('area', 0))) <= 0.5 and
            property1.get('layout') == property2.get('layout')
        )