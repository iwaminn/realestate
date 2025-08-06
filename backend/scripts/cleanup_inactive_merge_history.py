#!/usr/bin/env python3
"""
is_active=falseの建物統合履歴を削除するクリーンアップスクリプト
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


def cleanup_inactive_merge_history():
    """is_active=falseの履歴を削除"""
    session = Session()
    
    try:
        # 1. is_active=falseの履歴を確認
        logger.info("Checking for inactive merge histories...")
        
        result = session.execute(text("""
            SELECT 
                id,
                merged_building_id,
                merged_building_name,
                direct_primary_building_id,
                final_primary_building_id,
                is_active
            FROM building_merge_history
            WHERE is_active = FALSE
        """)).fetchall()
        
        if not result:
            logger.info("No inactive merge histories found.")
            return
        
        logger.info(f"Found {len(result)} inactive merge histories:")
        for row in result:
            logger.info(f"  - ID: {row.id}, Merged Building: {row.merged_building_name} (ID: {row.merged_building_id})")
        
        # 2. 削除実行
        logger.info("Deleting inactive merge histories...")
        
        deleted_count = session.execute(text("""
            DELETE FROM building_merge_history
            WHERE is_active = FALSE
        """)).rowcount
        
        session.commit()
        logger.info(f"Successfully deleted {deleted_count} inactive merge histories.")
        
        # 4. 残った履歴の統計を表示
        stats = session.execute(text("""
            SELECT 
                COUNT(*) as total_active,
                COUNT(DISTINCT merged_building_id) as unique_merged,
                COUNT(DISTINCT final_primary_building_id) as unique_primary
            FROM building_merge_history
        """)).fetchone()
        
        logger.info("\nRemaining active histories:")
        logger.info(f"  Total: {stats.total_active}")
        logger.info(f"  Unique merged buildings: {stats.unique_merged}")
        logger.info(f"  Unique primary buildings: {stats.unique_primary}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Cleanup failed: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    cleanup_inactive_merge_history()