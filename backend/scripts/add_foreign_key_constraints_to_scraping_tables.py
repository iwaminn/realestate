#!/usr/bin/env python3
"""
スクレイピング関連テーブルに外部キー制約を追加するスクリプト

ScrapingTaskProgressとScrapingTaskLogテーブルに、
ScrapingTaskテーブルへの外部キー制約（CASCADE DELETE）を追加します。
これにより、タスクが削除された際に関連レコードも自動的に削除されます。
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

def add_foreign_key_constraints():
    """外部キー制約を追加"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # まず孤立したレコードを削除（外部キー制約を追加する前にクリーンアップ）
            print("孤立したレコードをクリーンアップしています...")
            
            # ScrapingTaskProgressの孤立レコードを削除
            result = conn.execute(text("""
                DELETE FROM scraping_task_progress
                WHERE task_id NOT IN (SELECT task_id FROM scraping_tasks)
            """))
            deleted_progress = result.rowcount
            
            # ScrapingTaskLogの孤立レコードを削除
            result = conn.execute(text("""
                DELETE FROM scraping_task_logs
                WHERE task_id NOT IN (SELECT task_id FROM scraping_tasks)
            """))
            deleted_logs = result.rowcount
            
            conn.commit()
            
            if deleted_progress > 0:
                print(f"✓ {deleted_progress}件の孤立したScrapingTaskProgressレコードを削除しました")
            if deleted_logs > 0:
                print(f"✓ {deleted_logs}件の孤立したScrapingTaskLogレコードを削除しました")
            if deleted_progress == 0 and deleted_logs == 0:
                print("✓ 孤立したレコードはありませんでした")
            
            print()
            
            # 既存の外部キー制約を確認
            result = conn.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'scraping_task_progress' 
                AND constraint_type = 'FOREIGN KEY'
                AND constraint_name = 'fk_scraping_task_progress_task_id'
            """))
            
            if not result.fetchone():
                # ScrapingTaskProgressテーブルに外部キー制約を追加
                print("ScrapingTaskProgressテーブルに外部キー制約を追加しています...")
                conn.execute(text("""
                    ALTER TABLE scraping_task_progress
                    ADD CONSTRAINT fk_scraping_task_progress_task_id
                    FOREIGN KEY (task_id) 
                    REFERENCES scraping_tasks(task_id)
                    ON DELETE CASCADE
                """))
                conn.commit()
                print("✓ ScrapingTaskProgressテーブルに外部キー制約を追加しました")
            else:
                print("✓ ScrapingTaskProgressテーブルの外部キー制約は既に存在します")
            
            # ScrapingTaskLogテーブルの外部キー制約を確認
            result = conn.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'scraping_task_logs' 
                AND constraint_type = 'FOREIGN KEY'
                AND constraint_name = 'fk_scraping_task_logs_task_id'
            """))
            
            if not result.fetchone():
                # ScrapingTaskLogテーブルに外部キー制約を追加
                print("ScrapingTaskLogテーブルに外部キー制約を追加しています...")
                conn.execute(text("""
                    ALTER TABLE scraping_task_logs
                    ADD CONSTRAINT fk_scraping_task_logs_task_id
                    FOREIGN KEY (task_id) 
                    REFERENCES scraping_tasks(task_id)
                    ON DELETE CASCADE
                """))
                conn.commit()
                print("✓ ScrapingTaskLogテーブルに外部キー制約を追加しました")
            else:
                print("✓ ScrapingTaskLogテーブルの外部キー制約は既に存在します")
                
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            raise

def verify_constraints():
    """制約が正しく設定されているか確認"""
    engine = create_engine(DATABASE_URL)
    
    print("\n制約の確認...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                tc.table_name,
                tc.constraint_name,
                tc.constraint_type,
                rc.delete_rule
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            WHERE tc.table_name IN ('scraping_task_progress', 'scraping_task_logs')
            AND tc.constraint_type = 'FOREIGN KEY'
        """))
        
        for row in result:
            print(f"テーブル: {row[0]}, 制約名: {row[1]}, 削除ルール: {row[3]}")

if __name__ == "__main__":
    print("スクレイピング関連テーブルに外部キー制約を追加します...")
    print("=" * 50)
    
    try:
        add_foreign_key_constraints()
        verify_constraints()
        print("\n✅ 外部キー制約の追加が完了しました！")
        print("今後、ScrapingTaskを削除すると関連するProgressとLogレコードも自動的に削除されます。")
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        sys.exit(1)