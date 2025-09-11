#!/usr/bin/env python3
"""
建物名の正規化を全体的に修正するスクリプト
1. buildingsテーブルのnormalized_name
2. master_propertiesテーブルのdisplay_building_name  
3. building_listing_namesテーブルのcanonical_name
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, MasterProperty, BuildingListingName
from app.utils.building_name_normalizer import normalize_building_name
from app.scrapers.data_normalizer import canonicalize_building_name
from sqlalchemy import or_


def fix_all_building_names():
    """すべての建物名関連フィールドを再正規化"""
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("建物名の正規化処理を開始します")
        print("=" * 60)
        
        # 1. buildingsテーブルのnormalized_nameを修正
        print("\n1. buildingsテーブルの処理")
        print("-" * 40)
        
        buildings = db.query(Building).filter(
            or_(
                Building.normalized_name.like('%＆%'),
                Building.normalized_name.like('%&%'),
                Building.normalized_name.like('%　%')
            )
        ).all()
        
        building_count = 0
        for building in buildings:
            old_name = building.normalized_name
            new_name = normalize_building_name(old_name)
            
            if old_name != new_name:
                print(f"建物ID {building.id}: {old_name} → {new_name}")
                building.normalized_name = new_name
                building_count += 1
        
        print(f"→ {building_count}件の建物名を更新")
        
        # 2. master_propertiesテーブルのdisplay_building_nameを修正
        print("\n2. master_propertiesテーブルの処理")
        print("-" * 40)
        
        properties = db.query(MasterProperty).filter(
            or_(
                MasterProperty.display_building_name.like('%＆%'),
                MasterProperty.display_building_name.like('%&%'),
                MasterProperty.display_building_name.like('%　%')
            )
        ).all()
        
        property_count = 0
        for prop in properties:
            if prop.display_building_name:
                old_name = prop.display_building_name
                new_name = normalize_building_name(old_name)
                
                if old_name != new_name:
                    print(f"物件ID {prop.id}: {old_name} → {new_name}")
                    prop.display_building_name = new_name
                    property_count += 1
        
        print(f"→ {property_count}件の物件表示名を更新")
        
        # 3. building_listing_namesテーブルのcanonical_nameを修正
        print("\n3. building_listing_namesテーブルの処理")
        print("-" * 40)
        
        # すべてのレコードを処理（canonical_nameは常にlisting_nameから生成されるため）
        listing_names = db.query(BuildingListingName).all()
        
        listing_count = 0
        for listing in listing_names:
            old_canonical = listing.canonical_name
            new_canonical = canonicalize_building_name(listing.listing_name)
            
            if old_canonical != new_canonical:
                print(f"建物ID {listing.building_id}, 掲載名 '{listing.listing_name}':")
                print(f"  {old_canonical} → {new_canonical}")
                listing.canonical_name = new_canonical
                listing_count += 1
        
        print(f"→ {listing_count}件のcanonical_nameを更新")
        
        # コミット
        if building_count > 0 or property_count > 0 or listing_count > 0:
            db.commit()
            print("\n" + "=" * 60)
            print("✅ 正規化処理が完了しました")
            print(f"  - 建物: {building_count}件")
            print(f"  - 物件: {property_count}件")
            print(f"  - 掲載名: {listing_count}件")
            print("=" * 60)
        else:
            print("\n更新が必要なレコードはありませんでした")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_all_building_names()