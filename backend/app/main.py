#!/usr/bin/env python3
"""
不動産物件API サーバー v2.0
重複排除と複数サイト管理に対応
"""

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, distinct, String, case, select
from difflib import SequenceMatcher
import os
import re

from backend.app.database import get_db, init_db
from backend.app.models import (
    Building, MasterProperty, PropertyListing, 
    ListingPriceHistory, BuildingExternalId,
    BuildingMergeExclusion, BuildingMergeHistory
)
from backend.app.utils.logger import app_logger, error_logger, api_logger, db_logger, LogContext, log_api_request, log_database_operation
from backend.app.api.price_analysis import (
    create_unified_price_timeline,
    analyze_source_price_consistency
)
from backend.app.api import admin
from backend.app.api import admin_listings
from backend.app.api import admin_properties
from backend.app.api import admin_buildings

app = FastAPI(title="不動産横断検索API v2", version="2.0.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ロギングミドルウェア
@app.middleware("http")
async def log_requests(request, call_next):
    """すべてのHTTPリクエストをログに記録"""
    import time
    start_time = time.time()
    
    # リクエスト情報をログ
    api_logger.info(f"Request started: {request.method} {request.url.path}", extra={
        "method": request.method,
        "path": str(request.url.path),
        "query_params": dict(request.query_params),
        "client": request.client.host if request.client else None
    })
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        api_logger.info(f"Request completed: {request.method} {request.url.path}", extra={
            "method": request.method,
            "path": str(request.url.path),
            "status_code": response.status_code,
            "process_time": process_time
        })
        
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as e:
        process_time = time.time() - start_time
        api_logger.error(f"Request failed: {request.method} {request.url.path}", extra={
            "method": request.method,
            "path": str(request.url.path),
            "error": str(e),
            "process_time": process_time
        }, exc_info=True)
        raise

# Pydanticモデル
class BuildingSchema(BaseModel):
    id: int
    normalized_name: str
    address: Optional[str]
    total_floors: Optional[int]
    basement_floors: Optional[int]
    total_units: Optional[int]  # 総戸数を追加
    built_year: Optional[int]
    built_month: Optional[int]
    construction_type: Optional[str]
    land_rights: Optional[str]
    station_info: Optional[str]
    
    class Config:
        from_attributes = True

class ListingSchema(BaseModel):
    id: int
    source_site: str
    site_property_id: Optional[str]
    url: str
    title: Optional[str]
    agency_name: Optional[str]
    agency_tel: Optional[str]
    current_price: Optional[int]
    management_fee: Optional[int]
    repair_fund: Optional[int]
    remarks: Optional[str]
    is_active: bool
    first_seen_at: datetime
    last_scraped_at: datetime
    published_at: Optional[datetime]
    first_published_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class PriceHistorySchema(BaseModel):
    price: int
    management_fee: Optional[int]
    repair_fund: Optional[int]
    recorded_at: datetime
    
    class Config:
        from_attributes = True

class MasterPropertySchema(BaseModel):
    id: int
    building: BuildingSchema
    room_number: Optional[str]
    floor_number: Optional[int]
    area: Optional[float]
    balcony_area: Optional[float]
    layout: Optional[str]
    direction: Optional[str]
    min_price: Optional[int]
    max_price: Optional[int]
    listing_count: int
    source_sites: List[str]
    station_info: Optional[str]
    management_fee: Optional[int]  # 管理費（月額・円）
    repair_fund: Optional[int]     # 修繕積立金（月額・円）
    earliest_published_at: Optional[datetime]  # 最も古い情報提供日
    sold_at: Optional[datetime]
    final_price: Optional[int]
    has_active_listing: bool = True
    
    class Config:
        from_attributes = True

class UnifiedPriceRecord(BaseModel):
    recorded_at: datetime
    price: int
    source_site: str
    listing_id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class PriceDiscrepancy(BaseModel):
    date: str
    prices: Dict[str, List[str]]  # {価格: [ソースサイトのリスト]}
    
    class Config:
        from_attributes = True

class PropertyDetailSchema(BaseModel):
    master_property: MasterPropertySchema
    listings: List[ListingSchema]
    price_histories_by_listing: Dict[int, List[PriceHistorySchema]]  # フロントエンド互換性
    price_timeline: Dict[str, Any]              # 価格推移タイムライン
    price_consistency: Dict[str, Any]           # 価格一貫性分析
    unified_price_history: List[Dict[str, Any]] # 統合価格履歴（生データ）
    price_discrepancies: List[Dict[str, Any]]   # 価格差異情報
    
    class Config:
        from_attributes = True

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    init_db()

# 管理画面用ルーターを追加
app.include_router(admin.router)
app.include_router(admin_listings.router, prefix="/api/admin")
app.include_router(admin_properties.router)
app.include_router(admin_buildings.router, prefix="/api/admin")

@app.get("/")
async def root():
    return {"message": "不動産横断検索API v2", "version": "2.0.0"}

@app.get("/api/v2/areas", response_model=List[Dict[str, Any]])
async def get_areas(db: Session = Depends(get_db)):
    """物件が存在する区の一覧を取得"""
    # 住所から区名を抽出し、物件数をカウント
    query = db.query(
        func.substring(Building.address, r'東京都([^区]+区)').label('ward'),
        func.count(distinct(MasterProperty.id)).label('property_count')
    ).join(
        MasterProperty, Building.id == MasterProperty.building_id
    ).filter(
        Building.address.like('東京都%'),
        Building.address.isnot(None)
    ).group_by(
        func.substring(Building.address, r'東京都([^区]+区)')
    ).having(
        func.substring(Building.address, r'東京都([^区]+区)').isnot(None)
    ).order_by(
        'ward'
    )
    
    results = query.all()
    
    # area_config.pyの定義も含めて返す
    from .scrapers.area_config import TOKYO_AREA_CODES
    
    # 地価順の並び（辞書の順序を保持するため、Python 3.7+で有効）
    area_order = list(TOKYO_AREA_CODES.keys())
    
    area_list = []
    for ward, property_count in results:
        if ward:
            # 区コードを取得
            area_code = TOKYO_AREA_CODES.get(ward, None)
            area_list.append({
                "name": ward,
                "code": area_code,
                "property_count": property_count
            })
    
    # 地価順でソート（TOKYO_AREA_CODESの定義順）
    area_list.sort(key=lambda x: area_order.index(x["name"]) if x["name"] in area_order else 999)
    
    return area_list

@app.get("/api/v2/buildings", response_model=Dict[str, Any])
async def get_buildings_v2(
    wards: Optional[List[str]] = Query(None, description="区名リスト（例: 港区、中央区）"),
    search: Optional[str] = Query(None, description="建物名検索"),
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    max_building_age: Optional[int] = Query(None, description="築年数以内"),
    min_total_floors: Optional[int] = Query(None, description="最低階数"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    sort_by: str = Query("property_count", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """建物一覧を取得（物件集計情報付き）"""
    
    # 各建物の物件統計を取得するサブクエリ
    property_stats = db.query(
        MasterProperty.building_id,
        func.count(distinct(MasterProperty.id)).label('property_count'),
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.avg(PropertyListing.current_price).label('avg_price'),
        func.count(distinct(PropertyListing.id)).label('total_listings'),
        func.sum(case((PropertyListing.is_active == True, 1), else_=0)).label('active_listings')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id
    ).filter(
        PropertyListing.is_active == True  # アクティブな掲載のみ
    ).group_by(
        MasterProperty.building_id
    ).subquery()
    
    # メインクエリ
    query = db.query(
        Building,
        property_stats.c.property_count,
        property_stats.c.min_price,
        property_stats.c.max_price,
        property_stats.c.avg_price,
        property_stats.c.total_listings,
        property_stats.c.active_listings
    ).outerjoin(
        property_stats, Building.id == property_stats.c.building_id
    )
    
    # アクティブな物件がある建物のみ表示
    query = query.filter(property_stats.c.property_count > 0)
    
    # フィルター条件
    if wards:
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.like(f'%{ward}%'))
        query = query.filter(or_(*ward_conditions))
    
    if search:
        # 建物名で検索（部分一致）
        search_pattern = f'%{search}%'
        query = query.filter(
            or_(
                Building.normalized_name.ilike(search_pattern),
                Building.canonical_name.ilike(search_pattern) if hasattr(Building, 'canonical_name') else False
            )
        )
    
    if min_price:
        query = query.filter(property_stats.c.min_price >= min_price)
    
    if max_price:
        query = query.filter(property_stats.c.max_price <= max_price)
    
    if max_building_age:
        min_year = datetime.now().year - max_building_age
        query = query.filter(Building.built_year >= min_year)
    
    if min_total_floors:
        query = query.filter(Building.total_floors >= min_total_floors)
    
    # ソート
    if sort_by == "property_count":
        order_column = property_stats.c.property_count
    elif sort_by == "min_price":
        order_column = property_stats.c.min_price
    elif sort_by == "max_price":
        order_column = property_stats.c.max_price
    elif sort_by == "built_year":
        order_column = Building.built_year
    elif sort_by == "total_floors":
        order_column = Building.total_floors
    elif sort_by == "name":
        order_column = Building.normalized_name
    else:
        order_column = property_stats.c.property_count
    
    if sort_order == "asc":
        query = query.order_by(asc(order_column))
    else:
        query = query.order_by(desc(order_column))
    
    # ページネーション
    total = query.count()
    offset = (page - 1) * per_page
    buildings = query.offset(offset).limit(per_page).all()
    
    # レスポンス形式に変換
    result = []
    for building, property_count, min_price, max_price, avg_price, total_listings, active_listings in buildings:
        result.append({
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "built_year": building.built_year,
            "built_month": building.built_month,
            "construction_type": building.construction_type,
            "station_info": building.station_info,
            "property_count": property_count or 0,
            "active_listings": active_listings or 0,
            "price_range": {
                "min": min_price,
                "max": max_price,
                "avg": int(avg_price) if avg_price else None
            },
            "building_age": datetime.now().year - building.built_year if building.built_year else None
        })
    
    return {
        "buildings": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }

@app.get("/api/v2/properties", response_model=Dict[str, Any])
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
    
    
    # サブクエリ：各マスター物件の最新価格を取得（多数決）
    # 価格の多数決を計算するサブクエリ
    price_vote_query = db.query(
        PropertyListing.master_property_id,
        PropertyListing.current_price,
        func.count(PropertyListing.id).label('vote_count')
    ).filter(
        PropertyListing.is_active == True,
        PropertyListing.current_price.isnot(None)
    ).group_by(
        PropertyListing.master_property_id,
        PropertyListing.current_price
    ).subquery()
    
    # 多数決で最も多い価格を選択
    majority_price_query = db.query(
        price_vote_query.c.master_property_id,
        price_vote_query.c.current_price.label('majority_price'),
        func.row_number().over(
            partition_by=price_vote_query.c.master_property_id,
            order_by=[price_vote_query.c.vote_count.desc(), price_vote_query.c.current_price.asc()]
        ).label('rn')
    ).subquery()
    
    price_query = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.max(majority_price_query.c.majority_price).label('majority_price'),  # 多数決価格
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites'),
        func.bool_or(PropertyListing.is_active).label('has_active_listing'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.max(PropertyListing.delisted_at).label('delisted_at'),
        func.max(PropertyListing.station_info).label('station_info'),
        func.min(func.coalesce(PropertyListing.first_published_at, PropertyListing.published_at, PropertyListing.first_seen_at)).label('earliest_published_at'),
        # 価格改定日（価格が変更されていない場合は情報提供日）
        func.coalesce(
            func.max(PropertyListing.price_updated_at),
            func.min(PropertyListing.published_at)
        ).label('latest_price_update'),
        # 価格変更があったかどうかのフラグ
        # 各掲載の価格履歴で異なる価格が2つ以上ある場合はTrue
        func.bool_or(
            db.query(func.count(distinct(ListingPriceHistory.price)))
            .filter(ListingPriceHistory.property_listing_id == PropertyListing.id)
            .scalar_subquery() > 1
        ).label('has_price_change')
    ).outerjoin(
        majority_price_query,
        and_(
            PropertyListing.master_property_id == majority_price_query.c.master_property_id,
            majority_price_query.c.rn == 1
        )
    )
    
    # include_inactiveがFalseの場合はアクティブな物件のみ
    if not include_inactive:
        price_query = price_query.filter(PropertyListing.is_active == True)
    
    price_subquery = price_query.group_by(
        PropertyListing.master_property_id,
        majority_price_query.c.majority_price
    ).subquery()
    
    # メインクエリ
    query = db.query(
        MasterProperty,
        Building,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,  # 多数決価格を追加
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
    
    # フィルター条件
    # include_inactiveがFalseの場合は販売終了物件を除外
    if not include_inactive:
        query = query.filter(MasterProperty.sold_at.is_(None))
        # また、アクティブな掲載がある物件のみに限定
        query = query.filter(price_subquery.c.master_property_id.isnot(None))
    else:
        # 販売終了物件を含める場合でも、掲載情報が一つもない物件は除外
        # （sold_atがNULLかつ掲載情報がない物件は無効なデータ）
        query = query.filter(
            or_(
                price_subquery.c.master_property_id.isnot(None),  # 掲載情報がある
                MasterProperty.sold_at.isnot(None)  # または販売終了済み
            )
        )
    
    if min_price:
        query = query.filter(
            or_(
                price_subquery.c.min_price >= min_price,
                and_(
                    price_subquery.c.min_price.is_(None),
                    MasterProperty.last_sale_price >= min_price
                )
            )
        )
    if max_price:
        query = query.filter(
            or_(
                price_subquery.c.max_price <= max_price,
                and_(
                    price_subquery.c.max_price.is_(None),
                    MasterProperty.last_sale_price <= max_price
                )
            )
        )
    if min_area:
        query = query.filter(MasterProperty.area >= min_area)
    if max_area:
        query = query.filter(MasterProperty.area <= max_area)
    if layouts:
        # 間取りリストでフィルター
        query = query.filter(MasterProperty.layout.in_(layouts))
    if building_name:
        # 検索文字列を正規化
        from backend.app.utils.search_normalizer import create_search_patterns
        from .models import BuildingMergeHistory
        search_patterns = create_search_patterns(building_name)
        
        # 統合履歴（エイリアス）から該当する建物IDを取得
        alias_building_ids = db.query(BuildingMergeHistory.primary_building_id).filter(
            or_(
                BuildingMergeHistory.merged_building_name.ilike(f"%{building_name}%"),
                BuildingMergeHistory.canonical_merged_name.ilike(f"%{building_name}%")
            )
        ).distinct().subquery()
        
        # 各パターンでOR検索
        search_conditions = []
        for pattern in search_patterns:
            search_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
            search_conditions.append(Building.reading.ilike(f"%{pattern}%"))
        
        # エイリアス経由のマッチも含める
        search_conditions.append(Building.id.in_(alias_building_ids))
        
        if search_conditions:
            query = query.filter(or_(*search_conditions))
    if max_building_age is not None:
        # 築年数でフィルター（現在の年から築年数を引いて最低築年を計算）
        from datetime import datetime
        current_year = datetime.now().year
        min_built_year = current_year - max_building_age
        query = query.filter(Building.built_year >= min_built_year)
    
    if wards:
        # 区名リストでフィルター（例: ["港区", "中央区"]）
        # 複数の区名でOR条件を構築
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.like(f"東京都{ward}%"))
        if ward_conditions:
            query = query.filter(or_(*ward_conditions))
    
    # 総件数を取得
    total_count = query.count()
    
    # ソート
    if sort_by == "price":
        # 販売終了物件の場合はlast_sale_priceを使用
        order_column = func.coalesce(price_subquery.c.min_price, MasterProperty.last_sale_price)
    elif sort_by == "area":
        order_column = MasterProperty.area
    elif sort_by == "built_year":
        order_column = Building.built_year
    else:  # updated_at の場合は価格改定日でソート
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
            "majority_price": majority_price if not mp.sold_at else mp.final_price,  # 多数決価格を追加
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

@app.get("/api/v2/properties/{property_id}", response_model=PropertyDetailSchema)
async def get_property_detail_v2(
    property_id: int,
    db: Session = Depends(get_db)
):
    """物件詳細を取得（全掲載情報を含む）"""
    
    # マスター物件を取得
    master_property = db.query(MasterProperty).options(
        joinedload(MasterProperty.building),
        joinedload(MasterProperty.listings)
    ).filter(
        MasterProperty.id == property_id
    ).first()
    
    if not master_property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # 全ての掲載情報を取得（削除済みも含む）
    all_listings = master_property.listings
    active_listings = [l for l in all_listings if l.is_active]
    
    # 多数決更新クラスをインポート
    from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
    updater = MajorityVoteUpdater(db)
    
    # 販売終了物件の場合は非アクティブも含める
    include_inactive = master_property.sold_at is not None
    info = updater.collect_property_info_from_listings(master_property, include_inactive)
    
    # 価格の集計（多数決で決定）
    majority_price = None
    if active_listings:
        # アクティブな掲載から価格を集計
        price_votes = {}
        for listing in active_listings:
            if listing.current_price:
                price_votes[listing.current_price] = price_votes.get(listing.current_price, 0) + 1
        
        # 最も多い価格を選択（同票の場合は安い方）
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
    # 全掲載の価格履歴を時系列で統合
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
    
    # 交通情報はすでに多数決で決定済み（上記で処理）
    
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
    
    return {
        "master_property": master_property_data,
        "listings": [ListingSchema.from_orm(l) for l in active_listings],
        "price_histories_by_listing": price_histories_by_listing,
        "price_timeline": price_timeline,
        "price_consistency": price_consistency,
        "unified_price_history": all_price_records,
        "price_discrepancies": price_discrepancies
    }

@app.get("/api/v2/properties-grouped-by-buildings", response_model=Dict[str, Any])
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
        terms = building_name.split()
        for term in terms:
            base_query = base_query.filter(Building.normalized_name.ilike(f"%{term}%"))
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

@app.get("/api/v2/buildings/by-name/{building_name}/properties", response_model=Dict[str, Any])
async def get_building_properties_by_name(
    building_name: str,
    include_inactive: bool = Query(False, description="販売終了物件も含む"),
    db: Session = Depends(get_db)
):
    """建物名で建物内の全物件を取得"""
    
    # URLデコード
    from urllib.parse import unquote
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
    
    # 建物内の物件を取得（価格情報付き - 多数決）
    # 価格の多数決を計算
    price_vote_query = db.query(
        PropertyListing.master_property_id,
        PropertyListing.current_price,
        func.count(PropertyListing.id).label('vote_count')
    ).filter(
        PropertyListing.is_active == True if not include_inactive else True,
        PropertyListing.current_price.isnot(None)
    ).group_by(
        PropertyListing.master_property_id,
        PropertyListing.current_price
    ).subquery()
    
    # 多数決で最も多い価格を選択
    majority_price_query = db.query(
        price_vote_query.c.master_property_id,
        price_vote_query.c.current_price.label('majority_price'),
        func.row_number().over(
            partition_by=price_vote_query.c.master_property_id,
            order_by=[price_vote_query.c.vote_count.desc(), price_vote_query.c.current_price.asc()]
        ).label('rn')
    ).subquery()
    
    price_query = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.max(majority_price_query.c.majority_price).label('majority_price'),  # 多数決価格
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites'),
        func.min(func.coalesce(PropertyListing.first_published_at, PropertyListing.published_at, PropertyListing.first_seen_at)).label('earliest_published_at')
    ).outerjoin(
        majority_price_query,
        and_(
            PropertyListing.master_property_id == majority_price_query.c.master_property_id,
            majority_price_query.c.rn == 1
        )
    )
    
    # include_inactiveがFalseの場合はアクティブな掲載のみ
    if not include_inactive:
        price_query = price_query.filter(PropertyListing.is_active == True)
    
    price_subquery = price_query.group_by(
        PropertyListing.master_property_id,
        majority_price_query.c.majority_price
    ).subquery()
    
    properties_query = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,  # 多数決価格を追加
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.earliest_published_at
    ).outerjoin(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    ).filter(
        MasterProperty.building_id == building.id
    )
    
    # include_inactiveがFalseの場合は販売終了物件を除外
    if not include_inactive:
        properties_query = properties_query.filter(MasterProperty.sold_at.is_(None))
        # アクティブな掲載がある物件のみ
        properties_query = properties_query.filter(price_subquery.c.master_property_id.isnot(None))
    else:
        # 販売終了物件を含める場合でも、掲載情報が一つもない物件は除外
        properties_query = properties_query.filter(
            or_(
                price_subquery.c.master_property_id.isnot(None),  # 掲載情報がある
                MasterProperty.sold_at.isnot(None)  # または販売終了済み
            )
        )
    
    properties = properties_query.order_by(
        price_subquery.c.earliest_published_at.desc().nullslast(),
        MasterProperty.floor_number.desc(),
        MasterProperty.room_number
    ).all()
    
    # 結果を整形
    property_list = []
    for mp, min_price, max_price, majority_price, listing_count, source_sites, earliest_published_at in properties:
        property_list.append({
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
        "building": BuildingSchema.from_orm(building),
        "properties": property_list,
        "total": len(property_list)
    }

@app.get("/api/v2/buildings/{building_id}/properties", response_model=Dict[str, Any])
async def get_building_properties_v2(
    building_id: int,
    db: Session = Depends(get_db)
):
    """建物内の全物件を取得"""
    
    # 建物を取得
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 建物内の物件を取得（価格情報付き - 多数決）
    # 価格の多数決を計算
    price_vote_query = db.query(
        PropertyListing.master_property_id,
        PropertyListing.current_price,
        func.count(PropertyListing.id).label('vote_count')
    ).filter(
        PropertyListing.is_active == True,
        PropertyListing.current_price.isnot(None)
    ).group_by(
        PropertyListing.master_property_id,
        PropertyListing.current_price
    ).subquery()
    
    # 多数決で最も多い価格を選択
    majority_price_query = db.query(
        price_vote_query.c.master_property_id,
        price_vote_query.c.current_price.label('majority_price'),
        func.row_number().over(
            partition_by=price_vote_query.c.master_property_id,
            order_by=[price_vote_query.c.vote_count.desc(), price_vote_query.c.current_price.asc()]
        ).label('rn')
    ).subquery()
    
    price_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.max(majority_price_query.c.majority_price).label('majority_price'),  # 多数決価格
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.min(func.coalesce(PropertyListing.first_published_at, PropertyListing.published_at, PropertyListing.first_seen_at)).label('earliest_published_at')
    ).outerjoin(
        majority_price_query,
        and_(
            PropertyListing.master_property_id == majority_price_query.c.master_property_id,
            majority_price_query.c.rn == 1
        )
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.master_property_id,
        majority_price_query.c.majority_price
    ).subquery()
    
    # ソースサイト情報を含むサブクエリ
    source_sites_subquery = db.query(
        PropertyListing.master_property_id,
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites')
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    properties = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,  # 多数決価格を追加
        price_subquery.c.listing_count,
        price_subquery.c.last_confirmed_at,
        price_subquery.c.earliest_published_at,  # 最も古い売出確認日
        source_sites_subquery.c.source_sites
    ).join(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    ).outerjoin(
        source_sites_subquery, MasterProperty.id == source_sites_subquery.c.master_property_id
    ).filter(
        MasterProperty.building_id == building_id
    ).order_by(
        MasterProperty.floor_number.desc(),
        MasterProperty.room_number
    ).all()
    
    # 結果を整形
    property_list = []
    for mp, min_price, max_price, majority_price, listing_count, last_confirmed_at, earliest_published_at, source_sites in properties:
        property_list.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "majority_price": majority_price,  # 多数決価格
            "min_price": majority_price or min_price,  # 互換性のため
            "max_price": majority_price or max_price,  # 互換性のため
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else [],
            "last_confirmed_at": last_confirmed_at.isoformat() if last_confirmed_at else None,
            "earliest_published_at": earliest_published_at.isoformat() if earliest_published_at else None
        })
    
    return {
        "building": BuildingSchema.from_orm(building),
        "properties": property_list,
        "total": len(property_list)
    }

