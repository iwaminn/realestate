#!/usr/bin/env python3
"""
has_update_markカラムを削除するマイグレーションスクリプト
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

def drop_has_update_mark_column():
    """property_listingsテーブルからhas_update_markカラムを削除"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # カラムが存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'property_listings' 
                AND column_name = 'has_update_mark'
            """))
            
            if not result.fetchone():
                logger.info("has_update_markカラムは既に存在しません")
                return
            
            # カラムを削除
            logger.info("has_update_markカラムを削除しています...")
            conn.execute(text("""
                ALTER TABLE property_listings 
                DROP COLUMN has_update_mark
            """))
            conn.commit()
            
            logger.info("has_update_markカラムを正常に削除しました")
            
            # 削除されたことを確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'property_listings' 
                AND column_name = 'has_update_mark'
            """))
            
            if not result.fetchone():
                logger.info("確認: has_update_markカラムが正常に削除されました")
            else:
                logger.error("カラムの削除に失敗したようです")
                
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    drop_has_update_mark_column()