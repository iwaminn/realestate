#!/usr/bin/env python3
"""
SUUMOスクレイパーの修正が正しく動作しているか検証
"""

import sys
from pathlib import Path
import os

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# SQLiteを使用
os.environ['DATABASE_URL'] = 'sqlite:///data/realestate.db'

from backend.app.scrapers.suumo_scraper_v3 import SuumoScraperV3
from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty, PropertyListing


def verify_scraper_fixes():
    """スクレイパーの修正を検証"""
    print("=== SUUMOスクレイパー修正検証 ===\n")
    
    # テスト用に少数の物件をスクレイプ
    with SuumoScraperV3() as scraper:
        scraper.scrape_area("minato", max_pages=1)
    
    print("\n=== データベース検証 ===\n")
    
    session = SessionLocal()
    try:
        # 最新の建物を確認
        recent_buildings = session.query(Building).order_by(Building.id.desc()).limit(5).all()
        
        print("最新の建物（住所情報を確認）:")
        for building in recent_buildings:
            print(f"\n建物: {building.normalized_name}")
            print(f"  住所: {building.address or '空'}")
            print(f"  築年: {building.built_year or 'なし'}")
            print(f"  物件数: {len(building.properties)}")
            
            # この建物の物件を表示
            if building.properties:
                print("  物件一覧:")
                for prop in building.properties[:3]:
                    print(f"    - 部屋番号: {prop.room_number or '全体'}")
                    print(f"      階数: {prop.floor_number}階, 面積: {prop.area}m², 間取り: {prop.layout}")
                    print(f"      ハッシュ: {prop.property_hash[:16]}...")
        
        # 最新の掲載情報（駅情報を確認）
        recent_listings = session.query(PropertyListing).filter(
            PropertyListing.source_site == "SUUMO"
        ).order_by(PropertyListing.id.desc()).limit(5).all()
        
        print("\n\n最新のSUUMO掲載情報（駅情報を確認）:")
        for listing in recent_listings:
            print(f"\n物件: {listing.title}")
            print(f"  駅情報: {listing.station_info or '空'}")
            print(f"  価格: {listing.current_price}万円")
            print(f"  URL: {listing.url}")
            
            # 関連する建物情報
            master_prop = listing.master_property
            building = master_prop.building
            print(f"  建物: {building.normalized_name}")
            print(f"  建物住所: {building.address or '空'}")
        
        # 同一建物で複数物件を持つケースを確認
        from sqlalchemy import func
        buildings_with_multiple = session.query(Building).join(MasterProperty).group_by(Building.id).having(
            func.count(MasterProperty.id) > 1
        ).order_by(Building.id.desc()).limit(3).all()
        
        print("\n\n複数物件を持つ建物（最新3件）:")
        for building in buildings_with_multiple:
            print(f"\n建物: {building.normalized_name} ({len(building.properties)}件)")
            print(f"  住所: {building.address or '空'}")
            for i, prop in enumerate(building.properties[:5], 1):
                print(f"  物件{i}:")
                print(f"    ハッシュ: {prop.property_hash[:32]}...")
                print(f"    階数: {prop.floor_number}階, 面積: {prop.area}m², 間取り: {prop.layout}")
                
                # この物件の掲載情報を取得
                listing = session.query(PropertyListing).filter(
                    PropertyListing.master_property_id == prop.id,
                    PropertyListing.source_site == "SUUMO"
                ).first()
                if listing:
                    print(f"    URL: {listing.url}")
        
    finally:
        session.close()


if __name__ == "__main__":
    verify_scraper_fixes()