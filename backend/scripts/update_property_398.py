#!/usr/bin/env python3
"""
物件ID 398（ラ ヴォーグ南青山）の情報を再取得して更新
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper import SuumoScraper
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import PropertyListing

# データベース接続
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@postgres:5432/realestate')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def update_property_398():
    print("=== 物件ID 398の情報を再取得して更新 ===\n")
    
    session = Session()
    
    try:
        # SUUMOの掲載情報を取得
        listing = session.query(PropertyListing).filter(
            PropertyListing.url == 'https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77291959/',
            PropertyListing.source_site == 'SUUMO'
        ).first()
        
        if not listing:
            print("該当する物件が見つかりません")
            return
        
        print(f"物件情報:")
        print(f"  建物名: {listing.master_property.building.normalized_name}")
        print(f"  階数: {listing.master_property.floor_number}階")
        print(f"  現在の管理費: {listing.management_fee}円")
        print(f"  現在の修繕積立金: {listing.repair_fund}円")
        
        # スクレイパーで詳細を再取得
        print("\n詳細ページを再取得中...")
        scraper = SuumoScraper(force_detail_fetch=True)
        
        # 詳細ページを取得
        detail_data = scraper.parse_property_detail(listing.url)
        
        if detail_data:
            print("\n新しい情報:")
            print(f"  管理費: {detail_data.get('management_fee')}円")
            print(f"  修繕積立金: {detail_data.get('repair_fund')}円")
            
            # データベースを更新
            if detail_data.get('management_fee'):
                listing.management_fee = detail_data['management_fee']
            if detail_data.get('repair_fund'):
                listing.repair_fund = detail_data['repair_fund']
            
            # 価格履歴も更新
            from backend.app.models import ListingPriceHistory
            from datetime import datetime
            
            price_history = ListingPriceHistory(
                property_listing_id=listing.id,
                price=listing.current_price,
                management_fee=detail_data.get('management_fee'),
                repair_fund=detail_data.get('repair_fund')
            )
            session.add(price_history)
            
            # 詳細取得日時を更新
            listing.detail_fetched_at = datetime.now()
            
            session.commit()
            print("\n✓ データベースを更新しました")
            
            # 更新後の確認
            print("\n更新後の情報:")
            print(f"  管理費: {listing.management_fee}円")
            print(f"  修繕積立金: {listing.repair_fund}円")
            
        else:
            print("詳細ページの取得に失敗しました")
    
    finally:
        session.close()


if __name__ == "__main__":
    update_property_398()