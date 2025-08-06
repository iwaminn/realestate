#!/usr/bin/env python3
"""
BuildingMergeHistoryテーブルからis_activeカラムを削除するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def remove_is_active_column():
    """is_activeカラムを削除"""
    session = Session()
    
    try:
        # 1. カラムの存在確認
        logger.info("Checking if is_active column exists in building_merge_history...")
        
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'building_merge_history' 
              AND column_name = 'is_active'
        """)).fetchone()
        
        if not result:
            logger.info("is_active column does not exist in building_merge_history table.")
            return
        
        logger.info("is_active column found. Proceeding with removal...")
        
        # 2. インデックスを削除
        logger.info("Dropping index if exists...")
        session.execute(text("""
            DROP INDEX IF EXISTS idx_building_merge_history_is_active
        """))
        
        # 3. カラムを削除
        logger.info("Dropping is_active column...")
        session.execute(text("""
            ALTER TABLE building_merge_history 
            DROP COLUMN IF EXISTS is_active
        """))
        
        session.commit()
        logger.info("Successfully removed is_active column from building_merge_history table.")
        
        # 4. テーブル構造を確認
        logger.info("\nCurrent columns in building_merge_history:")
        columns = session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'building_merge_history'
            ORDER BY ordinal_position
        """)).fetchall()
        
        for col in columns:
            logger.info(f"  - {col.column_name}: {col.data_type} (nullable: {col.is_nullable})")
        
        # 5. 統計情報を表示
        stats = session.execute(text("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT merged_building_id) as unique_merged,
                COUNT(DISTINCT final_primary_building_id) as unique_primary,
                MAX(merge_depth) as max_depth
            FROM building_merge_history
        """)).fetchone()
        
        logger.info(f"\nTable statistics:")
        logger.info(f"  Total records: {stats.total_records}")
        logger.info(f"  Unique merged buildings: {stats.unique_merged}")
        logger.info(f"  Unique primary buildings: {stats.unique_primary}")
        logger.info(f"  Maximum merge depth: {stats.max_depth or 0}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to remove is_active column: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    remove_is_active_column()