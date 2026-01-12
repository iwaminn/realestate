"""物件関連のAPIエンドポイント"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, distinct, String, select, case

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, ListingPriceHistory, PropertyPriceChange
from ..schemas.property import PropertyDetailSchema, MasterPropertySchema, ListingSchema, PriceHistorySchema
from ..schemas.building import BuildingSchema
from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery, apply_price_filter, get_sold_property_final_price
from ..utils.building_filters import apply_building_name_filter, apply_building_filters, apply_property_filters, apply_land_rights_filter
from .price_analysis import create_unified_price_timeline, analyze_source_price_consistency

router = APIRouter(prefix="/api", tags=["properties"])

@router.get("/properties", response_model=Dict[str, Any])
async def get_properties(
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    min_area: Optional[float] = Query(None),
    max_area: Optional[float] = Query(None),
    layouts: Optional[List[str]] = Query(None),
    building_name: Optional[str] = Query(None),
    max_building_age: Optional[int] = Query(None),
    wards: Optional[List[str]] = Query(None),
    land_rights_types: Optional[List[str]] = Query(None, description="権利形態（ownership, old_leasehold, fixed_term_leasehold, regular_leasehold）"),
    include_inactive: bool = Query(False, description="販売終了物件を含む"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    sort_by: str = Query("updated_at", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """物件一覧を取得（重複排除済み）"""
    
    # 掲載情報サブクエリを作成
    # listing_countは常にアクティブな掲載のみカウント
    # latest_price_updateとhas_price_changeは常に全掲載を対象

    # 物件レベルの価格改定情報を property_price_changes テーブルから取得
    # 多数決価格が変更された場合のみ記録されている
    # 同じ日に複数の変更がある場合は、最新のcreated_atを取得
    price_change_subquery = db.query(
        PropertyPriceChange.master_property_id,
        func.max(PropertyPriceChange.change_date).label('latest_price_change_date'),
        func.max(PropertyPriceChange.created_at).label('latest_price_change_time'),
        func.bool_or(True).label('has_price_change')
    ).group_by(PropertyPriceChange.master_property_id).subquery()
    
    # 売出し確認日を全掲載から計算するサブクエリ
    published_date_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(func.coalesce(
            PropertyListing.first_published_at,
            PropertyListing.published_at,
            PropertyListing.first_seen_at
        )).label('earliest_published_at')
    ).group_by(PropertyListing.master_property_id).subquery()

    price_subquery = db.query(
        PropertyListing.master_property_id,
        func.count(distinct(case((PropertyListing.is_active == True, PropertyListing.id)))).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites'),
        func.bool_or(PropertyListing.is_active).label('has_active_listing'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.max(PropertyListing.delisted_at).label('delisted_at'),
        func.max(PropertyListing.listing_station_info).label('station_info')
    )

    if not include_inactive:
        price_subquery = price_subquery.filter(PropertyListing.is_active == True)

    price_subquery = price_subquery.group_by(
        PropertyListing.master_property_id
    ).subquery()

    # price_change_subquery と published_date_subquery を結合
    combined_subquery = db.query(
        price_subquery.c.master_property_id,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.has_active_listing,
        price_subquery.c.last_confirmed_at,
        price_subquery.c.delisted_at,
        price_subquery.c.station_info,
        published_date_subquery.c.earliest_published_at,
        price_change_subquery.c.latest_price_change_date.label('latest_price_update'),
        price_change_subquery.c.latest_price_change_time.label('latest_price_update_time'),
        func.coalesce(price_change_subquery.c.has_price_change, False).label('has_price_change')
    ).outerjoin(
        published_date_subquery,
        price_subquery.c.master_property_id == published_date_subquery.c.master_property_id
    ).outerjoin(
        price_change_subquery,
        price_subquery.c.master_property_id == price_change_subquery.c.master_property_id
    ).subquery()
    
    # メインクエリ
    query = db.query(
        MasterProperty,
        Building,
        combined_subquery.c.listing_count,
        combined_subquery.c.source_sites,
        combined_subquery.c.has_active_listing,
        combined_subquery.c.last_confirmed_at,
        combined_subquery.c.delisted_at,
        combined_subquery.c.station_info,
        combined_subquery.c.earliest_published_at,
        combined_subquery.c.latest_price_update,
        combined_subquery.c.latest_price_update_time,
        combined_subquery.c.has_price_change
    ).join(
        Building, MasterProperty.building_id == Building.id
    ).outerjoin(
        combined_subquery, MasterProperty.id == combined_subquery.c.master_property_id
    )
    
    # アクティブフィルタ（has_active_listingベースに変更）
    if not include_inactive:
        # アクティブな掲載がある物件のみ表示（sold_atは無視）
        query = query.filter(combined_subquery.c.has_active_listing == True)
        query = query.filter(combined_subquery.c.master_property_id.isnot(None))
    else:
        query = query.filter(
            or_(
                combined_subquery.c.master_property_id.isnot(None),
                MasterProperty.sold_at.isnot(None)
            )
        )

    # 価格フィルタ（has_active_listingベースに変更）
    if min_price:
        query = query.filter(
            or_(
                and_(
                    combined_subquery.c.has_active_listing == True,
                    MasterProperty.current_price >= min_price
                ),
                and_(
                    combined_subquery.c.has_active_listing == False,
                    MasterProperty.final_price >= min_price
                )
            )
        )
    if max_price:
        query = query.filter(
            or_(
                and_(
                    combined_subquery.c.has_active_listing == True,
                    MasterProperty.current_price <= max_price
                ),
                and_(
                    combined_subquery.c.has_active_listing == False,
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

    # 権利形態フィルタ
    query = apply_land_rights_filter(query, land_rights_types)

    # 総件数を取得
    total = query.count()

    # 販売終了物件数を正確にカウント
    sold_count = 0
    if include_inactive:
        # 販売中のみの件数を取得
        active_only_query = query.filter(
            combined_subquery.c.has_active_listing == True
        )
        active_count = active_only_query.count()
        # 販売終了 = 全体 - 販売中
        sold_count = total - active_count
    
    # ソート
    if sort_by == "price":
        query = query.order_by(
            MasterProperty.current_price.desc() if sort_order == "desc" 
            else MasterProperty.current_price.asc()
        )
    elif sort_by == "area":
        query = query.order_by(
            MasterProperty.area.desc() if sort_order == "desc" 
            else MasterProperty.area.asc()
        )
    elif sort_by == "building_age":
        query = query.order_by(
            Building.built_year.asc() if sort_order == "desc" 
            else Building.built_year.desc()
        )
    elif sort_by == "earliest_published_at":
        query = query.order_by(
            combined_subquery.c.earliest_published_at.desc() if sort_order == "desc"
            else combined_subquery.c.earliest_published_at.asc()
        )
    elif sort_by == "tsubo_price":
        # 坪単価で並び替え（価格 / (面積 / 3.30578)）
        # 面積が0の物件は最後に表示
        tsubo_price_expr = case(
            (MasterProperty.area > 0, 
             func.coalesce(MasterProperty.current_price, MasterProperty.final_price) / (MasterProperty.area / 3.30578)),
            else_=None
        )
        if sort_order == "desc":
            query = query.order_by(tsubo_price_expr.desc().nullslast())
        else:
            query = query.order_by(tsubo_price_expr.asc().nullsfirst())
    else:  # デフォルト: updated_at (価格改定日または売出確認日)
        # 価格改定日が存在する場合はそれを優先、なければ売出確認日を使用
        # 第二ソートキー: 価格改定時刻（同じ日の価格変更を時刻順に並べる）
        # 第三ソートキー: 物件ID（降順、より新しい物件を上に）
        sort_column = func.coalesce(
            combined_subquery.c.latest_price_update,
            combined_subquery.c.earliest_published_at
        )
        if sort_order == "desc":
            query = query.order_by(
                sort_column.desc().nullslast(),
                combined_subquery.c.latest_price_update_time.desc().nullslast(),
                MasterProperty.id.desc()
            )
        else:
            query = query.order_by(
                sort_column.asc().nullsfirst(),
                combined_subquery.c.latest_price_update_time.asc().nullsfirst(),
                MasterProperty.id.asc()
            )
    
    # ページネーション
    offset = (page - 1) * per_page
    results = query.limit(per_page).offset(offset).all()
    
    # レスポンスの構築
    properties = []
    for (mp, building, listing_count, source_sites, has_active_listing, 
         last_confirmed_at, delisted_at, station_info, earliest_published_at, 
         latest_price_update, latest_price_update_time, has_price_change) in results:
        
        # 価格を決定：アクティブな掲載がない場合のみfinal_priceを使用
        if not has_active_listing and mp.sold_at and mp.final_price:
            display_price = mp.final_price
        else:
            # アクティブな掲載がある場合は、current_priceを使用
            # current_priceがNULLの場合は、アクティブな掲載から多数決価格を計算
            if mp.current_price:
                display_price = mp.current_price
            else:
                # current_priceがNULLの場合、アクティブな掲載から価格を計算
                active_listings = db.query(PropertyListing).filter(
                    PropertyListing.master_property_id == mp.id,
                    PropertyListing.is_active == True
                ).all()
                
                if active_listings:
                    # 多数決で価格を決定
                    price_votes = {}
                    for listing in active_listings:
                        if listing.current_price:
                            price = listing.current_price
                            if price not in price_votes:
                                price_votes[price] = 0
                            price_votes[price] += 1
                    
                    if price_votes:
                        # 最も多い価格を採用（同数の場合は最小値）
                        sorted_prices = sorted(price_votes.items(), key=lambda x: (-x[1], x[0]))
                        display_price = sorted_prices[0][0]
                    else:
                        display_price = None
                else:
                    display_price = None
        
        properties.append({
            "id": mp.id,
            "building": {
                "id": building.id,
                "normalized_name": building.normalized_name,
                "address": building.address,
                "total_floors": building.total_floors,
                "built_year": building.built_year,
                "built_month": building.built_month,
                "total_units": building.total_units,
                "station_info": building.station_info
            },
            "display_building_name": mp.display_building_name,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": float(mp.area) if mp.area else None,
            "layout": mp.layout,
            "direction": mp.direction,
            "balcony_area": float(mp.balcony_area) if mp.balcony_area else None,
            "current_price": display_price,
            "min_price": display_price,
            "final_price": mp.final_price,
            "is_resale": getattr(mp, 'is_resale', False),
            "listing_count": listing_count or 0,
            "source_sites": source_sites.split(',') if source_sites else [],
            "has_active_listing": has_active_listing,
            "last_confirmed_at": last_confirmed_at.isoformat() if last_confirmed_at else None,
            "delisted_at": delisted_at.isoformat() if delisted_at else None,
            "sold_at": mp.sold_at.isoformat() if mp.sold_at else None,
            "earliest_published_at": earliest_published_at.isoformat() if earliest_published_at else None,
            "latest_price_update": latest_price_update.isoformat() if latest_price_update else None,
            "has_price_change": has_price_change or False,
        })

    return {
        "properties": properties,
        "total": total,
        "sold_count": sold_count,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
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

    # 掲載情報が0件の物件は表示しない（統合済み・削除済み物件）
    if not all_listings:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # アクティブな掲載のみフィルタ
    active_listings = [l for l in all_listings if l.is_active]
    
    # 各サイトの情報を集計（多数決用）
    from ..utils.majority_vote_updater import MajorityVoteUpdater
    updater = MajorityVoteUpdater(db)
    
    # 販売終了物件の場合は非アクティブも含める
    include_inactive = master_property.sold_at is not None
    info = updater.collect_property_info_from_listings(master_property, include_inactive)
    
    # 価格を決定
    # master_property.current_priceを使用（多数決で計算済み）
    # 販売終了物件の場合はfinal_priceを使用
    if master_property.sold_at and not active_listings:
        # アクティブな掲載がない場合のみfinal_priceを使用
        majority_price = master_property.final_price
    else:
        # アクティブな掲載がある場合はcurrent_priceを使用
        majority_price = master_property.current_price
    
    # ソースサイトのリスト（アクティブな掲載のみ）
    source_sites = list(set(l.source_site for l in active_listings))
    
    # 交通情報は建物レベルで管理
    
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
                'listing_start_date': listing.first_seen_at or listing.created_at,
                'delisted_at': listing.delisted_at  # 非アクティブになった日を追加
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