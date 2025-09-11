#!/usr/bin/env python3
"""
building_listing_namesテーブルのcanonical_nameを再正規化するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import BuildingListingName
from app.scrapers.data_normalizer import canonicalize_building_name


def fix_canonical_names():
    """すべてのcanonical_nameを再正規化"""
    db = SessionLocal()
    
    try:
        # すべてのbuilding_listing_namesを取得
        listing_names = db.query(BuildingListingName).all()
        
        print(f"処理対象: {len(listing_names)}件")
        print("-" * 60)
        
        updated_count = 0
        for listing in listing_names:
            old_canonical = listing.canonical_name
            # listing_nameから再度canonical_nameを生成
            new_canonical = canonicalize_building_name(listing.listing_name)
            
            if old_canonical != new_canonical:
                print(f"建物ID: {listing.building_id}")
                print(f"  掲載名: {listing.listing_name}")
                print(f"  変更前: {old_canonical}")
                print(f"  変更後: {new_canonical}")
                print()
                
                listing.canonical_name = new_canonical
                updated_count += 1
        
        if updated_count > 0:
            db.commit()
            print("-" * 60)
            print(f"✅ {updated_count}件のcanonical_nameを更新しました")
        else:
            print("更新が必要なレコードはありませんでした")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_canonical_names()