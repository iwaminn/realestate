#!/usr/bin/env python3
"""
重複した建物を統合するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, MasterProperty, PropertyListing, BuildingAlias
from app.utils.building_normalizer import BuildingNameNormalizer

def merge_shirokane_sky_buildings():
    """白金ザ・スカイ関連の建物を統合"""
    session = SessionLocal()
    normalizer = BuildingNameNormalizer()

    # 白金ザ・スカイ関連の建物を取得
    buildings = session.query(Building).filter(
        Building.normalized_name.like('%白金ザ%スカイ%')
    ).all()

    print('=== 白金ザ・スカイ関連の建物 ===')
    for b in buildings:
        print(f'ID: {b.id}, 名前: {b.normalized_name}')

    # メインの建物を選択（最も基本的な名前）
    main_building = session.query(Building).filter(
        Building.normalized_name == '白金ザ・スカイ'
    ).first()

    if not main_building:
        # なければ最初のものを使用
        main_building = buildings[0] if buildings else None
        if main_building:
            print(f'\nメイン建物として使用: {main_building.normalized_name}')

    if not main_building:
        print('建物が見つかりません')
        return

    # 他の建物の物件をメイン建物に移動
    moved_count = 0
    for b in buildings:
        if b.id != main_building.id:
            # この建物の物件を取得
            properties = session.query(MasterProperty).filter(
                MasterProperty.building_id == b.id
            ).all()
            
            for p in properties:
                # 同じ属性の物件がメイン建物に既に存在するか確認
                existing = session.query(MasterProperty).filter(
                    MasterProperty.building_id == main_building.id,
                    MasterProperty.floor_number == p.floor_number,
                    MasterProperty.area == p.area,
                    MasterProperty.layout == p.layout,
                    MasterProperty.direction == p.direction
                ).first()
                
                if not existing:
                    # 存在しなければ移動
                    p.building_id = main_building.id
                    moved_count += 1
                    print(f'  物件ID {p.id} を移動: 階{p.floor_number}, {p.area}㎡, {p.direction}')
                else:
                    # 既に存在する場合は、掲載情報を移動
                    listings = session.query(PropertyListing).filter(
                        PropertyListing.master_property_id == p.id
                    ).all()
                    
                    for l in listings:
                        l.master_property_id = existing.id
                        print(f'  掲載ID {l.id} を既存物件 {existing.id} に移動')
                    
                    # 元の物件を削除
                    session.delete(p)
            
            # 建物エイリアスを追加
            if b.normalized_name != main_building.normalized_name:
                # 既存のエイリアスをチェック
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
                    print(f'\nエイリアス追加: {b.normalized_name}')
            
            # この建物の既存のエイリアスをメイン建物に移動
            old_aliases = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == b.id
            ).all()
            
            for old_alias in old_aliases:
                # 同じエイリアスが既に存在するかチェック
                existing = session.query(BuildingAlias).filter(
                    BuildingAlias.building_id == main_building.id,
                    BuildingAlias.alias_name == old_alias.alias_name
                ).first()
                
                if not existing:
                    old_alias.building_id = main_building.id
                    print(f'  エイリアス移動: {old_alias.alias_name}')
                else:
                    # 重複する場合は削除
                    session.delete(old_alias)
            
            # 空になった建物を削除
            session.delete(b)

    print(f'\n合計 {moved_count} 物件を移動しました')

    # 変更を保存
    try:
        session.commit()
        print('変更を保存しました')
    except Exception as e:
        session.rollback()
        print(f'エラーが発生しました: {e}')
    finally:
        session.close()

if __name__ == "__main__":
    merge_shirokane_sky_buildings()