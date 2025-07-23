#!/usr/bin/env python3
"""建物テーブルに読み仮名カラムを追加するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal, engine

def add_reading_column():
    """読み仮名カラムを追加"""
    
    # SQLコマンドを準備
    add_column_sql = """
    ALTER TABLE buildings 
    ADD COLUMN IF NOT EXISTS reading VARCHAR(255);
    """
    
    add_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_buildings_reading 
    ON buildings(reading);
    """
    
    # データベース接続
    with engine.connect() as conn:
        try:
            # カラムを追加
            print("読み仮名カラムを追加中...")
            conn.execute(text(add_column_sql))
            conn.commit()
            
            # インデックスを作成
            print("インデックスを作成中...")
            conn.execute(text(add_index_sql))
            conn.commit()
            
            print("完了しました！")
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    add_reading_column()