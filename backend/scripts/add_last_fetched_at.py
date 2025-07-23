#!/usr/bin/env python3
"""
last_fetched_at列を追加するマイグレーションスクリプト
"""

import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from backend.app.database import engine


def add_last_fetched_at_column():
    """property_listingsテーブルにlast_fetched_at列を追加"""
    
    with engine.connect() as conn:
        # 列が既に存在するかチェック
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='property_listings' 
            AND column_name='last_fetched_at'
        """))
        
        if result.rowcount > 0:
            print("last_fetched_at列は既に存在します")
            return
        
        # 列を追加
        print("last_fetched_at列を追加しています...")
        conn.execute(text("""
            ALTER TABLE property_listings 
            ADD COLUMN last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """))
        conn.commit()
        
        # 既存のレコードのlast_fetched_atをlast_scraped_atと同じ値に設定
        print("既存レコードのlast_fetched_atを更新しています...")
        conn.execute(text("""
            UPDATE property_listings 
            SET last_fetched_at = last_scraped_at
            WHERE last_fetched_at IS NULL
        """))
        conn.commit()
        
        print("完了しました！")


if __name__ == "__main__":
    add_last_fetched_at_column()