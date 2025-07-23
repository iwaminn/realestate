#!/usr/bin/env python3
"""
SUUMOの既存物件の所在階と向きを更新するスクリプト
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from backend.app.scrapers.suumo_scraper import SuumoScraper
import time

def update_suumo_properties():
    """SUUMOの物件の所在階と向きを更新"""
    db = SessionLocal()
    scraper = SuumoScraper()
    
    try:
        # SUUMOの物件を取得
        suumo_listings = db.query(PropertyListing).filter(
            PropertyListing.source_site == 'SUUMO',
            PropertyListing.is_active == True
        ).all()
        
        print(f"更新対象: {len(suumo_listings)}件のSUUMO物件")
        
        updated_count = 0
        for idx, listing in enumerate(suumo_listings, 1):
            print(f"\n[{idx}/{len(suumo_listings)}] {listing.title}")
            print(f"  URL: {listing.url}")
            
            # 詳細ページを取得
            try:
                property_data = scraper.parse_property_detail(listing.url)
                if property_data:
                    master_property = listing.master_property
                    updated = False
                    
                    # 所在階を更新
                    if 'floor_number' in property_data:
                        old_floor = master_property.floor_number
                        new_floor = property_data['floor_number']
                        if old_floor != new_floor:
                            print(f"  所在階を更新: {old_floor} → {new_floor}")
                            master_property.floor_number = new_floor
                            updated = True
                    
                    # 向きを更新
                    if 'direction' in property_data:
                        old_direction = master_property.direction
                        new_direction = property_data['direction']
                        if old_direction != new_direction:
                            print(f"  向きを更新: {old_direction} → {new_direction}")
                            master_property.direction = new_direction
                            updated = True
                    
                    # 建物の総階数を更新
                    if 'detail_info' in property_data and 'total_floors' in property_data['detail_info']:
                        building = master_property.building
                        old_total = building.total_floors
                        new_total = property_data['detail_info']['total_floors']
                        if old_total != new_total:
                            print(f"  総階数を更新: {old_total} → {new_total}")
                            building.total_floors = new_total
                            updated = True
                    
                    if updated:
                        db.commit()
                        updated_count += 1
                        print("  ✓ 更新完了")
                    else:
                        print("  - 更新なし")
                
                # レート制限
                time.sleep(2)
                
            except Exception as e:
                print(f"  エラー: {e}")
                continue
        
        print(f"\n\n=== 更新完了 ===")
        print(f"更新された物件数: {updated_count}/{len(suumo_listings)}")
        
    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_suumo_properties()