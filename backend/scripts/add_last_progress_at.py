#!/usr/bin/env python3
"""
scraping_tasksテーブルにlast_progress_atカラムを追加するスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

# 環境変数からデータベースURLを取得
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://realestate:realestate_pass@localhost:5432/realestate"
)

def add_last_progress_at_column():
    """last_progress_atカラムを追加"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # カラムが既に存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'scraping_tasks' 
                AND column_name = 'last_progress_at'
            """))
            
            if result.fetchone():
                print("✓ last_progress_atカラムは既に存在します")
                return
            
            # カラムを追加
            conn.execute(text("""
                ALTER TABLE scraping_tasks 
                ADD COLUMN last_progress_at TIMESTAMP
            """))
            conn.commit()
            print("✓ last_progress_atカラムを追加しました")
            
            # 既存のレコードのlast_progress_atをstarted_atで初期化
            conn.execute(text("""
                UPDATE scraping_tasks 
                SET last_progress_at = started_at 
                WHERE last_progress_at IS NULL AND started_at IS NOT NULL
            """))
            conn.commit()
            print("✓ 既存レコードのlast_progress_atを初期化しました")
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            raise

if __name__ == "__main__":
    print("scraping_tasksテーブルにlast_progress_atカラムを追加します...")
    add_last_progress_at_column()
    print("完了しました！")