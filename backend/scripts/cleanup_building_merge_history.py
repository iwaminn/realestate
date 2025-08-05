#!/usr/bin/env python3
"""
building_merge_historyテーブルの旧フィールドを削除するスクリプト
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import SessionLocal, engine

def cleanup_building_merge_history():
    """旧バージョンのフィールドを削除"""
    
    print("building_merge_historyテーブルの旧フィールドを削除します...")
    
    with engine.connect() as conn:
        try:
            # 現在のテーブル構造を確認
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'building_merge_history'
                ORDER BY ordinal_position
            """))
            
            print("\n現在のテーブル構造:")
            for row in result:
                print(f"  {row[0]:<25} {row[1]:<20} NULL: {row[2]}")
            
            # 旧フィールドのNOT NULL制約を一時的に削除（データがある場合のため）
            print("\n旧フィールドのNOT NULL制約を削除...")
            conn.execute(text("ALTER TABLE building_merge_history ALTER COLUMN merged_building_ids DROP NOT NULL"))
            conn.execute(text("ALTER TABLE building_merge_history ALTER COLUMN moved_properties DROP NOT NULL"))
            conn.commit()
            
            # 旧フィールドを削除
            print("\n旧フィールドを削除...")
            conn.execute(text("ALTER TABLE building_merge_history DROP COLUMN IF EXISTS merged_building_ids"))
            conn.execute(text("ALTER TABLE building_merge_history DROP COLUMN IF EXISTS moved_properties"))
            conn.execute(text("ALTER TABLE building_merge_history DROP COLUMN IF EXISTS merge_details"))
            conn.execute(text("ALTER TABLE building_merge_history DROP COLUMN IF EXISTS created_at"))
            conn.commit()
            
            # 新フィールドのNOT NULL制約を削除（必要に応じて）
            print("\n新フィールドのNOT NULL制約を調整...")
            conn.execute(text("ALTER TABLE building_merge_history ALTER COLUMN merged_building_id DROP NOT NULL"))
            conn.commit()
            
            # 最終的なテーブル構造を確認
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'building_merge_history'
                ORDER BY ordinal_position
            """))
            
            print("\n更新後のテーブル構造:")
            for row in result:
                print(f"  {row[0]:<25} {row[1]:<20} NULL: {row[2]}")
            
            print("\n✓ 旧フィールドの削除が完了しました")
            
        except Exception as e:
            print(f"\n✗ エラーが発生しました: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    cleanup_building_merge_history()