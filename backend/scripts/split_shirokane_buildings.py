#!/usr/bin/env python3
"""白金ザ・スカイを東棟と西棟に分離するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Building, BuildingAlias, MasterProperty, PropertyListing
import os
from dotenv import load_dotenv

# 環境変数を読み込む
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def split_shirokane_buildings():
    """白金ザ・スカイを東棟と西棟に分離"""
    
    # データベース接続
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        # 現在の統合された建物を取得
        main_building = session.query(Building).filter(
            Building.normalized_name == "白金ザ・スカイ"
        ).first()
        
        if not main_building:
            print("白金ザ・スカイが見つかりません")
            return
        
        print(f"統合された建物: ID {main_building.id} - {main_building.normalized_name}")
        
        # 東棟と西棟の建物を作成
        east_building = Building(
            normalized_name="白金ザ・スカイE棟",
            address=main_building.address,
            built_year=main_building.built_year,
            total_floors=main_building.total_floors,
            basement_floors=main_building.basement_floors,
            total_units=main_building.total_units,
            structure=main_building.structure,
            land_rights=main_building.land_rights,
            parking_info=main_building.parking_info
        )
        session.add(east_building)
        
        west_building = Building(
            normalized_name="白金ザ・スカイW棟",
            address=main_building.address,
            built_year=main_building.built_year,
            total_floors=19,  # W棟は19階建て
            basement_floors=0,
            total_units=main_building.total_units,
            structure=main_building.structure,
            land_rights=main_building.land_rights,
            parking_info=main_building.parking_info
        )
        session.add(west_building)
        
        session.flush()
        
        print(f"東棟を作成: ID {east_building.id} - {east_building.normalized_name}")
        print(f"西棟を作成: ID {west_building.id} - {west_building.normalized_name}")
        
        # 物件を振り分ける
        # まず、各物件がどの棟に属するかを特定
        properties = session.query(MasterProperty).filter(
            MasterProperty.building_id == main_building.id
        ).all()
        
        print(f"\n物件の振り分けを開始: {len(properties)}件")
        
        for prop in properties:
            # この物件の掲載情報からタイトルを取得
            listing = session.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop.id
            ).first()
            
            if listing:
                title = listing.title
                # タイトルから棟を判定
                if 'W棟' in title or '西棟' in title:
                    prop.building_id = west_building.id
                    print(f"  物件ID {prop.id} → 西棟（タイトル: {title[:30]}...）")
                elif 'E棟' in title or '東棟' in title or 'Ｅ棟' in title:
                    prop.building_id = east_building.id
                    print(f"  物件ID {prop.id} → 東棟（タイトル: {title[:30]}...）")
                else:
                    # 棟が特定できない場合は階数で判定
                    if prop.floor_number and prop.floor_number <= 19:
                        # 19階以下は西棟の可能性
                        prop.building_id = west_building.id
                        print(f"  物件ID {prop.id} → 西棟（{prop.floor_number}階）")
                    else:
                        prop.building_id = east_building.id
                        print(f"  物件ID {prop.id} → 東棟（{prop.floor_number}階）")
        
        # エイリアスを振り分ける
        aliases = session.query(BuildingAlias).filter(
            BuildingAlias.building_id == main_building.id
        ).all()
        
        for alias in aliases:
            if 'W棟' in alias.alias_name or '西棟' in alias.alias_name:
                alias.building_id = west_building.id
                print(f"  エイリアス '{alias.alias_name}' → 西棟")
            elif 'E棟' in alias.alias_name or '東棟' in alias.alias_name or 'Ｅ棟' in alias.alias_name:
                alias.building_id = east_building.id
                print(f"  エイリアス '{alias.alias_name}' → 東棟")
            else:
                # その他（"白金ザ・スカイ"など）は削除
                session.delete(alias)
                print(f"  エイリアス '{alias.alias_name}' → 削除")
        
        # 変更を一旦フラッシュ
        session.flush()
        
        # 元の統合建物を削除
        session.delete(main_building)
        print(f"\n統合建物を削除: ID {main_building.id}")
        
        # 変更をコミット
        session.commit()
        print("\n分離完了")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    split_shirokane_buildings()