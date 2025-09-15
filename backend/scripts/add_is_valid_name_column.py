#!/usr/bin/env python3
"""
buildingsテーブルにis_valid_nameカラムを追加するスクリプト
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_is_valid_name_column():
    """is_valid_nameカラムを追加"""
    
    with engine.connect() as conn:
        # カラムが既に存在するかチェック
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'buildings' 
            AND column_name = 'is_valid_name'
        """))
        
        if result.fetchone():
            logger.info("is_valid_nameカラムは既に存在します")
            return
        
        # カラムを追加（デフォルトはtrue）
        logger.info("is_valid_nameカラムを追加中...")
        conn.execute(text("""
            ALTER TABLE buildings 
            ADD COLUMN is_valid_name BOOLEAN NOT NULL DEFAULT true
        """))
        conn.commit()
        
        logger.info("カラムの追加が完了しました")
        
        # インデックスを追加（検索性能向上のため）
        logger.info("インデックスを追加中...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_buildings_is_valid_name 
            ON buildings(is_valid_name)
        """))
        conn.commit()
        
        logger.info("インデックスの追加が完了しました")


if __name__ == "__main__":
    add_is_valid_name_column()