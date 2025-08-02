#!/usr/bin/env python3
"""
建物名更新の検出テスト - 実際に更新を実行
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 環境変数を設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing
from backend.app.scrapers.homes_scraper import HomesScraper
from datetime import datetime

def test_building_name_update():
    """建物名変更の検出をテスト"""
    session = SessionLocal()
    
    try:
        # HOMESの物件で駅情報が建物名に入っているものを1件探す
        listing = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'homes',
            PropertyListing.listing_building_name.like('%徒歩%分%'),
            PropertyListing.is_active == True
        ).first()
        
        if not listing:
            print("テスト対象の物件が見つかりません")
            return
            
        print(f"テスト対象物件:")
        print(f"  ID: {listing.id}")
        print(f"  現在の建物名: {listing.listing_building_name}")
        print(f"  URL: {listing.url}")
        
        # HOMESスクレイパーを初期化
        scraper = HomesScraper()
        
        # 詳細ページを取得して処理
        print(f"\n詳細ページを取得中...")
        soup = scraper.fetch_page(listing.url)
        
        if not soup:
            print("詳細ページの取得に失敗しました")
            return
            
        # parse_property_detailを呼び出して物件情報を抽出
        property_data = scraper.parse_property_detail(listing.url)
        
        if property_data:
            print(f"\n抽出された建物名: {property_data.get('building_name', '不明')}")
            
            # 建物名が変更されている場合のみ更新を実行
            if property_data.get('building_name') and property_data['building_name'] != listing.listing_building_name:
                print(f"\n建物名が変更されています！")
                print(f"  旧: {listing.listing_building_name}")
                print(f"  新: {property_data['building_name']}")
                
                # master_propertyを取得
                master_property = listing.master_property
                
                if master_property:
                    # create_or_update_listingを呼び出して更新
                    result = scraper.create_or_update_listing(
                        master_property=master_property,
                        url=listing.url,
                        title=listing.title,
                        price=listing.current_price,
                        listing_building_name=property_data['building_name']
                    )
                    
                    if isinstance(result, tuple) and len(result) >= 3:
                        listing_obj, update_type, update_details = result
                        print(f"\n更新結果:")
                        print(f"  update_type: {update_type}")
                        print(f"  update_details: {update_details}")
                        
                        # コミット
                        session.commit()
                        print("\n更新をコミットしました")
                    else:
                        print(f"\n予期しない戻り値: {result}")
                else:
                    print("master_propertyが見つかりません")
            else:
                print("\n建物名に変更はありません")
        else:
            print("物件情報の抽出に失敗しました")
            
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    test_building_name_update()