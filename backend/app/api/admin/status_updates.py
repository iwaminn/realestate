"""
ステータス更新API（掲載状態・販売終了物件の価格更新）
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from ...database import get_db
from ...api.auth import get_admin_user
from ...models import (
    PropertyListing, MasterProperty,
    ListingPriceHistory, Building
)
from ...utils.majority_vote_updater import MajorityVoteUpdater

router = APIRouter(
    tags=["admin-status"],
    dependencies=[Depends(get_admin_user)]
)


class SoldPriceUpdateResult(BaseModel):
    """販売終了価格更新結果"""
    property_id: int
    building_name: str
    floor_number: Optional[int]
    layout: Optional[str]
    final_price: Optional[int]
    price_source: str
    confidence: float


@router.get("/listing-status-stats")
async def get_listing_status_stats(
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """掲載状態の統計情報を取得"""
    
    try:
        now = datetime.now()
        threshold_24h = now - timedelta(hours=24)
        today_start = datetime.combine(now.date(), datetime.min.time())
        
        # 掲載中の数
        total_active = db.query(func.count(PropertyListing.id)).filter(
            PropertyListing.is_active == True
        ).scalar() or 0
        
        # 非掲載の数
        total_inactive = db.query(func.count(PropertyListing.id)).filter(
            PropertyListing.is_active == False
        ).scalar() or 0
        
        # 販売終了物件数
        total_sold = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.sold_at.isnot(None)
        ).scalar() or 0
        
        # 本日確認済みの掲載数
        checked_today = db.query(func.count(PropertyListing.id)).filter(
            PropertyListing.last_confirmed_at >= today_start
        ).scalar() or 0
        
        # 24時間以上確認されていない掲載数
        not_checked_24h = db.query(func.count(PropertyListing.id)).filter(
            PropertyListing.is_active == True,
            PropertyListing.last_confirmed_at < threshold_24h
        ).scalar() or 0
        
        # 最も古い未確認日時
        oldest_unchecked = db.query(func.min(PropertyListing.last_confirmed_at)).filter(
            PropertyListing.is_active == True
        ).scalar()
        
        return {
            "total_active_listings": total_active,
            "total_inactive_listings": total_inactive,
            "total_sold_properties": total_sold,
            "listings_checked_today": checked_today,
            "listings_not_checked_24h": not_checked_24h,
            "oldest_unchecked_date": oldest_unchecked.isoformat() if oldest_unchecked else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"統計情報の取得に失敗: {str(e)}")


@router.post("/update-listing-status")
async def update_listing_status(
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """掲載状態を一括更新（24時間以上確認されていない掲載を終了）"""
    
    try:
        # 現在時刻
        now = datetime.now()
        
        # 24時間前
        threshold = now - timedelta(hours=24)
        
        # 1. 24時間以内に確認された非アクティブな掲載を再アクティブ化
        reactivate_listings = db.query(PropertyListing).filter(
            PropertyListing.is_active == False,
            PropertyListing.last_confirmed_at >= threshold
        ).all()
        
        reactivate_count = len(reactivate_listings)
        reopened_properties = set()
        
        # 各掲載を再アクティブ化
        from ...utils.property_utils import update_earliest_listing_date
        properties_to_update = set()
        
        for listing in reactivate_listings:
            listing.is_active = True
            listing.delisted_at = None  # 非掲載日時をクリア
            listing.updated_at = now
            properties_to_update.add(listing.master_property_id)
            
            # その物件が販売終了となっていた場合、販売再開とする
            master_property = db.query(MasterProperty).filter(
                MasterProperty.id == listing.master_property_id
            ).first()
            
            if master_property and master_property.sold_at:
                master_property.sold_at = None
                master_property.final_price = None
                master_property.final_price_updated_at = None
                reopened_properties.add(master_property.id)
        
        # 2. 24時間以上確認されていないアクティブな掲載を非アクティブに
        inactive_listings = db.query(PropertyListing).filter(
            PropertyListing.is_active == True,
            PropertyListing.last_confirmed_at < threshold
        ).all()
        
        inactive_count = len(inactive_listings)
        sold_properties = set()
        
        # 各掲載を非アクティブに更新
        for listing in inactive_listings:
            listing.is_active = False
            listing.delisted_at = now
            listing.updated_at = now
            properties_to_update.add(listing.master_property_id)
        
        # 全掲載が非アクティブになった物件を販売終了とする
        from ...utils.price_queries import update_sold_status_and_final_price

        for property_id in properties_to_update:
            # sold_atとfinal_priceを更新
            try:
                result = update_sold_status_and_final_price(db, property_id)
                if result["sold_status_changed"] and result["is_sold"]:
                    sold_properties.add(property_id)
            except Exception as e:
                print(f"販売終了状態の更新に失敗: property_id={property_id}, error={e}")
        
        # 3. sold_atが未設定で全掲載が非アクティブの物件を販売終了とする（設定漏れの修正）
        # この処理により、過去に設定漏れがあった物件も自動修正される
        properties_missing_sold_at = db.query(MasterProperty.id).filter(
            MasterProperty.sold_at.is_(None)
        ).all()

        fixed_sold_properties = set()

        for (property_id,) in properties_missing_sold_at:
            # sold_atとfinal_priceを更新
            try:
                result = update_sold_status_and_final_price(db, property_id)
                if result["sold_status_changed"] and result["is_sold"]:
                    fixed_sold_properties.add(property_id)
            except Exception as e:
                print(f"販売終了状態の更新に失敗: property_id={property_id}, error={e}")

        # 4. sold_atは設定済みだがfinal_priceがNULLの物件を修正
        properties_missing_final_price = db.query(MasterProperty.id).filter(
            MasterProperty.sold_at.isnot(None),
            MasterProperty.final_price.is_(None)
        ).all()

        fixed_final_price_count = 0

        for (property_id,) in properties_missing_final_price:
            # final_priceのみを更新
            try:
                result = update_sold_status_and_final_price(db, property_id)
                if result["final_price"] is not None:
                    fixed_final_price_count += 1
            except Exception as e:
                print(f"final_priceの更新に失敗: property_id={property_id}, error={e}")
        
        # 影響を受けた全物件の最初の掲載日と価格改定日を更新
        from ...utils.property_utils import update_latest_price_change
        for property_id in properties_to_update:
            try:
                update_earliest_listing_date(db, property_id)
                update_latest_price_change(db, property_id)
            except Exception as e:
                print(f"最初の掲載日の更新に失敗: property_id={property_id}, error={e}")
        
        db.commit()
        
        # メッセージを構築
        messages = []
        if reactivate_count > 0:
            messages.append(f"{reactivate_count}件の掲載を再開")
            if len(reopened_properties) > 0:
                messages.append(f"{len(reopened_properties)}件の物件が販売再開")
        if inactive_count > 0:
            messages.append(f"{inactive_count}件の掲載を終了")
            if len(sold_properties) > 0:
                messages.append(f"{len(sold_properties)}件の物件が販売終了")
        if len(fixed_sold_properties) > 0:
            messages.append(f"{len(fixed_sold_properties)}件の物件のsold_atを修正")
        if fixed_final_price_count > 0:
            messages.append(f"{fixed_final_price_count}件の物件のfinal_priceを修正")

        if not messages:
            messages.append("更新対象の掲載はありませんでした")

        return {
            "success": True,
            "message": "、".join(messages) + "。",
            "reactivated_listings": reactivate_count,
            "reopened_properties": len(reopened_properties),
            "inactive_listings": inactive_count,
            "sold_properties": len(sold_properties),
            "fixed_sold_properties": len(fixed_sold_properties),
            "fixed_final_price": fixed_final_price_count
        }
        
    except Exception as e:
        db.rollback()
        print(f"掲載状態の更新でエラー: {e}")
        raise HTTPException(status_code=500, detail=f"更新処理でエラーが発生しました: {str(e)}")



@router.post("/update-sold-property-prices")
async def update_sold_property_prices(
    days_back: int = 7,
    db: Session = Depends(get_db)
):
    """販売終了物件の最終価格を多数決で更新
    
    Args:
        days_back: 販売終了前の何日間の価格を参照するか（デフォルト7日）
    """
    
    # 販売終了物件を取得
    sold_properties = db.query(MasterProperty).filter(
        MasterProperty.sold_at.isnot(None),
        MasterProperty.final_price.is_(None)  # まだ最終価格が設定されていないもの
    ).all()
    
    updated_count = 0
    results = []
    
    for property in sold_properties:
        # 販売終了前の期間を計算
        end_date = property.sold_at
        start_date = end_date - timedelta(days=days_back)
        
        # 期間内の価格履歴を集計
        price_counts = db.query(
            ListingPriceHistory.price,
            func.count(ListingPriceHistory.id).label('count')
        ).join(
            PropertyListing
        ).filter(
            PropertyListing.master_property_id == property.id,
            ListingPriceHistory.recorded_at >= start_date,
            ListingPriceHistory.recorded_at <= end_date
        ).group_by(
            ListingPriceHistory.price
        ).order_by(
            desc('count')
        ).all()
        
        if price_counts:
            # 最も多く記録された価格を最終価格とする
            most_common_price = price_counts[0].price
            total_records = sum(pc.count for pc in price_counts)
            confidence = price_counts[0].count / total_records
            
            property.final_price = most_common_price
            property.final_price_updated_at = datetime.now()
            updated_count += 1
            
            # 建物情報を取得
            building = db.query(Building).filter(
                Building.id == property.building_id
            ).first()
            
            results.append(SoldPriceUpdateResult(
                property_id=property.id,
                building_name=building.normalized_name if building else "不明",
                floor_number=property.floor_number,
                layout=property.layout,
                final_price=most_common_price,
                price_source=f"過去{days_back}日間の多数決",
                confidence=confidence
            ))
        else:
            # 価格履歴がない場合、最後の掲載価格を使用
            last_listing = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property.id
            ).order_by(
                PropertyListing.updated_at.desc()
            ).first()
            
            if last_listing and last_listing.current_price:
                property.final_price = last_listing.current_price
                property.final_price_updated_at = datetime.now()
                updated_count += 1
                
                building = db.query(Building).filter(
                    Building.id == property.building_id
                ).first()
                
                results.append(SoldPriceUpdateResult(
                    property_id=property.id,
                    building_name=building.normalized_name if building else "不明",
                    floor_number=property.floor_number,
                    layout=property.layout,
                    final_price=last_listing.current_price,
                    price_source="最後の掲載価格",
                    confidence=0.5
                ))
    
    db.commit()
    
    return {
        "message": f"{updated_count}件の販売終了物件の最終価格を更新しました",
        "updated_count": updated_count,
        "results": results[:10]  # 最初の10件のみ返す
    }


@router.get("/areas")
async def get_areas():
    """利用可能なエリアコードと名称を取得"""
    
    # 定義済みのエリアコード（地価の高い順）
    areas = [
        {"code": "13101", "name": "千代田区"},  # 1位
        {"code": "13103", "name": "港区"},      # 2位
        {"code": "13102", "name": "中央区"},    # 3位
        {"code": "13113", "name": "渋谷区"},    # 4位
        {"code": "13104", "name": "新宿区"},    # 5位
        {"code": "13105", "name": "文京区"},    # 6位
        {"code": "13110", "name": "目黒区"},    # 7位
        {"code": "13109", "name": "品川区"},    # 8位
        {"code": "13112", "name": "世田谷区"},  # 9位
        {"code": "13116", "name": "豊島区"},    # 10位
        {"code": "13106", "name": "台東区"},    # 11位
        {"code": "13114", "name": "中野区"},    # 12位
        {"code": "13115", "name": "杉並区"},    # 13位
        {"code": "13108", "name": "江東区"},    # 14位
        {"code": "13107", "name": "墨田区"}     # 16位
    ]
    
    # データベースから実際に物件が存在するエリアを取得
    # 注: PropertyListingにarea_codeがない場合は、物件数を0とする
    area_counts = {}
    
    # エリア情報に物件数を追加
    result = []
    for area in areas:
        area_info = area.copy()
        area_info['property_count'] = area_counts.get(area['code'], 0)
        result.append(area_info)
    
    return {"areas": result}