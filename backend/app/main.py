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
from sqlalchemy import func, or_, and_, distinct
from difflib import SequenceMatcher
import os
import re

from backend.app.database import get_db, init_db
from backend.app.models import (
    Building, BuildingAlias, MasterProperty, PropertyListing, 
    ListingPriceHistory, PropertyImage, BuildingExternalId,
    BuildingMergeExclusion, BuildingMergeHistory
)
from backend.app.api.price_analysis import (
    create_unified_price_timeline,
    analyze_source_price_consistency
)
from backend.app.api import admin

app = FastAPI(title="不動産横断検索API v2", version="2.0.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydanticモデル
class BuildingSchema(BaseModel):
    id: int
    normalized_name: str
    address: Optional[str]
    total_floors: Optional[int]
    basement_floors: Optional[int]
    total_units: Optional[int]
    built_year: Optional[int]
    structure: Optional[str]
    land_rights: Optional[str]
    parking_info: Optional[str]
    
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
    summary_remarks: Optional[str]
    is_resale: bool
    resale_property_id: Optional[int]
    min_price: Optional[int]
    max_price: Optional[int]
    listing_count: int
    source_sites: List[str]
    station_info: Optional[str]
    earliest_published_at: Optional[datetime]  # 最も古い情報提供日
    
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

@app.get("/")
async def root():
    return {"message": "不動産横断検索API v2", "version": "2.0.0"}

@app.get("/api/v2/properties", response_model=Dict[str, Any])
async def get_properties_v2(
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    min_area: Optional[float] = Query(None, description="最低面積（㎡）"),
    max_area: Optional[float] = Query(None, description="最高面積（㎡）"),
    layout: Optional[str] = Query(None, description="間取り"),
    building_name: Optional[str] = Query(None, description="建物名"),
    max_building_age: Optional[int] = Query(None, description="築年数以内"),
    include_inactive: bool = Query(False, description="削除済み物件も含む"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    sort_by: str = Query("updated_at", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """物件一覧を取得（重複排除済み）"""
    
    # サブクエリ：各マスター物件の最新価格を取得
    price_query = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(PropertyListing.source_site), ',').label('source_sites'),
        func.bool_or(PropertyListing.is_active).label('has_active_listing'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.max(PropertyListing.delisted_at).label('delisted_at'),
        func.max(PropertyListing.station_info).label('station_info'),
        func.min(func.coalesce(PropertyListing.first_published_at, PropertyListing.published_at, PropertyListing.first_seen_at)).label('earliest_published_at'),
        # 価格改定日（価格が変更されていない場合は情報提供日）
        func.coalesce(
            func.max(PropertyListing.price_updated_at),
            func.min(PropertyListing.published_at)
        ).label('latest_price_update')
    )
    
    # include_inactiveがFalseの場合はアクティブな物件のみ
    if not include_inactive:
        price_query = price_query.filter(PropertyListing.is_active == True)
    
    price_subquery = price_query.group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    # メインクエリ
    query = db.query(
        MasterProperty,
        Building,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.has_active_listing,
        price_subquery.c.last_confirmed_at,
        price_subquery.c.delisted_at,
        price_subquery.c.station_info,
        price_subquery.c.earliest_published_at,
        price_subquery.c.latest_price_update
    ).join(
        Building, MasterProperty.building_id == Building.id
    ).join(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    )
    
    # フィルター条件
    if min_price:
        query = query.filter(price_subquery.c.min_price >= min_price)
    if max_price:
        query = query.filter(price_subquery.c.max_price <= max_price)
    if min_area:
        query = query.filter(MasterProperty.area >= min_area)
    if max_area:
        query = query.filter(MasterProperty.area <= max_area)
    if layout:
        query = query.filter(MasterProperty.layout == layout)
    if building_name:
        # 建物名、読み仮名、または建物エイリアスで部分一致検索
        alias_subquery = db.query(BuildingAlias.building_id).filter(
            BuildingAlias.alias_name.ilike(f"%{building_name}%")
        )
        query = query.filter(
            or_(
                Building.normalized_name.ilike(f"%{building_name}%"),
                Building.reading.ilike(f"%{building_name}%"),
                Building.id.in_(alias_subquery)
            )
        )
    if max_building_age is not None:
        # 築年数でフィルター（現在の年から築年数を引いて最低築年を計算）
        from datetime import datetime
        current_year = datetime.now().year
        min_built_year = current_year - max_building_age
        query = query.filter(Building.built_year >= min_built_year)
    
    # 総件数を取得
    total_count = query.count()
    
    # ソート
    if sort_by == "price":
        order_column = price_subquery.c.min_price
    elif sort_by == "area":
        order_column = MasterProperty.area
    elif sort_by == "built_year":
        order_column = Building.built_year
    else:  # updated_at の場合は価格改定日でソート
        order_column = price_subquery.c.latest_price_update
    
    if sort_order == "asc":
        query = query.order_by(order_column.asc())
    else:
        query = query.order_by(order_column.desc())
    
    # ページネーション
    offset = (page - 1) * per_page
    results = query.offset(offset).limit(per_page).all()
    
    # 結果を整形
    properties = []
    for mp, building, min_price, max_price, listing_count, source_sites, has_active, last_confirmed, delisted, station_info, earliest_published_at, latest_price_update in results:
        properties.append({
            "id": mp.id,
            "building": {
                "id": building.id,
                "normalized_name": building.normalized_name,
                "address": building.address,
                "total_floors": building.total_floors,
                "basement_floors": building.basement_floors,
                "total_units": building.total_units,
                "built_year": building.built_year,
                "structure": building.structure,
                "land_rights": building.land_rights,
                "parking_info": building.parking_info
            },
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "summary_remarks": mp.summary_remarks,
            "is_resale": mp.is_resale,
            "resale_property_id": mp.resale_property_id,
            "min_price": min_price,
            "max_price": max_price,
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else [],
            "has_active_listing": has_active,
            "last_confirmed_at": str(last_confirmed) if last_confirmed else None,
            "delisted_at": str(delisted) if delisted else None,
            "station_info": station_info,
            "earliest_published_at": earliest_published_at,
            "latest_price_update": str(latest_price_update) if latest_price_update else None
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
    
    # 価格の集計
    prices = [l.current_price for l in active_listings if l.current_price]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    
    # ソースサイトのリスト
    source_sites = list(set(l.source_site for l in active_listings))
    
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
    
    # 最初のアクティブな掲載から交通情報を取得
    station_info = None
    for listing in active_listings:
        if listing.station_info:
            station_info = listing.station_info
            print(f"DEBUG: Found station_info: {station_info}")  # デバッグ用
            break
    
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
        "summary_remarks": master_property.summary_remarks,
        "is_resale": master_property.is_resale,
        "resale_property_id": master_property.resale_property_id,
        "min_price": min_price,
        "max_price": max_price,
        "listing_count": len(active_listings),
        "source_sites": source_sites,
        "station_info": station_info,
        "earliest_published_at": earliest_published_at
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

@app.get("/api/v2/buildings/by-name/{building_name}/properties", response_model=Dict[str, Any])
async def get_building_properties_by_name(
    building_name: str,
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
    
    # 建物内の物件を取得（価格情報付き）
    price_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(PropertyListing.source_site), ',').label('source_sites'),
        func.min(func.coalesce(PropertyListing.first_published_at, PropertyListing.published_at, PropertyListing.first_seen_at)).label('earliest_published_at')
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    properties = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.earliest_published_at
    ).join(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    ).filter(
        MasterProperty.building_id == building.id
    ).order_by(
        price_subquery.c.earliest_published_at.desc().nullslast(),
        MasterProperty.floor_number.desc(),
        MasterProperty.room_number
    ).all()
    
    # 結果を整形
    property_list = []
    for mp, min_price, max_price, listing_count, source_sites, earliest_published_at in properties:
        property_list.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "summary_remarks": mp.summary_remarks,
            "is_resale": mp.is_resale,
            "resale_property_id": mp.resale_property_id,
            "min_price": min_price,
            "max_price": max_price,
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else [],
            "earliest_published_at": earliest_published_at.isoformat() if earliest_published_at else None
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
    
    # 建物内の物件を取得（価格情報付き）
    price_subquery = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.count(distinct(PropertyListing.id)).label('listing_count')
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    # ソースサイト情報を含むサブクエリ
    source_sites_subquery = db.query(
        PropertyListing.master_property_id,
        func.string_agg(distinct(PropertyListing.source_site), ',').label('source_sites')
    ).filter(
        PropertyListing.is_active == True
    ).group_by(
        PropertyListing.master_property_id
    ).subquery()
    
    properties = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.listing_count,
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
    for mp, min_price, max_price, listing_count, source_sites in properties:
        property_list.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "summary_remarks": mp.summary_remarks,
            "is_resale": mp.is_resale,
            "resale_property_id": mp.resale_property_id,
            "min_price": min_price,
            "max_price": max_price,
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else []
        })
    
    return {
        "building": BuildingSchema.from_orm(building),
        "properties": property_list,
        "total": len(property_list)
    }

@app.get("/api/admin/duplicate-buildings", response_model=Dict[str, Any])
async def get_duplicate_buildings(
    min_similarity: float = Query(0.95, description="最小類似度"),
    limit: int = Query(50, description="最大グループ数"),
    search: Optional[str] = Query(None, description="建物名検索"),
    db: Session = Depends(get_db)
):
    """重複の可能性がある建物を検出"""
    from backend.app.utils.building_normalizer import BuildingNameNormalizer
    
    normalizer = BuildingNameNormalizer()
    
    # クエリを構築
    query = db.query(
        Building,
        func.count(MasterProperty.id).label('property_count')
    ).outerjoin(
        MasterProperty, Building.id == MasterProperty.building_id
    ).group_by(
        Building.id
    ).having(
        func.count(MasterProperty.id) > 0  # 物件がある建物のみ
    )
    
    # 検索フィルタを適用
    if search:
        # 中点（・）を除去した検索も行う
        search_normalized = search.replace('・', '')
        query = query.filter(
            or_(
                Building.normalized_name.ilike(f"%{search}%"),
                Building.normalized_name.ilike(f"%{search_normalized}%")
            )
        )
    
    # 検索が指定されている場合は少なめに、そうでない場合は多めに取得
    fetch_limit = 100 if search else 300
    buildings_with_count = query.order_by(
        Building.normalized_name
    ).limit(fetch_limit).all()
    
    # 除外ペアを取得
    exclusions = db.query(BuildingMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        # 両方向の組み合わせを除外
        excluded_pairs.add((exclusion.building1_id, exclusion.building2_id))
        excluded_pairs.add((exclusion.building2_id, exclusion.building1_id))
    
    # 事前に全ての建物名を正規化（キャッシュ）
    normalized_names = {}
    for building, _ in buildings_with_count:
        normalized_names[building.id] = normalizer.normalize(building.normalized_name)
    
    # 重複候補を検出
    duplicates = []
    processed_ids = set()
    total_comparisons = 0
    
    for i, (building1, count1) in enumerate(buildings_with_count):
        if building1.id in processed_ids:
            continue
            
        candidates = []
        norm_name1 = normalized_names[building1.id]
        
        for j, (building2, count2) in enumerate(buildings_with_count[i+1:], i+1):
            if building2.id in processed_ids:
                continue
            
            # 除外リストに含まれていたらスキップ
            if (building1.id, building2.id) in excluded_pairs:
                continue
                
            # 同じ住所の場合は重複候補に含める（表記ゆれの可能性）
            # if building1.address and building2.address and building1.address == building2.address:
            #     continue
                
            # 簡易チェック：建物名の長さが大きく異なる場合はスキップ
            if abs(len(building1.normalized_name) - len(building2.normalized_name)) > 10:
                continue
                
            norm_name2 = normalized_names[building2.id]
            
            # 簡易チェック：最初の3文字が全く異なる場合はスキップ
            if len(norm_name1) >= 3 and len(norm_name2) >= 3:
                if norm_name1[:3] != norm_name2[:3]:
                    continue
            
            # 住所の類似度をチェック
            addr_similarity = 0.0
            if building1.address and building2.address:
                # 住所の正規化（空白、全角半角を統一）
                addr1 = re.sub(r'[\s　]+', '', building1.address)
                addr2 = re.sub(r'[\s　]+', '', building2.address)
                addr_similarity = SequenceMatcher(None, addr1, addr2).ratio()
                
                # 住所が大きく異なる場合はスキップ（番地レベルの違いは許容）
                if addr_similarity < 0.7:
                    continue
            
            # 総階数のチェック
            floors_match = True
            if building1.total_floors and building2.total_floors:
                # 総階数が2階以上異なる場合は別建物の可能性が高い
                if abs(building1.total_floors - building2.total_floors) > 2:
                    floors_match = False
            
            # 建物名の類似度
            total_comparisons += 1
            name_similarity = normalizer.calculate_similarity(building1.normalized_name, building2.normalized_name)
            
            # 総合的な判定
            # 1. 名前が完全一致 → 同一建物
            # 2. 名前の類似度が高く、住所も一致 → 同一建物
            # 3. 名前の類似度が中程度でも、住所が完全一致し階数も一致 → 同一建物
            is_duplicate = False
            
            if norm_name1 == norm_name2:
                is_duplicate = True
            elif name_similarity >= min_similarity and addr_similarity >= 0.8:
                is_duplicate = True
            elif name_similarity >= 0.8 and addr_similarity >= 0.95 and floors_match:
                is_duplicate = True
            
            if is_duplicate:
                candidates.append({
                    "id": building2.id,
                    "normalized_name": building2.normalized_name,
                    "address": building2.address,
                    "total_floors": building2.total_floors,
                    "property_count": count2,
                    "similarity": name_similarity,
                    "address_similarity": addr_similarity,
                    "floors_match": floors_match
                })
                processed_ids.add(building2.id)
        
        if candidates:
            duplicates.append({
                "primary": {
                    "id": building1.id,
                    "normalized_name": building1.normalized_name,
                    "address": building1.address,
                    "total_floors": building1.total_floors,
                    "property_count": count1
                },
                "candidates": candidates
            })
            processed_ids.add(building1.id)
            
            # 制限に達したら終了
            if len(duplicates) >= limit:
                break
    
    print(f"[DEBUG] Total buildings: {len(buildings_with_count)}, Total comparisons: {total_comparisons}")
    
    return {
        "duplicate_groups": duplicates,
        "total_groups": len(duplicates),
        "total_buildings_checked": len(buildings_with_count),
        "total_comparisons": total_comparisons
    }


@app.get("/api/admin/buildings/search", response_model=Dict[str, Any])
async def search_buildings_for_merge(
    query: str = Query(..., description="建物名または建物IDで検索"),
    limit: int = Query(20, description="最大結果数"),
    db: Session = Depends(get_db)
):
    """建物をIDまたは名前で検索（統合用）"""
    results = []
    
    # まずIDで検索を試みる
    if query.isdigit():
        building_id = int(query)
        building = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).filter(
            Building.id == building_id
        ).group_by(
            Building.id
        ).first()
        
        if building:
            results.append({
                "id": building[0].id,
                "normalized_name": building[0].normalized_name,
                "address": building[0].address,
                "total_floors": building[0].total_floors,
                "property_count": building[1]
            })
    
    # 名前で検索
    name_results = db.query(
        Building,
        func.count(MasterProperty.id).label('property_count')
    ).outerjoin(
        MasterProperty, Building.id == MasterProperty.building_id
    ).filter(
        Building.normalized_name.ilike(f"%{query}%")
    ).group_by(
        Building.id
    ).order_by(
        Building.normalized_name
    ).limit(limit).all()
    
    for building, count in name_results:
        # 既にIDで見つかった建物は除外
        if not any(r["id"] == building.id for r in results):
            results.append({
                "id": building.id,
                "normalized_name": building.normalized_name,
                "address": building.address,
                "total_floors": building.total_floors,
                "property_count": count
            })
    
    return {
        "buildings": results,
        "total": len(results)
    }


from pydantic import BaseModel

class MergeBuildingsRequest(BaseModel):
    primary_id: int
    secondary_ids: List[int]

@app.post("/api/admin/merge-buildings", response_model=Dict[str, Any])
async def merge_buildings(
    request: MergeBuildingsRequest,
    db: Session = Depends(get_db)
):
    """複数の建物を統合"""
    primary_id = request.primary_id
    secondary_ids = request.secondary_ids
    
    # 主建物を取得
    primary = db.query(Building).filter(Building.id == primary_id).first()
    if not primary:
        raise HTTPException(status_code=404, detail="主建物が見つかりません")
    
    # 副建物を取得
    secondaries = db.query(Building).filter(Building.id.in_(secondary_ids)).all()
    if len(secondaries) != len(secondary_ids):
        raise HTTPException(status_code=404, detail="一部の建物が見つかりません")
    
    merged_count = 0
    moved_properties = 0
    merge_details = {
        "merged_buildings": [],
        "aliases_added": [],
        "aliases_moved": 0,
        "external_ids_moved": 0
    }
    
    try:
        for secondary in secondaries:
            building_detail = {
                "id": secondary.id,
                "normalized_name": secondary.normalized_name,
                "address": secondary.address,
                "total_floors": secondary.total_floors,
                "built_year": secondary.built_year,
                "structure": secondary.structure,
                "properties_moved": 0
            }
            
            # エイリアスを追加
            if secondary.normalized_name != primary.normalized_name:
                # 既存のエイリアスをチェック
                existing = db.query(BuildingAlias).filter(
                    BuildingAlias.building_id == primary_id,
                    BuildingAlias.alias_name == secondary.normalized_name
                ).first()
                
                if not existing:
                    alias = BuildingAlias(
                        building_id=primary_id,
                        alias_name=secondary.normalized_name,
                        source='MERGE'
                    )
                    db.add(alias)
                    merge_details["aliases_added"].append(secondary.normalized_name)
            
            # 副建物のエイリアスを移動
            alias_count = db.query(BuildingAlias).filter(
                BuildingAlias.building_id == secondary.id
            ).update({"building_id": primary_id})
            merge_details["aliases_moved"] += alias_count
            
            # 物件を移動
            count = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary.id
            ).update({"building_id": primary_id})
            moved_properties += count
            building_detail["properties_moved"] = count
            
            # 外部IDを移動
            ext_id_count = db.query(BuildingExternalId).filter(
                BuildingExternalId.building_id == secondary.id
            ).update({"building_id": primary_id})
            merge_details["external_ids_moved"] += ext_id_count
            
            # 建物情報を統合（より詳細な情報で上書き）
            if secondary.total_floors and not primary.total_floors:
                primary.total_floors = secondary.total_floors
            if secondary.built_year and not primary.built_year:
                primary.built_year = secondary.built_year
            if secondary.structure and not primary.structure:
                primary.structure = secondary.structure
            if secondary.address and not primary.address:
                primary.address = secondary.address
            
            merge_details["merged_buildings"].append(building_detail)
            
            # 副建物を削除
            db.delete(secondary)
            merged_count += 1
        
        # 統合履歴を記録
        history = BuildingMergeHistory(
            primary_building_id=primary_id,
            merged_building_ids=secondary_ids,
            moved_properties=moved_properties,
            merge_details=merge_details
        )
        db.add(history)
        
        db.commit()
        
        return {
            "success": True,
            "merged_count": merged_count,
            "moved_properties": moved_properties,
            "primary_building": {
                "id": primary.id,
                "normalized_name": primary.normalized_name,
                "address": primary.address,
                "total_floors": primary.total_floors
            }
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERROR] Building merge failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"統合中にエラーが発生しました: {str(e)}")


