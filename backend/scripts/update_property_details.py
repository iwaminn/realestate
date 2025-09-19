#!/usr/bin/env python3
"""
物件の詳細情報（不動産会社、バルコニー面積、備考）を更新
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.utils.remarks_summarizer import RemarksSummarizer
from datetime import datetime


def update_property_details(limit=5):
    """物件の詳細情報を更新"""
    
    session = SessionLocal()
    try:
        # HOMESの物件を更新
        print("=== HOMES物件の詳細情報を更新 ===")
        homes_listings = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True
        ).limit(limit).all()
        
        with HomesScraper() as scraper:
            for i, listing in enumerate(homes_listings, 1):
                print(f"\n[{i}/{len(homes_listings)}] {listing.master_property.building.normalized_name}")
                
                # 詳細を取得
                detail_data = scraper.parse_property_detail(listing.url)
                
                if detail_data:
                    # 不動産会社情報
                    if detail_data.get('agency_name'):
                        listing.agency_name = detail_data['agency_name']
                        print(f"  不動産会社: {listing.agency_name}")
                    
                    if detail_data.get('agency_tel'):
                        listing.agency_tel = detail_data['agency_tel']
                        print(f"  電話番号: {listing.agency_tel}")
                    
                    # バルコニー面積
                    if detail_data.get('balcony_area'):
                        listing.master_property.balcony_area = detail_data['balcony_area']
                        print(f"  バルコニー面積: {listing.master_property.balcony_area}㎡")
                    
                    # 備考
                    if detail_data.get('remarks'):
                        listing.remarks = detail_data['remarks']
                        print(f"  備考: あり")
                    
                    listing.detail_fetched_at = datetime.now()
                    session.commit()
                    print("  ✅ 更新完了")
                else:
                    print("  ❌ 詳細取得失敗")
        
        # 備考の要約を更新
        print("\n=== 備考の要約を作成 ===")
        
        # 備考がある物件を取得
        properties_with_remarks = session.query(MasterProperty).join(
            PropertyListing
        ).filter(
            PropertyListing.remarks.isnot(None),
            PropertyListing.is_active == True
        ).distinct().limit(limit).all()
        
        for prop in properties_with_remarks:
            print(f"\n{prop.building.normalized_name}")
            
            # この物件の全ての備考を収集
            remarks_list = []
            for listing in prop.listings:
                if listing.is_active and listing.remarks:
                    remarks_list.append(listing.remarks)
                    print(f"  [{listing.source_site}] 備考あり")
            
            if remarks_list:
                # 要約を作成
                summary = RemarksSummarizer.summarize_remarks(remarks_list)

                print(f"  要約: {summary[:100]}..." if len(summary) > 100 else f"  要約: {summary}")
                session.commit()
        
        print("\n✅ 詳細情報の更新が完了しました")
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    # コマンドライン引数で件数を指定可能
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    update_property_details(limit)