"""
座標取得API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from ..database import get_db
from ..utils.geocoding import GeocodingService
from ..utils.logger import api_logger

router = APIRouter(prefix="/api/geocoding", tags=["geocoding"])

class CoordinatesResponse(BaseModel):
    """座標レスポンス"""
    latitude: float
    longitude: float
    cached: bool  # キャッシュから取得したかどうか

class GeocodeRequest(BaseModel):
    """ジオコーディングリクエスト"""
    address: str

@router.get("/building/{building_id}")
def get_building_coordinates(
    building_id: int,
    db: Session = Depends(get_db)
) -> CoordinatesResponse:
    """
    建物IDから座標を取得
    DBにキャッシュされていればそれを返し、なければAPIから取得して保存
    """
    try:
        # 建物の座標を取得（キャッシュ優先）
        from ..models import Building
        building = db.query(Building).filter(Building.id == building_id).first()
        
        if not building:
            raise HTTPException(status_code=404, detail="建物が見つかりません")
        
        # すでに座標がキャッシュされている場合
        if building.latitude is not None and building.longitude is not None:
            return CoordinatesResponse(
                latitude=building.latitude,
                longitude=building.longitude,
                cached=True
            )
        
        # キャッシュがない場合は取得
        coords = GeocodingService.get_or_update_coordinates(db, building_id)
        if coords:
            lat, lng = coords
            return CoordinatesResponse(
                latitude=lat,
                longitude=lng,
                cached=False
            )
        
        raise HTTPException(status_code=404, detail="座標を取得できませんでした")
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"座標取得エラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="座標取得中にエラーが発生しました")

@router.post("/geocode")
def geocode_address(
    request: GeocodeRequest
) -> CoordinatesResponse:
    """
    住所から座標を取得（キャッシュなし、直接API呼び出し）
    """
    try:
        coords = GeocodingService.get_coordinates_from_address(request.address)
        
        if coords:
            lat, lng = coords
            return CoordinatesResponse(
                latitude=lat,
                longitude=lng,
                cached=False
            )
        
        raise HTTPException(status_code=404, detail="座標を取得できませんでした")
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"ジオコーディングエラー: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="ジオコーディング中にエラーが発生しました")