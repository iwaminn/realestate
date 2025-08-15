"""
除外管理API（建物・物件の統合除外設定）
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from ...database import get_db
from ...models import (
    PropertyMergeExclusion, BuildingMergeExclusion,
    MasterProperty, Building
)

router = APIRouter(tags=["admin-exclusions"])


class PropertyExclusionRequest(BaseModel):
    """物件除外リクエスト"""
    property1_id: int
    property2_id: int
    reason: Optional[str] = None


class BuildingExclusionRequest(BaseModel):
    """建物除外リクエスト"""
    building1_id: int
    building2_id: int
    reason: Optional[str] = None


class PropertyExclusionResponse(BaseModel):
    """物件除外レスポンス"""
    id: int
    property1_id: int
    property2_id: int
    property1_name: Optional[str]
    property2_name: Optional[str]
    reason: Optional[str]
    created_at: datetime
    created_by: Optional[str]


class BuildingExclusionResponse(BaseModel):
    """建物除外レスポンス"""
    id: int
    building1_id: int
    building2_id: int
    building1_name: Optional[str]
    building2_name: Optional[str]
    reason: Optional[str]
    created_at: datetime
    created_by: Optional[str]


@router.post("/exclude-properties")
async def exclude_properties(
    request: PropertyExclusionRequest,
    db: Session = Depends(get_db)
):
    """物件の統合を除外設定に追加"""
    
    # 既存の除外設定をチェック
    existing = db.query(PropertyMergeExclusion).filter(
        ((PropertyMergeExclusion.property1_id == request.property1_id) &
         (PropertyMergeExclusion.property2_id == request.property2_id)) |
        ((PropertyMergeExclusion.property1_id == request.property2_id) &
         (PropertyMergeExclusion.property2_id == request.property1_id))
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="この物件ペアは既に除外設定されています")
    
    # 物件の存在確認
    prop1 = db.query(MasterProperty).filter(MasterProperty.id == request.property1_id).first()
    prop2 = db.query(MasterProperty).filter(MasterProperty.id == request.property2_id).first()
    
    if not prop1 or not prop2:
        raise HTTPException(status_code=404, detail="指定された物件が見つかりません")
    
    # 除外設定を追加（ID順に保存）
    exclusion = PropertyMergeExclusion(
        property1_id=min(request.property1_id, request.property2_id),
        property2_id=max(request.property1_id, request.property2_id),
        reason=request.reason,
        created_at=datetime.now(),
        excluded_by="admin"
    )
    
    db.add(exclusion)
    db.commit()
    
    return {"message": "物件の除外設定を追加しました", "exclusion_id": exclusion.id}


@router.delete("/exclude-properties/{exclusion_id}")
async def delete_property_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db)
):
    """物件の除外設定を削除"""
    
    exclusion = db.query(PropertyMergeExclusion).filter(
        PropertyMergeExclusion.id == exclusion_id
    ).first()
    
    if not exclusion:
        raise HTTPException(status_code=404, detail="除外設定が見つかりません")
    
    db.delete(exclusion)
    db.commit()
    
    return {"message": "除外設定を削除しました"}


@router.get("/property-exclusions")
async def get_property_exclusions(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """物件の除外設定一覧を取得"""
    
    exclusions = db.query(PropertyMergeExclusion).order_by(
        PropertyMergeExclusion.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    results = []
    for exc in exclusions:
        # 物件情報を取得（建物情報も含める）
        prop1 = db.query(MasterProperty).options(
            joinedload(MasterProperty.building)
        ).filter(MasterProperty.id == exc.property1_id).first()
        prop2 = db.query(MasterProperty).options(
            joinedload(MasterProperty.building)
        ).filter(MasterProperty.id == exc.property2_id).first()
        
        # 物件1の情報を生成
        if prop1 and prop1.building:
            info_parts = [prop1.building.normalized_name]
            if prop1.room_number:
                info_parts.append(prop1.room_number)
            if prop1.floor_number:
                info_parts.append(f"{prop1.floor_number}F")
            if prop1.layout:
                info_parts.append(prop1.layout)
            if prop1.area:
                info_parts.append(f"{prop1.area}㎡")
            if prop1.direction:
                info_parts.append(prop1.direction)
            prop1_info = " / ".join(info_parts)
        else:
            prop1_info = f"物件ID: {exc.property1_id}"
        
        # 物件2の情報を生成
        if prop2 and prop2.building:
            info_parts = [prop2.building.normalized_name]
            if prop2.room_number:
                info_parts.append(prop2.room_number)
            if prop2.floor_number:
                info_parts.append(f"{prop2.floor_number}F")
            if prop2.layout:
                info_parts.append(prop2.layout)
            if prop2.area:
                info_parts.append(f"{prop2.area}㎡")
            if prop2.direction:
                info_parts.append(prop2.direction)
            prop2_info = " / ".join(info_parts)
        else:
            prop2_info = f"物件ID: {exc.property2_id}"
        
        results.append({
            "id": exc.id,
            "property1": {
                "id": exc.property1_id,
                "info": prop1_info,
                "building_name": prop1.building.normalized_name if prop1 and prop1.building else None,
                "room_number": prop1.room_number if prop1 else None,
                "floor_number": prop1.floor_number if prop1 else None,
                "area": prop1.area if prop1 else None,
                "direction": prop1.direction if prop1 else None
            },
            "property2": {
                "id": exc.property2_id,
                "info": prop2_info,
                "building_name": prop2.building.normalized_name if prop2 and prop2.building else None,
                "room_number": prop2.room_number if prop2 else None,
                "floor_number": prop2.floor_number if prop2 else None,
                "area": prop2.area if prop2 else None,
                "direction": prop2.direction if prop2 else None
            },
            "reason": exc.reason,
            "excluded_by": exc.excluded_by,
            "created_at": exc.created_at
        })
    
    return {"exclusions": results, "total": len(results)}


@router.post("/exclude-buildings")
async def exclude_buildings(
    request: BuildingExclusionRequest,
    db: Session = Depends(get_db)
):
    """建物ペアを統合候補から除外"""
    building1_id = request.building1_id
    building2_id = request.building2_id
    reason = request.reason
    
    # 既に除外されているかチェック
    from sqlalchemy import or_, and_
    existing = db.query(BuildingMergeExclusion).filter(
        or_(
            and_(
                BuildingMergeExclusion.building1_id == building1_id,
                BuildingMergeExclusion.building2_id == building2_id
            ),
            and_(
                BuildingMergeExclusion.building1_id == building2_id,
                BuildingMergeExclusion.building2_id == building1_id
            )
        )
    ).first()
    
    if existing:
        return {"success": False, "message": "既に除外済みです"}
    
    # 小さいIDを building1_id として保存（一貫性のため）
    if building1_id > building2_id:
        building1_id, building2_id = building2_id, building1_id
    
    exclusion = BuildingMergeExclusion(
        building1_id=building1_id,
        building2_id=building2_id,
        reason=reason,
        excluded_by="admin"  # TODO: 実際のユーザー名を設定
    )
    db.add(exclusion)
    db.commit()
    
    # キャッシュをクリア（除外リストが変更されたため）
    # duplicates.pyのキャッシュをクリアする必要がある
    from .duplicates import clear_duplicate_buildings_cache
    clear_duplicate_buildings_cache()
    
    return {"success": True, "exclusion_id": exclusion.id}


@router.delete("/exclude-buildings/{exclusion_id}")
async def delete_building_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db)
):
    """建物除外を取り消す"""
    exclusion = db.query(BuildingMergeExclusion).filter(
        BuildingMergeExclusion.id == exclusion_id
    ).first()
    
    if not exclusion:
        raise HTTPException(status_code=404, detail="除外記録が見つかりません")
    
    db.delete(exclusion)
    db.commit()
    
    # キャッシュをクリア（除外リストが変更されたため）
    from .duplicates import clear_duplicate_buildings_cache
    clear_duplicate_buildings_cache()
    
    return {"success": True}


@router.get("/building-exclusions")
async def get_building_exclusions(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """建物除外リストを取得"""
    from ...utils.datetime_utils import to_jst_string
    
    exclusions = db.query(BuildingMergeExclusion).order_by(
        BuildingMergeExclusion.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for exclusion in exclusions:
        # 建物情報を取得
        building1 = db.query(Building).filter(
            Building.id == exclusion.building1_id
        ).first()
        building2 = db.query(Building).filter(
            Building.id == exclusion.building2_id
        ).first()
        
        # 物件数を取得
        count1 = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.building_id == exclusion.building1_id
        ).scalar() or 0
        count2 = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.building_id == exclusion.building2_id
        ).scalar() or 0
        
        result.append({
            "id": exclusion.id,
            "building1": {
                "id": exclusion.building1_id,
                "normalized_name": building1.normalized_name if building1 else "削除済み",
                "address": building1.address if building1 else "-",
                "property_count": count1
            },
            "building2": {
                "id": exclusion.building2_id,
                "normalized_name": building2.normalized_name if building2 else "削除済み",
                "address": building2.address if building2 else "-",
                "property_count": count2
            },
            "reason": exclusion.reason,
            "excluded_by": exclusion.excluded_by or "admin",
            "created_at": to_jst_string(exclusion.created_at) if exclusion.created_at else None
        })
    
    return {"exclusions": result, "total": len(result)}