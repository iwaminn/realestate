"""物件関連のPydanticスキーマ"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from .building import BuildingSchema

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
    display_building_name: Optional[str]  # 表示用建物名（多数決で決定）
    room_number: Optional[str]
    floor_number: Optional[int]
    area: Optional[float]
    balcony_area: Optional[float]
    layout: Optional[str]
    direction: Optional[str]
    current_price: Optional[int]
    listing_count: int
    source_sites: List[str]
    station_info: Optional[str]
    management_fee: Optional[int]
    repair_fund: Optional[int]
    earliest_published_at: Optional[datetime]
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
    prices: Dict[str, List[str]]
    
    class Config:
        from_attributes = True

class PropertyDetailSchema(BaseModel):
    master_property: MasterPropertySchema
    listings: List[ListingSchema]
    price_histories_by_listing: Dict[int, List[PriceHistorySchema]]
    price_timeline: Dict[str, Any]
    price_consistency: Dict[str, Any]
    unified_price_history: List[Dict[str, Any]]
    price_discrepancies: List[Dict[str, Any]]
    
    class Config:
        from_attributes = True