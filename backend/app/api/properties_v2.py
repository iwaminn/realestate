"""
価格改定履歴キャッシュを使用する新しいAPIエンドポイント
"""

from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ..database import get_db
from ..models import (
    PropertyPriceChange,
    MasterProperty,
    PropertyListing,
    Building
)

router = APIRouter(prefix="/api", tags=["properties-v2"])


@router.get("/v2/properties/recent-updates", response_model=Dict[str, Any])
async def get_recent_updates_cached(
    hours: int = Query(24, ge=1, le=168, description="過去N時間以内の更新"),
    db: Session = Depends(get_db)
):
    """
    キャッシュテーブルから価格改定情報を取得（高速版）
    """
    
    # 対象期間の開始日
    from ..utils.datetime_utils import get_utc_now
    # 日本時間での計算
    jst_now = get_utc_now()  # 実際は日本時間
    cutoff_date = jst_now.date() - timedelta(days=hours/24)
    
    # 価格改定物件を取得（キャッシュテーブルから）
    # サブクエリでアクティブな掲載情報を取得
    active_listing_subq = (
        db.query(
            PropertyListing.master_property_id,
            func.max(PropertyListing.title).label('title'),
            func.max(PropertyListing.url).label('url'),
            func.max(PropertyListing.source_site).label('source_site')
        )
        .filter(PropertyListing.is_active == True)
        .group_by(PropertyListing.master_property_id)
        .subquery()
    )
    
    price_changes_query = (
        db.query(
            PropertyPriceChange,
            MasterProperty,
            Building,
            active_listing_subq.c.title,
            active_listing_subq.c.url,
            active_listing_subq.c.source_site
        )
        .join(MasterProperty, MasterProperty.id == PropertyPriceChange.master_property_id)
        .join(Building, Building.id == MasterProperty.building_id)
        .join(active_listing_subq, active_listing_subq.c.master_property_id == MasterProperty.id)
        .filter(
            PropertyPriceChange.change_date >= cutoff_date,
            MasterProperty.sold_at.is_(None)  # 販売終了物件を除外
        )
        .order_by(PropertyPriceChange.change_date.desc())
    ).all()
    
    # 新着物件を取得（既存のロジックを使用）
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # 各MasterPropertyの最初の掲載日時を取得
    first_listing_subq = (
        db.query(
            PropertyListing.master_property_id,
            func.min(PropertyListing.created_at).label('first_created_at')
        )
        .group_by(PropertyListing.master_property_id)
        .subquery()
    )
    
    # 指定期間内に初めて掲載された物件を取得
    new_listings_query = (
        db.query(
            MasterProperty,
            Building,
            PropertyListing.current_price,
            PropertyListing.title,
            PropertyListing.url,
            PropertyListing.source_site,
            first_listing_subq.c.first_created_at.label('created_at')
        )
        .join(PropertyListing, PropertyListing.master_property_id == MasterProperty.id)
        .join(Building, MasterProperty.building_id == Building.id)
        .join(
            first_listing_subq,
            first_listing_subq.c.master_property_id == MasterProperty.id
        )
        .filter(
            PropertyListing.is_active == True,
            first_listing_subq.c.first_created_at >= cutoff_time,
            MasterProperty.sold_at.is_(None)
        )
        .distinct(MasterProperty.id)
    ).all()
    
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
    for price_change, master_property, building, title, url, source in price_changes_query:
        ward = get_ward(building.address)
        
        if ward not in updates_by_ward:
            updates_by_ward[ward] = {
                'ward': ward,
                'price_changes': [],
                'new_listings': []
            }
        
        # 経過日数を計算
        days_on_market = None
        if master_property.earliest_listing_date:
            days_on_market = (datetime.now() - master_property.earliest_listing_date).days
        
        updates_by_ward[ward]['price_changes'].append({
            'id': master_property.id,
            'building_name': building.normalized_name,
            'room_number': master_property.room_number,
            'floor_number': master_property.floor_number,
            'area': master_property.area,
            'layout': master_property.layout,
            'direction': master_property.direction,
            'price': price_change.new_price,
            'previous_price': price_change.old_price,
            'price_diff': price_change.price_diff,
            'price_diff_rate': float(price_change.price_diff_rate) if price_change.price_diff_rate else 0,
            'title': title,
            'url': url,
            'source_site': source,
            'changed_at': price_change.change_date.isoformat(),
            'address': building.address,
            'built_year': building.built_year,
            'built_month': building.built_month,
            'days_on_market': days_on_market
        })
    
    # 新着物件を処理
    for master_property, building, price, title, url, source, created_at in new_listings_query:
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
            'created_at': created_at.isoformat() if created_at else None,
            'address': building.address,
            'built_year': building.built_year,
            'built_month': building.built_month
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
        'updates_by_ward': sorted_updates,
        'cache_info': {
            'using_cache': True,
            'cache_updated_at': db.query(func.max(PropertyPriceChange.updated_at)).scalar()
        }
    }