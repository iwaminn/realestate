#!/usr/bin/env python3
"""
スクレイピングタスク管理用のテーブルを追加するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from backend.app.models_scraping_task import Base
from backend.app.database import DATABASE_URL

def create_tables():
    """テーブルを作成"""
    engine = create_engine(DATABASE_URL)
    
    # 既存のテーブルをチェック
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('scraping_tasks', 'scraping_task_progress')
        """))
        existing_tables = [row[0] for row in result]
        
        if existing_tables:
            print(f"既存のテーブルが見つかりました: {existing_tables}")
            response = input("テーブルを削除して再作成しますか？ (y/N): ")
            if response.lower() == 'y':
                # テーブルを削除
                for table in existing_tables:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    print(f"テーブル {table} を削除しました")
                conn.commit()
            else:
                print("処理を中止しました")
                return
    
    # テーブルを作成
    Base.metadata.create_all(bind=engine)
    print("スクレイピングタスク管理テーブルを作成しました")
    
    # テーブル一覧を表示
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('scraping_tasks', 'scraping_task_progress')
            ORDER BY table_name
        """))
        
        print("\n作成されたテーブル:")
        for row in result:
            print(f"  - {row[0]}")

if __name__ == "__main__":
    create_tables()