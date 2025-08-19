#!/usr/bin/env python3
"""
建物重複管理の高速化用インデックスを追加するスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import engine
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_indexes():
    """パフォーマンス向上のためのインデックスを追加"""
    
    with engine.connect() as conn:
        # 既存のインデックスをチェック
        result = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'buildings'
        """))
        existing_indexes = {row[0] for row in result}
        
        # 新しいインデックスを追加
        indexes_to_add = [
            # 重複検出の高速化用複合インデックス
            ("idx_buildings_duplicate_detection", 
             "CREATE INDEX IF NOT EXISTS idx_buildings_duplicate_detection ON buildings(normalized_name, built_year, total_floors)"),
            
            # 属性ベースの検索用インデックス
            ("idx_buildings_attributes", 
             "CREATE INDEX IF NOT EXISTS idx_buildings_attributes ON buildings(built_year, total_floors, total_units)"),
            
            # 住所前方一致検索用インデックス
            ("idx_buildings_normalized_address_text", 
             "CREATE INDEX IF NOT EXISTS idx_buildings_normalized_address_text ON buildings(normalized_address text_pattern_ops)"),
        ]
        
        for index_name, create_sql in indexes_to_add:
            if index_name not in existing_indexes:
                logger.info(f"インデックス {index_name} を作成中...")
                conn.execute(text(create_sql))
                conn.commit()
                logger.info(f"インデックス {index_name} を作成しました")
            else:
                logger.info(f"インデックス {index_name} は既に存在します")
        
        # BuildingListingNameテーブルのインデックスも最適化
        result = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'building_listing_names'
        """))
        existing_listing_indexes = {row[0] for row in result}
        
        listing_indexes = [
            ("idx_building_listing_names_building_batch",
             "CREATE INDEX IF NOT EXISTS idx_building_listing_names_building_batch ON building_listing_names(building_id, canonical_name)"),
        ]
        
        for index_name, create_sql in listing_indexes:
            if index_name not in existing_listing_indexes:
                logger.info(f"インデックス {index_name} を作成中...")
                conn.execute(text(create_sql))
                conn.commit()
                logger.info(f"インデックス {index_name} を作成しました")
            else:
                logger.info(f"インデックス {index_name} は既に存在します")
        
        logger.info("すべてのインデックスの追加が完了しました")

if __name__ == "__main__":
    add_indexes()