from functools import lru_cache
from time import time

# 建物重複検出関連のエンドポイントはadmin.pyまたはadmin_buildings.pyに移動済み



# 建物除外関連のエンドポイントはadmin.pyに移動済み





@app.get("/api/v2/stats", response_model=Dict[str, Any])
async def get_stats_v2(db: Session = Depends(get_db)):
    """統計情報を取得"""
    
    stats = {
        "total_buildings": db.query(Building).count(),
        "total_properties": db.query(MasterProperty).count(),
        "total_listings": db.query(PropertyListing).filter(PropertyListing.is_active == True).count(),
        "total_price_records": db.query(ListingPriceHistory).count(),
    }
    
    # サイト別の掲載数
    by_source = db.query(
        PropertyListing.source_site,
        func.count(PropertyListing.id)
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.source_site
    ).all()
    
    stats["by_source"] = {source: count for source, count in by_source}
    
    # 価格帯別の物件数
    price_ranges = [
        (0, 3000, "3000万円未満"),
        (3000, 5000, "3000-5000万円"),
        (5000, 8000, "5000-8000万円"),
        (8000, 10000, "8000万-1億円"),
        (10000, None, "1億円以上")
    ]
    
    by_price = {}
    for min_p, max_p, label in price_ranges:
        subquery = db.query(
            PropertyListing.master_property_id,
            func.min(PropertyListing.current_price).label('min_price')
        ).filter(
            PropertyListing.is_active == True
        ).group_by(
            PropertyListing.master_property_id
        ).subquery()
        
        query = db.query(func.count(distinct(subquery.c.master_property_id)))
        
        if min_p is not None:
            query = query.filter(subquery.c.min_price >= min_p)
        if max_p is not None:
            query = query.filter(subquery.c.min_price < max_p)
        
        count = query.scalar() or 0
        by_price[label] = count
    
    stats["by_price_range"] = by_price
    
    # 最終更新日時
    latest = db.query(func.max(PropertyListing.last_scraped_at)).scalar()
    stats["last_updated"] = str(latest) if latest else None
    
    return stats

