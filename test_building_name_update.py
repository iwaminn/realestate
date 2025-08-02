#!/usr/bin/env python3
"""
建物名更新の検出テスト
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 環境変数を設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing
from datetime import datetime

def test_building_name_change():
    """建物名変更の検出をテスト"""
    session = SessionLocal()
    
    try:
        # HOMESの物件で建物名が間違っているものを探す
        listings = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'homes',
            PropertyListing.listing_building_name.like('%徒歩%分%'),
            PropertyListing.is_active == True
        ).limit(5).all()
        
        print(f"見つかった物件数: {len(listings)}")
        
        for listing in listings:
            print(f"\n物件ID: {listing.id}")
            print(f"現在の建物名: {listing.listing_building_name}")
            print(f"URL: {listing.url}")
            
            # テスト用に建物名を更新（実際には更新しない）
            new_building_name = "テストマンション"
            print(f"新しい建物名（テスト）: {new_building_name}")
            
            # 実際のスクレイパーでは、create_or_update_listingメソッドで
            # listing_building_name=new_building_name として渡されます
            
    finally:
        session.close()

if __name__ == "__main__":
    test_building_name_change()