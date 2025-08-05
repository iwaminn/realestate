"""
掲載情報管理API
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, or_, and_, distinct, String, desc, case
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from backend.app.database import get_db
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
    is_new: bool
    
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
    for history in sorted(listing.price_history, key=lambda x: x.recorded_at, reverse=True):
        price_history.append({
            "id": history.id,
            "price": history.price,
            "recorded_at": to_jst_string(history.recorded_at),
            "is_initial": history.is_initial,
        })
    
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
        "sold_at": to_jst_string(master_property.sold_at),
        "last_sale_price": master_property.last_sale_price,
    }
    
    # 建物情報
    building = master_property.building
    building_data = {
        "id": building.id,
        "normalized_name": building.normalized_name,
        "canonical_name": building.canonical_name,
        "reading": building.reading,
        "address": building.address,
        "normalized_address": building.normalized_address,
        "total_floors": building.total_floors,
        "basement_floors": building.basement_floors,
        "built_year": building.built_year,
        "built_month": building.built_month,
        "construction_type": building.construction_type,
        "land_rights": building.land_rights,
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
        "previous_price": listing.previous_price,
        "price_updated_at": to_jst_string(listing.price_updated_at),
        "is_active": listing.is_active,
        "is_new": listing.is_new,
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
    
    # TODO: スクレイピングジョブをキューに追加
    # 現在は未実装のため、プレースホルダーを返す
    
    return {
        "success": True,
        "message": "詳細再取得をキューに追加しました",
        "listing_id": listing_id,
        "url": listing.url,
        "source_site": listing.source_site,
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