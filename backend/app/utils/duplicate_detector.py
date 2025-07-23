"""
建物重複検出の最適化されたユーティリティ
"""

from typing import List, Dict, Set, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from difflib import SequenceMatcher
import re

from ..models import Building, MasterProperty, BuildingMergeExclusion
from .building_normalizer import BuildingNameNormalizer


class OptimizedDuplicateDetector:
    """最適化された建物重複検出クラス"""
    
    def __init__(self, db: Session):
        self.db = db
        self.normalizer = BuildingNameNormalizer()
        self._normalized_cache = {}
        self._excluded_pairs = None
    
    def get_excluded_pairs(self) -> Set[Tuple[int, int]]:
        """除外ペアを取得（キャッシュ付き）"""
        if self._excluded_pairs is None:
            exclusions = self.db.query(BuildingMergeExclusion).all()
            self._excluded_pairs = set()
            for exclusion in exclusions:
                self._excluded_pairs.add((exclusion.building1_id, exclusion.building2_id))
                self._excluded_pairs.add((exclusion.building2_id, exclusion.building1_id))
        return self._excluded_pairs
    
    def normalize_cached(self, building_id: int, name: str) -> str:
        """正規化された名前を取得（キャッシュ付き）"""
        if building_id not in self._normalized_cache:
            self._normalized_cache[building_id] = self.normalizer.normalize(name)
        return self._normalized_cache[building_id]
    
    def quick_similarity_check(self, name1: str, name2: str) -> bool:
        """簡易的な類似度チェック（高速）"""
        # 長さの差が大きい場合は類似していない
        if abs(len(name1) - len(name2)) > 10:
            return False
        
        # 最初の3文字が異なる場合は類似していない
        if len(name1) >= 3 and len(name2) >= 3:
            if name1[:3] != name2[:3]:
                return False
        
        return True
    
    def find_duplicates(
        self, 
        min_similarity: float = 0.95,
        limit: int = 50,
        search: Optional[str] = None
    ) -> Dict[str, any]:
        """重複建物を効率的に検出"""
        
        # 建物を取得（物件数付き）
        query = self.db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).group_by(
            Building.id
        ).having(
            func.count(MasterProperty.id) > 0
        )
        
        if search:
            search_normalized = search.replace('・', '')
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    Building.normalized_name.ilike(f"%{search}%"),
                    Building.normalized_name.ilike(f"%{search_normalized}%")
                )
            )
        
        # 検索時は少なめ、通常時は多めに取得
        fetch_limit = 100 if search else 300
        buildings_with_count = query.order_by(
            Building.normalized_name
        ).limit(fetch_limit).all()
        
        # グループ化による効率的な重複検出
        name_groups = {}
        for building, count in buildings_with_count:
            # 名前の最初の3文字でグループ化
            norm_name = self.normalize_cached(building.id, building.normalized_name)
            if len(norm_name) >= 3:
                key = norm_name[:3]
            else:
                key = norm_name
            
            if key not in name_groups:
                name_groups[key] = []
            name_groups[key].append((building, count, norm_name))
        
        # 各グループ内で比較
        duplicates = []
        processed_ids = set()
        excluded_pairs = self.get_excluded_pairs()
        total_comparisons = 0
        
        for group_key, group_buildings in name_groups.items():
            # 同じグループ内の建物同士を比較
            for i, (building1, count1, norm1) in enumerate(group_buildings):
                if building1.id in processed_ids:
                    continue
                
                candidates = []
                
                for j, (building2, count2, norm2) in enumerate(group_buildings[i+1:], i+1):
                    if building2.id in processed_ids:
                        continue
                    
                    # 除外ペアチェック
                    if (building1.id, building2.id) in excluded_pairs:
                        continue
                    
                    # 簡易チェック
                    if not self.quick_similarity_check(norm1, norm2):
                        continue
                    
                    # 住所チェック（高速版）
                    if building1.address and building2.address:
                        # 異なる区の場合はスキップ
                        if '区' in building1.address and '区' in building2.address:
                            district1 = building1.address.split('区')[0]
                            district2 = building2.address.split('区')[0]
                            if district1 != district2:
                                continue
                    
                    # 詳細な類似度計算
                    total_comparisons += 1
                    similarity = self.normalizer.calculate_similarity(
                        building1.normalized_name, 
                        building2.normalized_name
                    )
                    
                    if similarity >= min_similarity:
                        candidates.append({
                            "id": building2.id,
                            "normalized_name": building2.normalized_name,
                            "address": building2.address,
                            "total_floors": building2.total_floors,
                            "property_count": count2,
                            "similarity": similarity
                        })
                        processed_ids.add(building2.id)
                
                if candidates:
                    duplicates.append({
                        "primary": {
                            "id": building1.id,
                            "normalized_name": building1.normalized_name,
                            "address": building1.address,
                            "total_floors": building1.total_floors,
                            "property_count": count1
                        },
                        "candidates": candidates
                    })
                    processed_ids.add(building1.id)
                    
                    if len(duplicates) >= limit:
                        break
            
            if len(duplicates) >= limit:
                break
        
        return {
            "duplicate_groups": duplicates,
            "total_groups": len(duplicates),
            "total_buildings_checked": len(buildings_with_count),
            "total_comparisons": total_comparisons
        }