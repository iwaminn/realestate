"""統計関連のAPIエンドポイント"""
from fastapi import APIRouter, Depends
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, ListingPriceHistory

router = APIRouter(prefix="/api", tags=["stats"])

@router.get("/stats", response_model=Dict[str, Any])
async def get_stats(db: Session = Depends(get_db)):
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