class ExcludeBuildingsRequest(BaseModel):
    building1_id: int
    building2_id: int
    reason: Optional[str] = None

@app.post("/api/admin/exclude-buildings", response_model=Dict[str, Any])
async def exclude_buildings(
    request: ExcludeBuildingsRequest,
    db: Session = Depends(get_db)
):
    """建物ペアを統合候補から除外"""
    building1_id = request.building1_id
    building2_id = request.building2_id
    reason = request.reason
    
    # 既に除外されているかチェック
    existing = db.query(BuildingMergeExclusion).filter(
        or_(
            and_(
                BuildingMergeExclusion.building1_id == building1_id,
                BuildingMergeExclusion.building2_id == building2_id
            ),
            and_(
                BuildingMergeExclusion.building1_id == building2_id,
                BuildingMergeExclusion.building2_id == building1_id
            )
        )
    ).first()
    
    if existing:
        return {"success": False, "message": "既に除外済みです"}
    
    # 小さいIDを building1_id として保存（一貫性のため）
    if building1_id > building2_id:
        building1_id, building2_id = building2_id, building1_id
    
    exclusion = BuildingMergeExclusion(
        building1_id=building1_id,
        building2_id=building2_id,
        reason=reason
    )
    db.add(exclusion)
    db.commit()
    
    return {"success": True, "exclusion_id": exclusion.id}


