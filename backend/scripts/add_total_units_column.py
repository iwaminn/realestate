#!/usr/bin/env python3
"""
総戸数カラムを追加するマイグレーションスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.app.database import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_total_units_columns():
    """総戸数カラムを追加"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # buildingsテーブルにtotal_unitsカラムを追加
            logger.info("Adding total_units column to buildings table...")
            conn.execute(text("""
                ALTER TABLE buildings 
                ADD COLUMN IF NOT EXISTS total_units INTEGER
            """))
            conn.commit()
            
            # property_listingsテーブルにlisting_total_unitsカラムを追加
            logger.info("Adding listing_total_units column to property_listings table...")
            conn.execute(text("""
                ALTER TABLE property_listings 
                ADD COLUMN IF NOT EXISTS listing_total_units INTEGER
            """))
            conn.commit()
            
            logger.info("Successfully added total_units columns")
            
    except Exception as e:
        logger.error(f"Error adding columns: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    add_total_units_columns()