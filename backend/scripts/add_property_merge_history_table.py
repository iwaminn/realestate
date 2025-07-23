#!/usr/bin/env python3
"""
物件統合履歴テーブルを追加するスクリプト
"""

import sys
import os
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)

def add_property_merge_history_table():
    """物件統合履歴テーブルを追加"""
    
    with engine.connect() as conn:
        # テーブルが既に存在するかチェック
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'property_merge_history'
            );
        """))
        
        if result.scalar():
            print("property_merge_history table already exists.")
            return
        
        # テーブル作成
        print("Creating property_merge_history table...")
        conn.execute(text("""
            CREATE TABLE property_merge_history (
                id SERIAL PRIMARY KEY,
                primary_property_id INTEGER NOT NULL REFERENCES master_properties(id),
                secondary_property_id INTEGER NOT NULL,
                moved_listings INTEGER DEFAULT 0,
                merge_details JSONB,
                merged_by VARCHAR(100),
                merged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reverted_at TIMESTAMP,
                reverted_by VARCHAR(100)
            );
        """))
        
        # インデックス作成
        print("Creating indexes...")
        conn.execute(text("""
            CREATE INDEX idx_property_merge_history_primary ON property_merge_history(primary_property_id);
        """))
        
        conn.execute(text("""
            CREATE INDEX idx_property_merge_history_created ON property_merge_history(merged_at);
        """))
        
        conn.commit()
        
    print("property_merge_history table created successfully!")

if __name__ == "__main__":
    add_property_merge_history_table()