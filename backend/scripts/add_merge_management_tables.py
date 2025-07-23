#!/usr/bin/env python3
"""
建物統合管理用テーブルを追加
"""

import sys
import os
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text
from backend.app.database import Base, get_db
from backend.app.models import BuildingMergeExclusion, BuildingMergeHistory
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_merge_management_tables():
    """統合管理用テーブルを追加"""
    
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
    engine = create_engine(DATABASE_URL)
    
    try:
        # 新しいテーブルのみを作成
        logger.info("Creating building merge management tables...")
        
        # BuildingMergeExclusionテーブルを作成
        BuildingMergeExclusion.__table__.create(engine, checkfirst=True)
        logger.info("Created building_merge_exclusions table")
        
        # BuildingMergeHistoryテーブルを作成
        BuildingMergeHistory.__table__.create(engine, checkfirst=True)
        logger.info("Created building_merge_history table")
        
        logger.info("✅ Successfully created merge management tables")
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise

if __name__ == "__main__":
    add_merge_management_tables()