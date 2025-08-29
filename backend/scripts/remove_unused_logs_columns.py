#!/usr/bin/env python3
"""
ScrapingTaskテーブルから未使用のログカラムを削除
"""

import os
import sys
from pathlib import Path

# プロジェクトルートへのパスを追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
import os

def remove_unused_columns():
    """未使用のログカラムを削除"""
    
    # データベース接続
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.begin() as conn:
            # カラムが存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'scraping_tasks' 
                AND column_name IN ('logs', 'error_logs', 'warning_logs')
            """))
            
            existing_columns = [row[0] for row in result]
            
            if not existing_columns:
                print("削除対象のカラムは既に存在しません。")
                return
            
            print(f"削除対象カラム: {', '.join(existing_columns)}")
            
            # 各カラムを削除
            for column in existing_columns:
                print(f"カラム '{column}' を削除中...")
                conn.execute(text(f"ALTER TABLE scraping_tasks DROP COLUMN IF EXISTS {column}"))
                print(f"カラム '{column}' を削除しました。")
            
            print("\n✅ すべてのカラムを正常に削除しました。")
                
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("ScrapingTaskテーブルから未使用のログカラムを削除します。")
    print("=" * 50)
    
    # 確認
    response = input("続行しますか？ (y/n): ")
    if response.lower() != 'y':
        print("処理を中止しました。")
        sys.exit(0)
    
    remove_unused_columns()
    print("\n処理が完了しました。")