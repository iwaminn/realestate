#!/usr/bin/env python3
"""
既存物件のproperty_hashを再計算（方角を除外）
"""

import sys
import os
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text
import hashlib

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)

def generate_property_hash(building_id: int, room_number: str, 
                          floor_number: int = None, area: float = None, 
                          layout: str = None) -> str:
    """新しい方式でproperty_hashを生成（方角を除外）"""
    if room_number:
        data = f"{building_id}:{room_number}"
    else:
        floor_str = f"F{floor_number}" if floor_number else "F?"
        area_str = f"A{area:.1f}" if area else "A?"
        layout_str = layout if layout else "L?"
        data = f"{building_id}:{floor_str}_{area_str}_{layout_str}"
    
    return hashlib.md5(data.encode()).hexdigest()

def recalculate_hashes():
    """すべての物件のハッシュを再計算"""
    
    # まず現在の状況を調査
    with engine.connect() as conn:
        # 部屋番号がない物件を取得
        query = text("""
            SELECT id, building_id, room_number, floor_number, area, layout, property_hash
            FROM master_properties
            WHERE room_number IS NULL OR room_number = ''
            ORDER BY id
        """)
        
        properties = conn.execute(query).fetchall()
        print(f"部屋番号なしの物件数: {len(properties)}")
        
        # 新旧ハッシュのマッピングを作成
        hash_updates = []
        hash_mapping = {}  # old_hash -> new_hash
        duplicate_new_hashes = {}  # new_hash -> [property_ids]
        
        for prop in properties:
            old_hash = prop.property_hash
            new_hash = generate_property_hash(
                prop.building_id,
                prop.room_number,
                prop.floor_number,
                prop.area,
                prop.layout
            )
            
            if old_hash != new_hash:
                hash_updates.append({
                    'id': prop.id,
                    'old_hash': old_hash,
                    'new_hash': new_hash
                })
                
                # 重複チェック用
                if new_hash not in duplicate_new_hashes:
                    duplicate_new_hashes[new_hash] = []
                duplicate_new_hashes[new_hash].append(prop.id)
                
                hash_mapping[old_hash] = new_hash
        
        print(f"\n更新が必要な物件数: {len(hash_updates)}")
        
        # 重複するハッシュを表示
        duplicate_count = 0
        for new_hash, prop_ids in duplicate_new_hashes.items():
            if len(prop_ids) > 1:
                duplicate_count += 1
                if duplicate_count <= 5:
                    print(f"重複ハッシュ {new_hash}: ID {prop_ids}")
        
        print(f"\n新しいハッシュで重複する物件グループ数: {duplicate_count}")
    
    # 更新を実行
    if hash_updates:
        with engine.begin() as conn:
            try:
                # 重複を避けるため、一時的にユニーク制約を無効化
                conn.execute(text("ALTER TABLE master_properties DROP CONSTRAINT IF EXISTS master_properties_property_hash_key"))
                
                # ハッシュを更新
                print("\n最初の10件の更新:")
                for update in hash_updates[:10]:
                    print(f"ID {update['id']}: {update['old_hash']} -> {update['new_hash']}")
                
                # バッチ更新
                for update in hash_updates:
                    conn.execute(
                        text("UPDATE master_properties SET property_hash = :new_hash WHERE id = :id"),
                        {'new_hash': update['new_hash'], 'id': update['id']}
                    )
                
                # ユニーク制約を再作成
                conn.execute(text("ALTER TABLE master_properties ADD CONSTRAINT master_properties_property_hash_key UNIQUE (property_hash)"))
                
                print(f"\n{len(hash_updates)}件のproperty_hashを更新しました")
                    
            except Exception as e:
                print(f"エラー: {e}")
                raise
    
    # 更新後の重複確認
    with engine.connect() as conn:
        duplicate_check = text("""
            SELECT property_hash, COUNT(*) as cnt
            FROM master_properties
            GROUP BY property_hash
            HAVING COUNT(*) > 1
        """)
        
        duplicates = conn.execute(duplicate_check).fetchall()
        if duplicates:
            print(f"\n警告: {len(duplicates)}個の重複ハッシュが見つかりました")
            print("重複物件の統合が必要です")
            for dup in duplicates[:10]:
                print(f"  ハッシュ {dup.property_hash}: {dup.cnt}件")

if __name__ == "__main__":
    recalculate_hashes()