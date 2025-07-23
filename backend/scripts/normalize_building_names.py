#!/usr/bin/env python3
"""既存の建物名を正規化し、部屋番号を抽出するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import Building, BuildingAlias, MasterProperty, PropertyListing
from app.utils.building_normalizer import BuildingNameNormalizer
import os
from dotenv import load_dotenv

# 環境変数を読み込む
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def normalize_existing_buildings():
    """既存の建物名を正規化し、部屋番号がある場合は抽出"""
    
    # データベース接続
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    normalizer = BuildingNameNormalizer()
    
    try:
        # 部屋番号が含まれそうな建物を検索
        # 末尾に数字があるパターンを持つ建物を抽出
        buildings = session.query(Building).filter(
            text("normalized_name ~ '\\s+\\d{3,4}$' OR normalized_name ~ '[-・]\\d{3,4}$'")
        ).all()
        
        print(f"部屋番号が含まれている可能性のある建物: {len(buildings)}件")
        
        for building in buildings:
            print(f"\n建物ID {building.id}: {building.normalized_name}")
            
            # 建物名から部屋番号を抽出
            clean_name, room_number = normalizer.extract_room_number(building.normalized_name)
            
            if room_number:
                print(f"  → 部屋番号 '{room_number}' を抽出")
                print(f"  → クリーンな建物名: '{clean_name}'")
                
                # 正規化した建物名
                normalized_clean_name = normalizer.normalize(clean_name)
                
                # 同じ建物が既に存在するか確認
                existing_building = session.query(Building).filter(
                    Building.normalized_name == normalized_clean_name,
                    Building.id != building.id
                ).first()
                
                if existing_building:
                    print(f"  → 既存の建物 (ID: {existing_building.id}) にマージ")
                    
                    # この建物に紐づく物件を既存の建物に移行
                    properties = session.query(MasterProperty).filter(
                        MasterProperty.building_id == building.id
                    ).all()
                    
                    for prop in properties:
                        # 部屋番号が空の場合は抽出した部屋番号を設定
                        if not prop.room_number:
                            prop.room_number = room_number
                            print(f"    → 物件ID {prop.id} に部屋番号 '{room_number}' を設定")
                        
                        # 建物IDを更新
                        prop.building_id = existing_building.id
                    
                    # 元の建物名をエイリアスとして保存
                    alias = BuildingAlias(
                        building_id=existing_building.id,
                        alias_name=building.normalized_name,
                        source='NORMALIZATION'
                    )
                    session.add(alias)
                    
                    # 元の建物を削除
                    session.delete(building)
                    
                else:
                    print(f"  → 建物名を更新: '{normalized_clean_name}'")
                    
                    # 元の建物名をエイリアスとして保存
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=building.normalized_name,
                        source='NORMALIZATION'
                    )
                    session.add(alias)
                    
                    # 建物名を更新
                    building.normalized_name = normalized_clean_name
                    
                    # この建物に紐づく物件で部屋番号が空のものに設定
                    properties = session.query(MasterProperty).filter(
                        MasterProperty.building_id == building.id,
                        MasterProperty.room_number == ''
                    ).all()
                    
                    for prop in properties:
                        prop.room_number = room_number
                        print(f"    → 物件ID {prop.id} に部屋番号 '{room_number}' を設定")
        
        # 変更をコミット
        session.commit()
        print(f"\n正規化完了")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    normalize_existing_buildings()