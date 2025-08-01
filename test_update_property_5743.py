#!/usr/bin/env python3
"""
特定の物件（ID: 5743）の詳細を再取得して更新
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.models import PropertyListing, MasterProperty, Building
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def update_property():
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
        
        # スクレイパーで詳細を取得
        scraper = NomuScraper()
        detail_data = scraper._parse_property_detail_from_url(listing.url)
        
        if detail_data:
            print(f"\n取得した詳細データ:")
            for key, value in detail_data.items():
                print(f"  {key}: {value}")
            
            # 住所が取得できた場合
            if detail_data.get('address'):
                # detail_infoを更新
                if not listing.detail_info:
                    listing.detail_info = {}
                listing.detail_info['address'] = detail_data['address']
                
                # 建物の住所も更新
                master_property = session.query(MasterProperty).filter(
                    MasterProperty.id == listing.master_property_id
                ).first()
                
                if master_property:
                    building = session.query(Building).filter(
                        Building.id == master_property.building_id
                    ).first()
                    
                    if building and not building.address:
                        building.address = detail_data['address']
                        print(f"\n建物の住所を更新: {building.normalized_name} -> {detail_data['address']}")
                
                session.commit()
                print("\n更新完了")
            else:
                print("\n住所が取得できませんでした")
        else:
            print("\n詳細データの取得に失敗しました")
            
    except Exception as e:
        session.rollback()
        print(f"エラー: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    update_property()