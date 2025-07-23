#!/usr/bin/env python3
"""
重複している可能性がある物件を検出するスクリプト
"""

import sys
import os
from sqlalchemy import create_engine, text
import hashlib

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)

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

def find_duplicate_properties():
    """重複している可能性がある物件を検出"""
    
    with engine.connect() as conn:
        # 同じ建物内で同じ階数・面積・間取り・方角の物件を探す
        result = conn.execute(text("""
            WITH property_details AS (
                SELECT 
                    mp.id,
                    mp.building_id,
                    mp.floor_number,
                    mp.area,
                    mp.layout,
                    mp.direction,
                    mp.property_hash,
                    COUNT(pl.id) as listing_count
                FROM master_properties mp
                LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
                WHERE mp.room_number IS NULL
                GROUP BY mp.id
            ),
            property_groups AS (
                SELECT 
                    pd.building_id,
                    pd.floor_number,
                    pd.area,
                    pd.layout,
                    pd.direction,
                    COUNT(*) as duplicate_count,
                    STRING_AGG(
                        pd.id::text || ':' || pd.property_hash || ':' || pd.listing_count::text,
                        ', ' ORDER BY pd.id
                    ) as all_properties
                FROM property_details pd
                GROUP BY pd.building_id, pd.floor_number, pd.area, pd.layout, pd.direction
                HAVING COUNT(*) > 1
            )
            SELECT 
                pg.*,
                b.normalized_name
            FROM property_groups pg
            JOIN buildings b ON pg.building_id = b.id
            ORDER BY pg.duplicate_count DESC
            LIMIT 20
        """))
        
        print("同じ建物内で重複の可能性がある物件（部屋番号なし）:")
        print("=" * 120)
        
        duplicates_found = False
        for row in result:
            duplicates_found = True
            print(f"\n建物: {row.normalized_name} (ID: {row.building_id})")
            print(f"  階数: {row.floor_number}F, 面積: {row.area}㎡, 間取り: {row.layout}, 方角: {row.direction}")
            print(f"  重複数: {row.duplicate_count}")
            
            # 正しいハッシュを計算
            correct_hash = generate_property_hash(
                row.building_id, None, row.floor_number, 
                row.area, row.layout, row.direction
            )
            print(f"  正しいハッシュ: {correct_hash}")
            print(f"  物件リスト:")
            
            # 各物件の情報を表示
            properties = row.all_properties.split(', ')
            for prop in properties:
                parts = prop.split(':')
                if len(parts) >= 3:
                    prop_id = parts[0]
                    prop_hash = parts[1]
                    listing_count = parts[2]
                    status = '✓' if prop_hash == correct_hash else '✗'
                    print(f"    物件ID {prop_id}: hash={prop_hash} (掲載数: {listing_count}) {status}")
        
        if not duplicates_found:
            print("重複の可能性がある物件は見つかりませんでした")
        
        # 物件ID 1534の詳細を確認
        print("\n\n物件ID 1534の詳細確認:")
        print("=" * 80)
        
        result = conn.execute(text("""
            SELECT 
                mp.*,
                b.normalized_name,
                COUNT(pl.id) as listing_count
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
            WHERE mp.id = 1534
            GROUP BY mp.id, b.normalized_name
        """))
        
        row = result.fetchone()
        if row:
            print(f"ID: {row.id}")
            print(f"建物: {row.normalized_name} (ID: {row.building_id})")
            print(f"部屋番号: {row.room_number or '-'}")
            print(f"階数: {row.floor_number}F")
            print(f"面積: {row.area}㎡")
            print(f"間取り: {row.layout}")
            print(f"方角: {row.direction}")
            print(f"property_hash: {row.property_hash}")
            print(f"掲載数: {row.listing_count}")

if __name__ == "__main__":
    find_duplicate_properties()