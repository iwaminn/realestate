"""物件関連のAPIエンドポイント v2"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, distinct, String, select

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, ListingPriceHistory
from ..schemas.property import PropertyDetailSchema, MasterPropertySchema, ListingSchema, PriceHistorySchema
from ..schemas.building import BuildingSchema
from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery, apply_price_filter
from ..utils.building_filters import apply_building_name_filter, apply_building_filters, apply_property_filters
from .price_analysis import create_unified_price_timeline, analyze_source_price_consistency

router = APIRouter(prefix="/api/v2", tags=["properties"])

@router.get("/properties", response_model=Dict[str, Any])
async def get_properties_v2(
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
    
    # 価格の多数決サブクエリを作成
    majority_price_query = create_majority_price_subquery(db, include_inactive)
    
    # 価格統計サブクエリを作成
    price_subquery = create_price_stats_subquery(db, majority_price_query, include_inactive)
    
    # メインクエリ
    query = db.query(
        MasterProperty,
        Building,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,
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
    
    # 価格フィルタ
    query = apply_price_filter(query, price_subquery, min_price, max_price)
    
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
        order_column = func.coalesce(price_subquery.c.min_price, MasterProperty.final_price)
    elif sort_by == "area":
        order_column = MasterProperty.area
    elif sort_by == "built_year":
        order_column = Building.built_year
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
    for mp, building, min_price, max_price, majority_price, listing_count, source_sites, has_active, last_confirmed, delisted, station_info, earliest_published_at, latest_price_update, has_price_change in results:
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
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "min_price": min_price if not mp.sold_at else mp.final_price,
            "max_price": max_price if not mp.sold_at else mp.final_price,
            "majority_price": majority_price if not mp.sold_at else mp.final_price,
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
            "last_sale_price": mp.final_price
        })
    
    return {
        "properties": properties,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_count + per_page - 1) // per_page
    }

@router.get("/properties/{property_id}", response_model=PropertyDetailSchema)
async def get_property_details_v2(
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
    for listing in all_listings:
        histories = db.query(ListingPriceHistory).filter(
            ListingPriceHistory.property_listing_id == listing.id
        ).all()
        
        for history in histories:
            all_price_records.append({
                'recorded_at': history.recorded_at,
                'price': history.price,
                'source_site': listing.source_site,
                'listing_id': listing.id,
                'is_active': listing.is_active
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
    earliest_published_at = None
    for listing in all_listings:
        if listing.published_at:
            if not earliest_published_at or listing.published_at < earliest_published_at:
                earliest_published_at = listing.published_at
    
    # レスポンスを構築
    master_property_data = {
        "id": master_property.id,
        "building": BuildingSchema.from_orm(master_property.building),
        "room_number": master_property.room_number,
        "floor_number": master_property.floor_number,
        "area": master_property.area,
        "balcony_area": master_property.balcony_area,
        "layout": master_property.layout,
        "direction": master_property.direction,
        "majority_price": majority_price,  # 多数決価格に変更
        "min_price": majority_price,  # 互換性のため維持
        "max_price": majority_price,  # 互換性のため維持
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


@router.get("/properties/recent-updates", response_model=Dict[str, Any])
async def get_recent_updates(
    hours: int = Query(24, ge=1, le=168, description="過去N時間以内の更新"),
    db: Session = Depends(get_db)
):
    """
    直近N時間以内の価格改定物件と新着物件を取得
    デフォルトは24時間以内
    """
    from datetime import datetime, timedelta
    from sqlalchemy import case
    
    # 対象期間の開始時刻
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # 価格履歴から価格改定物件を取得
    price_changes_subq = (
        db.query(
            ListingPriceHistory.listing_id,
            func.max(ListingPriceHistory.changed_at).label('last_change')
        )
        .filter(ListingPriceHistory.changed_at >= cutoff_time)
        .group_by(ListingPriceHistory.listing_id)
        .subquery()
    )
    
    # 価格改定のあった物件を取得
    price_changed_properties = (
        db.query(
            MasterProperty,
            Building,
            PropertyListing.current_price,
            PropertyListing.title,
            PropertyListing.url,
            PropertyListing.source_site,
            price_changes_subq.c.last_change.label('changed_at'),
            func.literal('price_change').label('update_type')
        )
        .join(PropertyListing, PropertyListing.master_property_id == MasterProperty.id)
        .join(Building, MasterProperty.building_id == Building.id)
        .join(price_changes_subq, price_changes_subq.c.listing_id == PropertyListing.id)
        .filter(PropertyListing.is_active == True)
        .all()
    )
    
    # 新着物件を取得（created_atが期間内）
    new_properties = (
        db.query(
            MasterProperty,
            Building,
            PropertyListing.current_price,
            PropertyListing.title,
            PropertyListing.url,
            PropertyListing.source_site,
            PropertyListing.created_at.label('changed_at'),
            func.literal('new').label('update_type')
        )
        .join(PropertyListing, PropertyListing.master_property_id == MasterProperty.id)
        .join(Building, MasterProperty.building_id == Building.id)
        .filter(
            PropertyListing.is_active == True,
            PropertyListing.created_at >= cutoff_time
        )
        .all()
    )
    
    # 結果を区ごとにグループ化
    updates_by_ward = {}
    
    def get_ward(address):
        """住所から区名を抽出"""
        if not address:
            return "不明"
        import re
        match = re.search(r'(.*?[区市町村])', address)
        if match:
            ward = match.group(1)
            # 都道府県名を除去
            ward = re.sub(r'^東京都', '', ward)
            return ward
        return "不明"
    
    # 価格改定物件を処理
    for item in price_changed_properties:
        master_property, building, price, title, url, source, changed_at, update_type = item
        ward = get_ward(building.address)
        
        if ward not in updates_by_ward:
            updates_by_ward[ward] = {
                'ward': ward,
                'price_changes': [],
                'new_listings': []
            }
        
        updates_by_ward[ward]['price_changes'].append({
            'id': master_property.id,
            'building_name': building.normalized_name,
            'room_number': master_property.room_number,
            'floor_number': master_property.floor_number,
            'area': master_property.area,
            'layout': master_property.layout,
            'direction': master_property.direction,
            'price': price,
            'title': title,
            'url': url,
            'source_site': source,
            'changed_at': changed_at.isoformat() if changed_at else None,
            'address': building.address
        })
    
    # 新着物件を処理
    for item in new_properties:
        master_property, building, price, title, url, source, changed_at, update_type = item
        ward = get_ward(building.address)
        
        if ward not in updates_by_ward:
            updates_by_ward[ward] = {
                'ward': ward,
                'price_changes': [],
                'new_listings': []
            }
        
        updates_by_ward[ward]['new_listings'].append({
            'id': master_property.id,
            'building_name': building.normalized_name,
            'room_number': master_property.room_number,
            'floor_number': master_property.floor_number,
            'area': master_property.area,
            'layout': master_property.layout,
            'direction': master_property.direction,
            'price': price,
            'title': title,
            'url': url,
            'source_site': source,
            'created_at': changed_at.isoformat() if changed_at else None,
            'address': building.address
        })
    
    # 区名でソート
    sorted_wards = sorted(updates_by_ward.keys())
    sorted_updates = [updates_by_ward[ward] for ward in sorted_wards]
    
    # サマリー情報を計算
    total_price_changes = sum(len(w['price_changes']) for w in sorted_updates)
    total_new_listings = sum(len(w['new_listings']) for w in sorted_updates)
    
    return {
        'period_hours': hours,
        'cutoff_time': cutoff_time.isoformat(),
        'total_price_changes': total_price_changes,
        'total_new_listings': total_new_listings,
        'updates_by_ward': sorted_updates
    }