@app.delete("/api/admin/exclude-buildings/{exclusion_id}", response_model=Dict[str, Any])
async def remove_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db)
):
    """除外を取り消す"""
    exclusion = db.query(BuildingMergeExclusion).filter(
        BuildingMergeExclusion.id == exclusion_id
    ).first()
    
    if not exclusion:
        raise HTTPException(status_code=404, detail="除外記録が見つかりません")
    
    db.delete(exclusion)
    db.commit()
    
    return {"success": True}


@app.get("/api/admin/merge-history", response_model=Dict[str, Any])
async def get_merge_history(
    limit: int = Query(50, description="取得件数"),
    include_reverted: bool = Query(False, description="取り消し済みも含む"),
    db: Session = Depends(get_db)
):
    """統合履歴を取得"""
    query = db.query(BuildingMergeHistory).options(
        joinedload(BuildingMergeHistory.primary_building)
    )
    
    if not include_reverted:
        query = query.filter(BuildingMergeHistory.reverted_at.is_(None))
    
    histories = query.order_by(
        BuildingMergeHistory.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for history in histories:
        # 統合元の建物情報を取得
        merged_buildings_info = []
        if history.merge_details and "merged_buildings" in history.merge_details:
            # merge_detailsに建物情報が保存されている場合（新しい統合）
            merged_buildings_info = history.merge_details["merged_buildings"]
        else:
            # merge_detailsに建物情報がない場合（古い統合）、IDから建物名を取得
            for building_id in history.merged_building_ids:
                building = db.query(Building).filter(Building.id == building_id).first()
                if building:
                    merged_buildings_info.append({
                        "id": building.id,
                        "normalized_name": building.normalized_name,
                        "properties_moved": None  # 古い統合では物件数の詳細は不明
                    })
                else:
                    # 建物が削除されている場合
                    merged_buildings_info.append({
                        "id": building_id,
                        "normalized_name": f"削除済み建物 (ID: {building_id})",
                        "properties_moved": None
                    })
        
        result.append({
            "id": history.id,
            "primary_building": {
                "id": history.primary_building.id,
                "normalized_name": history.primary_building.normalized_name
            },
            "merged_building_ids": history.merged_building_ids,
            "merged_buildings": merged_buildings_info,
            "moved_properties": history.moved_properties,
            "merge_details": history.merge_details,
            "created_at": history.created_at,
            "reverted_at": history.reverted_at,
            "reverted_by": history.reverted_by
        })
    
    return {"histories": result, "total": len(result)}


@app.post("/api/admin/revert-merge/{history_id}", response_model=Dict[str, Any])
async def revert_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """統合を取り消す（建物を復元）"""
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    if history.reverted_at:
        raise HTTPException(status_code=400, detail="既に取り消し済みです")
    
    try:
        # 主建物の存在確認
        primary_building = db.query(Building).filter(
            Building.id == history.primary_building_id
        ).first()
        
        if not primary_building:
            raise HTTPException(status_code=404, detail="主建物が見つかりません")
        
        # 統合時の詳細情報から建物を復元
        restored_count = 0
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            
            # 既に存在するかチェック
            existing = db.query(Building).filter(Building.id == building_id).first()
            if existing:
                print(f"[WARNING] Building {building_id} already exists, skipping restoration")
                continue
            
            # 建物を復元（読み仮名も生成）
            from backend.app.utils.reading_generator import generate_reading
            building = Building(
                id=building_id,
                normalized_name=merged_building["normalized_name"],
                address=merged_building.get("address"),
                reading=generate_reading(merged_building["normalized_name"]),
                total_floors=merged_building.get("total_floors"),
                built_year=merged_building.get("built_year"),
                structure=merged_building.get("structure")
            )
            db.add(building)
            
            # この建物に移動された物件を元に戻す
            properties_moved = merged_building.get("properties_moved", 0)
            if properties_moved > 0:
                # 物件を元の建物に戻す
                # 統合時にこの建物から移動した物件を特定して戻す
                db.query(MasterProperty).filter(
                    MasterProperty.building_id == history.primary_building_id
                ).limit(properties_moved).update(
                    {"building_id": building_id}
                )
            
            # エイリアスを復元（統合時に作成されたMERGEソースのエイリアスを削除）
            db.query(BuildingAlias).filter(
                BuildingAlias.building_id == history.primary_building_id,
                BuildingAlias.alias_name == merged_building["normalized_name"],
                BuildingAlias.source == 'MERGE'
            ).delete()
            
            restored_count += 1
        
        # 統合時に作成された可能性のある除外ペアを削除
        # 主建物と統合された建物間の除外ペアを削除
        merged_building_ids = [b["id"] for b in history.merge_details.get("merged_buildings", [])]
        for building_id in merged_building_ids:
            # 両方向の除外ペアを削除
            db.query(BuildingMergeExclusion).filter(
                or_(
                    and_(
                        BuildingMergeExclusion.building1_id == history.primary_building_id,
                        BuildingMergeExclusion.building2_id == building_id
                    ),
                    and_(
                        BuildingMergeExclusion.building1_id == building_id,
                        BuildingMergeExclusion.building2_id == history.primary_building_id
                    )
                )
            ).delete()
        
        # 履歴を更新
        history.reverted_at = datetime.now()
        history.reverted_by = "admin"  # TODO: 実際のユーザー名を記録
        
        db.commit()
        
        print(f"[INFO] Merge revert completed: restored {restored_count} buildings")
        
        return {
            "success": True, 
            "message": f"統合を取り消しました。{restored_count}件の建物を復元しました。",
            "restored_count": restored_count
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERROR] Merge revert failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"取り消し中にエラーが発生しました: {str(e)}")


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

