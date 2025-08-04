#!/usr/bin/env python3
"""
不足しているカラムを追加するスクリプト
"""

import os
import sys
from sqlalchemy import create_engine, text
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)


def add_missing_columns():
    """不足しているカラムを追加"""
    
    alter_sql = """
    -- buildingsテーブルに不足しているカラムを追加
    ALTER TABLE buildings 
    ADD COLUMN IF NOT EXISTS built_month INTEGER,
    ADD COLUMN IF NOT EXISTS construction_type VARCHAR(100);
    
    -- master_propertiesテーブルに不足しているカラムを追加
    ALTER TABLE master_properties
    ADD COLUMN IF NOT EXISTS management_fee INTEGER,
    ADD COLUMN IF NOT EXISTS repair_fund INTEGER,
    ADD COLUMN IF NOT EXISTS station_info TEXT;
    """
    
    with engine.connect() as conn:
        conn.execute(text(alter_sql))
        conn.commit()
        logger.info("不足しているカラムを追加しました")


def check_table_structure():
    """テーブル構造を確認"""
    
    check_sql = """
    SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_name IN ('buildings', 'master_properties', 'building_aliases')
    AND table_schema = 'public'
    ORDER BY table_name, ordinal_position;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(check_sql))
        current_table = None
        
        for row in result:
            table_name = None
            if row.column_name in ['id', 'normalized_name', 'canonical_name', 'address', 'total_floors', 'built_year', 'built_month', 'construction_type', 'created_at', 'updated_at']:
                table_name = 'buildings'
            elif row.column_name in ['building_id', 'room_number', 'property_hash', 'floor_number', 'area', 'balcony_area', 'layout', 'direction', 'management_fee', 'repair_fund', 'station_info', 'display_building_name', 'sold_at', 'final_price']:
                if table_name is None:
                    table_name = 'master_properties'
            elif row.column_name in ['alias_name', 'alias_type', 'source_site', 'is_primary', 'confidence_score']:
                if table_name is None:
                    table_name = 'building_aliases'
            
            if table_name and table_name != current_table:
                current_table = table_name
                logger.info(f"\n{table_name}テーブル:")
            
            if table_name == current_table:
                logger.info(f"  {row.column_name}: {row.data_type} (nullable: {row.is_nullable})")


def main():
    """メイン処理"""
    try:
        logger.info("カラムを追加しています...")
        add_missing_columns()
        
        logger.info("\nテーブル構造を確認しています...")
        check_table_structure()
        
        logger.info("\n処理が完了しました")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()