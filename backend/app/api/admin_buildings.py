"""
管理者用建物管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, Integer
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, BuildingExternalId
from ..auth import verify_admin_credentials

router = APIRouter(tags=["admin-buildings"])


@router.get("/buildings")
async def get_buildings(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    name: Optional[str] = None,
    address: Optional[str] = None,
    min_built_year: Optional[int] = None,
    max_built_year: Optional[int] = None,
    min_total_floors: Optional[int] = None,
    max_total_floors: Optional[int] = None,
    has_active_listings: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物一覧を取得（管理者用）"""
    query = db.query(Building)
    
    # フィルタリング
    if name:
        query = query.filter(Building.normalized_name.ilike(f"%{name}%"))
    
    if address:
        query = query.filter(Building.address.ilike(f"%{address}%"))
    
    if min_built_year is not None:
        query = query.filter(Building.built_year >= min_built_year)
    
    if max_built_year is not None:
        query = query.filter(Building.built_year <= max_built_year)
    
    if min_total_floors is not None:
        query = query.filter(Building.total_floors >= min_total_floors)
    
    if max_total_floors is not None:
        query = query.filter(Building.total_floors <= max_total_floors)
    
    # 掲載状態でフィルタ
    if has_active_listings is not None:
        active_building_subquery = db.query(MasterProperty.building_id).join(
            PropertyListing
        ).filter(
            PropertyListing.is_active == True
        ).distinct().subquery()
        
        if has_active_listings:
            query = query.filter(Building.id.in_(active_building_subquery))
        else:
            query = query.filter(~Building.id.in_(active_building_subquery))
    
    # 総件数を取得
    total = query.count()
    
    # ページネーション
    buildings = query.offset(offset).limit(limit).all()
    
    # 各建物の統計情報を取得
    building_ids = [b.id for b in buildings]
    
    # 物件数と掲載情報の集計
    stats = db.query(
        MasterProperty.building_id,
        func.count(func.distinct(MasterProperty.id)).label('property_count'),
        func.count(func.distinct(PropertyListing.id)).filter(PropertyListing.is_active == True).label('active_listing_count'),
        func.min(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('min_price'),
        func.max(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('max_price')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id, isouter=True
    ).filter(
        MasterProperty.building_id.in_(building_ids)
    ).group_by(MasterProperty.building_id).all()
    
    stats_dict = {
        stat.building_id: {
            'property_count': stat.property_count or 0,
            'active_listing_count': stat.active_listing_count or 0,
            'min_price': stat.min_price,
            'max_price': stat.max_price
        }
        for stat in stats
    }
    
    # レスポンスの構築
    items = []
    for building in buildings:
        building_stats = stats_dict.get(building.id, {
            'property_count': 0,
            'active_listing_count': 0,
            'min_price': None,
            'max_price': None
        })
        
        items.append({
            'id': building.id,
            'normalized_name': building.normalized_name,
            'address': building.address,
            'total_floors': building.total_floors,
            'built_year': building.built_year,
            'created_at': building.created_at.isoformat() if building.created_at else None,
            'updated_at': building.updated_at.isoformat() if building.updated_at else None,
            **building_stats
        })
    
    return {
        'items': items,
        'total': total,
        'offset': offset,
        'limit': limit
    }


@router.get("/buildings/search")
async def search_buildings_for_merge(
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    credentials: Any = Depends(verify_admin_credentials)
):
    """建物検索（統合用）"""
    from ..utils.search_normalizer import create_search_patterns, normalize_search_text
    from ..models import BuildingMergeHistory
    
    # 検索文字列を正規化してAND検索用に分割
    normalized_search = normalize_search_text(query)
    search_terms = normalized_search.split()
    
    # まず統合履歴（エイリアス）から検索
    alias_matches = db.query(
        BuildingMergeHistory.primary_building_id,
        BuildingMergeHistory.merged_building_name.label('alias_name')
    ).filter(
        or_(
            BuildingMergeHistory.merged_building_name.ilike(f"%{query}%"),
            BuildingMergeHistory.canonical_merged_name.ilike(f"%{normalized_search}%")
        )
    ).distinct().all()
    
    # エイリアスにマッチした建物IDのリスト
    alias_building_ids = [match.primary_building_id for match in alias_matches]
    
    # クエリ構築
    name_query = db.query(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors,
        func.count(MasterProperty.id).label('property_count')
    ).outerjoin(
        MasterProperty, Building.id == MasterProperty.building_id
    )
    
    # 複数の検索語がある場合はAND検索
    if len(search_terms) > 1:
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                term_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
            if term_conditions:
                # 各検索語について、いずれかのパターンにマッチ
                and_conditions.append(or_(*term_conditions))
        
        if and_conditions:
            # 全ての検索語を含む（AND条件）、またはエイリアスにマッチした建物
            if alias_building_ids:
                name_query = name_query.filter(
                    or_(
                        and_(*and_conditions),
                        Building.id.in_(alias_building_ids)
                    )
                )
            else:
                name_query = name_query.filter(and_(*and_conditions))
    else:
        # 単一の検索語の場合
        search_patterns = create_search_patterns(query)
        search_conditions = []
        for pattern in search_patterns:
            search_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
        
        # エイリアスマッチも含める
        if alias_building_ids:
            search_conditions.append(Building.id.in_(alias_building_ids))
        
        if search_conditions:
            name_query = name_query.filter(or_(*search_conditions))
    
    # グループ化と並び替え
    buildings = name_query.group_by(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors
    ).order_by(
        func.count(MasterProperty.id).desc()
    ).limit(limit).all()
    
    # 各建物のエイリアス情報を取得
    building_ids_for_alias = [b.id for b in buildings]
    aliases_dict = {}
    if building_ids_for_alias:
        aliases = db.query(
            BuildingMergeHistory.primary_building_id,
            func.string_agg(
                BuildingMergeHistory.merged_building_name, 
                ', '
            ).label('aliases')
        ).filter(
            BuildingMergeHistory.primary_building_id.in_(building_ids_for_alias)
        ).group_by(
            BuildingMergeHistory.primary_building_id
        ).all()
        
        aliases_dict = {alias.primary_building_id: alias.aliases for alias in aliases}
    
    result = []
    for building in buildings:
        building_data = {
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "property_count": building.property_count
        }
        
        # エイリアス情報があれば追加
        if building.id in aliases_dict:
            building_data["aliases"] = aliases_dict[building.id]
        
        # エイリアス検索でマッチした場合、どのエイリアスでマッチしたか表示
        for match in alias_matches:
            if match.primary_building_id == building.id:
                building_data["matched_alias"] = match.alias_name
                break
        
        result.append(building_data)
    
    return {
        "buildings": result,
        "total": len(result)
    }


@router.get("/buildings/{building_id}")
async def get_building_detail(
    building_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物詳細を取得（管理者用）"""
    building = db.query(Building).filter(Building.id == building_id).first()
    
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 物件一覧を取得
    properties = db.query(
        MasterProperty.id,
        MasterProperty.room_number,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction,
        func.count(PropertyListing.id).filter(PropertyListing.is_active == True).label('active_listing_count'),
        func.min(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('min_price'),
        func.max(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('max_price')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id, isouter=True
    ).filter(
        MasterProperty.building_id == building_id
    ).group_by(
        MasterProperty.id,
        MasterProperty.room_number,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction
    ).order_by(
        MasterProperty.floor_number.nullslast(),
        MasterProperty.room_number.nullslast()
    ).all()
    
    # 外部建物IDを取得
    external_ids = db.query(BuildingExternalId).filter(
        BuildingExternalId.building_id == building_id
    ).all()
    
    # 統計情報を計算
    property_count = len(properties)
    active_listing_count = sum(1 for p in properties if p.active_listing_count > 0)
    all_prices = [p.min_price for p in properties if p.min_price] + [p.max_price for p in properties if p.max_price]
    min_price = min(all_prices) if all_prices else None
    max_price = max(all_prices) if all_prices else None
    
    return {
        'id': building.id,
        'normalized_name': building.normalized_name,
        'address': building.address,
        'total_floors': building.total_floors,
        'built_year': building.built_year,
        'created_at': building.created_at.isoformat() if building.created_at else None,
        'updated_at': building.updated_at.isoformat() if building.updated_at else None,
        'property_count': property_count,
        'active_listing_count': active_listing_count,
        'min_price': min_price,
        'max_price': max_price,
        'external_ids': [
            {
                'source_site': ext_id.source_site,
                'external_id': ext_id.external_id,
                'created_at': ext_id.created_at.isoformat() if ext_id.created_at else None
            }
            for ext_id in external_ids
        ],
        'properties': [
            {
                'id': p.id,
                'room_number': p.room_number,
                'floor_number': p.floor_number,
                'area': p.area,
                'layout': p.layout,
                'direction': p.direction,
                'active_listing_count': p.active_listing_count or 0,
                'min_price': p.min_price,
                'max_price': p.max_price
            }
            for p in properties
        ]
    }


@router.patch("/buildings/{building_id}")
async def update_building(
    building_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物情報を更新（管理者用）"""
    building = db.query(Building).filter(Building.id == building_id).first()
    
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 更新可能なフィールドのみ更新
    updatable_fields = [
        'normalized_name', 'address', 
        'total_floors', 'built_year'
    ]
    
    for field in updatable_fields:
        if field in data:
            setattr(building, field, data[field])
    
    building.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(building)
        return {"message": "建物情報を更新しました", "building_id": building.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新に失敗しました: {str(e)}")

