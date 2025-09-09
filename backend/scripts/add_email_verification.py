#!/usr/bin/env python
"""
メールアドレス確認機能用のテーブルを追加
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from app.models import Base, EmailVerificationToken
from app.database import SessionLocal
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_email_verification_tables():
    """メール確認用テーブルを作成"""
    # データベース接続
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    
    # Docker環境からの実行を考慮
    if 'localhost' in DATABASE_URL and os.path.exists('/.dockerenv'):
        DATABASE_URL = DATABASE_URL.replace('localhost', 'postgres')
    
    logger.info(f"データベースに接続中: {DATABASE_URL}")
    
    engine = create_engine(DATABASE_URL)
    
    # EmailVerificationTokenテーブルの存在確認
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'email_verification_tokens'
            );
        """))
        table_exists = result.scalar()
        
        if table_exists:
            logger.info("email_verification_tokensテーブルは既に存在します")
        else:
            logger.info("email_verification_tokensテーブルを作成中...")
            
            # テーブルを作成
            conn.execute(text("""
                CREATE TABLE email_verification_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            # インデックスを作成
            conn.execute(text("""
                CREATE INDEX idx_verification_tokens_user ON email_verification_tokens(user_id);
            """))
            conn.execute(text("""
                CREATE INDEX idx_verification_tokens_expires ON email_verification_tokens(expires_at);
            """))
            conn.execute(text("""
                CREATE INDEX idx_verification_tokens_token ON email_verification_tokens(token);
            """))
            
            conn.commit()
            logger.info("email_verification_tokensテーブルを作成しました")
        
        # is_verifiedカラムの確認（既存のusersテーブルに存在するか）
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'is_verified';
        """))
        
        if result.fetchone():
            logger.info("usersテーブルにis_verifiedカラムは既に存在します")
        else:
            logger.info("usersテーブルにis_verifiedカラムを追加中...")
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN is_verified BOOLEAN DEFAULT FALSE NOT NULL;
            """))
            conn.commit()
            logger.info("is_verifiedカラムを追加しました")
        
        # テーブル情報を表示
        result = conn.execute(text("""
            SELECT 
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            WHERE c.table_name = 'email_verification_tokens'
            ORDER BY c.ordinal_position;
        """))
        
        logger.info("\nemail_verification_tokensテーブル構造:")
        for row in result:
            logger.info(f"  {row[0]}: {row[1]} (nullable: {row[2]}, default: {row[3]})")
        
        # 統計情報
        result = conn.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM users) as user_count,
                (SELECT COUNT(*) FROM users WHERE is_verified = true) as verified_count,
                (SELECT COUNT(*) FROM email_verification_tokens) as token_count;
        """))
        
        stats = result.fetchone()
        logger.info(f"\n統計情報:")
        logger.info(f"  総ユーザー数: {stats[0]}")
        logger.info(f"  確認済みユーザー数: {stats[1]}")
        logger.info(f"  確認トークン数: {stats[2]}")

if __name__ == "__main__":
    try:
        create_email_verification_tables()
        logger.info("\nスクリプトが正常に完了しました")
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        sys.exit(1)