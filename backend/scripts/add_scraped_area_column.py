#!/usr/bin/env python3
"""
property_listingsテーブルにscraped_from_areaカラムを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_scraped_area_column():
    """scraped_from_areaカラムを追加"""
    
    # データベース接続
    database_url = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@postgres:5432/realestate')
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # カラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='property_listings' 
                AND column_name='scraped_from_area'
            """))
            
            if result.fetchone():
                logger.info("scraped_from_areaカラムは既に存在します")
                return
            
            # カラムを追加
            logger.info("scraped_from_areaカラムを追加中...")
            conn.execute(text("""
                ALTER TABLE property_listings 
                ADD COLUMN scraped_from_area VARCHAR(20)
            """))
            
            # インデックスを追加（エリアごとの検索を高速化）
            conn.execute(text("""
                CREATE INDEX idx_property_listings_scraped_area 
                ON property_listings(scraped_from_area)
            """))
            
            conn.commit()
            logger.info("scraped_from_areaカラムとインデックスを追加しました")
            
    except SQLAlchemyError as e:
        logger.error(f"データベースエラー: {e}")
        raise

if __name__ == "__main__":
    add_scraped_area_column()