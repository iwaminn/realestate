#!/usr/bin/env python3
"""
新しいlisting_*カラムを追加するマイグレーションスクリプト
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

def add_new_listing_columns():
    """property_listingsテーブルに新しいlisting_*カラムを追加"""
    engine = create_engine(settings.DATABASE_URL)
    
    # 追加するカラムのリスト
    columns_to_add = [
        ('listing_basement_floors', 'INTEGER'),
        ('listing_land_rights', 'VARCHAR(500)'),
        ('listing_parking_info', 'TEXT'),
        ('listing_station_info', 'TEXT')
    ]
    
    try:
        with engine.connect() as conn:
            for column_name, column_type in columns_to_add:
                # カラムが既に存在するか確認
                result = conn.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'property_listings' 
                    AND column_name = '{column_name}'
                """))
                
                if result.fetchone():
                    logger.info(f"{column_name}カラムは既に存在します")
                    continue
                
                # カラムを追加
                logger.info(f"{column_name}カラムを追加しています...")
                conn.execute(text(f"""
                    ALTER TABLE property_listings 
                    ADD COLUMN {column_name} {column_type}
                """))
                conn.commit()
                
                logger.info(f"{column_name}カラムを正常に追加しました")
            
            # 追加されたカラムを確認
            logger.info("\n追加されたカラムの確認:")
            for column_name, _ in columns_to_add:
                result = conn.execute(text(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'property_listings' 
                    AND column_name = '{column_name}'
                """))
                
                row = result.fetchone()
                if row:
                    logger.info(f"  {row[0]} ({row[1]})")
                    
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

def add_building_columns():
    """buildingsテーブルにstation_infoカラムを追加（既に他のカラムは存在）"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # station_infoカラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'buildings' 
                AND column_name = 'station_info'
            """))
            
            if result.fetchone():
                logger.info("buildings.station_infoカラムは既に存在します")
                return
            
            # カラムを追加
            logger.info("buildings.station_infoカラムを追加しています...")
            conn.execute(text("""
                ALTER TABLE buildings 
                ADD COLUMN station_info TEXT
            """))
            conn.commit()
            
            logger.info("buildings.station_infoカラムを正常に追加しました")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

def add_master_property_columns():
    """master_propertiesテーブルにparking_infoカラムを追加"""
    engine = create_engine(settings.DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # parking_infoカラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'master_properties' 
                AND column_name = 'parking_info'
            """))
            
            if result.fetchone():
                logger.info("master_properties.parking_infoカラムは既に存在します")
                return
            
            # カラムを追加
            logger.info("master_properties.parking_infoカラムを追加しています...")
            conn.execute(text("""
                ALTER TABLE master_properties 
                ADD COLUMN parking_info TEXT
            """))
            conn.commit()
            
            logger.info("master_properties.parking_infoカラムを正常に追加しました")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    logger.info("=== 新しいカラムの追加を開始 ===")
    
    # property_listingsテーブルのカラム追加
    logger.info("\n1. property_listingsテーブルの更新")
    add_new_listing_columns()
    
    # buildingsテーブルのカラム追加
    logger.info("\n2. buildingsテーブルの更新")
    add_building_columns()
    
    # master_propertiesテーブルのカラム追加
    logger.info("\n3. master_propertiesテーブルの更新")
    add_master_property_columns()
    
    logger.info("\n=== すべてのカラム追加が完了しました ===")