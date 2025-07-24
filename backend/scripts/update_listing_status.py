"""
掲載情報のステータスを更新するスクリプト
24時間以上確認されていない掲載を終了扱いにし、全掲載が終了した物件に販売終了日を設定
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートのパスを追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from sqlalchemy import func


def update_listing_status():
    """掲載ステータスを更新"""
    db = SessionLocal()
    try:
        # 現在時刻
        now = datetime.now()
        # 24時間前
        threshold = now - timedelta(hours=24)
        
        # 1. 24時間以上確認されていないアクティブな掲載を非アクティブに
        inactive_listings = db.query(PropertyListing).filter(
            PropertyListing.is_active == True,
            PropertyListing.last_confirmed_at < threshold
        ).all()
        
        print(f"24時間以上確認されていないアクティブな掲載: {len(inactive_listings)}件")
        
        for listing in inactive_listings:
            listing.is_active = False
            listing.delisted_at = listing.last_confirmed_at  # 最終確認日を掲載終了日とする
            print(f"  - {listing.title} (最終確認: {listing.last_confirmed_at})")
        
        # 2. 各物件について、全掲載が非アクティブになったものに販売終了日を設定
        # アクティブな掲載がない物件を取得
        subquery = db.query(PropertyListing.master_property_id).filter(
            PropertyListing.is_active == True
        ).subquery()
        
        properties_without_active_listings = db.query(MasterProperty).filter(
            ~MasterProperty.id.in_(subquery),
            MasterProperty.sold_at.is_(None)  # まだ販売終了日が設定されていない
        ).all()
        
        print(f"\n販売終了となる物件: {len(properties_without_active_listings)}件")
        
        for property in properties_without_active_listings:
            # この物件の全掲載から最新のdelisted_atを取得
            latest_delisted = db.query(func.max(PropertyListing.delisted_at)).filter(
                PropertyListing.master_property_id == property.id
            ).scalar()
            
            if latest_delisted:
                property.sold_at = latest_delisted
                
                # 最終販売価格を記録（最後にアクティブだった掲載の価格）
                last_listing = db.query(PropertyListing).filter(
                    PropertyListing.master_property_id == property.id,
                    PropertyListing.delisted_at == latest_delisted
                ).order_by(PropertyListing.current_price.desc()).first()
                
                if last_listing:
                    property.last_sale_price = last_listing.current_price
                    print(f"  - 物件ID: {property.id}, 販売終了日: {property.sold_at}, 最終価格: {property.last_sale_price}万円")
        
        # 変更をコミット
        db.commit()
        print("\nステータス更新が完了しました")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    update_listing_status()