#!/usr/bin/env python3
"""
パフォーマンス向上のためのインデックスを追加
"""

import os
import sys
from pathlib import Path

# プロジェクトルートへのパスを追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import engine

def add_indexes():
    """パフォーマンス向上のためのインデックスを追加"""
    
    indexes = [
        # 建物検索用インデックス
        "CREATE INDEX IF NOT EXISTS idx_buildings_normalized_name_gin ON buildings USING gin(normalized_name gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_buildings_address_gin ON buildings USING gin(address gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_buildings_built_year ON buildings(built_year)",
        
        # 物件検索用インデックス
        "CREATE INDEX IF NOT EXISTS idx_master_properties_building_id ON master_properties(building_id)",
        "CREATE INDEX IF NOT EXISTS idx_master_properties_area ON master_properties(area)",
        "CREATE INDEX IF NOT EXISTS idx_master_properties_layout ON master_properties(layout)",
        "CREATE INDEX IF NOT EXISTS idx_master_properties_floor_number ON master_properties(floor_number)",
        
        # 掲載情報検索用インデックス
        "CREATE INDEX IF NOT EXISTS idx_property_listings_master_property_id_active ON property_listings(master_property_id, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_property_listings_current_price ON property_listings(current_price) WHERE is_active = true",
        "CREATE INDEX IF NOT EXISTS idx_property_listings_updated_at ON property_listings(updated_at DESC)",
        
        # 複合インデックス（よく使われる組み合わせ）
        "CREATE INDEX IF NOT EXISTS idx_master_properties_building_area_layout ON master_properties(building_id, area, layout)",
        "CREATE INDEX IF NOT EXISTS idx_buildings_address_year ON buildings(address, built_year)",
    ]
    
    with engine.connect() as conn:
        # pg_trgm拡張を有効化（テキスト検索用）
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()
        
        # インデックスを作成
        for index_sql in indexes:
            try:
                print(f"Creating index: {index_sql[:60]}...")
                conn.execute(text(index_sql))
                conn.commit()
                print("  ✓ Created")
            except Exception as e:
                print(f"  ✗ Error: {e}")
    
    print("\nインデックスの作成が完了しました。")
    
    # 統計情報を更新
    with engine.connect() as conn:
        print("\n統計情報を更新中...")
        conn.execute(text("ANALYZE buildings"))
        conn.execute(text("ANALYZE master_properties"))
        conn.execute(text("ANALYZE property_listings"))
        conn.commit()
        print("統計情報の更新が完了しました。")

if __name__ == "__main__":
    add_indexes()