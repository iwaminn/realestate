#!/usr/bin/env python3
"""
property_imagesテーブルを削除するマイグレーションスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPYTHONPATHに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
import logging
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://realestate:realestate_pass@localhost:5432/realestate"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_property_images_table():
    """property_imagesテーブルを削除"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # テーブルが存在するか確認
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'property_images'
                )
            """))
            
            table_exists = result.fetchone()[0]
            
            if not table_exists:
                logger.info("property_imagesテーブルは既に存在しません")
                return
            
            # レコード数を確認
            result = conn.execute(text("SELECT COUNT(*) FROM property_images"))
            record_count = result.fetchone()[0]
            logger.info(f"property_imagesテーブルのレコード数: {record_count}")
            
            # テーブルを削除
            logger.info("property_imagesテーブルを削除しています...")
            conn.execute(text("DROP TABLE property_images CASCADE"))
            conn.commit()
            
            logger.info("property_imagesテーブルを正常に削除しました")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    drop_property_images_table()