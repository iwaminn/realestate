"""建物ごとにグループ化された物件のAPIエンドポイント"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, distinct, select
from urllib.parse import unquote

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, BuildingMergeHistory
from ..utils.building_filters import apply_building_name_filter

router = APIRouter(prefix="/api/v2", tags=["grouped-properties"])

@router.get("/properties-grouped-by-buildings", response_model=Dict[str, Any])
async def get_properties_grouped_by_buildings(
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    min_area: Optional[float] = Query(None),
    max_area: Optional[float] = Query(None),
    layouts: Optional[List[str]] = Query(None),
    building_name: Optional[str] = Query(None),
    max_building_age: Optional[int] = Query(None),
    wards: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db)
):
    """物件検索結果を建物ごとにグループ化して返す（最適化版）"""
    
    # 建物ごとの物件数と条件に合う物件の集計クエリ
    base_query = db.query(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors,
        Building.built_year,
        Building.built_month,
        Building.construction_type,
        func.count(distinct(MasterProperty.id)).label('property_count')
    ).join(MasterProperty)
    
    # フィルタ条件の適用
    if min_area:
        base_query = base_query.filter(MasterProperty.area >= min_area)
    if max_area:
        base_query = base_query.filter(MasterProperty.area <= max_area)
    if layouts:
        base_query = base_query.filter(MasterProperty.layout.in_(layouts))
    if building_name:
        # エイリアス（統合履歴）も含めて検索
        terms = building_name.split()
        for term in terms:
            # エイリアスマッチした建物IDを取得
            alias_building_ids = db.query(
                BuildingMergeHistory.primary_building_id
            ).filter(
                or_(
                    BuildingMergeHistory.merged_building_name.ilike(f"%{term}%"),
                    BuildingMergeHistory.canonical_merged_name.ilike(f"%{term}%")
                )
            ).distinct().subquery()
            
            # Building.normalized_name または エイリアスでマッチ
            base_query = base_query.filter(
                or_(
                    Building.normalized_name.ilike(f"%{term}%"),
                    Building.id.in_(alias_building_ids)
                )
            )
    if max_building_age:
        min_year = datetime.now().year - max_building_age
        base_query = base_query.filter(Building.built_year >= min_year)
    if wards:
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.ilike(f"%{ward}%"))
        base_query = base_query.filter(or_(*ward_conditions))
    
    # 価格フィルタを適用（存在する場合）
    if min_price or max_price:
        # 最新価格のサブクエリ
        price_subq = db.query(
            PropertyListing.master_property_id,
            func.max(PropertyListing.current_price).label('latest_price')
        ).filter(
            PropertyListing.is_active == True
        ).group_by(PropertyListing.master_property_id).subquery()
        
        base_query = base_query.outerjoin(
            price_subq, MasterProperty.id == price_subq.c.master_property_id
        )
        
        if min_price:
            base_query = base_query.filter(
                or_(
                    price_subq.c.latest_price >= min_price,
                    and_(price_subq.c.latest_price.is_(None), MasterProperty.final_price >= min_price)
                )
            )
        if max_price:
            base_query = base_query.filter(
                or_(
                    price_subq.c.latest_price <= max_price,
                    and_(price_subq.c.latest_price.is_(None), MasterProperty.final_price <= max_price)
                )
            )
    
    # アクティブフィルタ
    if not include_inactive:
        active_subq = db.query(PropertyListing.master_property_id).filter(
            PropertyListing.is_active == True
        ).subquery()
        base_query = base_query.filter(MasterProperty.id.in_(select(active_subq)))
    
    # グループ化して建物ごとの物件数を取得
    base_query = base_query.group_by(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors,
        Building.built_year,
        Building.built_month,
        Building.construction_type
    ).order_by(func.count(distinct(MasterProperty.id)).desc())
    
    # 全件数を取得
    total_query = base_query.subquery()
    total = db.query(func.count()).select_from(total_query).scalar()
    
    # ページネーション
    buildings = base_query.offset((page - 1) * per_page).limit(per_page).all()
    
    # 建物IDリストを取得
    building_ids = [b.id for b in buildings]
    
    if building_ids:
        # 各建物の物件を一括取得（最大6件ずつ）
        properties_query = db.query(
            MasterProperty.id,
            MasterProperty.building_id,
            MasterProperty.room_number,
            MasterProperty.floor_number,
            MasterProperty.area,
            MasterProperty.layout,
            MasterProperty.direction,
            MasterProperty.sold_at,
            MasterProperty.final_price,
            func.max(PropertyListing.current_price).label('current_price')
        ).outerjoin(
            PropertyListing,
            and_(
                PropertyListing.master_property_id == MasterProperty.id,
                PropertyListing.is_active == True
            )
        ).filter(
            MasterProperty.building_id.in_(building_ids)
        )
        
        # 同じフィルタ条件を適用
        if min_area:
            properties_query = properties_query.filter(MasterProperty.area >= min_area)
        if max_area:
            properties_query = properties_query.filter(MasterProperty.area <= max_area)
        if layouts:
            properties_query = properties_query.filter(MasterProperty.layout.in_(layouts))
        
        # 価格フィルタ
        if min_price or max_price:
            price_having = []
            if min_price:
                price_having.append(
                    or_(
                        func.max(PropertyListing.current_price) >= min_price,
                        and_(
                            func.max(PropertyListing.current_price).is_(None),
                            MasterProperty.final_price >= min_price
                        )
                    )
                )
            if max_price:
                price_having.append(
                    or_(
                        func.max(PropertyListing.current_price) <= max_price,
                        and_(
                            func.max(PropertyListing.current_price).is_(None),
                            MasterProperty.final_price <= max_price
                        )
                    )
                )
            if price_having:
                properties_query = properties_query.having(and_(*price_having))
        
        if not include_inactive:
            active_props = db.query(PropertyListing.master_property_id).filter(
                PropertyListing.is_active == True
            ).subquery()
            properties_query = properties_query.filter(MasterProperty.id.in_(select(active_props)))
        
        properties_query = properties_query.group_by(
            MasterProperty.id,
            MasterProperty.building_id,
            MasterProperty.room_number,
            MasterProperty.floor_number,
            MasterProperty.area,
            MasterProperty.layout,
            MasterProperty.direction,
            MasterProperty.sold_at,
            MasterProperty.final_price
        ).order_by(MasterProperty.floor_number.asc())
        
        all_properties = properties_query.all()
        
        # 建物ごとに物件をグループ化
        properties_by_building = {}
        for prop in all_properties:
            if prop.building_id not in properties_by_building:
                properties_by_building[prop.building_id] = []
            
            # 最大6件まで
            if len(properties_by_building[prop.building_id]) < 6:
                properties_by_building[prop.building_id].append({
                    "id": prop.id,
                    "room_number": prop.room_number,
                    "floor_number": prop.floor_number,
                    "area": prop.area,
                    "layout": prop.layout,
                    "direction": prop.direction,
                    "current_price": prop.current_price or prop.final_price,
                    "sold_at": prop.sold_at
                })
    else:
        properties_by_building = {}
    
    # 結果を構築
    result_buildings = []
    for building in buildings:
        result_buildings.append({
            "building": {
                "id": building.id,
                "normalized_name": building.normalized_name,
                "address": building.address,
                "total_floors": building.total_floors,
                "built_year": building.built_year,
                "built_month": building.built_month,
                "construction_type": building.construction_type,
                "building_age": datetime.now().year - building.built_year if building.built_year else None
            },
            "properties": properties_by_building.get(building.id, []),
            "total_properties": building.property_count
        })
    
    return {
        "buildings": result_buildings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
    }

@router.get("/buildings/by-name/{building_name}/properties", response_model=Dict[str, Any])
async def get_building_properties_by_name(
    building_name: str,
    include_inactive: bool = Query(False, description="販売終了物件も含む"),
    db: Session = Depends(get_db)
):
    """建物名で建物内の全物件を取得"""
    
    # URLデコード
    building_name = unquote(building_name)
    
    # 正規化された建物名で検索（完全一致優先）
    building = db.query(Building).filter(
        Building.normalized_name == building_name
    ).first()
    
    if not building:
        # 完全一致しない場合は部分一致で検索
        buildings = db.query(Building).filter(
            Building.normalized_name.like(f"%{building_name}%")
        ).all()
        
        if len(buildings) == 1:
            building = buildings[0]
        elif len(buildings) > 1:
            # 複数見つかった場合は最も基本的な名前のものを選択
            for b in buildings:
                if b.normalized_name == building_name or "EAST" not in b.normalized_name and "WEST" not in b.normalized_name and "棟" not in b.normalized_name:
                    building = b
                    break
            if not building:
                building = buildings[0]
    
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 価格の多数決を計算するサブクエリ
    from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery
    
    majority_price_query = create_majority_price_subquery(db, include_inactive)
    price_subquery = create_price_stats_subquery(db, majority_price_query, include_inactive)
    
    # 物件取得クエリ
    query = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.earliest_published_at
    ).filter(
        MasterProperty.building_id == building.id
    ).outerjoin(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    )
    
    # アクティブフィルタ
    if not include_inactive:
        query = query.filter(MasterProperty.sold_at.is_(None))
        query = query.filter(price_subquery.c.master_property_id.isnot(None))
    else:
        query = query.filter(
            or_(
                price_subquery.c.master_property_id.isnot(None),
                MasterProperty.sold_at.isnot(None)
            )
        )
    
    # 階数でソート
    query = query.order_by(
        price_subquery.c.earliest_published_at.desc().nullslast(),
        MasterProperty.floor_number.desc(),
        MasterProperty.room_number
    )
    
    results = query.all()
    
    # 結果を整形
    properties = []
    for mp, min_price, max_price, majority_price, listing_count, source_sites, earliest_published_at in results:
        properties.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "min_price": min_price if not mp.sold_at else mp.final_price,
            "max_price": max_price if not mp.sold_at else mp.final_price,
            "majority_price": majority_price if not mp.sold_at else mp.final_price,
            "listing_count": listing_count or 0,
            "source_sites": source_sites.split(',') if source_sites else [],
            "earliest_published_at": earliest_published_at.isoformat() if earliest_published_at else None,
            "sold_at": mp.sold_at.isoformat() if mp.sold_at else None,
            "last_sale_price": mp.final_price
        })
    
    return {
        "building": {
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "built_year": building.built_year,
            "built_month": building.built_month,
            "construction_type": building.construction_type,
            "station_info": building.station_info
        },
        "properties": properties,
        "total": len(properties)
    }