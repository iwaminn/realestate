#!/usr/bin/env python
"""
仮登録ユーザーテーブルを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.models import Base, PendingUser
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def add_pending_users_table():
    """仮登録ユーザーテーブルを追加"""
    
    engine = create_engine(DATABASE_URL)
    
    # テーブルが存在しない場合のみ作成
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'pending_users'
            );
        """))
        exists = result.scalar()
        
        if not exists:
            # テーブル作成
            PendingUser.__table__.create(engine)
            print("✅ pending_usersテーブルを作成しました")
            
            # 古い仮登録を自動削除するためのインデックスも作成済み
            print("✅ インデックスも作成しました")
        else:
            print("ℹ️ pending_usersテーブルは既に存在します")

if __name__ == "__main__":
    add_pending_users_table()