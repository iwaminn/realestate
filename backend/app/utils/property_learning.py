"""
物件統合履歴から学習して、向きの表記揺れなどを自動紐付けする機能
"""

from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import logging
from collections import defaultdict

from ..models import PropertyMergeHistory, MasterProperty, Building

logger = logging.getLogger(__name__)


class PropertyLearningService:
    """物件統合履歴から学習するサービス"""
    
    def __init__(self, session: Session):
        self.session = session
        self.direction_patterns = defaultdict(set)  # 建物ごとの方角パターンを記録
        self.layout_patterns = defaultdict(set)     # 建物ごとの間取りパターンを記録
        
    def learn_from_merge_history(self, building_id: int) -> Dict[str, any]:
        """
        特定の建物の統合履歴から学習
        
        Returns:
            学習した関連性のパターン
        """
        # その建物の物件統合履歴を取得
        properties_in_building = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == building_id
        ).all()
        
        property_ids = [p.id for p in properties_in_building]
        
        # 統合履歴を取得（統合元と統合先の両方を取得）
        merge_histories = self.session.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.final_primary_property_id.in_(property_ids)
        ).all()
        
        # 学習パターンを抽出
        direction_aliases = defaultdict(set)  # 同じ物件で使われた方角のバリエーション
        layout_aliases = defaultdict(set)     # 同じ物件で使われた間取りのバリエーション
        
        for history in merge_histories:
            if history.merge_details:
                secondary = history.merge_details.get('secondary_property', {})
                primary_updates = history.merge_details.get('primary_updates', {})
                
                # 統合先の物件情報を取得
                primary_property = self.session.query(MasterProperty).get(history.final_primary_property_id)
                if not primary_property:
                    continue
                
                # 方角のパターンを学習
                if secondary.get('direction') and primary_property.direction:
                    # 同じ物件だが異なる方角表記を記録
                    key = (
                        primary_property.floor_number,
                        primary_property.area,
                        primary_property.layout
                    )
                    direction_aliases[key].add(secondary['direction'])
                    direction_aliases[key].add(primary_property.direction)
                
                # 間取りのパターンを学習
                if secondary.get('layout') and primary_property.layout:
                    key = (
                        primary_property.floor_number,
                        primary_property.area,
                        primary_property.direction
                    )
                    layout_aliases[key].add(secondary['layout'])
                    layout_aliases[key].add(primary_property.layout)
        
        # 学習結果をまとめる
        learning_result = {
            'building_id': building_id,
            'direction_patterns': {},
            'layout_patterns': {},
            'learned_count': len(merge_histories)
        }
        
        # 方角パターンを整理
        for key, directions in direction_aliases.items():
            if len(directions) > 1:
                floor, area, layout = key
                pattern_key = f"{floor}F_{area}㎡_{layout}"
                learning_result['direction_patterns'][pattern_key] = list(directions)
                logger.info(f"建物{building_id}の{pattern_key}で複数の方角パターンを発見: {directions}")
        
        # 間取りパターンを整理
        for key, layouts in layout_aliases.items():
            if len(layouts) > 1:
                floor, area, direction = key
                pattern_key = f"{floor}F_{area}㎡_{direction}"
                learning_result['layout_patterns'][pattern_key] = list(layouts)
                logger.info(f"建物{building_id}の{pattern_key}で複数の間取りパターンを発見: {layouts}")
        
        return learning_result
    
    def find_property_with_learning(
        self,
        building_id: int,
        floor_number: Optional[int],
        area: Optional[float],
        layout: Optional[str],
        direction: Optional[str],
        room_number: Optional[str] = None
    ) -> List[MasterProperty]:
        """
        学習結果を使って物件を検索
        
        完全一致しない場合でも、過去の統合パターンから類似物件を見つける
        """
        # まず通常の検索
        query = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == building_id
        )
        
        if floor_number is not None:
            query = query.filter(MasterProperty.floor_number == floor_number)
        
        if area is not None:
            query = query.filter(
                MasterProperty.area.between(area - 0.5, area + 0.5)
            )
        
        # 通常の検索で見つかった場合
        exact_matches = query.all()
        if exact_matches:
            # 方角と間取りも完全一致するものを優先
            perfect_matches = [
                p for p in exact_matches
                if p.layout == layout and p.direction == direction
            ]
            if perfect_matches:
                return perfect_matches
        
        # 学習結果を使った柔軟な検索
        learning_result = self.learn_from_merge_history(building_id)
        
        # 方角の代替パターンを確認
        alternative_directions = set([direction]) if direction else set()
        for pattern_key, directions in learning_result['direction_patterns'].items():
            if direction in directions:
                alternative_directions.update(directions)
                logger.info(f"方角の代替パターンを発見: {direction} → {directions}")
        
        # 間取りの代替パターンを確認
        alternative_layouts = set([layout]) if layout else set()
        for pattern_key, layouts in learning_result['layout_patterns'].items():
            if layout in layouts:
                alternative_layouts.update(layouts)
                logger.info(f"間取りの代替パターンを発見: {layout} → {layouts}")
        
        # 代替パターンで再検索
        flexible_matches = []
        for match in exact_matches:
            # 方角の柔軟な一致
            direction_match = (
                match.direction in alternative_directions or
                direction in alternative_directions or
                match.direction is None or
                direction is None
            )
            
            # 間取りの柔軟な一致
            layout_match = (
                match.layout in alternative_layouts or
                layout in alternative_layouts or
                match.layout is None or
                layout is None
            )
            
            if direction_match and layout_match:
                flexible_matches.append(match)
                logger.info(
                    f"学習により物件を発見: ID={match.id}, "
                    f"方角={match.direction}（入力: {direction}）, "
                    f"間取り={match.layout}（入力: {layout}）"
                )
        
        return flexible_matches
    
    def get_direction_variations(self, building_id: int, floor_number: int) -> Set[str]:
        """
        特定の建物・階の方角バリエーションを取得
        
        同じ階で過去に統合された物件の方角パターンを返す
        """
        # その階の統合履歴を確認
        properties = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == building_id,
            MasterProperty.floor_number == floor_number
        ).all()
        
        property_ids = [p.id for p in properties]
        
        # 統合履歴から方角のバリエーションを収集
        variations = set()
        
        merge_histories = self.session.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.final_primary_property_id.in_(property_ids)
        ).all()
        
        for history in merge_histories:
            if history.merge_details:
                secondary = history.merge_details.get('secondary_property', {})
                if secondary.get('direction'):
                    variations.add(secondary['direction'])
            
            # 現在の物件の方角も追加
            primary = self.session.query(MasterProperty).get(history.final_primary_property_id)
            if primary and primary.direction:
                variations.add(primary.direction)
        
        return variations
    
    def suggest_merge_candidates(
        self,
        property_id: int,
        confidence_threshold: float = 0.7
    ) -> List[Tuple[MasterProperty, float, str]]:
        """
        学習結果を使って統合候補を提案
        
        Returns:
            [(候補物件, 信頼度スコア, 理由)]
        """
        target_property = self.session.query(MasterProperty).get(property_id)
        if not target_property:
            return []
        
        # 学習結果を取得
        learning_result = self.learn_from_merge_history(target_property.building_id)
        
        # 同じ建物の他の物件を検索
        candidates = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == target_property.building_id,
            MasterProperty.id != property_id,
            MasterProperty.floor_number == target_property.floor_number
        ).all()
        
        suggestions = []
        
        for candidate in candidates:
            score = 0.0
            reasons = []
            
            # 面積の一致度
            if target_property.area and candidate.area:
                area_diff = abs(target_property.area - candidate.area)
                if area_diff <= 0.5:
                    score += 0.4
                    reasons.append(f"面積が一致（差{area_diff}㎡）")
            
            # 方角の一致度（学習パターンを考慮）
            if target_property.direction and candidate.direction:
                # 過去の統合パターンで関連があるか確認
                pattern_key = f"{target_property.floor_number}F_{target_property.area}㎡_{target_property.layout}"
                if pattern_key in learning_result['direction_patterns']:
                    learned_directions = learning_result['direction_patterns'][pattern_key]
                    if (target_property.direction in learned_directions and 
                        candidate.direction in learned_directions):
                        score += 0.3
                        reasons.append(f"方角が統合パターンに一致（{target_property.direction}↔{candidate.direction}）")
            
            # 間取りの一致度（学習パターンを考慮）
            if target_property.layout and candidate.layout:
                pattern_key = f"{target_property.floor_number}F_{target_property.area}㎡_{target_property.direction}"
                if pattern_key in learning_result['layout_patterns']:
                    learned_layouts = learning_result['layout_patterns'][pattern_key]
                    if (target_property.layout in learned_layouts and 
                        candidate.layout in learned_layouts):
                        score += 0.3
                        reasons.append(f"間取りが統合パターンに一致（{target_property.layout}↔{candidate.layout}）")
            
            if score >= confidence_threshold and reasons:
                suggestions.append((candidate, score, "、".join(reasons)))
        
        # スコア順にソート
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return suggestions