"""建物関連のPydanticスキーマ"""
from pydantic import BaseModel
from typing import Optional

class BuildingSchema(BaseModel):
    id: int
    normalized_name: str
    address: Optional[str]
    total_floors: Optional[int]
    basement_floors: Optional[int]
    total_units: Optional[int]
    built_year: Optional[int]
    built_month: Optional[int]
    construction_type: Optional[str]
    land_rights: Optional[str]
    station_info: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        from_attributes = True


class NearbyBuildingSchema(BaseModel):
    """周辺建物のスキーマ"""
    id: int
    normalized_name: str
    address: Optional[str]
    total_floors: Optional[int]
    built_year: Optional[int]
    built_month: Optional[int]
    station_info: Optional[str]
    distance_meters: float  # 距離（メートル）
    property_count: int  # 販売中物件数
    price_range: Optional[dict] = None  # 価格帯

    class Config:
        from_attributes = True