"""
掲載情報管理API
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, or_, and_, distinct, String, desc, case
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from backend.app.database import get_db, SessionLocal
from backend.app.models import (
    PropertyListing, MasterProperty, Building, 
    ListingPriceHistory
)
from backend.app.utils.logger import api_logger, db_logger
from backend.app.utils.datetime_utils import to_jst_string

router = APIRouter(prefix="/api/admin/listings", tags=["admin_listings"])


class ListingListItemSchema(BaseModel):
    """掲載情報一覧アイテム"""
    id: int
    source_site: str
    site_property_id: Optional[str]
    url: str
    title: Optional[str]
    listing_building_name: Optional[str]
    current_price: Optional[int]
    is_active: bool
    master_property_id: int
    building_id: int
    building_name: str
    address: Optional[str]
    floor_number: Optional[int]
    area: Optional[float]
    layout: Optional[str]
    station_info: Optional[str]
    first_seen_at: Optional[str]
    last_confirmed_at: Optional[str]
    delisted_at: Optional[str]
    detail_fetched_at: Optional[str]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class ListingDetailSchema(BaseModel):
    """掲載情報詳細"""
    id: int
    source_site: str
    site_property_id: Optional[str]
    url: str
    title: Optional[str]
    listing_building_name: Optional[str]
    current_price: Optional[int]
    previous_price: Optional[int]
    price_updated_at: Optional[str]
    is_active: bool
    
    # マスター物件情報
    master_property: Dict[str, Any]
    
    # 建物情報
    building: Dict[str, Any]
    
    # 掲載独自の情報
    station_info: Optional[str]
    listing_floor_number: Optional[int]
    listing_area: Optional[float]
    listing_layout: Optional[str]
    listing_direction: Optional[str]
    management_fee: Optional[int]
    repair_fund: Optional[int]
    agency_name: Optional[str]
    agency_tel: Optional[str]
    remarks: Optional[str]
    summary_remarks: Optional[str]
    
    # タイムスタンプ
    first_seen_at: Optional[str]
    last_confirmed_at: Optional[str]
    first_published_at: Optional[str]
    published_at: Optional[str]
    delisted_at: Optional[str]
    detail_fetched_at: Optional[str]
    created_at: str
    updated_at: str
    
    # 詳細情報
    detail_info: Optional[Dict[str, Any]]
    
    # 価格履歴
    price_history: List[Dict[str, Any]]
    
    # 画像
    images: List[Dict[str, Any]]
    
    class Config:
        from_attributes = True


@router.get("", response_model=Dict[str, Any])
async def get_listings(
    source_site: Optional[str] = Query(None, description="サイト名でフィルター"),
    building_name: Optional[str] = Query(None, description="建物名で検索"),
    is_active: Optional[bool] = Query(None, description="アクティブな掲載のみ"),
    has_detail: Optional[bool] = Query(None, description="詳細取得済みのみ"),
    min_price: Optional[int] = Query(None, description="最低価格"),
    max_price: Optional[int] = Query(None, description="最高価格"),
    ward: Optional[str] = Query(None, description="区名でフィルター"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(50, ge=1, le=100, description="1ページあたりの件数"),
    sort_by: str = Query("updated_at", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """掲載情報一覧を取得"""
    api_logger.info(f"Get listings - filters: source_site={source_site}, building_name={building_name}, is_active={is_active}")
    
    # ベースクエリ
    query = db.query(
        PropertyListing,
        MasterProperty,
        Building
    ).join(
        MasterProperty, PropertyListing.master_property_id == MasterProperty.id
    ).join(
        Building, MasterProperty.building_id == Building.id
    )
    
    # フィルター
    if source_site:
        query = query.filter(PropertyListing.source_site == source_site)
    
    if building_name:
        # 建物名検索（正規化名と掲載名の両方を検索）
        search_pattern = f"%{building_name}%"
        query = query.filter(
            or_(
                Building.normalized_name.ilike(search_pattern),
                PropertyListing.listing_building_name.ilike(search_pattern)
            )
        )
    
    if is_active is not None:
        query = query.filter(PropertyListing.is_active == is_active)
    
    if has_detail:
        query = query.filter(PropertyListing.detail_fetched_at.isnot(None))
    
    if min_price:
        query = query.filter(PropertyListing.current_price >= min_price)
    
    if max_price:
        query = query.filter(PropertyListing.current_price <= max_price)
    
    if ward:
        query = query.filter(Building.address.like(f"東京都{ward}%"))
    
    # 総件数を取得
    total_count = query.count()
    
    # ソート
    sort_column_map = {
        "id": PropertyListing.id,
        "source_site": PropertyListing.source_site,
        "current_price": PropertyListing.current_price,
        "is_active": PropertyListing.is_active,
        "building_name": Building.normalized_name,
        "created_at": PropertyListing.created_at,
        "updated_at": PropertyListing.updated_at,
        "last_confirmed_at": PropertyListing.last_confirmed_at,
        "detail_fetched_at": PropertyListing.detail_fetched_at,
    }
    
    sort_column = sort_column_map.get(sort_by, PropertyListing.updated_at)
    
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    # ページネーション
    offset = (page - 1) * per_page
    results = query.offset(offset).limit(per_page).all()
    
    # 結果を整形
    listings = []
    for listing, master_property, building in results:
        listings.append({
            "id": listing.id,
            "source_site": listing.source_site,
            "site_property_id": listing.site_property_id,
            "url": listing.url,
            "title": listing.title,
            "listing_building_name": listing.listing_building_name,
            "current_price": listing.current_price,
            "is_active": listing.is_active,
            "master_property_id": master_property.id,
            "building_id": building.id,
            "building_name": building.normalized_name,
            "address": building.address,
            "floor_number": master_property.floor_number,
            "area": master_property.area,
            "layout": master_property.layout,
            "station_info": listing.station_info,
            "first_seen_at": to_jst_string(listing.first_seen_at),
            "last_confirmed_at": to_jst_string(listing.last_confirmed_at),
            "delisted_at": to_jst_string(listing.delisted_at),
            "detail_fetched_at": to_jst_string(listing.detail_fetched_at),
            "created_at": to_jst_string(listing.created_at),
            "updated_at": to_jst_string(listing.updated_at),
        })
    
    # 統計情報
    stats_query = db.query(
        func.count(distinct(PropertyListing.id)).label('total_listings'),
        func.count(distinct(PropertyListing.master_property_id)).label('unique_properties'),
        func.count(distinct(case((PropertyListing.is_active == True, PropertyListing.id), else_=None))).label('active_listings'),
        func.count(distinct(case((PropertyListing.detail_fetched_at.isnot(None), PropertyListing.id), else_=None))).label('with_details')
    )
    
    if source_site:
        stats_query = stats_query.filter(PropertyListing.source_site == source_site)
    
    stats = stats_query.one()
    
    return {
        "listings": listings,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_count + per_page - 1) // per_page,
        "stats": {
            "total_listings": stats.total_listings,
            "unique_properties": stats.unique_properties,
            "active_listings": stats.active_listings,
            "with_details": stats.with_details,
        }
    }


@router.get("/{listing_id}", response_model=ListingDetailSchema)
async def get_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """掲載情報の詳細を取得"""
    api_logger.info(f"Get listing detail - id: {listing_id}")
    
    # 掲載情報を取得
    listing = db.query(PropertyListing).options(
        joinedload(PropertyListing.master_property).joinedload(MasterProperty.building),
        joinedload(PropertyListing.price_history)
    ).filter(PropertyListing.id == listing_id).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # 価格履歴を整形
    price_history = []
    sorted_history = sorted(listing.price_history, key=lambda x: x.recorded_at, reverse=True)
    previous_price = None
    price_updated_at = None
    
    for i, history in enumerate(sorted_history):
        price_history.append({
            "id": history.id,
            "price": history.price,
            "management_fee": history.management_fee,
            "repair_fund": history.repair_fund,
            "recorded_at": to_jst_string(history.recorded_at),
            "is_initial": i == len(sorted_history) - 1,  # 最古のレコードを初回とする
        })
        
        # 前回価格を取得（2番目に新しい価格）
        if i == 1:
            previous_price = history.price
        # 最新の価格更新日時
        if i == 0 and len(sorted_history) > 1:
            price_updated_at = to_jst_string(history.recorded_at)
    
    # 画像を整形（現在はPropertyImageモデルが未実装のため空リスト）
    images = []
    
    # マスター物件情報
    master_property = listing.master_property
    master_property_data = {
        "id": master_property.id,
        "room_number": master_property.room_number,
        "floor_number": master_property.floor_number,
        "area": master_property.area,
        "balcony_area": master_property.balcony_area,
        "layout": master_property.layout,
        "direction": master_property.direction,
        "display_building_name": master_property.display_building_name,
        "management_fee": master_property.management_fee,
        "repair_fund": master_property.repair_fund,
    }
    
    # 建物情報
    building = master_property.building
    building_data = {
        "id": building.id,
        "normalized_name": building.normalized_name,
        "canonical_name": getattr(building, 'canonical_name', None),
        "reading": building.reading,
        "address": building.address,
        "normalized_address": building.normalized_address,
        "total_floors": building.total_floors,
        "basement_floors": getattr(building, 'basement_floors', None),
        "built_year": building.built_year,
        "built_month": building.built_month,
        "construction_type": getattr(building, 'construction_type', None),
        "land_rights": getattr(building, 'land_rights', None),
    }
    
    # 詳細データを構築
    detail_data = {
        "id": listing.id,
        "source_site": listing.source_site,
        "site_property_id": listing.site_property_id,
        "url": listing.url,
        "title": listing.title,
        "listing_building_name": listing.listing_building_name,
        "current_price": listing.current_price,
        "previous_price": previous_price,
        "price_updated_at": price_updated_at,
        "is_active": listing.is_active,
        "master_property": master_property_data,
        "building": building_data,
        "station_info": listing.station_info,
        "listing_floor_number": listing.listing_floor_number,
        "listing_area": listing.listing_area,
        "listing_layout": listing.listing_layout,
        "listing_direction": listing.listing_direction,
        "management_fee": listing.management_fee,
        "repair_fund": listing.repair_fund,
        "agency_name": listing.agency_name,
        "agency_tel": listing.agency_tel,
        "remarks": listing.remarks,
        "summary_remarks": listing.summary_remarks,
        "first_seen_at": to_jst_string(listing.first_seen_at),
        "last_confirmed_at": to_jst_string(listing.last_confirmed_at),
        "first_published_at": to_jst_string(listing.first_published_at),
        "published_at": to_jst_string(listing.published_at),
        "delisted_at": to_jst_string(listing.delisted_at),
        "detail_fetched_at": to_jst_string(listing.detail_fetched_at),
        "created_at": to_jst_string(listing.created_at),
        "updated_at": to_jst_string(listing.updated_at),
        "detail_info": listing.detail_info,
        "price_history": price_history,
        "images": images,
    }
    
    return detail_data


@router.get("/stats/by-source", response_model=Dict[str, Any])
async def get_listings_stats_by_source(db: Session = Depends(get_db)):
    """サイト別の掲載統計を取得"""
    
    # サイト別統計
    stats = db.query(
        PropertyListing.source_site,
        func.count(distinct(PropertyListing.id)).label('total_listings'),
        func.count(distinct(PropertyListing.master_property_id)).label('unique_properties'),
        func.count(distinct(case((PropertyListing.is_active == True, PropertyListing.id), else_=None))).label('active_listings'),
        func.count(distinct(case((PropertyListing.detail_fetched_at.isnot(None), PropertyListing.id), else_=None))).label('with_details'),
        func.avg(PropertyListing.current_price).label('avg_price'),
        func.min(PropertyListing.first_seen_at).label('earliest_listing'),
        func.max(PropertyListing.last_confirmed_at).label('latest_update')
    ).group_by(PropertyListing.source_site).all()
    
    results = []
    for stat in stats:
        results.append({
            "source_site": stat.source_site,
            "total_listings": stat.total_listings,
            "unique_properties": stat.unique_properties,
            "active_listings": stat.active_listings,
            "with_details": stat.with_details,
            "avg_price": int(stat.avg_price) if stat.avg_price else None,
            "earliest_listing": to_jst_string(stat.earliest_listing),
            "latest_update": to_jst_string(stat.latest_update),
        })
    
    # 全体統計
    total_stats = db.query(
        func.count(distinct(PropertyListing.id)).label('total_listings'),
        func.count(distinct(PropertyListing.master_property_id)).label('unique_properties'),
        func.count(distinct(PropertyListing.source_site)).label('source_sites')
    ).one()
    
    return {
        "by_source": results,
        "total": {
            "total_listings": total_stats.total_listings,
            "unique_properties": total_stats.unique_properties,
            "source_sites": total_stats.source_sites,
        }
    }


@router.post("/{listing_id}/refresh-detail")
async def refresh_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """掲載情報の詳細を再取得（スクレイピング）"""
    api_logger.info(f"Refresh listing detail - id: {listing_id}")
    
    listing = db.query(PropertyListing).filter(PropertyListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # 古い詳細再取得タスクをクリーンアップ（1時間以上前のものを削除）
    from backend.app.models_scraping_task import ScrapingTask
    from sqlalchemy import cast, String
    
    one_hour_ago = datetime.now() - timedelta(hours=1)
    old_tasks = db.query(ScrapingTask).filter(
        ScrapingTask.task_id.like('%detail_refresh_%'),
        ScrapingTask.created_at < one_hour_ago
    ).all()
    
    for old_task in old_tasks:
        db.delete(old_task)
    
    if old_tasks:
        db.commit()
        api_logger.info(f"Cleaned up {len(old_tasks)} old detail refresh tasks")
    
    # 既存の実行中タスクがないか確認（同じ掲載IDの詳細再取得タスクのみチェック）
    existing_task = db.query(ScrapingTask).filter(
        ScrapingTask.status.in_(['running', 'pending']),
        ScrapingTask.task_id.like(f'%detail_refresh_{listing.source_site}_{listing_id}%')
    ).first()
    
    if existing_task:
        api_logger.warning(f"Detail refresh task already exists for {listing.source_site}")
        return {
            "success": False,
            "message": f"{listing.source_site}の詳細再取得タスクが既に実行中です",
            "listing_id": listing_id,
            "url": listing.url,
            "source_site": listing.source_site,
            "existing_task_id": existing_task.task_id
        }
    
    # 個別の詳細取得タスクを作成
    import uuid
    
    task_id = f"detail_refresh_{listing.source_site}_{listing_id}_{uuid.uuid4().hex[:8]}"
    
    task = ScrapingTask(
        task_id=task_id,
        status='pending',
        scrapers=[listing.source_site],
        areas=[],  # 個別詳細取得なのでエリアは空
        max_properties=1,
        force_detail_fetch=True,
        created_at=datetime.now(),
        properties_found=0,
        detail_fetched=0,
        detail_skipped=0,
        price_missing=0,
        building_info_missing=0,
        total_processed=0,
        total_new=0,
        total_updated=0,
        total_errors=0,
        progress_detail={
            'type': 'detail_refresh',
            'target_listings': [{
                'id': listing_id,
                'url': listing.url,
                'source_site': listing.source_site
            }]
        }
    )
    
    db.add(task)
    db.commit()
    
    # バックグラウンドでスクレイピングを実行
    from fastapi import BackgroundTasks
    from backend.app.scrapers import get_scraper_class
    
    def run_detail_refresh():
        """詳細再取得を実行"""
        db_session = SessionLocal()
        try:
            # タスクのステータスを更新
            task_db = db_session.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task_db:
                task_db.status = 'running'
                task_db.started_at = datetime.now()
                db_session.commit()
            
            # 既存の掲載情報とマスター物件情報を取得
            listing_db = db_session.query(PropertyListing).filter(PropertyListing.id == listing_id).first()
            if not listing_db:
                raise ValueError(f"Listing {listing_id} not found in database")
            
            master_property = db_session.query(MasterProperty).filter(
                MasterProperty.id == listing_db.master_property_id
            ).first()
            
            building = db_session.query(Building).filter(
                Building.id == master_property.building_id
            ).first() if master_property else None
            
            # スクレイパーインスタンスを取得
            scraper_class = get_scraper_class(listing_db.source_site)
            if not scraper_class:
                raise ValueError(f"Unknown scraper: {listing_db.source_site}")
            
            scraper = scraper_class(force_detail_fetch=True)
            
            # 詳細ページのHTMLを取得
            soup = scraper.fetch_page(listing_db.url)
            if not soup:
                raise ValueError(f"Failed to fetch page: {listing_db.url}")
            
            # 既存の情報を使って詳細データを構築
            property_data_from_list = {
                'url': listing_db.url,
                'site_property_id': listing_db.site_property_id,
                'title': listing_db.title,
                'price': listing_db.current_price,
                'building_name': listing_db.listing_building_name or (building.normalized_name if building else None),
                'floor_number': listing_db.listing_floor_number or (master_property.floor_number if master_property else None),
                'area': listing_db.listing_area or (master_property.area if master_property else None),
                'layout': listing_db.listing_layout or (master_property.layout if master_property else None),
                'direction': listing_db.listing_direction or (master_property.direction if master_property else None),
                'station_info': listing_db.station_info,
            }
            
            # 詳細ページを解析（既存の情報を渡す）
            property_data = None
            if hasattr(scraper, 'parse_property_detail'):
                # parse_property_detailメソッドの引数を確認
                import inspect
                sig = inspect.signature(scraper.parse_property_detail)
                params = list(sig.parameters.keys())
                
                if 'property_data_from_list' in params:
                    # LIFULL HOME'Sのような場合
                    property_data = scraper.parse_property_detail(listing_db.url, property_data_from_list)
                else:
                    # その他のスクレイパー
                    property_data = scraper.parse_property_detail(listing_db.url)
            
            if property_data:
                # 詳細ページの解析に成功したら、detail_fetched_atを更新
                # 日本時間で保存
                jst_now = datetime.now()
                listing_db.detail_fetched_at = jst_now
                listing_db.updated_at = jst_now
                # 詳細ページから取得した情報で更新（Noneでない値のみ更新）
                if property_data.get('title'):
                    listing_db.title = property_data['title']
                if property_data.get('building_name'):
                    listing_db.listing_building_name = property_data['building_name']
                if property_data.get('floor_number') is not None:
                    listing_db.listing_floor_number = property_data['floor_number']
                if property_data.get('area') is not None:
                    listing_db.listing_area = property_data['area']
                if property_data.get('layout'):
                    listing_db.listing_layout = property_data['layout']
                if property_data.get('direction'):
                    listing_db.listing_direction = property_data['direction']
                if property_data.get('management_fee') is not None:
                    listing_db.management_fee = property_data['management_fee']
                if property_data.get('repair_fund') is not None:
                    listing_db.repair_fund = property_data['repair_fund']
                if property_data.get('agency_name'):
                    listing_db.agency_name = property_data['agency_name']
                if property_data.get('agency_tel'):
                    listing_db.agency_tel = property_data['agency_tel']
                if property_data.get('remarks'):
                    listing_db.remarks = property_data['remarks']
                if property_data.get('summary_remarks'):
                    listing_db.summary_remarks = property_data['summary_remarks']
                if property_data.get('detail_info'):
                    listing_db.detail_info = property_data['detail_info']
                
                # 価格が変更されていれば更新
                new_price = property_data.get('price')
                if new_price and new_price != listing_db.current_price:
                    listing_db.previous_price = listing_db.current_price
                    listing_db.current_price = new_price
                    listing_db.price_updated_at = jst_now
                    
                    # 価格履歴を追加
                    price_history = ListingPriceHistory(
                        property_listing_id=listing_id,
                        price=new_price,
                        recorded_at=jst_now,
                        is_initial=False
                    )
                    db_session.add(price_history)
                
                # 掲載状態の確認（販売終了チェック）
                if hasattr(scraper, '_check_if_sold') and property_data.get('url'):
                    is_sold = scraper._check_if_sold(soup, property_data['url'])
                    if is_sold and listing_db.is_active:
                        listing_db.is_active = False
                        listing_db.delisted_at = jst_now
                        api_logger.info(f"Property marked as sold: {listing_db.url}")
                
                db_session.commit()
                
                # タスクを完了
                task_db.status = 'completed'
                task_db.completed_at = datetime.now()
                task_db.total_processed = 1
                task_db.total_updated = 1
                task_db.detail_fetched = 1
                task_db.elapsed_time = (datetime.now() - task_db.started_at).total_seconds()
                task_db.progress_detail['updated_fields'] = list(property_data.keys())
                db_session.commit()
                
                api_logger.info(f"Successfully refreshed detail for listing {listing_id}")
                
                # 詳細再取得タスクは完了後に削除
                db_session.delete(task_db)
                db_session.commit()
                api_logger.info(f"Deleted completed detail refresh task: {task_id}")
            else:
                # 詳細取得失敗
                task_db.status = 'error'
                task_db.completed_at = datetime.now()
                task_db.total_processed = 1
                task_db.total_errors = 1
                task_db.error_logs = [{
                    'timestamp': datetime.now().isoformat(),
                    'error': 'Failed to parse property detail',
                    'url': listing_db.url
                }]
                db_session.commit()
                
                # エラーの場合も削除（ログは既に記録済み）
                db_session.delete(task_db)
                db_session.commit()
                api_logger.info(f"Deleted failed detail refresh task: {task_id}")
                
        except Exception as e:
            api_logger.error(f"Error in detail refresh for listing {listing_id}: {str(e)}", exc_info=True)
            # タスクをエラーステータスに
            task_db = db_session.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task_db:
                task_db.status = 'error'
                task_db.completed_at = datetime.now()
                task_db.total_errors = 1
                task_db.error_logs = [{
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e),
                    'url': listing.url
                }]
                db_session.commit()
                
                # エラーの場合も削除
                db_session.delete(task_db)
                db_session.commit()
                api_logger.info(f"Deleted error detail refresh task: {task_id}")
        finally:
            db_session.close()
    
    # バックグラウンドタスクとして実行
    import threading
    thread = threading.Thread(target=run_detail_refresh)
    thread.start()
    
    return {
        "success": True,
        "message": "詳細再取得をキューに追加しました",
        "listing_id": listing_id,
        "url": listing.url,
        "source_site": listing.source_site,
        "task_id": task_id
    }


@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """掲載情報を削除（非アクティブ化）"""
    api_logger.info(f"Delete listing - id: {listing_id}")
    
    listing = db.query(PropertyListing).filter(PropertyListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    
    # 物理削除ではなく、非アクティブ化
    listing.is_active = False
    listing.delisted_at = datetime.now()
    
    db.commit()
    
    return {
        "success": True,
        "message": "掲載情報を非アクティブ化しました",
        "listing_id": listing_id,
    }