#!/usr/bin/env python3
"""
重複した建物を安全にクリーンアップするスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, MasterProperty, PropertyListing, BuildingAlias, BuildingExternalId

def cleanup_buildings():
    """建物の重複を整理"""
    session = SessionLocal()
    
    try:
        # 1. 白金ザ・スカイの重複を手動で処理
        print("=== 白金ザ・スカイの重複整理 ===")
        
        # メインの建物（ID: 569）を取得
        main_building = session.query(Building).filter(Building.id == 569).first()
        if not main_building:
            print("メイン建物が見つかりません")
            return
        
        # 他の白金ザ・スカイ関連建物を探す
        duplicate_buildings = session.query(Building).filter(
            Building.normalized_name.like('%白金ザ%スカイ%'),
            Building.id != 569
        ).all()
        
        print(f"メイン建物: {main_building.normalized_name} (ID: {main_building.id})")
        print(f"重複建物数: {len(duplicate_buildings)}")
        
        for dup_building in duplicate_buildings:
            print(f"\n処理中: {dup_building.normalized_name} (ID: {dup_building.id})")
            
            # この建物の物件を取得
            properties = session.query(MasterProperty).filter(
                MasterProperty.building_id == dup_building.id
            ).all()
            
            print(f"  物件数: {len(properties)}")
            
            for prop in properties:
                # 同じ属性の物件がメイン建物に存在するか確認
                existing = session.query(MasterProperty).filter(
                    MasterProperty.building_id == main_building.id,
                    MasterProperty.floor_number == prop.floor_number,
                    MasterProperty.area == prop.area,
                    MasterProperty.layout == prop.layout,
                    MasterProperty.direction == prop.direction
                ).first()
                
                if existing:
                    print(f"  既存物件あり: 階{prop.floor_number}, {prop.area}㎡, {prop.direction}")
                    # 掲載情報を既存物件に移動
                    listings = session.query(PropertyListing).filter(
                        PropertyListing.master_property_id == prop.id
                    ).all()
                    
                    for listing in listings:
                        # 同じURLの掲載が既に存在しないか確認
                        existing_listing = session.query(PropertyListing).filter(
                            PropertyListing.master_property_id == existing.id,
                            PropertyListing.url == listing.url
                        ).first()
                        
                        if not existing_listing:
                            listing.master_property_id = existing.id
                            print(f"    掲載移動: {listing.source_site}")
                        else:
                            print(f"    掲載削除（重複）: {listing.source_site}")
                            session.delete(listing)
                    
                    # 元の物件を削除
                    session.delete(prop)
                else:
                    # 物件をメイン建物に移動
                    print(f"  物件移動: 階{prop.floor_number}, {prop.area}㎡, {prop.direction}")
                    prop.building_id = main_building.id
            
            # 建物関連データを処理
            # BuildingAliasを移動
            aliases = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == dup_building.id
            ).all()
            
            for alias in aliases:
                session.delete(alias)
                print(f"  エイリアス削除: {alias.alias_name}")
            
            # BuildingExternalIdを移動
            external_ids = session.query(BuildingExternalId).filter(
                BuildingExternalId.building_id == dup_building.id
            ).all()
            
            for ext_id in external_ids:
                session.delete(ext_id)
                print(f"  外部ID削除: {ext_id.external_id}")
            
            # 建物を削除
            session.delete(dup_building)
            print(f"  建物削除: {dup_building.normalized_name}")
        
        # 変更をコミット
        session.commit()
        print("\n処理完了")
        
    except Exception as e:
        session.rollback()
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    cleanup_buildings()