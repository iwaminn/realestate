"""
建物管理用のAPIエンドポイント
高パフォーマンス版の重複検出を実装
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from backend.app.database import get_db
from backend.app.models import Building, MasterProperty, BuildingMergeExclusion
from backend.app.utils.enhanced_building_matcher import EnhancedBuildingMatcher
from backend.app.schemas import BuildingSchema
import logging

app_logger = logging.getLogger("api")

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/duplicate-buildings-fast", response_model=Dict[str, Any])
async def get_duplicate_buildings_fast(
    min_similarity: float = Query(0.94, description="最小類似度"),
    limit: int = Query(50, description="最大グループ数"),
    search: Optional[str] = Query(None, description="建物名検索"),
    db: Session = Depends(get_db)
):
    """高速版：重複の可能性がある建物を検出"""
    from backend.app.utils.address_normalizer import AddressNormalizer
    
    enhanced_matcher = EnhancedBuildingMatcher()
    address_normalizer = AddressNormalizer()
    
    # クエリを構築
    query = db.query(
        Building,
        func.count(distinct(MasterProperty.id)).label('property_count')
    ).outerjoin(
        MasterProperty, Building.id == MasterProperty.building_id
    ).group_by(
        Building.id
    ).having(
        func.count(distinct(MasterProperty.id)) > 0  # 物件がある建物のみ
    )
    
    # 検索フィルタを適用
    if search:
        from backend.app.utils.building_search import apply_building_search_to_query
        query = apply_building_search_to_query(query, search, Building)
    
    # すべての建物を取得（制限なし）
    buildings_with_count = query.order_by(Building.normalized_name).all()
    
    if search:
        app_logger.info(f"Search '{search}' returned {len(buildings_with_count)} buildings")
    
    # 除外ペアを取得
    exclusions = db.query(BuildingMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        excluded_pairs.add((exclusion.building1_id, exclusion.building2_id))
        excluded_pairs.add((exclusion.building2_id, exclusion.building1_id))
    
    # 住所でグループ化して効率的に比較
    address_groups = {}
    for building, count in buildings_with_count:
        # 住所を正規化
        normalized_addr = address_normalizer.normalize(building.address)
        base_addr = normalized_addr.split('丁目')[0]  # 丁目より前の部分で大まかにグループ化
        
        if base_addr not in address_groups:
            address_groups[base_addr] = []
        address_groups[base_addr].append((building, count))
    
    # 重複候補を検出
    duplicates = []
    processed_ids = set()
    total_comparisons = 0
    
    # 各住所グループ内でのみ比較
    for base_addr, buildings_in_group in address_groups.items():
        # 住所グループ内での比較
        for i, (building1, count1) in enumerate(buildings_in_group):
            if building1.id in processed_ids:
                continue
                
            candidates = []
            
            for j, (building2, count2) in enumerate(buildings_in_group[i+1:], i+1):
                if building2.id in processed_ids:
                    continue
                
                # 除外リストに含まれていたらスキップ
                if (building1.id, building2.id) in excluded_pairs:
                    continue
                
                # 類似度計算
                total_comparisons += 1
                
                # 総合的な類似度を計算
                comprehensive_similarity = enhanced_matcher.calculate_comprehensive_similarity(
                    building1, building2
                )
                debug_info = enhanced_matcher.get_debug_info()
                
                # 閾値チェック
                if comprehensive_similarity >= min_similarity:
                    candidates.append({
                        "id": building2.id,
                        "normalized_name": building2.normalized_name,
                        "address": building2.address,
                        "total_floors": building2.total_floors,
                        "built_year": building2.built_year,
                        "built_month": building2.built_month,
                        "property_count": count2,
                        "similarity": comprehensive_similarity,
                        "address_similarity": debug_info['scores'].get('address', 0),
                        "name_similarity": debug_info['scores'].get('name', 0),
                        "attribute_similarity": debug_info['scores'].get('attributes', 0),
                        "match_reason": debug_info.get('match_reason', ''),
                        "floors_match": True
                    })
                    processed_ids.add(building2.id)
            
            if candidates:
                duplicates.append({
                    "primary": {
                        "id": building1.id,
                        "normalized_name": building1.normalized_name,
                        "address": building1.address,
                        "total_floors": building1.total_floors,
                        "built_year": building1.built_year,
                        "built_month": building1.built_month,
                        "property_count": count1
                    },
                    "candidates": candidates
                })
                processed_ids.add(building1.id)
                
                # 制限に達したら終了
                if len(duplicates) >= limit:
                    break
            
        # 制限に達したら終了
        if len(duplicates) >= limit:
            break
    
    return {
        "duplicate_groups": duplicates,
        "total_groups": len(duplicates),
        "total_buildings_checked": len(buildings_with_count),
        "total_comparisons": total_comparisons,
        "address_groups": len(address_groups)
    }