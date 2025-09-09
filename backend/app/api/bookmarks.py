"""
物件ブックマーク機能のAPI（ユーザー認証ベース）
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import PropertyBookmark, MasterProperty, User
from ..api.auth import get_current_user, require_auth
from pydantic import BaseModel

router = APIRouter()

# Pydanticモデル
class BookmarkCreate(BaseModel):
    master_property_id: int

class BookmarkResponse(BaseModel):
    id: int
    master_property_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class BookmarkWithPropertyResponse(BaseModel):
    id: int
    master_property_id: int
    created_at: datetime
    master_property: dict  # 物件情報を含む
    
    class Config:
        from_attributes = True

# セッション管理は削除 - ユーザー認証ベースに変更

@router.post("/", response_model=BookmarkResponse)
async def add_bookmark(
    bookmark_data: BookmarkCreate,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """物件をブックマークに追加"""
    
    # 物件が存在するかチェック
    master_property = db.query(MasterProperty).filter(
        MasterProperty.id == bookmark_data.master_property_id
    ).first()
    
    if not master_property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    # 既にブックマークされているかチェック
    existing_bookmark = db.query(PropertyBookmark).filter(
        PropertyBookmark.master_property_id == bookmark_data.master_property_id,
        PropertyBookmark.user_id == current_user.id
    ).first()
    
    if existing_bookmark:
        raise HTTPException(status_code=409, detail="既にブックマークされています")
    
    # ブックマークを作成
    bookmark = PropertyBookmark(
        master_property_id=bookmark_data.master_property_id,
        user_id=current_user.id
    )
    
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    
    return bookmark

@router.delete("/{master_property_id}")
async def remove_bookmark(
    master_property_id: int,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """物件をブックマークから削除"""
    
    # ブックマークを検索
    bookmark = db.query(PropertyBookmark).filter(
        PropertyBookmark.master_property_id == master_property_id,
        PropertyBookmark.user_id == current_user.id
    ).first()
    
    if not bookmark:
        raise HTTPException(status_code=404, detail="ブックマークが見つかりません")
    
    db.delete(bookmark)
    db.commit()
    
    return {"message": "ブックマークを削除しました"}

@router.get("/", response_model=List[BookmarkWithPropertyResponse])
async def get_bookmarks(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """ブックマーク一覧を取得"""
    
    # ブックマークを物件情報と一緒に取得
    bookmarks = db.query(PropertyBookmark).filter(
        PropertyBookmark.user_id == current_user.id
    ).order_by(PropertyBookmark.created_at.desc()).all()
    
    # レスポンスデータを構築
    result = []
    for bookmark in bookmarks:
        # 物件情報を取得
        property_data = db.query(MasterProperty).filter(
            MasterProperty.id == bookmark.master_property_id
        ).first()
        
        if property_data:
            # 建物情報を含む物件データを構築
            master_property_dict = {
                "id": property_data.id,
                "building_id": property_data.building_id,
                "room_number": property_data.room_number,
                "floor_number": property_data.floor_number,
                "area": property_data.area,
                "balcony_area": property_data.balcony_area,
                "layout": property_data.layout,
                "direction": property_data.direction,
                "management_fee": property_data.management_fee,
                "repair_fund": property_data.repair_fund,
                "station_info": property_data.station_info,
                "display_building_name": property_data.display_building_name,
                "sold_at": property_data.sold_at,
                "final_price": property_data.final_price,
                "building": {
                    "id": property_data.building.id,
                    "normalized_name": property_data.building.normalized_name,
                    "address": property_data.building.address,
                    "total_floors": property_data.building.total_floors,
                    "built_year": property_data.building.built_year,
                    "built_month": property_data.building.built_month
                } if property_data.building else None
            }
            
            result.append({
                "id": bookmark.id,
                "master_property_id": bookmark.master_property_id,
                "created_at": bookmark.created_at,
                "master_property": master_property_dict
            })
    
    return result

@router.get("/check/{master_property_id}")
async def check_bookmark_status(
    master_property_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """物件がブックマークされているかチェック（認証オプショナル）"""
    
    if not current_user:
        return {
            "is_bookmarked": False,
            "bookmark_id": None,
            "requires_login": True
        }
    
    # ブックマークが存在するかチェック
    bookmark = db.query(PropertyBookmark).filter(
        PropertyBookmark.master_property_id == master_property_id,
        PropertyBookmark.user_id == current_user.id
    ).first()
    
    return {
        "is_bookmarked": bookmark is not None,
        "bookmark_id": bookmark.id if bookmark else None,
        "requires_login": False
    }