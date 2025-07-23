#!/usr/bin/env python3
"""
自動重複検出・統合スクリプト
過去のハッシュ生成ロジックの違いによって発生した重複物件を自動的に検出し統合する
"""

import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import hashlib

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.models import PropertyMergeHistory

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def generate_property_hash(building_id, room_number, floor_number, area, layout, direction):
    """現在のハッシュ生成ロジック"""
    hash_input = f"{building_id}_{room_number or ''}"
    
    # 部屋番号がない場合は、階数・面積・間取り・方角を含める
    if not room_number and floor_number is not None:
        hash_parts = [str(building_id)]
        if floor_number is not None:
            hash_parts.append(f"floor_{floor_number}")
        if area is not None:
            hash_parts.append(f"area_{area:.2f}")
        if layout:
            hash_parts.append(f"layout_{layout}")
        if direction:
            hash_parts.append(f"direction_{direction}")
        hash_input = "_".join(hash_parts)
    
    return hashlib.md5(hash_input.encode()).hexdigest()

def find_duplicate_groups():
    """重複グループを検出"""
    with engine.connect() as conn:
        # 現在のハッシュ生成ロジックで重複する物件を探す
        result = conn.execute(text("""
            WITH hash_calculations AS (
                SELECT 
                    mp.id,
                    mp.building_id,
                    mp.room_number,
                    mp.floor_number,
                    mp.area,
                    mp.layout,
                    mp.direction,
                    mp.property_hash as current_hash,
                    -- 現在のハッシュ生成ロジックを再現
                    CASE 
                        WHEN mp.room_number IS NOT NULL THEN 
                            MD5(mp.building_id::text || '_' || mp.room_number)
                        WHEN mp.floor_number IS NOT NULL THEN
                            MD5(
                                mp.building_id::text || 
                                '_floor_' || mp.floor_number::text ||
                                '_area_' || ROUND(mp.area::numeric, 2)::text ||
                                CASE WHEN mp.layout IS NOT NULL THEN '_layout_' || mp.layout ELSE '' END ||
                                CASE WHEN mp.direction IS NOT NULL THEN '_direction_' || mp.direction ELSE '' END
                            )
                        ELSE 
                            MD5(mp.building_id::text || '_')
                    END as calculated_hash,
                    COUNT(pl.id) as listing_count,
                    MAX(CASE WHEN pl.is_active THEN 1 ELSE 0 END) as has_active_listing,
                    MIN(mp.created_at) as created_at
                FROM master_properties mp
                LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
                GROUP BY mp.id
            )
            SELECT 
                calculated_hash,
                building_id,
                floor_number,
                area,
                layout,
                direction,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'id', id,
                        'current_hash', current_hash,
                        'listing_count', listing_count,
                        'has_active_listing', has_active_listing,
                        'created_at', created_at
                    ) ORDER BY created_at, id
                ) as properties
            FROM hash_calculations
            GROUP BY calculated_hash, building_id, floor_number, area, layout, direction
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """))
        
        duplicate_groups = []
        for row in result:
            duplicate_groups.append({
                'calculated_hash': row.calculated_hash,
                'building_id': row.building_id,
                'floor_number': row.floor_number,
                'area': row.area,
                'layout': row.layout,
                'direction': row.direction,
                'properties': row.properties
            })
        
        return duplicate_groups

def merge_properties(primary_id, secondary_ids, session):
    """物件を統合"""
    try:
        # 掲載情報を移動
        total_moved = 0
        for secondary_id in secondary_ids:
            result = session.execute(text("""
                UPDATE property_listings 
                SET master_property_id = :primary_id 
                WHERE master_property_id = :secondary_id
                RETURNING id
            """), {'primary_id': primary_id, 'secondary_id': secondary_id})
            
            moved_count = result.rowcount
            total_moved += moved_count
            
            if moved_count > 0:
                # 統合履歴を記録
                merge_history = PropertyMergeHistory(
                    primary_property_id=primary_id,
                    secondary_property_id=secondary_id,
                    moved_listings=moved_count,
                    merge_details={'reason': 'Automatic merge due to duplicate hash'},
                    merged_by='auto_merge_script'
                )
                session.add(merge_history)
            
            # 物件を削除
            session.execute(text("""
                DELETE FROM master_properties 
                WHERE id = :secondary_id
            """), {'secondary_id': secondary_id})
        
        return total_moved
    
    except Exception as e:
        print(f"エラー: {e}")
        raise

def auto_merge_duplicates(dry_run=True):
    """重複物件を自動統合"""
    
    print("重複物件の自動検出・統合スクリプト")
    print("=" * 80)
    
    # 重複グループを検出
    duplicate_groups = find_duplicate_groups()
    
    if not duplicate_groups:
        print("重複物件は見つかりませんでした。")
        return
    
    print(f"\n{len(duplicate_groups)}個の重複グループが見つかりました。")
    
    session = Session()
    total_merged = 0
    total_groups_merged = 0
    
    try:
        for i, group in enumerate(duplicate_groups):
            properties = group['properties']
            
            # 最も古い物件または最も掲載数が多い物件を統合先に選ぶ
            # 優先順位: 1. アクティブな掲載がある 2. 掲載数が多い 3. 作成日が古い
            properties_sorted = sorted(
                properties, 
                key=lambda p: (-p['has_active_listing'], -p['listing_count'], p['created_at'])
            )
            
            primary_property = properties_sorted[0]
            secondary_properties = properties_sorted[1:]
            
            print(f"\nグループ {i+1}/{len(duplicate_groups)}:")
            print(f"  建物ID: {group['building_id']}, 階数: {group['floor_number']}F, ")
            print(f"  面積: {group['area']}㎡, 間取り: {group['layout']}, 方角: {group['direction']}")
            print(f"  統合先: 物件ID {primary_property['id']} (掲載数: {primary_property['listing_count']})")
            secondary_list = ', '.join([f"ID {p['id']} (掲載数: {p['listing_count']})" for p in secondary_properties])
            print(f"  統合元: {secondary_list}")
            
            if dry_run:
                print("  → [DRY RUN] 実際の統合は行いません")
            else:
                # 実際に統合を実行
                secondary_ids = [p['id'] for p in secondary_properties]
                moved_count = merge_properties(primary_property['id'], secondary_ids, session)
                
                print(f"  → {len(secondary_ids)}件の物件を統合し、{moved_count}件の掲載情報を移動しました")
                total_merged += len(secondary_ids)
                total_groups_merged += 1
        
        if not dry_run:
            session.commit()
            print(f"\n統合完了: {total_groups_merged}グループ、{total_merged}件の物件を統合しました。")
        else:
            print(f"\n[DRY RUN] {len(duplicate_groups)}グループ、{sum(len(g['properties']) - 1 for g in duplicate_groups)}件の物件が統合対象です。")
            print("\n実際に統合を実行するには、--execute オプションを付けて実行してください。")
    
    except Exception as e:
        session.rollback()
        print(f"\nエラーが発生しました: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='重複物件を自動統合')
    parser.add_argument('--execute', action='store_true', help='実際に統合を実行（デフォルトはドライラン）')
    parser.add_argument('--limit', type=int, help='処理する重複グループ数の上限')
    
    args = parser.parse_args()
    
    auto_merge_duplicates(dry_run=not args.execute)