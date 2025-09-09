#!/usr/bin/env python3
"""
物件ブックマーク機能用のテーブルを追加するマイグレーションスクリプト
"""

import sys
import os

# プロジェクトのルートパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.database import DATABASE_URL
from app.models import Base, PropertyBookmark
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_bookmarks_table():
    """ブックマークテーブルを作成"""
    
    # データベース接続
    logger.info(f"データベースに接続中: {DATABASE_URL}")
    
    engine = create_engine(DATABASE_URL)
    
    try:
        # property_bookmarksテーブルが存在するかチェック
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'property_bookmarks'
                )
            """))
            table_exists = result.scalar()
            
            if table_exists:
                logger.info("property_bookmarksテーブルは既に存在します")
                return
        
        # テーブル作成
        logger.info("property_bookmarksテーブルを作成中...")
        PropertyBookmark.__table__.create(engine)
        logger.info("property_bookmarksテーブルの作成が完了しました")
        
        # インデックスの確認
        with engine.connect() as conn:
            indices = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'property_bookmarks'
            """)).fetchall()
            logger.info(f"作成されたインデックス: {[idx[0] for idx in indices]}")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    logger.info("ブックマークテーブル作成スクリプトを開始")
    create_bookmarks_table()
    logger.info("スクリプト完了")