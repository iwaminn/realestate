#!/usr/bin/env python3
"""
published_atカラムを追加するマイグレーションスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal, engine
from sqlalchemy import text

def add_published_at_column():
    """published_atカラムを追加"""
    session = SessionLocal()
    try:
        print("=== published_atカラムを追加します ===")
        
        # カラムが既に存在するかチェック
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'property_listings' 
            AND column_name = 'published_at'
        """))
        
        if result.fetchone():
            print("published_atカラムは既に存在します")
            return
        
        # published_atカラムを追加
        session.execute(text("""
            ALTER TABLE property_listings 
            ADD COLUMN published_at TIMESTAMP
        """))
        
        session.commit()
        print("✅ published_atカラムを追加しました")
        
        # 確認
        result = session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'property_listings' 
            AND column_name = 'published_at'
        """))
        
        row = result.fetchone()
        if row:
            print(f"カラム情報: {row[0]} ({row[1]})")
        
    except Exception as e:
        print(f"エラー: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    add_published_at_column()