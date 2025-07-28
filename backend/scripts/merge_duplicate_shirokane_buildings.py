#!/usr/bin/env python3
"""
白金ザスカイ関連の重複建物を統合するスクリプト
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Building, BuildingAlias, MasterProperty, PropertyListing, BuildingMergeHistory
from backend.app.utils.building_merger import merge_buildings_internal
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_and_merge_shirokane_buildings():
    """白金ザスカイ関連の建物を分析・統合"""
    session = SessionLocal()
    
    try:
        # 白金ザスカイE棟の重複を確認
        east_buildings = session.query(Building).filter(
            Building.normalized_name.like('%白金%スカイ%E%')
        ).all()
        
        print("=== 白金ザスカイE棟関連の建物 ===")
        for b in east_buildings:
            prop_count = session.query(MasterProperty).filter_by(building_id=b.id).count()
            listing_count = session.query(PropertyListing).join(MasterProperty).filter(
                MasterProperty.building_id == b.id
            ).count()
            print(f"ID: {b.id}, 名前: {b.normalized_name}, 物件数: {prop_count}, 掲載数: {listing_count}")
        
        # 白金ザスカイ（棟なし）の確認
        main_buildings = session.query(Building).filter(
            Building.normalized_name.like('%白金%スカイ%')
        ).filter(
            ~Building.normalized_name.like('%棟%')
        ).all()
        
        print("\n=== 白金ザスカイ（棟なし）関連の建物 ===")
        for b in main_buildings:
            prop_count = session.query(MasterProperty).filter_by(building_id=b.id).count()
            listing_count = session.query(PropertyListing).join(MasterProperty).filter(
                MasterProperty.building_id == b.id
            ).count()
            print(f"ID: {b.id}, 名前: {b.normalized_name}, 物件数: {prop_count}, 掲載数: {listing_count}")
        
        # ユーザーに確認
        print("\n統合を実行しますか？")
        print("1. 白金ザスカイE棟の重複を統合（ID: 1665, 2326 → 361）")
        print("2. 白金ザスカイ（棟なし）の重複を統合（ID: 687 → 1701）")
        print("3. 両方実行")
        print("4. キャンセル")
        
        choice = input("\n選択してください (1-4): ")
        
        if choice == "1" or choice == "3":
            # 白金ザスカイE棟の統合
            print("\n白金ザスカイE棟の統合を実行します...")
            
            # ID: 361を主建物とする
            primary_east = session.query(Building).filter_by(id=361).first()
            if primary_east:
                # ID: 1665を統合
                building_1665 = session.query(Building).filter_by(id=1665).first()
                if building_1665:
                    print(f"統合中: {building_1665.normalized_name} (ID: {building_1665.id}) → {primary_east.normalized_name} (ID: {primary_east.id})")
                    merge_buildings_internal(session, primary_east.id, building_1665.id, merge_type="duplicate")
                
                # ID: 2326を統合
                building_2326 = session.query(Building).filter_by(id=2326).first()
                if building_2326:
                    print(f"統合中: {building_2326.normalized_name} (ID: {building_2326.id}) → {primary_east.normalized_name} (ID: {primary_east.id})")
                    merge_buildings_internal(session, primary_east.id, building_2326.id, merge_type="duplicate")
                
                print("白金ザスカイE棟の統合が完了しました。")
        
        if choice == "2" or choice == "3":
            # 白金ザスカイ（棟なし）の統合
            print("\n白金ザスカイ（棟なし）の統合を実行します...")
            
            # ID: 1701を主建物とする
            primary_main = session.query(Building).filter_by(id=1701).first()
            building_687 = session.query(Building).filter_by(id=687).first()
            
            if primary_main and building_687:
                print(f"統合中: {building_687.normalized_name} (ID: {building_687.id}) → {primary_main.normalized_name} (ID: {primary_main.id})")
                merge_buildings_internal(session, primary_main.id, building_687.id, merge_type="duplicate")
                print("白金ザスカイ（棟なし）の統合が完了しました。")
        
        if choice in ["1", "2", "3"]:
            session.commit()
            print("\n統合処理が完了しました。")
            
            # 結果の確認
            print("\n=== 統合後の確認 ===")
            remaining = session.query(Building).filter(
                Building.normalized_name.like('%白金%スカイ%')
            ).all()
            
            for b in remaining:
                prop_count = session.query(MasterProperty).filter_by(building_id=b.id).count()
                listing_count = session.query(PropertyListing).join(MasterProperty).filter(
                    MasterProperty.building_id == b.id
                ).count()
                print(f"ID: {b.id}, 名前: {b.normalized_name}, 物件数: {prop_count}, 掲載数: {listing_count}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    analyze_and_merge_shirokane_buildings()