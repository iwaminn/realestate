#!/usr/bin/env python3
"""
特定の物件を再スクレイピングして更新
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing
from backend.app.scrapers.suumo_scraper import SuumoScraper

def update_property(property_id: int):
    """特定の物件を更新"""
    session = SessionLocal()
    try:
        # 物件の掲載情報を取得
        listing = session.query(PropertyListing).filter(
            PropertyListing.master_property_id == property_id,
            PropertyListing.source_site == "SUUMO"
        ).first()
        
        if not listing:
            print(f"物件ID {property_id} のSUUMO掲載が見つかりません")
            return
        
        print(f"物件を更新: {listing.url}")
        
        # スクレイパーを初期化（強制詳細取得モード）
        with SuumoScraper(force_detail_fetch=True) as scraper:
            # 詳細を取得して更新
            if scraper.fetch_and_update_detail(listing):
                print("✅ 更新成功")
                session.commit()
            else:
                print("❌ 更新失敗")
                session.rollback()
                
    except Exception as e:
        print(f"エラー: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    # 物件ID 394を更新
    update_property(394)