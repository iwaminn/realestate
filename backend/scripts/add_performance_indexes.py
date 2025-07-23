#!/usr/bin/env python3
"""
パフォーマンス改善のためのインデックスを追加
"""

import sys
import os
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)

def add_indexes():
    """パフォーマンス改善のためのインデックスを追加"""
    
    indexes = [
        # 建物名での検索を高速化
        "CREATE INDEX IF NOT EXISTS idx_buildings_normalized_name ON buildings(normalized_name);",
        
        # 建物名の前方一致検索を高速化
        "CREATE INDEX IF NOT EXISTS idx_buildings_normalized_name_pattern ON buildings(normalized_name varchar_pattern_ops);",
        
        # 建物IDでの物件数カウントを高速化
        "CREATE INDEX IF NOT EXISTS idx_master_properties_building_id ON master_properties(building_id);",
        
        # 除外ペアの検索を高速化
        "CREATE INDEX IF NOT EXISTS idx_building_merge_exclusions_pair ON building_merge_exclusions(building1_id, building2_id);",
    ]
    
    with engine.connect() as conn:
        for index_sql in indexes:
            print(f"Creating index: {index_sql[:80]}...")
            conn.execute(text(index_sql))
            conn.commit()
    
    print("All indexes created successfully!")

if __name__ == "__main__":
    add_indexes()