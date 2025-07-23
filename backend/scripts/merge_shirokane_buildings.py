#!/usr/bin/env python3
"""白金ザ・スカイの重複建物を統合するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Building, BuildingAlias, MasterProperty
import os
from dotenv import load_dotenv

# 環境変数を読み込む
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def merge_shirokane_buildings():
    """白金ザ・スカイの建物を統合"""
    
    # データベース接続
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        # 白金ザ・スカイ関連の建物を取得
        buildings = session.query(Building).filter(
            Building.normalized_name.like('%白金ザ・スカイ%')
        ).order_by(Building.built_year.desc(), Building.id).all()
        
        print(f"白金ザ・スカイ関連の建物: {len(buildings)}件")
        for b in buildings:
            print(f"  ID: {b.id}, 名前: {b.normalized_name}, 住所: {b.address}, 築年: {b.built_year}")
        
        if len(buildings) <= 1:
            print("統合する建物がありません")
            return
        
        # メイン建物として最新（2023年築）かつIDが最も小さいものを選択
        main_building = None
        for b in buildings:
            if b.built_year == 2023:
                if main_building is None or b.id < main_building.id:
                    main_building = b
        
        if not main_building:
            # 2023年築がない場合は最初の建物を使用
            main_building = buildings[0]
        
        print(f"\nメイン建物として選択: ID {main_building.id} - {main_building.normalized_name}")
        
        # メイン建物の情報を更新（最も詳細な情報で）
        for b in buildings:
            if b.id == main_building.id:
                continue
                
            # より詳細な情報があれば更新
            if b.total_floors and (not main_building.total_floors or b.total_floors > main_building.total_floors):
                main_building.total_floors = b.total_floors
            if b.basement_floors and not main_building.basement_floors:
                main_building.basement_floors = b.basement_floors
            if b.total_units and not main_building.total_units:
                main_building.total_units = b.total_units
            if b.structure and not main_building.structure:
                main_building.structure = b.structure
            if b.land_rights and not main_building.land_rights:
                main_building.land_rights = b.land_rights
            if b.parking_info and not main_building.parking_info:
                main_building.parking_info = b.parking_info
        
        # 他の建物をメイン建物に統合
        for b in buildings:
            if b.id == main_building.id:
                continue
            
            print(f"\n統合: {b.normalized_name} (ID: {b.id}) → {main_building.normalized_name} (ID: {main_building.id})")
            
            # この建物の名前をエイリアスとして保存
            existing_alias = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == main_building.id,
                BuildingAlias.alias_name == b.normalized_name
            ).first()
            
            if not existing_alias:
                alias = BuildingAlias(
                    building_id=main_building.id,
                    alias_name=b.normalized_name,
                    source='MERGE'
                )
                session.add(alias)
                print(f"  エイリアス追加: {b.normalized_name}")
            
            # この建物のエイリアスもメイン建物に移行
            aliases = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == b.id
            ).all()
            
            for alias in aliases:
                # 既存チェック
                existing = session.query(BuildingAlias).filter(
                    BuildingAlias.building_id == main_building.id,
                    BuildingAlias.alias_name == alias.alias_name
                ).first()
                
                if not existing:
                    new_alias = BuildingAlias(
                        building_id=main_building.id,
                        alias_name=alias.alias_name,
                        source=alias.source
                    )
                    session.add(new_alias)
                    print(f"  エイリアス移行: {alias.alias_name}")
                
                # 古いエイリアスは削除
                session.delete(alias)
            
            # この建物に紐づく物件をメイン建物に移行
            properties = session.query(MasterProperty).filter(
                MasterProperty.building_id == b.id
            ).all()
            
            for prop in properties:
                prop.building_id = main_building.id
                print(f"  物件移行: ID {prop.id}")
            
            # コミットして外部キー制約を満たす
            session.flush()
            
            # 元の建物を削除
            session.delete(b)
        
        # 棟情報を含む統一された建物名に更新
        main_building.normalized_name = "白金ザ・スカイ"
        print(f"\n建物名を統一: {main_building.normalized_name}")
        
        # 変更をコミット
        session.commit()
        print(f"\n統合完了")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    merge_shirokane_buildings()