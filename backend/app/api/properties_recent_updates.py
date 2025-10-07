"""
価格改定履歴キャッシュを使用する新しいAPIエンドポイント
"""

from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ..database import get_db
from ..utils.cache import get_cache
from ..models import (
    PropertyPriceChange,
    MasterProperty,
    PropertyListing,
    Building
)
from ..models_scraping_task import ScrapingTask

router = APIRouter(prefix="/api", tags=["properties"])


@router.get("/properties/recent-updates", response_model=Dict[str, Any])
async def get_recent_updates_cached(
    hours: int = Query(24, ge=1, le=168, description="過去N時間以内の更新"),
    db: Session = Depends(get_db)
):
    """
    キャッシュテーブルから価格改定情報を取得（高速版・サーバーサイドキャッシュ対応）
    """
    
    # サーバーサイドキャッシュをチェック
    cache = get_cache()
    cache_key = f"recent_updates_{hours}h"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        # キャッシュヒット
        cached_data['cache_info']['cache_hit'] = True
        return cached_data
    
    # キャッシュミス - データベースから取得
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
            func.max(PropertyListing.source_site).label('source_site'),
            func.bool_or(PropertyListing.is_active).label('has_active_listing')
        )
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
            active_listing_subq.c.has_active_listing == True,  # 販売中物件のみ
            Building.is_valid_name == True  # 広告文のみの建物を除外
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
    
    # 新着物件用のアクティブ掲載情報サブクエリ（価格を含む）
    new_listing_active_subq = (
        db.query(
            PropertyListing.master_property_id,
            func.max(PropertyListing.title).label('title'),
            func.max(PropertyListing.url).label('url'),
            func.max(PropertyListing.source_site).label('source_site'),
            func.max(PropertyListing.current_price).label('listing_price'),  # 掲載価格を取得
            func.bool_or(PropertyListing.is_active).label('has_active_listing')
        )
        .group_by(PropertyListing.master_property_id)
        .subquery()
    )
    
    # 指定期間内に初めて掲載された物件を取得（既存のロジックを使用）
    new_listings_query = (
        db.query(
            MasterProperty,
            Building,
            new_listing_active_subq.c.title,
            new_listing_active_subq.c.url,
            new_listing_active_subq.c.source_site,
            new_listing_active_subq.c.listing_price,  # 掲載価格を取得
            first_listing_subq.c.first_created_at.label('created_at')
        )
        .join(new_listing_active_subq, new_listing_active_subq.c.master_property_id == MasterProperty.id)
        .join(Building, MasterProperty.building_id == Building.id)
        .join(
            first_listing_subq,
            first_listing_subq.c.master_property_id == MasterProperty.id
        )
        .filter(
            first_listing_subq.c.first_created_at >= cutoff_time,
            new_listing_active_subq.c.has_active_listing == True,  # 販売中物件のみ
            Building.is_valid_name == True  # 広告文のみの建物を除外
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
    for master_property, building, title, url, source, listing_price, created_at in new_listings_query:
        ward = get_ward(building.address)
        
        if ward not in updates_by_ward:
            updates_by_ward[ward] = {
                'ward': ward,
                'price_changes': [],
                'new_listings': []
            }
        
        # 価格の優先順位: current_price → listing_price
        display_price = master_property.current_price or listing_price
        
        updates_by_ward[ward]['new_listings'].append({
            'id': master_property.id,
            'building_name': building.normalized_name,
            'room_number': master_property.room_number,
            'floor_number': master_property.floor_number,
            'area': master_property.area,
            'layout': master_property.layout,
            'direction': master_property.direction,
            'price': display_price,
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
    
    # 最後に完了したスクレイパーの実行時刻を取得
    last_scraping_task = (
        db.query(ScrapingTask)
        .filter(ScrapingTask.status == 'completed')
        .order_by(ScrapingTask.completed_at.desc())
        .first()
    )
    last_scraper_completed_at = last_scraping_task.completed_at if last_scraping_task else None
    
    # レスポンスデータを作成
    response_data = {
        'period_hours': hours,
        'cutoff_time': cutoff_time.isoformat(),
        'total_price_changes': total_price_changes,
        'total_new_listings': total_new_listings,
        'updates_by_ward': sorted_updates,
        'last_scraper_completed_at': last_scraper_completed_at.isoformat() if last_scraper_completed_at else None,
        'cache_info': {
            'using_cache': True,
            'cache_updated_at': db.query(func.max(PropertyPriceChange.updated_at)).scalar(),
            'cache_hit': False
        }
    }
    
    # サーバーサイドキャッシュに保存（30分間有効）
    cache.set(cache_key, response_data, ttl_seconds=1800)
    
    return response_data


@router.get("/properties/recent-updates/counts", response_model=Dict[str, Any])
async def get_recent_updates_counts(
    hours: int = Query(24, ge=1, le=168, description="過去N時間以内の更新"),
    db: Session = Depends(get_db)
):
    """
    価格改定・新規掲載の件数のみを取得（トップページ用・軽量版）
    """
    
    # サーバーサイドキャッシュをチェック
    cache = get_cache()
    cache_key = f"recent_updates_counts_{hours}h"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        cached_data['cache_hit'] = True
        return cached_data
    
    # キャッシュミス - データベースから件数を集計
    from ..utils.datetime_utils import get_utc_now
    jst_now = get_utc_now()
    cutoff_date = jst_now.date() - timedelta(days=hours/24)
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    # has_active_listingサブクエリ
    active_listing_check = (
        db.query(
            PropertyListing.master_property_id,
            func.bool_or(PropertyListing.is_active).label('has_active_listing')
        )
        .group_by(PropertyListing.master_property_id)
        .subquery()
    )
    
    # 価格改定件数を集計
    price_changes_count = (
        db.query(func.count(PropertyPriceChange.id))
        .join(MasterProperty, MasterProperty.id == PropertyPriceChange.master_property_id)
        .join(Building, Building.id == MasterProperty.building_id)
        .join(active_listing_check, active_listing_check.c.master_property_id == MasterProperty.id)
        .filter(
            PropertyPriceChange.change_date >= cutoff_date,
            active_listing_check.c.has_active_listing == True,
            Building.is_valid_name == True
        )
        .scalar() or 0
    )
    
    # 新規掲載件数を集計
    first_listing_subq = (
        db.query(
            PropertyListing.master_property_id,
            func.min(PropertyListing.created_at).label('first_created_at')
        )
        .group_by(PropertyListing.master_property_id)
        .subquery()
    )
    
    new_listings_count = (
        db.query(func.count(MasterProperty.id.distinct()))
        .join(Building, MasterProperty.building_id == Building.id)
        .join(active_listing_check, active_listing_check.c.master_property_id == MasterProperty.id)
        .join(
            first_listing_subq,
            first_listing_subq.c.master_property_id == MasterProperty.id
        )
        .filter(
            first_listing_subq.c.first_created_at >= cutoff_time,
            active_listing_check.c.has_active_listing == True,
            Building.is_valid_name == True
        )
        .scalar() or 0
    )
    
    # 区ごとの件数を集計
    ward_counts = {}
    
    # 価格改定の区ごと件数
    price_changes_by_ward = (
        db.query(
            Building.address,
            func.count(PropertyPriceChange.id).label('count')
        )
        .join(MasterProperty, MasterProperty.id == PropertyPriceChange.master_property_id)
        .join(Building, Building.id == MasterProperty.building_id)
        .join(active_listing_check, active_listing_check.c.master_property_id == MasterProperty.id)
        .filter(
            PropertyPriceChange.change_date >= cutoff_date,
            active_listing_check.c.has_active_listing == True,
            Building.is_valid_name == True
        )
        .group_by(Building.address)
        .all()
    )
    
    for address, count in price_changes_by_ward:
        import re
        match = re.search(r'(.*?[区市町村])', address or '')
        if match:
            ward = re.sub(r'^東京都', '', match.group(1))
            if ward not in ward_counts:
                ward_counts[ward] = {'price_changes': 0, 'new_listings': 0}
            ward_counts[ward]['price_changes'] += count
    
    # 新規掲載の区ごと件数
    new_listings_by_ward = (
        db.query(
            Building.address,
            func.count(MasterProperty.id.distinct()).label('count')
        )
        .join(Building, MasterProperty.building_id == Building.id)
        .join(active_listing_check, active_listing_check.c.master_property_id == MasterProperty.id)
        .join(
            first_listing_subq,
            first_listing_subq.c.master_property_id == MasterProperty.id
        )
        .filter(
            first_listing_subq.c.first_created_at >= cutoff_time,
            active_listing_check.c.has_active_listing == True,
            Building.is_valid_name == True
        )
        .group_by(Building.address)
        .all()
    )
    
    for address, count in new_listings_by_ward:
        import re
        match = re.search(r'(.*?[区市町村])', address or '')
        if match:
            ward = re.sub(r'^東京都', '', match.group(1))
            if ward not in ward_counts:
                ward_counts[ward] = {'price_changes': 0, 'new_listings': 0}
            ward_counts[ward]['new_listings'] += count
    
    # レスポンスデータを作成
    response_data = {
        'total_price_changes': price_changes_count,
        'total_new_listings': new_listings_count,
        'ward_counts': ward_counts,
        'cache_hit': False
    }
    
    # サーバーサイドキャッシュに保存（30分間有効）
    cache.set(cache_key, response_data, ttl_seconds=1800)
    
    return response_data
