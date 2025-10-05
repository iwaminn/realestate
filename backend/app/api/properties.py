"""物件関連のAPIエンドポイント"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, distinct, String, select, case

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, ListingPriceHistory
from ..schemas.property import PropertyDetailSchema, MasterPropertySchema, ListingSchema, PriceHistorySchema
from ..schemas.building import BuildingSchema
from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery, apply_price_filter, get_sold_property_final_price
from ..utils.building_filters import apply_building_name_filter, apply_building_filters, apply_property_filters
from .price_analysis import create_unified_price_timeline, analyze_source_price_consistency

router = APIRouter(prefix="/api", tags=["properties"])

@router.get("/properties", response_model=Dict[str, Any])
async def get_properties(
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    min_area: Optional[float] = Query(None, description="最低面積（㎡）"),
    max_area: Optional[float] = Query(None, description="最高面積（㎡）"),
    layouts: Optional[List[str]] = Query(None, description="間取りリスト"),
    building_name: Optional[str] = Query(None, description="建物名"),
    max_building_age: Optional[int] = Query(None, description="築年数以内"),
    wards: Optional[List[str]] = Query(None, description="区名リスト（例: 港区、中央区）"),
    include_inactive: bool = Query(False, description="削除済み物件も含む"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    sort_by: str = Query("updated_at", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """物件一覧を取得（重複排除済み）"""
    
    # 掲載情報サブクエリを作成（listing_count等のみ）
    price_subquery = db.query(
        PropertyListing.master_property_id,
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites'),
        func.bool_or(PropertyListing.is_active).label('has_active_listing'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.max(PropertyListing.delisted_at).label('delisted_at'),
        func.max(PropertyListing.station_info).label('station_info'),
        func.min(func.coalesce(
            PropertyListing.first_published_at, 
            PropertyListing.published_at, 
            PropertyListing.first_seen_at
        )).label('earliest_published_at'),
        func.coalesce(
            func.max(PropertyListing.price_updated_at),
            func.min(PropertyListing.published_at)
        ).label('latest_price_update'),
        func.bool_or(
            db.query(func.count(distinct(PropertyListing.id)))
            .filter(PropertyListing.master_property_id == PropertyListing.master_property_id)
            .scalar_subquery() > 1
        ).label('has_price_change')
    )
    
    if not include_inactive:
        price_subquery = price_subquery.filter(PropertyListing.is_active == True)
    
    price_subquery = price_subquery.group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    # メインクエリ
    query = db.query(
        MasterProperty,
        Building,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.has_active_listing,
        price_subquery.c.last_confirmed_at,
        price_subquery.c.delisted_at,
        price_subquery.c.station_info,
        price_subquery.c.earliest_published_at,
        price_subquery.c.latest_price_update,
        price_subquery.c.has_price_change
    ).join(
        Building, MasterProperty.building_id == Building.id
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
    
    # 価格フィルタ（販売中物件はcurrent_price、販売終了物件はfinal_priceを使用）
    if min_price:
        query = query.filter(
            or_(
                and_(
                    MasterProperty.sold_at.is_(None),
                    MasterProperty.current_price >= min_price
                ),
                and_(
                    MasterProperty.sold_at.isnot(None),
                    MasterProperty.final_price >= min_price
                )
            )
        )
    if max_price:
        query = query.filter(
            or_(
                and_(
                    MasterProperty.sold_at.is_(None),
                    MasterProperty.current_price <= max_price
                ),
                and_(
                    MasterProperty.sold_at.isnot(None),
                    MasterProperty.final_price <= max_price
                )
            )
        )
    
    # 物件フィルタ
    query = apply_property_filters(query, min_area, max_area, layouts)
    
    # 建物名フィルタ（エイリアス対応）
    query = apply_building_name_filter(query, db, building_name)
    
    # 建物フィルタ
    query = apply_building_filters(query, wards, max_building_age)
    
    # 総件数を取得
    total_count = query.count()
    
    # ソート
    if sort_by == "price":
        order_column = func.coalesce(MasterProperty.current_price, MasterProperty.final_price)
    elif sort_by == "area":
        order_column = MasterProperty.area
    elif sort_by == "built_year":
        order_column = Building.built_year
    elif sort_by == "tsubo_price":
        # 坪単価を計算（価格 ÷ 面積 × 3.30578）
        # 面積が0の場合を除外するため、CASE文を使用
        order_column = case(
            (MasterProperty.area > 0, 
             func.coalesce(MasterProperty.current_price, MasterProperty.final_price) / (MasterProperty.area / 3.30578)),
            else_=None
        )
    else:
        order_column = price_subquery.c.latest_price_update
    
    if sort_order == "asc":
        query = query.order_by(order_column.asc().nullslast())
    else:
        query = query.order_by(order_column.desc().nullslast())
    
    # ページネーション
    offset = (page - 1) * per_page
    results = query.offset(offset).limit(per_page).all()
    
    # 結果を整形
    properties = []
    for mp, building, listing_count, source_sites, has_active, last_confirmed, delisted, station_info, earliest_published_at, latest_price_update, has_price_change in results:
        # 表示価格を決定
        if mp.sold_at:
            # 販売終了物件はfinal_priceを使用
            display_price = mp.final_price
        else:
            # 販売中物件はcurrent_priceを使用
            display_price = mp.current_price
        
        properties.append({
            "id": mp.id,
            "building": {
                "id": building.id,
                "normalized_name": building.normalized_name,
                "address": building.address,
                "total_floors": building.total_floors,
                "built_year": building.built_year,
                "built_month": building.built_month,
                "construction_type": building.construction_type
            },
            "display_building_name": mp.display_building_name,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "current_price": display_price,
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else [],
            "has_active_listing": has_active,
            "last_confirmed_at": str(last_confirmed) if last_confirmed else None,
            "delisted_at": str(delisted) if delisted else None,
            "station_info": mp.station_info if mp.station_info else station_info,
            "management_fee": mp.management_fee,
            "repair_fund": mp.repair_fund,
            "earliest_published_at": earliest_published_at,
            "latest_price_update": str(latest_price_update) if latest_price_update else None,
            "has_price_change": has_price_change if has_price_change is not None else False,
            "sold_at": mp.sold_at.isoformat() if mp.sold_at else None,
            "last_sale_price": mp.final_price if mp.sold_at else None
        })
    
    return {
        "properties": properties,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_count + per_page - 1) // per_page
    }

@router.get("/recent-updates-count", response_model=Dict[str, Any])
async def get_recent_updates_count(
    hours: int = Query(24, ge=1, le=168, description="過去N時間以内の更新"),
    db: Session = Depends(get_db)
):
    """
    直近N時間以内の価格改定物件と新着物件の件数のみを高速取得
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    # 対象期間の開始時刻
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # 価格変更があった物件の件数を取得（Full APIと同じロジック）
    from sqlalchemy import text
    
    price_changes_query = text("""
        WITH listing_prices_expanded AS (
            -- 各掲載の価格を日付ごとに展開（前回価格を引き継ぐ）
            SELECT DISTINCT
                pl.master_property_id,
                pl.id as listing_id,
                dates.price_date,
                COALESCE(
                    lph_today.price,
                    -- その日の記録がない場合は、直近の価格を使用
                    (SELECT price FROM listing_price_history lph_prev
                     WHERE lph_prev.property_listing_id = pl.id
                       AND DATE(lph_prev.recorded_at) < dates.price_date
                     ORDER BY lph_prev.recorded_at DESC
                     LIMIT 1),
                    pl.current_price  -- 履歴がない場合は現在価格を使用
                ) as price
            FROM property_listings pl
            CROSS JOIN (
                -- 対象期間内のすべての日付を生成
                SELECT DISTINCT DATE(lph.recorded_at) as price_date
                FROM listing_price_history lph
                WHERE lph.recorded_at >= :cutoff_time - INTERVAL '7 days'  -- 余裕を持って取得
            ) dates
            LEFT JOIN listing_price_history lph_today 
                ON lph_today.property_listing_id = pl.id 
                AND DATE(lph_today.recorded_at) = dates.price_date
            WHERE pl.master_property_id IN (
                -- 指定期間内に価格記録がある物件のみ対象
                SELECT DISTINCT pl2.master_property_id
                FROM property_listings pl2
                INNER JOIN listing_price_history lph2 ON lph2.property_listing_id = pl2.id
                WHERE lph2.recorded_at >= :cutoff_time
            )
            AND pl.is_active = true  -- アクティブな掲載のみ対象
        ),
        daily_majority_prices AS (
            -- 各物件の日付ごとの多数決価格を計算
            SELECT 
                master_property_id,
                price_date,
                price,
                COUNT(*) as vote_count
            FROM listing_prices_expanded
            WHERE price IS NOT NULL
            GROUP BY master_property_id, price_date, price
        ),
        daily_majority AS (
            -- 各物件・日付の多数決価格を決定
            SELECT DISTINCT ON (master_property_id, price_date)
                master_property_id,
                price_date,
                price as majority_price
            FROM daily_majority_prices
            ORDER BY master_property_id, price_date, vote_count DESC, price ASC
        ),
        price_changes AS (
            -- 多数決価格の変動を検出
            SELECT 
                dm1.master_property_id,
                dm1.price_date as change_date,
                dm1.majority_price as new_price,
                dm2.majority_price as old_price
            FROM daily_majority dm1
            LEFT JOIN LATERAL (
                SELECT majority_price
                FROM daily_majority dm2
                WHERE dm2.master_property_id = dm1.master_property_id
                  AND dm2.price_date < dm1.price_date
                ORDER BY dm2.price_date DESC
                LIMIT 1
            ) dm2 ON true
            WHERE dm2.majority_price IS NOT NULL
              AND dm1.majority_price != dm2.majority_price
              AND dm1.price_date >= DATE(:cutoff_time)  -- 変更日が指定期間内
        )
        SELECT COUNT(DISTINCT master_property_id) FROM price_changes
    """)
    
    price_changes_count = db.execute(price_changes_query, {"cutoff_time": cutoff_time}).scalar() or 0
    
    # 新着物件の件数を取得
    new_listings_count = db.query(func.count(MasterProperty.id))\
        .filter(
            MasterProperty.created_at >= cutoff_time,
            MasterProperty.sold_at.is_(None)
        ).scalar() or 0
    
    return {
        "total_price_changes": price_changes_count,
        "total_new_listings": new_listings_count,
        "hours": hours,
        "updated_at": datetime.now().isoformat()
    }

