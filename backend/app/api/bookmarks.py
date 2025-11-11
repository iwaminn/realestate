"""
物件ブックマーク機能のAPI（ユーザー認証ベース）
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import PropertyBookmark, MasterProperty, User, PropertyListing
from ..api.auth import get_current_user_from_cookie, require_auth_cookie, require_auth_flexible, get_current_user_flexible
from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery
from pydantic import BaseModel
from sqlalchemy import func

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
    current_user: User = Depends(require_auth_flexible),
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
    current_user: User = Depends(require_auth_flexible),
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

def _get_property_details(db: Session, property_data, current_price):
    """物件の詳細情報を取得するヘルパー関数"""
    from ..models import PropertyPriceChange
    
    # 全掲載を取得
    all_listings = property_data.listings
    
    # アクティブな掲載のみフィルタ
    active_listings = [l for l in all_listings if l.is_active]
    has_active = len(active_listings) > 0
    
    # 価格を決定
    # master_property.current_priceを使用（多数決で計算済み）
    if has_active:
        majority_price = property_data.current_price
    else:
        # 販売終了物件はfinal_priceを使用
        majority_price = property_data.final_price if property_data.sold_at else None
    
    # 最終確認日、販売終了日、売出確認日を取得
    last_confirmed_at = None
    delisted_at = None
    earliest_published_at = None
    
    if has_active and active_listings:
        last_confirmed_at = active_listings[0].last_confirmed_at
    
    # 売出確認日は全掲載から最も古いものを取得
    if all_listings:
        earliest_dates = [
            l.first_published_at or l.published_at or l.first_seen_at 
            for l in all_listings 
            if l.first_published_at or l.published_at or l.first_seen_at
        ]
        if earliest_dates:
            earliest_published_at = min(earliest_dates)
    
    # 販売終了の場合、最後に見つかった掲載から終了日を取得
    if not has_active:
        last_listing = db.query(PropertyListing).filter(
            PropertyListing.master_property_id == property_data.id
        ).order_by(PropertyListing.last_scraped_at.desc()).first()
        if last_listing:
            delisted_at = last_listing.delisted_at
    
    # 坪単価を計算（万円/坪）
    price_per_tsubo = None
    if property_data.area and property_data.area > 0 and current_price:
        price_per_tsubo = int(round(current_price / (property_data.area / 3.30578)))
    
    # 価格変更情報を取得（PropertyPriceChangeテーブルから）
    price_change_info = None
    latest_price_change = db.query(PropertyPriceChange).filter(
        PropertyPriceChange.master_property_id == property_data.id
    ).order_by(PropertyPriceChange.change_date.desc()).first()
    
    if latest_price_change:
        price_change_info = {
            "date": latest_price_change.change_date.isoformat(),
            "previous_price": latest_price_change.old_price,
            "current_price": latest_price_change.new_price,
            "change_amount": latest_price_change.price_diff,
            "change_rate": round(latest_price_change.price_diff_rate, 2) if latest_price_change.price_diff_rate else 0
        }
    
    return {
        "has_active_listing": has_active,
        "majority_price": majority_price,
        "price_per_tsubo": price_per_tsubo,
        "price_change_info": price_change_info,
        "last_confirmed_at": last_confirmed_at,
        "delisted_at": delisted_at,
        "earliest_published_at": earliest_published_at
    }

@router.get("/")
async def get_bookmarks(
    group_by: Optional[str] = None,  # "ward", "building", or None
    current_user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """
    ブックマーク一覧を取得
    
    Parameters:
    - group_by: グルーピング方法 ("ward": エリア別, "building": 建物別, None: すべて)
    """
    from ..models import Building
    from sqlalchemy import case
    
    # ブックマークを物件情報と一緒に取得
    bookmarks = db.query(PropertyBookmark).filter(
        PropertyBookmark.user_id == current_user.id
    ).order_by(PropertyBookmark.created_at.desc()).all()

    # グルーピングなしの場合は従来通りの処理
    if not group_by:
        result = []
        for bookmark in bookmarks:
            # 物件情報を取得
            property_data = db.query(MasterProperty).filter(
                MasterProperty.id == bookmark.master_property_id
            ).first()

            if property_data:
                # 掲載情報が存在するかチェック（統合済み物件を除外）
                has_any_listings = db.query(PropertyListing).filter(
                    PropertyListing.master_property_id == property_data.id
                ).count() > 0
                
                # 掲載情報がない物件はスキップ
                if not has_any_listings:
                    continue
                
                # 詳細情報を取得（仮の価格で呼び出し）
                details = _get_property_details(db, property_data, None)
                
                # 価格を決定：アクティブな掲載がない場合のみfinal_priceを使用
                if not details["has_active_listing"] and property_data.sold_at and property_data.final_price:
                    current_price = property_data.final_price
                else:
                    # アクティブな掲載がある場合は、多数決価格を使用
                    current_price = details.get("majority_price")
                
                # 坪単価を再計算
                if property_data.area and property_data.area > 0 and current_price:
                    details["price_per_tsubo"] = int(round(current_price / (property_data.area / 3.30578)))
                
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
                    "display_building_name": property_data.display_building_name,
                    "sold_at": property_data.sold_at,
                    "final_price": property_data.final_price,
                    "current_price": current_price,
                    "updated_at": property_data.updated_at,
                    "has_active_listing": details["has_active_listing"],
                    "price_per_tsubo": details["price_per_tsubo"],
                    "price_change_info": details["price_change_info"],
                    "last_confirmed_at": details["last_confirmed_at"],
                    "delisted_at": details["delisted_at"],
                    "earliest_published_at": details["earliest_published_at"],
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
    
    # エリア別グルーピング
    if group_by == "ward":
        import re
        
        # ブックマークされた物件を取得
        properties_query = (
            db.query(
                PropertyBookmark,
                MasterProperty,
                Building
            )
            .join(MasterProperty, MasterProperty.id == PropertyBookmark.master_property_id)
            .join(Building, Building.id == MasterProperty.building_id)
            .filter(PropertyBookmark.user_id == current_user.id)
        ).all()
        
        # エリアごとにグルーピング
        grouped = {}
        for bookmark, property_data, building in properties_query:
            # 掲載情報が存在するかチェック（統合済み物件を除外）
            has_any_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id
            ).count() > 0
            
            # 掲載情報がない物件はスキップ
            if not has_any_listings:
                continue
            
            # 住所から区名を抽出
            address = building.address or ""
            match = re.search(r'(.*?[区市町村])', address)
            if match:
                ward = re.sub(r'^東京都', '', match.group(1))
            else:
                ward = "不明"
            
            if ward not in grouped:
                grouped[ward] = {
                    "ward": ward,
                    "count": 0,
                    "properties": [],
                    "avg_price": 0,
                    "min_price": None,
                    "max_price": None,
                    "price_sum": 0
                }
            
            # 詳細情報を取得（仮の価格で呼び出し）
            details = _get_property_details(db, property_data, None)
            
            # 価格を決定：アクティブな掲載がない場合のみfinal_priceを使用
            if not details["has_active_listing"] and property_data.sold_at and property_data.final_price:
                current_price = property_data.final_price
            else:
                # アクティブな掲載がある場合は、多数決価格を使用
                current_price = details.get("majority_price")
            
            # 坪単価を再計算
            if property_data.area and property_data.area > 0 and current_price:
                details["price_per_tsubo"] = int(round(current_price / (property_data.area / 3.30578)))
            
            # 統計情報を更新
            if current_price:
                grouped[ward]["price_sum"] += current_price
                if grouped[ward]["min_price"] is None or current_price < grouped[ward]["min_price"]:
                    grouped[ward]["min_price"] = current_price
                if grouped[ward]["max_price"] is None or current_price > grouped[ward]["max_price"]:
                    grouped[ward]["max_price"] = current_price
            
            grouped[ward]["count"] += 1
            grouped[ward]["properties"].append({
                "id": bookmark.id,
                "master_property_id": bookmark.master_property_id,
                "created_at": bookmark.created_at,
                "master_property": {
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
                    "display_building_name": property_data.display_building_name,
                    "sold_at": property_data.sold_at,
                    "final_price": property_data.final_price,
                    "current_price": current_price,
                    "updated_at": property_data.updated_at,
                    "has_active_listing": details["has_active_listing"],
                    "price_per_tsubo": details["price_per_tsubo"],
                    "price_change_info": details["price_change_info"],
                    "last_confirmed_at": details["last_confirmed_at"],
                    "delisted_at": details["delisted_at"],
                    "earliest_published_at": details["earliest_published_at"],
                    "building": {
                        "id": building.id,
                        "normalized_name": building.normalized_name,
                        "address": building.address,
                        "total_floors": building.total_floors,
                        "built_year": building.built_year,
                        "built_month": building.built_month
                    }
                }
            })
        
        # 平均価格を計算
        for ward_data in grouped.values():
            if ward_data["count"] > 0:
                ward_data["avg_price"] = ward_data["price_sum"] // ward_data["count"]
            del ward_data["price_sum"]  # 合計は不要なので削除
        
        return {"grouped_bookmarks": grouped, "group_by": "ward"}
    
    # 建物別グルーピング
    if group_by == "building":
        # ブックマークされた物件を取得
        properties_query = (
            db.query(
                PropertyBookmark,
                MasterProperty,
                Building
            )
            .join(MasterProperty, MasterProperty.id == PropertyBookmark.master_property_id)
            .join(Building, Building.id == MasterProperty.building_id)
            .filter(PropertyBookmark.user_id == current_user.id)
            .order_by(PropertyBookmark.created_at.desc())
        ).all()
        
        # 建物ごとにグルーピング
        grouped = {}
        for bookmark, property_data, building in properties_query:
            # 掲載情報が存在するかチェック（統合済み物件を除外）
            has_any_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id
            ).count() > 0
            
            # 掲載情報がない物件はスキップ
            if not has_any_listings:
                continue
            
            building_key = f"{building.id}_{building.normalized_name}"
            
            if building_key not in grouped:
                grouped[building_key] = {
                    "building_id": building.id,
                    "building_name": building.normalized_name,
                    "count": 0,
                    "properties": [],
                    "avg_price": 0,
                    "avg_price_per_sqm": 0,
                    "min_price": None,
                    "max_price": None,
                    "price_sum": 0,
                    "area_sum": 0,
                    "building_info": {
                        "address": building.address,
                        "total_floors": building.total_floors,
                        "built_year": building.built_year,
                        "built_month": building.built_month
                    }
                }
            
            # 詳細情報を取得（仮の価格で呼び出し）
            details = _get_property_details(db, property_data, None)
            
            # 価格を決定：アクティブな掲載がない場合のみfinal_priceを使用
            if not details["has_active_listing"] and property_data.sold_at and property_data.final_price:
                current_price = property_data.final_price
            else:
                # アクティブな掲載がある場合は、多数決価格を使用
                current_price = details.get("majority_price")
            
            # 坪単価を再計算
            if property_data.area and property_data.area > 0 and current_price:
                details["price_per_tsubo"] = int(round(current_price / (property_data.area / 3.30578)))
            
            # 統計情報を更新
            if current_price:
                grouped[building_key]["price_sum"] += current_price
                if grouped[building_key]["min_price"] is None or current_price < grouped[building_key]["min_price"]:
                    grouped[building_key]["min_price"] = current_price
                if grouped[building_key]["max_price"] is None or current_price > grouped[building_key]["max_price"]:
                    grouped[building_key]["max_price"] = current_price
            
            if property_data.area:
                grouped[building_key]["area_sum"] += property_data.area
            
            grouped[building_key]["count"] += 1
            grouped[building_key]["properties"].append({
                "id": bookmark.id,
                "master_property_id": bookmark.master_property_id,
                "created_at": bookmark.created_at,
                "master_property": {
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
                    "display_building_name": property_data.display_building_name,
                    "sold_at": property_data.sold_at,
                    "final_price": property_data.final_price,
                    "current_price": current_price,
                    "updated_at": property_data.updated_at,
                    "has_active_listing": details["has_active_listing"],
                    "price_per_tsubo": details["price_per_tsubo"],
                    "price_change_info": details["price_change_info"],
                    "last_confirmed_at": details["last_confirmed_at"],
                    "delisted_at": details["delisted_at"],
                    "earliest_published_at": details["earliest_published_at"],
                    "building": {
                        "id": building.id,
                        "normalized_name": building.normalized_name,
                        "address": building.address,
                        "total_floors": building.total_floors,
                        "built_year": building.built_year,
                        "built_month": building.built_month
                    }
                }
            })
        
        # 建物全体の統計情報を計算（販売中物件のみ）
        for building_data in grouped.values():
            building_id = building_data["building_id"]
            
            # 建物全体の販売中物件を取得
            all_active_properties = (
                db.query(MasterProperty)
                .filter(
                    MasterProperty.building_id == building_id,
                    MasterProperty.sold_at.is_(None)  # 販売中のみ
                )
                .all()
            )
            
            # 建物全体の統計を計算
            if all_active_properties:
                total_price_sum = sum(p.current_price for p in all_active_properties if p.current_price)
                total_area_sum = sum(p.area for p in all_active_properties if p.area)
                
                building_data["building_stats"] = {
                    "active_count": len(all_active_properties),
                    "avg_price_per_tsubo": None
                }
                
                # 坪単価を計算（平米単価 × 3.3058）
                if total_area_sum > 0 and total_price_sum > 0:
                    avg_price_per_sqm = total_price_sum / total_area_sum
                    avg_price_per_tsubo = int(avg_price_per_sqm * 3.3058)  # 坪単価 = 平米単価 × 3.3058
                    building_data["building_stats"]["avg_price_per_tsubo"] = avg_price_per_tsubo
            
            # ブックマーク物件の統計は削除
            del building_data["price_sum"]
            del building_data["area_sum"]
        
        return {"grouped_bookmarks": grouped, "group_by": "building"}
    
    raise HTTPException(status_code=400, detail="Invalid group_by parameter")

@router.get("/check/{master_property_id}")
async def check_bookmark_status(
    master_property_id: int,
    current_user: Optional[User] = Depends(get_current_user_flexible),
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


@router.post("/check-bulk")
async def check_bookmarks_bulk(
    property_ids: List[int],
    current_user: Optional[User] = Depends(get_current_user_flexible),
    db: Session = Depends(get_db)
):
    """複数物件のブックマーク状態を一括チェック（認証オプショナル）"""
    
    if not current_user:
        # 未認証の場合は全てfalse
        return {
            "bookmarks": {str(prop_id): False for prop_id in property_ids},
            "requires_login": True
        }
    
    # ユーザーのブックマークを一括取得
    bookmarks = db.query(PropertyBookmark.master_property_id).filter(
        PropertyBookmark.user_id == current_user.id,
        PropertyBookmark.master_property_id.in_(property_ids)
    ).all()
    
    # ブックマークされている物件IDのセット
    bookmarked_ids = {bookmark.master_property_id for bookmark in bookmarks}
    
    # 結果を辞書形式で返す
    return {
        "bookmarks": {str(prop_id): prop_id in bookmarked_ids for prop_id in property_ids},
        "requires_login": False
    }
