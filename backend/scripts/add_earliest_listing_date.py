#!/usr/bin/env python3
"""
最初の掲載日（earliest_listing_date）カラムを追加し、既存データを更新するスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import SessionLocal, engine
from backend.app.models import MasterProperty, PropertyListing
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_column_if_not_exists():
    """カラムが存在しない場合のみ追加"""
    with engine.connect() as conn:
        # カラムの存在確認
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'master_properties' 
            AND column_name = 'earliest_listing_date'
        """))
        
        if not result.fetchone():
            logger.info("Adding earliest_listing_date column to master_properties table...")
            conn.execute(text("""
                ALTER TABLE master_properties 
                ADD COLUMN earliest_listing_date TIMESTAMP
            """))
            conn.commit()
            logger.info("Column added successfully")
        else:
            logger.info("Column earliest_listing_date already exists")

def update_earliest_listing_dates():
    """既存の物件の最初の掲載日を更新"""
    db = SessionLocal()
    try:
        logger.info("Updating earliest_listing_date for all master properties...")
        
        # 各MasterPropertyの最初の掲載日を計算して更新
        master_properties = db.query(MasterProperty).all()
        total = len(master_properties)
        
        for i, mp in enumerate(master_properties):
            # アクティブな掲載の中で最も古い日付を取得
            earliest_date = db.query(func.min(PropertyListing.created_at))\
                .filter(PropertyListing.master_property_id == mp.id)\
                .filter(PropertyListing.is_active == True)\
                .scalar()
            
            if earliest_date:
                mp.earliest_listing_date = earliest_date
            
            if (i + 1) % 100 == 0:
                db.commit()
                logger.info(f"Updated {i + 1}/{total} properties...")
        
        db.commit()
        logger.info(f"Completed updating {total} properties")
        
    finally:
        db.close()

def create_index():
    """インデックスを作成"""
    with engine.connect() as conn:
        logger.info("Creating index on earliest_listing_date...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_master_properties_earliest_listing_date 
                ON master_properties(earliest_listing_date)
            """))
            conn.commit()
            logger.info("Index created successfully")
        except Exception as e:
            logger.warning(f"Index might already exist: {e}")

if __name__ == "__main__":
    logger.info("Starting migration...")
    add_column_if_not_exists()
    update_earliest_listing_dates()
    create_index()
    logger.info("Migration completed successfully")