@router.get("/properties/{property_id}", response_model=PropertyDetailSchema)
async def get_property_details(
    property_id: int,
    db: Session = Depends(get_db)
):
    """物件の詳細情報を取得（全掲載情報を含む）"""
    
    # マスター物件を取得
    master_property = db.query(MasterProperty).options(
        joinedload(MasterProperty.building),
        joinedload(MasterProperty.listings)
    ).filter(MasterProperty.id == property_id).first()
    
    if not master_property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # 全掲載情報を取得（非アクティブも含む）
    all_listings = master_property.listings
    
    # アクティブな掲載のみフィルタ
    active_listings = [l for l in all_listings if l.is_active]
    
    # 各サイトの情報を集計（多数決用）
    from ..utils.majority_vote_updater import MajorityVoteUpdater
    updater = MajorityVoteUpdater(db)
    
    # 販売終了物件の場合は非アクティブも含める
    include_inactive = master_property.sold_at is not None
    info = updater.collect_property_info_from_listings(master_property, include_inactive)
    
    # 価格の多数決を計算（アクティブな掲載のみ）
    price_votes = {}
    for listing in active_listings:
        if listing.current_price:
            price = listing.current_price
            if price not in price_votes:
                price_votes[price] = 0
            price_votes[price] += 1
    
    majority_price = None
    if price_votes:
        sorted_prices = sorted(price_votes.items(), key=lambda x: (-x[1], x[0]))
        majority_price = sorted_prices[0][0]
    
    # 販売終了物件の場合はfinal_priceを使用
    if master_property.sold_at and master_property.final_price:
        majority_price = master_property.final_price
    
    # ソースサイトのリスト（アクティブな掲載のみ）
    source_sites = list(set(l.source_site for l in active_listings))
    
    # 交通情報を多数決で決定（マスター物件に保存されていない場合のみ）
    station_info = master_property.station_info
    if not station_info and info['station_infos']:
        station_info = updater.get_majority_value(info['station_infos'])
    
    # 統合価格履歴を作成（物件単位）
    all_price_records = []
    
    # 各掲載の情報を収集
    listing_info = {}
    for listing in all_listings:
        listing_info[listing.id] = {
            'source_site': listing.source_site,
            'is_active': listing.is_active,
            'current_price': listing.current_price,
            'start_date': listing.first_seen_at or listing.created_at
        }
        
        histories = db.query(ListingPriceHistory).filter(
            ListingPriceHistory.property_listing_id == listing.id
        ).all()
        
        # 価格履歴を追加
        for history in histories:
            all_price_records.append({
                'recorded_at': history.recorded_at,
                'price': history.price,
                'source_site': listing.source_site,
                'listing_id': listing.id,
                'is_active': listing.is_active,
                'current_price': listing.current_price,
                'listing_start_date': listing.first_seen_at or listing.created_at
            })
    
    # 時系列でソート
    all_price_records.sort(key=lambda x: x['recorded_at'])
    
    # 同一時点で異なるソースの価格差を検出
    price_discrepancies = []
    grouped_by_date = {}
    for record in all_price_records:
        date_key = record['recorded_at'].date()
        if date_key not in grouped_by_date:
            grouped_by_date[date_key] = []
        grouped_by_date[date_key].append(record)
    
    for date_key, records in grouped_by_date.items():
        unique_prices = {}
        for record in records:
            if record['is_active']:  # アクティブな掲載のみ
                price = record['price']
                source = record['source_site']
                if price not in unique_prices:
                    unique_prices[price] = []
                unique_prices[price].append(source)
        
        if len(unique_prices) > 1:
            price_discrepancies.append({
                'date': str(date_key),
                'prices': {str(price): sources for price, sources in unique_prices.items()}
            })
    
    # 最も古い情報提供日を取得
    # first_published_at（初回掲載日）を優先、なければpublished_atを使用
    earliest_published_at = None
    for listing in all_listings:
        # first_published_atがある場合はそれを使用
        if listing.first_published_at:
            if not earliest_published_at or listing.first_published_at < earliest_published_at:
                earliest_published_at = listing.first_published_at
        # first_published_atがない場合はpublished_atを使用
        elif listing.published_at:
            if not earliest_published_at or listing.published_at < earliest_published_at:
                earliest_published_at = listing.published_at
    
    # レスポンスを構築
    master_property_data = {
        "id": master_property.id,
        "building": BuildingSchema.from_orm(master_property.building),
        "display_building_name": master_property.display_building_name,  # 表示用建物名を追加
        "room_number": master_property.room_number,
        "floor_number": master_property.floor_number,
        "area": master_property.area,
        "balcony_area": master_property.balcony_area,
        "layout": master_property.layout,
        "direction": master_property.direction,
        "current_price": majority_price,  # 多数決価格
        "listing_count": len(active_listings),
        "source_sites": source_sites,
        "station_info": station_info,
        "management_fee": master_property.management_fee,
        "repair_fund": master_property.repair_fund,
        "earliest_published_at": earliest_published_at,
        "sold_at": master_property.sold_at,
        "final_price": master_property.final_price,
        "has_active_listing": len(active_listings) > 0
    }
    
    # 価格分析を実行
    price_timeline = create_unified_price_timeline(all_price_records)
    price_consistency = analyze_source_price_consistency(all_price_records)
    
    # 各掲載の価格履歴を取得（フロントエンド互換性のため）
    price_histories_by_listing = {}
    for listing in active_listings:
        histories = db.query(ListingPriceHistory).filter(
            ListingPriceHistory.property_listing_id == listing.id
        ).order_by(
            ListingPriceHistory.recorded_at.desc()
        ).all()
        
        price_histories_by_listing[listing.id] = [
            PriceHistorySchema.from_orm(h) for h in histories
        ]
    
    return PropertyDetailSchema(
        master_property=master_property_data,
        listings=[ListingSchema.from_orm(l) for l in active_listings],
        price_histories_by_listing=price_histories_by_listing,
        price_timeline=price_timeline,
        price_consistency=price_consistency,
        unified_price_history=all_price_records,
        price_discrepancies=price_discrepancies
    )