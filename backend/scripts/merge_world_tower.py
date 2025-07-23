#!/usr/bin/env python3
"""WORLD TOWER RESIDENCEとワールドタワーレジデンスを統合"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, BuildingAlias, MasterProperty

def merge_world_tower():
    """重複した建物を統合"""
    
    session = SessionLocal()
    
    try:
        # 英語版を残す（ID: 163）
        english_building = session.query(Building).filter(Building.id == 163).first()
        katakana_building = session.query(Building).filter(Building.id == 327).first()
        
        if not english_building or not katakana_building:
            print("建物が見つかりません")
            return
        
        print(f"統合対象:")
        print(f"  残す: {english_building.normalized_name} (ID: {english_building.id})")
        print(f"  削除: {katakana_building.normalized_name} (ID: {katakana_building.id})")
        
        # カタカナ版の建物名をエイリアスとして追加
        existing_alias = session.query(BuildingAlias).filter(
            BuildingAlias.building_id == english_building.id,
            BuildingAlias.alias_name == katakana_building.normalized_name
        ).first()
        
        if not existing_alias:
            alias = BuildingAlias(
                building_id=english_building.id,
                alias_name=katakana_building.normalized_name,
                source='DUPLICATE_MERGE'
            )
            session.add(alias)
            print(f"  → エイリアス追加: {katakana_building.normalized_name}")
        
        # カタカナ版の物件を英語版に移動
        properties = session.query(MasterProperty).filter(
            MasterProperty.building_id == katakana_building.id
        ).all()
        
        for prop in properties:
            prop.building_id = english_building.id
            print(f"  → 物件移動: 部屋番号 {prop.room_number}")
        
        # カタカナ版のエイリアスも移動
        aliases = session.query(BuildingAlias).filter(
            BuildingAlias.building_id == katakana_building.id
        ).all()
        
        for alias in aliases:
            # 既存チェック
            existing = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == english_building.id,
                BuildingAlias.alias_name == alias.alias_name
            ).first()
            
            if not existing:
                alias.building_id = english_building.id
                print(f"  → エイリアス移動: {alias.alias_name}")
            else:
                session.delete(alias)
        
        # 必要なら変更を反映
        session.flush()
        
        # カタカナ版の建物を削除
        session.delete(katakana_building)
        
        # 変更を保存
        session.commit()
        
        print("\n統合完了！")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    merge_world_tower()