@app.get("/api/v2/buildings/suggest", response_model=List[str])
async def suggest_buildings(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(10, ge=1, le=50, description="最大候補数"),
    db: Session = Depends(get_db)
):
    """建物名のサジェスト（インクリメンタルサーチ）"""
    
    if len(q) < 1:
        return []
    
    # エイリアスから建物を検索し、正規化された名前のみを返す
    # まず建物名で直接検索
    direct_matches = db.query(Building).filter(
        Building.normalized_name.ilike(f"%{q}%")
    ).all()
    
    # 読み仮名で検索
    reading_matches = db.query(Building).filter(
        Building.reading.ilike(f"%{q}%")
    ).all()
    
    # エイリアスから建物を検索
    alias_matches = db.query(Building).join(
        BuildingAlias, Building.id == BuildingAlias.building_id
    ).filter(
        BuildingAlias.alias_name.ilike(f"%{q}%")
    ).distinct().all()
    
    # 結果を結合して重複を除去
    all_buildings = {}
    for building in direct_matches + reading_matches + alias_matches:
        all_buildings[building.id] = building.normalized_name
    
    # ユニークな建物名のリスト
    unique_names = sorted(set(all_buildings.values()))
    
    # 前方一致を優先的に並べる
    prefix_matches = [name for name in unique_names if name.lower().startswith(q.lower())]
    other_matches = [name for name in unique_names if not name.lower().startswith(q.lower())]
    
    result = prefix_matches + other_matches
    
    return result[:limit]

# 互換性のための旧APIエンドポイント（リダイレクト）
@app.get("/api/properties")
async def get_properties_legacy():
    """旧APIエンドポイント（v2にリダイレクト）"""
    return {"message": "このエンドポイントは非推奨です。/api/v2/properties を使用してください。"}