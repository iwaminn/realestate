#!/usr/bin/env python
"""
警告ログカラムを追加するマイグレーションスクリプト
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 環境変数からデータベースURLを取得
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def add_warning_logs_column():
    """警告ログカラムを追加"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # カラムが既に存在するかチェック
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'scraping_tasks' 
                AND column_name = 'warning_logs'
            """))
            
            if result.rowcount > 0:
                print("warning_logsカラムは既に存在します")
                return
            
            # warning_logsカラムを追加
            conn.execute(text("""
                ALTER TABLE scraping_tasks 
                ADD COLUMN warning_logs JSONB
            """))
            conn.commit()
            
            print("warning_logsカラムを追加しました")
            
    except SQLAlchemyError as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    add_warning_logs_column()