#!/usr/bin/env python3
"""
listing_built_monthカラムを追加するマイグレーションスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPYTHONPATHに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from backend.app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_listing_built_month_column():
    """property_listingsテーブルにlisting_built_monthカラムを追加"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # カラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'property_listings' 
                AND column_name = 'listing_built_month'
            """))
            
            if result.fetchone():
                logger.info("listing_built_monthカラムは既に存在します")
                return
            
            # カラムを追加
            logger.info("listing_built_monthカラムを追加しています...")
            conn.execute(text("""
                ALTER TABLE property_listings 
                ADD COLUMN listing_built_month INTEGER
            """))
            conn.commit()
            
            logger.info("listing_built_monthカラムを正常に追加しました")
            
            # 追加されたことを確認
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'property_listings' 
                AND column_name = 'listing_built_month'
            """))
            
            row = result.fetchone()
            if row:
                logger.info(f"確認: カラム '{row[0]}' (型: {row[1]}) が追加されました")
            else:
                logger.error("カラムの追加に失敗したようです")
                
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_listing_built_month_column()