#!/usr/bin/env python3
"""
ScrapingTaskテーブルにlogsフィールドを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_logs_field():
    """logsフィールドを追加"""
    try:
        with engine.connect() as conn:
            # カラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'scraping_tasks' 
                AND column_name = 'logs'
            """))
            
            if result.fetchone():
                logger.info("logsカラムは既に存在します")
                return
            
            # logsカラムを追加
            logger.info("logsカラムを追加しています...")
            conn.execute(text("""
                ALTER TABLE scraping_tasks 
                ADD COLUMN logs JSON
            """))
            conn.commit()
            
            logger.info("logsカラムを追加しました")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    add_logs_field()