"""建物ごとにグループ化された物件のAPIエンドポイント"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, distinct, select, String, case
from urllib.parse import unquote
import re

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, PropertyPriceChange
from ..utils.building_filters import apply_building_name_filter

router = APIRouter(prefix="/api", tags=["grouped-properties"])

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
    sort_by: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """物件検索結果を建物ごとにグループ化して返す（最適化版）"""

    # 各物件のhas_active_listingを計算するサブクエリ
    active_listing_subq = db.query(
        PropertyListing.master_property_id,
        func.bool_or(PropertyListing.is_active).label('has_active_listing')
    ).group_by(PropertyListing.master_property_id).subquery()

    # 建物ごとの物件数と条件に合う物件の集計クエリ
    # 平均坪単価の計算用サブクエリ（㎡を坪に変換: 面積 / 3.30578）
    tsubo_subq = db.query(
        MasterProperty.building_id,
        func.avg(
            func.coalesce(MasterProperty.current_price, MasterProperty.final_price) / (MasterProperty.area / 3.30578)
        ).label('avg_tsubo_price')
    ).filter(
        MasterProperty.area > 0
    ).group_by(MasterProperty.building_id).subquery()
    
    base_query = db.query(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors,
        Building.built_year,
        Building.built_month,
        Building.construction_type,
        Building.total_units,
        func.count(distinct(MasterProperty.id)).label('property_count'),
        tsubo_subq.c.avg_tsubo_price
    ).join(MasterProperty).outerjoin(
        tsubo_subq, Building.id == tsubo_subq.c.building_id
    )
    
    # フィルタ条件の適用
    if min_area:
        base_query = base_query.filter(MasterProperty.area >= min_area)
    if max_area:
        base_query = base_query.filter(MasterProperty.area <= max_area)
    if layouts:
        base_query = base_query.filter(MasterProperty.layout.in_(layouts))
    # 建物名フィルタを適用（物件一覧と同じロジック）
    base_query = apply_building_name_filter(base_query, db, building_name, Building)
    if max_building_age:
        min_year = datetime.now().year - max_building_age
        base_query = base_query.filter(Building.built_year >= min_year)
    if wards:
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.ilike(f"%{ward}%"))
        base_query = base_query.filter(or_(*ward_conditions))
    
    # 価格フィルタを適用（has_active_listingベース）
    # サブクエリをjoinして使用
    base_query = base_query.outerjoin(
        active_listing_subq,
        MasterProperty.id == active_listing_subq.c.master_property_id
    )
    
    if min_price:
        base_query = base_query.filter(
            or_(
                and_(active_listing_subq.c.has_active_listing == True, MasterProperty.current_price >= min_price),
                and_(active_listing_subq.c.has_active_listing == False, MasterProperty.final_price >= min_price)
            )
        )
    if max_price:
        base_query = base_query.filter(
            or_(
                and_(active_listing_subq.c.has_active_listing == True, MasterProperty.current_price <= max_price),
                and_(active_listing_subq.c.has_active_listing == False, MasterProperty.final_price <= max_price)
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
        Building.construction_type,
        Building.total_units,
        tsubo_subq.c.avg_tsubo_price
    )
    
    # 並び替えの適用（第2キーとして建物IDを追加して順序を安定させる）
    if sort_by == 'building_age_asc':
        # 築年数が新しい順（築年が大きい順）
        base_query = base_query.order_by(
            Building.built_year.desc().nullslast(),
            Building.id  # 同じ築年の場合は建物IDで順序を固定
        )
    elif sort_by == 'building_age_desc':
        # 築年数が古い順（築年が小さい順）
        base_query = base_query.order_by(
            Building.built_year.asc().nullsfirst(),
            Building.id
        )
    elif sort_by == 'total_units_asc':
        # 総戸数が少ない順
        base_query = base_query.order_by(
            Building.total_units.asc().nullsfirst(),
            Building.id
        )
    elif sort_by == 'total_units_desc':
        # 総戸数が多い順
        base_query = base_query.order_by(
            Building.total_units.desc().nullslast(),
            Building.id
        )
    elif sort_by == 'property_count_asc':
        # 販売戸数が少ない順
        base_query = base_query.order_by(
            func.count(distinct(MasterProperty.id)).asc(),
            Building.id
        )
    elif sort_by == 'property_count_desc':
        # 販売戸数が多い順
        base_query = base_query.order_by(
            func.count(distinct(MasterProperty.id)).desc(),
            Building.id
        )
    elif sort_by == 'avg_tsubo_price_asc':
        # 平均坪単価が安い順
        base_query = base_query.order_by(
            tsubo_subq.c.avg_tsubo_price.asc().nullsfirst(),
            Building.id
        )
    elif sort_by == 'avg_tsubo_price_desc':
        # 平均坪単価が高い順
        base_query = base_query.order_by(
            tsubo_subq.c.avg_tsubo_price.desc().nullslast(),
            Building.id
        )
    else:
        # デフォルト：販売戸数が多い順
        base_query = base_query.order_by(
            func.count(distinct(MasterProperty.id)).desc(),
            Building.id
        )
    
    # 全件数を取得
    total_query = base_query.subquery()
    total = db.query(func.count()).select_from(total_query).scalar()
    
    # ページネーション
    buildings = base_query.offset((page - 1) * per_page).limit(per_page).all()
    
    # 建物IDリストを取得
    building_ids = [b.id for b in buildings]
    
    if building_ids:
        # 売出確認日を取得するサブクエリ
        earliest_published_subq = db.query(
            PropertyListing.master_property_id,
            func.min(func.coalesce(
                PropertyListing.first_published_at,
                PropertyListing.published_at,
                PropertyListing.first_seen_at
            )).label('earliest_published_at')
        ).group_by(PropertyListing.master_property_id).subquery()
        
        # 各建物の物件を一括取得（最大3件ずつ）
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
            func.max(PropertyListing.current_price).label('current_price'),
            active_listing_subq.c.has_active_listing,
            earliest_published_subq.c.earliest_published_at
        ).outerjoin(
            PropertyListing,
            and_(
                PropertyListing.master_property_id == MasterProperty.id,
                PropertyListing.is_active == True
            )
        ).outerjoin(
            active_listing_subq,
            MasterProperty.id == active_listing_subq.c.master_property_id
        ).outerjoin(
            earliest_published_subq,
            MasterProperty.id == earliest_published_subq.c.master_property_id
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
            MasterProperty.final_price,
            active_listing_subq.c.has_active_listing,
            earliest_published_subq.c.earliest_published_at
        ).order_by(
            # 売出確認日の降順（新しいものが先）
            earliest_published_subq.c.earliest_published_at.desc().nullslast()
        )
        
        all_properties = properties_query.all()
        
        # 建物ごとに物件をグループ化
        properties_by_building = {}
        for prop in all_properties:
            if prop.building_id not in properties_by_building:
                properties_by_building[prop.building_id] = []
            
            # 最大3件まで
            if len(properties_by_building[prop.building_id]) < 3:
                properties_by_building[prop.building_id].append({
                    "id": prop.id,
                    "room_number": prop.room_number,
                    "floor_number": prop.floor_number,
                    "area": prop.area,
                    "layout": prop.layout,
                    "direction": prop.direction,
                    "current_price": prop.current_price or prop.final_price,
                    "sold_at": prop.sold_at,
                    "has_active_listing": prop.has_active_listing if prop.has_active_listing is not None else False
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
                "building_age": datetime.now().year - building.built_year if building.built_year else None,
                "total_units": building.total_units,
                "avg_tsubo_price": float(building.avg_tsubo_price) if building.avg_tsubo_price else None
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
    
    # 掲載統計サブクエリを作成（アクティブな掲載のみ）
    active_price_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites')
    ).filter(PropertyListing.is_active == True).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    # 全掲載から売出確認日を取得（アクティブ・非アクティブ含む）
    all_listing_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(func.coalesce(
            PropertyListing.first_published_at,
            PropertyListing.published_at,
            PropertyListing.first_seen_at
        )).label('earliest_published_at'),
        func.max(PropertyListing.price_updated_at).label('latest_price_update')
    ).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    # 物件取得クエリ
    query = db.query(
        MasterProperty,
        active_price_subquery.c.min_price,
        active_price_subquery.c.max_price,
        active_price_subquery.c.listing_count,
        active_price_subquery.c.source_sites,
        all_listing_subquery.c.earliest_published_at,
        all_listing_subquery.c.latest_price_update
    ).filter(
        MasterProperty.building_id == building.id
    ).outerjoin(
        active_price_subquery, MasterProperty.id == active_price_subquery.c.master_property_id
    ).outerjoin(
        all_listing_subquery, MasterProperty.id == all_listing_subquery.c.master_property_id
    )
    
    # アクティブフィルタ（has_active_listingベース）
    if not include_inactive:
        # 販売中物件のみ（アクティブな掲載がある物件）
        query = query.filter(active_price_subquery.c.master_property_id.isnot(None))
    else:
        # すべての物件（アクティブまたは販売終了）
        query = query.filter(
            or_(
                active_price_subquery.c.master_property_id.isnot(None),
                all_listing_subquery.c.master_property_id.isnot(None)
            )
        )
    
    # 階数でソート
    query = query.order_by(
        all_listing_subquery.c.earliest_published_at.desc().nullslast(),
        MasterProperty.floor_number.desc(),
        MasterProperty.room_number
    )
    
    results = query.all()
    
    # 結果を整形
    properties = []
    for mp, min_price, max_price, listing_count, source_sites, earliest_published_at, latest_price_update in results:
        # 価格を決定
        if mp.sold_at:
            display_price = mp.final_price
        else:
            display_price = mp.current_price
        
        # 価格改定情報を取得（PropertyPriceChangeテーブルから）
        price_change_info = None
        latest_price_change = db.query(PropertyPriceChange).filter(
            PropertyPriceChange.master_property_id == mp.id
        ).order_by(PropertyPriceChange.change_date.desc()).first()
        
        if latest_price_change:
            price_change_info = {
                "date": latest_price_change.change_date.isoformat(),
                "previous_price": latest_price_change.old_price,
                "current_price": latest_price_change.new_price,
                "change_amount": latest_price_change.price_diff,
                "change_rate": round(latest_price_change.price_diff_rate, 2) if latest_price_change.price_diff_rate else 0
            }
        
        # has_active_listingを判定
        has_active_listing = listing_count is not None and listing_count > 0

        properties.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "min_price": min_price if not mp.sold_at else display_price,
            "max_price": max_price if not mp.sold_at else display_price,
            "majority_price": display_price,
            "listing_count": listing_count or 0,
            "source_sites": source_sites.split(',') if source_sites else [],
            "earliest_published_at": earliest_published_at.isoformat() if earliest_published_at else None,
            "sold_at": mp.sold_at.isoformat() if mp.sold_at else None,
            "last_sale_price": mp.final_price,
            "price_change_info": price_change_info,
            "latest_price_update": latest_price_update.isoformat() if latest_price_update else None,
            "has_active_listing": has_active_listing
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