"""
管理者用物件管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, Integer, cast, String
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database import get_db
from ..models import MasterProperty, Building, PropertyListing, ListingPriceHistory
from ..auth import verify_admin_credentials

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/properties")
async def get_properties(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    building_name: Optional[str] = None,
    address: Optional[str] = None,
    room_number: Optional[str] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    layouts: Optional[str] = None,  # カンマ区切りで複数の間取り
    directions: Optional[str] = None,  # カンマ区切りで複数の方角
    has_active_listings: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """物件一覧を取得（管理者用）"""
    query = db.query(MasterProperty).join(Building)
    
    # フィルタリング
    if building_name:
        # 統合履歴からエイリアスも検索
        from ..models import BuildingMergeHistory
        
        # まず統合履歴から該当する建物IDを取得
        alias_building_ids = db.query(BuildingMergeHistory.primary_building_id).filter(
            or_(
                BuildingMergeHistory.merged_building_name.ilike(f"%{building_name}%"),
                BuildingMergeHistory.canonical_merged_name.ilike(f"%{building_name}%")
            )
        ).distinct().subquery()
        
        # 通常の建物名検索とエイリアス検索を組み合わせる
        query = query.filter(or_(
            Building.normalized_name.ilike(f"%{building_name}%"),
            MasterProperty.display_building_name.ilike(f"%{building_name}%"),
            Building.id.in_(alias_building_ids)  # エイリアス経由での検索
        ))
    
    if address:
        query = query.filter(Building.address.ilike(f"%{address}%"))
    
    if room_number:
        query = query.filter(MasterProperty.room_number.ilike(f"%{room_number}%"))
    
    if min_area is not None:
        query = query.filter(MasterProperty.area >= min_area)
    
    if max_area is not None:
        query = query.filter(MasterProperty.area <= max_area)
    
    if layouts:
        # カンマ区切りの間取りリストを処理
        layout_list = [l.strip() for l in layouts.split(',')]
        query = query.filter(MasterProperty.layout.in_(layout_list))
    
    if directions:
        # カンマ区切りの方角リストを処理
        direction_list = [d.strip() for d in directions.split(',')]
        query = query.filter(MasterProperty.direction.in_(direction_list))
    
    # 掲載状態でフィルタ
    if has_active_listings is not None:
        active_listing_subquery = db.query(PropertyListing.master_property_id).filter(
            PropertyListing.is_active == True
        ).subquery()
        
        if has_active_listings:
            query = query.filter(MasterProperty.id.in_(active_listing_subquery))
        else:
            query = query.filter(~MasterProperty.id.in_(active_listing_subquery))
    
    # 総件数を取得
    total = query.count()
    
    # ページネーション
    properties = query.options(
        joinedload(MasterProperty.building)
    ).offset(offset).limit(limit).all()
    
    # 各物件の掲載情報サマリーを取得
    property_ids = [p.id for p in properties]
    
    # 掲載情報の集計
    listing_stats = db.query(
        PropertyListing.master_property_id,
        func.count(PropertyListing.id).label('total_count'),
        func.sum(func.cast(PropertyListing.is_active, Integer)).label('active_count'),
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price')
    ).filter(
        PropertyListing.master_property_id.in_(property_ids)
    ).group_by(PropertyListing.master_property_id).all()
    
    # ソース情報を別途取得
    source_stats = db.query(
        PropertyListing.master_property_id,
        PropertyListing.source_site
    ).filter(
        PropertyListing.master_property_id.in_(property_ids)
    ).distinct().all()
    
    # ソース情報をグループ化
    sources_dict = {}
    for stat in source_stats:
        if stat.master_property_id not in sources_dict:
            sources_dict[stat.master_property_id] = []
        sources_dict[stat.master_property_id].append(stat.source_site)
    
    stats_dict = {
        stat.master_property_id: {
            'total_count': stat.total_count or 0,
            'active_count': stat.active_count or 0,
            'min_price': stat.min_price,
            'max_price': stat.max_price,
            'sources': sources_dict.get(stat.master_property_id, [])
        }
        for stat in listing_stats
    }
    
    # レスポンスの構築
    items = []
    for prop in properties:
        listing_summary = stats_dict.get(prop.id, {
            'total_count': 0,
            'active_count': 0,
            'min_price': None,
            'max_price': None,
            'sources': []
        })
        
        items.append({
            'id': prop.id,
            'building_id': prop.building_id,
            'room_number': prop.room_number,
            'floor_number': prop.floor_number,
            'area': prop.area,
            'layout': prop.layout,
            'direction': prop.direction,
            'property_hash': prop.property_hash,
            'display_building_name': prop.display_building_name,
            'created_at': prop.created_at.isoformat() if prop.created_at else None,
            'updated_at': prop.updated_at.isoformat() if prop.updated_at else None,
            'building': {
                'id': prop.building.id,
                'normalized_name': prop.building.normalized_name,
                'address': prop.building.address,
                'total_floors': prop.building.total_floors,
                'built_year': prop.building.built_year,
            },
            'listing_summary': listing_summary
        })
    
    return {
        'items': items,
        'total': total,
        'offset': offset,
        'limit': limit
    }


@router.get("/properties/{property_id}")
async def get_property_detail(
    property_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """物件詳細を取得（管理者用）"""
    property = db.query(MasterProperty).options(
        joinedload(MasterProperty.building),
        joinedload(MasterProperty.listings).joinedload(PropertyListing.price_history)
    ).filter(MasterProperty.id == property_id).first()
    
    if not property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # 掲載情報を分類
    active_listings = []
    inactive_listings = []
    
    for listing in property.listings:
        listing_data = {
            'id': listing.id,
            'source_site': listing.source_site,
            'url': listing.url,
            'current_price': listing.current_price,
            'station_info': listing.station_info,
            'listing_building_name': listing.listing_building_name,
        }
        
        if listing.is_active:
            listing_data['last_confirmed_at'] = listing.last_confirmed_at.isoformat() if listing.last_confirmed_at else None
            active_listings.append(listing_data)
        else:
            listing_data['delisted_at'] = listing.delisted_at.isoformat() if listing.delisted_at else None
            inactive_listings.append(listing_data)
    
    # 価格履歴を集計
    price_history = []
    for listing in property.listings:
        for history in listing.price_history:
            price_history.append({
                'price': history.price,
                'recorded_at': history.recorded_at.isoformat() if history.recorded_at else None,
                'source_site': listing.source_site
            })
    
    # 日時でソート
    price_history.sort(key=lambda x: x['recorded_at'] or '')
    
    return {
        'id': property.id,
        'building_id': property.building_id,
        'room_number': property.room_number,
        'floor_number': property.floor_number,
        'area': property.area,
        'layout': property.layout,
        'direction': property.direction,
        'property_hash': property.property_hash,
        'display_building_name': property.display_building_name,
        'created_at': property.created_at.isoformat() if property.created_at else None,
        'updated_at': property.updated_at.isoformat() if property.updated_at else None,
        'building': {
            'id': property.building.id,
            'normalized_name': property.building.normalized_name,
            'address': property.building.address,
            'total_floors': property.building.total_floors,
            'built_year': property.building.built_year,
        },
        'active_listings': active_listings,
        'inactive_listings': inactive_listings,
        'price_history': price_history
    }


@router.patch("/properties/{property_id}")
async def update_property(
    property_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """物件情報を更新（管理者用）"""
    property = db.query(MasterProperty).filter(MasterProperty.id == property_id).first()
    
    if not property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # 更新可能なフィールドのみ更新
    updatable_fields = [
        'display_building_name', 'room_number', 
        'floor_number', 'area', 'layout', 'direction'
    ]
    
    for field in updatable_fields:
        if field in data:
            setattr(property, field, data[field])
    
    property.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(property)
        return {"message": "物件情報を更新しました", "property_id": property.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新に失敗しました: {str(e)}")