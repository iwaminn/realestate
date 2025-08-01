#!/usr/bin/env python3
"""
特定の物件（ID: 5743）の駅情報を再取得して更新
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.models import PropertyListing, MasterProperty
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def update_station_info():
    session = Session()
    
    try:
        # 物件情報を取得
        listing = session.query(PropertyListing).filter(
            PropertyListing.master_property_id == 5743,
            PropertyListing.source_site == 'nomu'
        ).first()
        
        if not listing:
            print("物件が見つかりません")
            return
        
        print(f"物件URL: {listing.url}")
        print(f"現在の駅情報: {listing.station_info}")
        
        # スクレイパーで詳細を取得
        scraper = NomuScraper()
        detail_data = scraper._parse_property_detail_from_url(listing.url)
        
        if detail_data:
            if detail_data.get('station_info'):
                # 駅情報を更新
                listing.station_info = detail_data['station_info']
                print(f"\n新しい駅情報:")
                print(detail_data['station_info'])
                
                session.commit()
                print("\n更新完了")
            else:
                print("\n駅情報が取得できませんでした")
        else:
            print("\n詳細データの取得に失敗しました")
            
    except Exception as e:
        session.rollback()
        print(f"エラー: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    update_station_info()