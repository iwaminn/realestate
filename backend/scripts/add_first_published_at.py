#!/usr/bin/env python3
"""
property_listingsテーブルにfirst_published_atカラムを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """メイン処理"""
    with engine.begin() as conn:
        try:
            # first_published_atカラムを追加
            logger.info("Adding first_published_at column to property_listings...")
            conn.execute(text("""
                ALTER TABLE property_listings 
                ADD COLUMN IF NOT EXISTS first_published_at TIMESTAMP
            """))
            logger.info("Column added successfully")
            
            # 既存のデータを更新
            # first_published_atがNULLの場合、published_atかfirst_seen_atの古い方を設定
            logger.info("Updating existing data...")
            conn.execute(text("""
                UPDATE property_listings
                SET first_published_at = LEAST(
                    COALESCE(published_at, first_seen_at),
                    first_seen_at
                )
                WHERE first_published_at IS NULL
            """))
            
            # 更新件数を確認
            result = conn.execute(text("""
                SELECT COUNT(*) FROM property_listings WHERE first_published_at IS NOT NULL
            """))
            count = result.scalar()
            logger.info(f"Updated {count} records")
            
        except Exception as e:
            logger.error(f"Error: {e}")
            raise

if __name__ == "__main__":
    main()