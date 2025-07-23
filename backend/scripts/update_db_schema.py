#!/usr/bin/env python3
"""
データベーススキーマを更新
property_hashとmaster_property_hashカラムを追加
"""

import sqlite3

def update_schema():
    conn = sqlite3.connect('data/realestate.db')
    cursor = conn.cursor()
    
    # カラムが存在するか確認
    cursor.execute("PRAGMA table_info(properties)")
    columns = [col[1] for col in cursor.fetchall()]
    
    # property_hashカラムを追加
    if 'property_hash' not in columns:
        print("Adding property_hash column...")
        cursor.execute("ALTER TABLE properties ADD COLUMN property_hash TEXT")
    
    # master_property_hashカラムを追加
    if 'master_property_hash' not in columns:
        print("Adding master_property_hash column...")
        cursor.execute("ALTER TABLE properties ADD COLUMN master_property_hash TEXT")
    
    # source_siteカラムを追加
    if 'source_site' not in columns:
        print("Adding source_site column...")
        cursor.execute("ALTER TABLE properties ADD COLUMN source_site TEXT")
    
    # インデックスを作成
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_property_hash ON properties(property_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_property_hash ON properties(master_property_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_site ON properties(source_site)")
        print("Indexes created successfully")
    except Exception as e:
        print(f"Error creating indexes: {e}")
    
    conn.commit()
    conn.close()
    print("Schema update completed!")

if __name__ == "__main__":
    update_schema()