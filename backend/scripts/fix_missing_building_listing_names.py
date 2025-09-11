#!/usr/bin/env python3
"""
building_listing_namesが欠落している建物を修正するスクリプト
BuildingListingNameManager.refresh_building_names()を使用して再生成
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import MasterProperty, PropertyListing, BuildingListingName
from app.utils.building_listing_name_manager import BuildingListingNameManager
from sqlalchemy import func


def fix_missing_building_listing_names():
    """building_listing_namesが欠落している建物を修正"""
    db = SessionLocal()
    
    try:
        # 掲載情報があるのにbuilding_listing_namesがない建物を特定
        buildings_with_listings = db.query(
            MasterProperty.building_id
        ).join(
            PropertyListing,
            MasterProperty.id == PropertyListing.master_property_id
        ).filter(
            PropertyListing.listing_building_name.isnot(None),
            PropertyListing.listing_building_name != ''
        ).distinct().subquery()
        
        # building_listing_namesが存在しない建物
        missing_buildings = db.query(buildings_with_listings.c.building_id).filter(
            ~buildings_with_listings.c.building_id.in_(
                db.query(BuildingListingName.building_id).distinct()
            )
        ).all()
        
        print(f"building_listing_namesが欠落している建物: {len(missing_buildings)}件")
        
        if not missing_buildings:
            print("✅ すべての建物にbuilding_listing_namesレコードが存在します")
            return
        
        print("-" * 60)
        
        # BuildingListingNameManagerを使用して修正
        manager = BuildingListingNameManager(db)
        
        fixed_count = 0
        for i, (building_id,) in enumerate(missing_buildings, 1):
            if i % 10 == 0:
                print(f"処理中: {i}/{len(missing_buildings)}件...")
            
            try:
                # refresh_building_namesで再生成
                manager.refresh_building_names(building_id)
                
                # 作成されたレコードを確認
                created_records = db.query(BuildingListingName).filter_by(
                    building_id=building_id
                ).count()
                
                if created_records > 0:
                    print(f"建物ID {building_id}: {created_records}件のレコードを作成")
                    fixed_count += 1
                else:
                    print(f"建物ID {building_id}: レコード作成失敗")
                    
            except Exception as e:
                print(f"建物ID {building_id}: エラー - {e}")
                db.rollback()
                continue
        
        if fixed_count > 0:
            db.commit()
            print("-" * 60)
            print(f"✅ {fixed_count}件の建物のbuilding_listing_namesを修正しました")
        else:
            print("修正が必要なレコードはありませんでした")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_missing_building_listing_names()