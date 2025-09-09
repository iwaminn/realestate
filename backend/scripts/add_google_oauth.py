#!/usr/bin/env python
"""
Google OAuth用のカラムを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def add_google_oauth_columns():
    """Google OAuth用のカラムを追加"""
    
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # google_idカラムが存在しない場合のみ追加
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'google_id';
        """))
        
        if not result.fetchone():
            # google_idカラムを追加
            conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN google_id VARCHAR(255) UNIQUE;
            """))
            
            # インデックスを追加
            conn.execute(text("""
                CREATE INDEX idx_users_google_id ON users(google_id);
            """))
            
            # hashed_passwordをNULL許可に変更
            conn.execute(text("""
                ALTER TABLE users 
                ALTER COLUMN hashed_password DROP NOT NULL;
            """))
            
            conn.commit()
            print("✅ Google OAuth用のカラムを追加しました")
        else:
            print("ℹ️ google_idカラムは既に存在します")

if __name__ == "__main__":
    add_google_oauth_columns()