#!/usr/bin/env python3
"""
物件更新情報APIのパフォーマンス改善用インデックスを追加
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.database import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_indexes():
    """パフォーマンス改善用のインデックスを追加"""
    
    engine = create_engine(DATABASE_URL)
    
    indexes = [
        # 価格履歴検索の高速化
        {
            "name": "idx_listing_price_history_composite",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_listing_price_history_composite 
                ON listing_price_history(recorded_at DESC, property_listing_id, price)
            """
        },
        {
            "name": "idx_listing_price_history_listing_date",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_listing_price_history_listing_date 
                ON listing_price_history(property_listing_id, recorded_at DESC)
            """
        },
        
        # 新着物件検索の高速化
        {
            "name": "idx_property_listings_created_composite",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_property_listings_created_composite 
                ON property_listings(created_at DESC, master_property_id, is_active)
            """
        },
        {
            "name": "idx_property_listings_master_created",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_property_listings_master_created 
                ON property_listings(master_property_id, created_at DESC)
                WHERE is_active = true
            """
        },
        
        # 物件マスターの検索高速化
        {
            "name": "idx_master_properties_building_sold",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_master_properties_building_sold 
                ON master_properties(building_id, sold_at)
                WHERE sold_at IS NULL
            """
        },
        
        # 日付範囲検索の高速化
        {
            "name": "idx_listing_price_history_date_range",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_listing_price_history_date_range 
                ON listing_price_history(DATE(recorded_at), property_listing_id)
            """
        },
        
        # アクティブな掲載の価格取得高速化
        {
            "name": "idx_property_listings_active_price",
            "sql": """
                CREATE INDEX IF NOT EXISTS idx_property_listings_active_price 
                ON property_listings(master_property_id, current_price)
                WHERE is_active = true
            """
        }
    ]
    
    with engine.connect() as conn:
        for index in indexes:
            try:
                logger.info(f"Creating index: {index['name']}")
                conn.execute(text(index['sql']))
                conn.commit()
                logger.info(f"✓ Index {index['name']} created successfully")
            except Exception as e:
                logger.error(f"✗ Failed to create index {index['name']}: {e}")
    
    # 統計情報を更新
    logger.info("Updating table statistics...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ANALYZE listing_price_history"))
            conn.execute(text("ANALYZE property_listings"))
            conn.execute(text("ANALYZE master_properties"))
            conn.commit()
            logger.info("✓ Table statistics updated")
        except Exception as e:
            logger.error(f"✗ Failed to update statistics: {e}")
    
    logger.info("Index creation completed!")

if __name__ == "__main__":
    add_indexes()