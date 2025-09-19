#!/usr/bin/env python3
"""
property_listingsテーブルに不足しているカラムを追加
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from sqlalchemy import text
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_missing_columns():
    """不足しているカラムを追加"""
    session = SessionLocal()
    
    # 追加するカラムのリスト
    columns_to_add = [
        ("management_company", "VARCHAR(200)"),

        ("published_at", "TIMESTAMP"),
        ("first_published_at", "TIMESTAMP"),
        ("price_updated_at", "TIMESTAMP"),
    ]
    
    try:
        logger.info("=== property_listingsテーブルのカラム追加開始 ===")
        
        for column_name, column_type in columns_to_add:
            try:
                # カラムが既に存在するか確認
                check_query = text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'property_listings' 
                    AND column_name = :column_name
                """)
                result = session.execute(check_query, {"column_name": column_name})
                
                if result.rowcount == 0:
                    # カラムを追加
                    alter_query = text(f"""
                        ALTER TABLE property_listings 
                        ADD COLUMN {column_name} {column_type}
                    """)
                    session.execute(alter_query)
                    session.commit()
                    logger.info(f"✓ カラム追加成功: {column_name} ({column_type})")
                else:
                    logger.info(f"- カラム既存: {column_name}")
                    
            except Exception as e:
                session.rollback()
                logger.error(f"✗ カラム追加失敗: {column_name} - {e}")
        
        logger.info("\n=== カラム追加完了 ===")
        
        # 現在のカラム一覧を表示
        logger.info("\n現在のproperty_listingsテーブルのカラム:")
        columns_query = text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'property_listings' 
            ORDER BY ordinal_position
        """)
        
        result = session.execute(columns_query)
        for row in result:
            logger.info(f"  - {row.column_name}: {row.data_type}")
            
    except Exception as e:
        logger.error(f"エラー発生: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    add_missing_columns()