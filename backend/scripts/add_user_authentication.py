#!/usr/bin/env python3
"""
ユーザー認証機能用のテーブルを追加するマイグレーションスクリプト
"""

import sys
import os

# プロジェクトのルートパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.database import DATABASE_URL
from app.models import Base, User, UserSession, PropertyBookmark
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_user_tables():
    """ユーザー認証用のテーブルを作成"""
    
    # データベース接続
    logger.info(f"データベースに接続中: {DATABASE_URL}")
    
    engine = create_engine(DATABASE_URL)
    
    try:
        # 新しいテーブルが存在するかチェック
        with engine.connect() as conn:
            # usersテーブル
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                )
            """))
            users_exists = result.scalar()
            
            # user_sessionsテーブル
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'user_sessions'
                )
            """))
            sessions_exists = result.scalar()
            
        # テーブル作成
        if not users_exists:
            logger.info("usersテーブルを作成中...")
            User.__table__.create(engine)
            logger.info("usersテーブルの作成が完了しました")
        else:
            logger.info("usersテーブルは既に存在します")
            
        if not sessions_exists:
            logger.info("user_sessionsテーブルを作成中...")
            UserSession.__table__.create(engine)
            logger.info("user_sessionsテーブルの作成が完了しました")
        else:
            logger.info("user_sessionsテーブルは既に存在します")
        
        # property_bookmarksテーブルのカラム変更
        logger.info("property_bookmarksテーブルの更新を確認中...")
        with engine.connect() as conn:
            # user_idカラムが存在するかチェック
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'property_bookmarks'
                    AND column_name = 'user_id'
                )
            """))
            user_id_exists = result.scalar()
            
            if not user_id_exists:
                logger.info("property_bookmarksテーブルにuser_idカラムを追加中...")
                # まず、user_idカラムを追加（NULLable）
                conn.execute(text("ALTER TABLE property_bookmarks ADD COLUMN user_id INTEGER"))
                
                # 外部キー制約を追加
                conn.execute(text("""
                    ALTER TABLE property_bookmarks 
                    ADD CONSTRAINT fk_bookmarks_user 
                    FOREIGN KEY (user_id) REFERENCES users(id)
                """))
                
                logger.warning("既存のproperty_bookmarksデータは手動でuser_idを設定する必要があります")
                logger.info("property_bookmarksテーブルの更新が完了しました")
                conn.commit()
            else:
                logger.info("property_bookmarksテーブルは既に更新済みです")
        
        # インデックスの確認
        with engine.connect() as conn:
            tables = ['users', 'user_sessions', 'property_bookmarks']
            for table in tables:
                indices = conn.execute(text(f"""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = '{table}'
                """)).fetchall()
                logger.info(f"{table}テーブルのインデックス: {[idx[0] for idx in indices]}")
            
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    logger.info("ユーザー認証テーブル作成スクリプトを開始")
    create_user_tables()
    logger.info("スクリプト完了")