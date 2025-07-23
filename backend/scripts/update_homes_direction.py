#!/usr/bin/env python3
"""
HOMESの既存物件の向き（主要採光面）を更新するスクリプト
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from backend.app.scrapers.homes_scraper import HomesScraper
import time

def update_homes_properties():
    """HOMESの物件の向きを更新"""
    db = SessionLocal()
    scraper = HomesScraper(db)
    
    try:
        # HOMESの物件を取得（向きがないものを優先）
        homes_listings = db.query(PropertyListing).join(
            MasterProperty
        ).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True,
            MasterProperty.direction.is_(None)  # 向きがない物件を優先
        ).all()
        
        print(f"更新対象: {len(homes_listings)}件のHOMES物件（向きなし）")
        
        updated_count = 0
        for idx, listing in enumerate(homes_listings, 1):
            print(f"\n[{idx}/{len(homes_listings)}] {listing.title}")
            print(f"  URL: {listing.url}")
            
            # 詳細ページを取得
            try:
                property_data = scraper.parse_property_detail(listing.url)
                if property_data:
                    master_property = listing.master_property
                    updated = False
                    
                    # 向きを更新
                    if 'direction' in property_data and property_data['direction']:
                        old_direction = master_property.direction
                        new_direction = property_data['direction']
                        if old_direction != new_direction:
                            print(f"  向きを更新: {old_direction} → {new_direction}")
                            master_property.direction = new_direction
                            updated = True
                    
                    if updated:
                        db.commit()
                        updated_count += 1
                        print("  ✓ 更新完了")
                    else:
                        print("  - 更新なし（向き情報なし）")
                
                # レート制限
                time.sleep(2)
                
            except Exception as e:
                print(f"  エラー: {e}")
                continue
        
        print(f"\n\n=== 更新完了 ===")
        print(f"更新された物件数: {updated_count}/{len(homes_listings)}")
        
        # 更新後の統計
        total_homes = db.query(PropertyListing).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True
        ).count()
        
        homes_with_direction = db.query(PropertyListing).join(
            MasterProperty
        ).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True,
            MasterProperty.direction.isnot(None)
        ).count()
        
        print(f"\nHOMES全体の統計:")
        print(f"  総物件数: {total_homes}")
        print(f"  向きあり: {homes_with_direction} ({homes_with_direction/total_homes*100:.1f}%)")
        
    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_homes_properties()