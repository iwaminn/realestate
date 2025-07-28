#!/usr/bin/env python3
"""
建物名カラムを追加するマイグレーションスクリプト

実行方法:
docker exec realestate-backend poetry run python /app/backend/scripts/add_building_name_columns.py
"""

import sys
import os

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app.database import engine, SessionLocal
from backend.app.models import Base, MasterProperty, PropertyListing, Building
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_columns_if_not_exists():
    """必要なカラムを追加する"""
    session = SessionLocal()
    inspector = inspect(engine)
    
    try:
        # property_listingsテーブルにlisting_building_nameカラムを追加
        columns = [col['name'] for col in inspector.get_columns('property_listings')]
        if 'listing_building_name' not in columns:
            logger.info("property_listingsテーブルにlisting_building_nameカラムを追加します...")
            session.execute(text("""
                ALTER TABLE property_listings 
                ADD COLUMN listing_building_name VARCHAR(255)
            """))
            session.commit()
            logger.info("listing_building_nameカラムを追加しました")
        else:
            logger.info("listing_building_nameカラムは既に存在します")
        
        # master_propertiesテーブルにdisplay_building_nameカラムを追加
        columns = [col['name'] for col in inspector.get_columns('master_properties')]
        if 'display_building_name' not in columns:
            logger.info("master_propertiesテーブルにdisplay_building_nameカラムを追加します...")
            session.execute(text("""
                ALTER TABLE master_properties 
                ADD COLUMN display_building_name VARCHAR(255)
            """))
            session.commit()
            logger.info("display_building_nameカラムを追加しました")
        else:
            logger.info("display_building_nameカラムは既に存在します")
        
        logger.info("カラムの追加が完了しました")
        
    except SQLAlchemyError as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def migrate_existing_data():
    """既存データをマイグレーション"""
    session = SessionLocal()
    
    try:
        logger.info("既存データのマイグレーションを開始します...")
        
        # 1. property_listingsのlisting_building_nameを更新
        # titleから建物名を抽出する（簡易的な実装）
        logger.info("property_listingsのlisting_building_nameを更新中...")
        
        # まず、建物情報を結合して取得
        result = session.execute(text("""
            UPDATE property_listings pl
            SET listing_building_name = b.normalized_name
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            WHERE pl.master_property_id = mp.id
            AND pl.listing_building_name IS NULL
        """))
        
        updated_count = result.rowcount
        session.commit()
        logger.info(f"{updated_count}件のproperty_listingsを更新しました")
        
        # 2. master_propertiesのdisplay_building_nameを更新
        # 最初は関連する建物のnormalized_nameで初期化
        logger.info("master_propertiesのdisplay_building_nameを更新中...")
        
        result = session.execute(text("""
            UPDATE master_properties mp
            SET display_building_name = b.normalized_name
            FROM buildings b
            WHERE mp.building_id = b.id
            AND mp.display_building_name IS NULL
        """))
        
        updated_count = result.rowcount
        session.commit()
        logger.info(f"{updated_count}件のmaster_propertiesを更新しました")
        
        logger.info("データマイグレーションが完了しました")
        
    except SQLAlchemyError as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    logger.info("建物名カラムの追加を開始します...")
    
    # カラムを追加
    add_columns_if_not_exists()
    
    # 既存データをマイグレーション
    migrate_existing_data()
    
    logger.info("すべての処理が完了しました")


if __name__ == "__main__":
    main()