@app.get("/api/v2/buildings/suggest")
async def suggest_buildings(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(10, ge=1, le=50, description="最大候補数"),
    db: Session = Depends(get_db)
):
    """建物名のサジェスト（インクリメンタルサーチ）- エイリアス対応版"""
    from typing import Dict, List, Union
    
    if len(q) < 1:
        return []
    
    # 結果を格納する辞書（building_id -> 情報）
    building_info: Dict[int, Dict[str, Union[str, List[str]]]] = {}
    
    # 1. 建物名で直接検索
    direct_matches = db.query(Building).filter(
        Building.normalized_name.ilike(f"%{q}%")
    ).all()
    
    for building in direct_matches:
        building_info[building.id] = {
            "name": building.normalized_name,
            "matched_by": "name"
        }
    
    # 2. 読み仮名で検索
    reading_matches = db.query(Building).filter(
        Building.reading.ilike(f"%{q}%")
    ).all()
    
    for building in reading_matches:
        if building.id not in building_info:
            building_info[building.id] = {
                "name": building.normalized_name,
                "matched_by": "reading"
            }
    
    # 3. 統合履歴（エイリアス）から検索
    alias_matches = db.query(
        BuildingMergeHistory.primary_building_id,
        BuildingMergeHistory.merged_building_name
    ).filter(
        or_(
            BuildingMergeHistory.merged_building_name.ilike(f"%{q}%"),
            BuildingMergeHistory.canonical_merged_name.ilike(f"%{q}%")
        )
    ).distinct().all()
    
    # エイリアスでマッチした建物の情報を取得
    for alias_match in alias_matches:
        building = db.query(Building).filter(
            Building.id == alias_match.primary_building_id
        ).first()
        
        if building:
            if building.id not in building_info:
                building_info[building.id] = {
                    "name": building.normalized_name,
                    "matched_by": "alias",
                    "alias": alias_match.merged_building_name
                }
            elif building_info[building.id].get("matched_by") != "name":
                # 既に他の方法でマッチしていて、かつ名前マッチではない場合はエイリアス情報を追加
                building_info[building.id]["alias"] = alias_match.merged_building_name
    
    # 結果をリスト形式に変換
    results = []
    for building_id, info in building_info.items():
        result_item = {
            "value": info["name"],
            "label": info["name"]
        }
        
        # エイリアスでマッチした場合はラベルに表示
        if info.get("matched_by") == "alias" and info.get("alias"):
            result_item["label"] = f"{info['name']} (旧: {info['alias']})"
        elif info.get("alias"):
            result_item["label"] = f"{info['name']} (別名: {info['alias']})"
        
        results.append(result_item)
    
    # 前方一致を優先的に並べる
    def sort_key(item):
        name = item["value"]
        if name.lower().startswith(q.lower()):
            return (0, name)  # 前方一致は優先
        return (1, name)  # その他
    
    results.sort(key=sort_key)
    
    # レガシー対応: 文字列のリストも返せるようにする
    # フロントエンドが新しい形式に対応するまでの暫定措置
    if limit <= 10:  # デフォルトの呼び出しの場合は新形式
        return results[:limit]
    else:  # 明示的に大きな limit が指定された場合は旧形式
        return [r["value"] for r in results[:limit]]

# 互換性のための旧APIエンドポイント（リダイレクト）
@app.get("/api/properties")
async def get_properties_legacy():
    """旧APIエンドポイント（v2にリダイレクト）"""
    return {"message": "このエンドポイントは非推奨です。/api/v2/properties を使用してください。"}