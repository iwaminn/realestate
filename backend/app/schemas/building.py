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
    
    class Config:
        from_attributes = True