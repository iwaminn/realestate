#!/usr/bin/env python3
"""
property_merge_historyテーブルにmerge_detailsフィールドを追加するスクリプト
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import SessionLocal, engine

def add_merge_details_field():
    """merge_detailsフィールドを追加"""
    
    print("property_merge_historyテーブルにmerge_detailsフィールドを追加します...")
    
    with engine.connect() as conn:
        try:
            # 現在のテーブル構造を確認
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'property_merge_history'
                AND column_name = 'merge_details'
            """))
            
            if result.fetchone():
                print("merge_detailsフィールドは既に存在します")
                return
            
            # merge_detailsフィールドを追加（JSON型）
            print("\nmerge_detailsフィールドを追加...")
            conn.execute(text("""
                ALTER TABLE property_merge_history 
                ADD COLUMN merge_details JSON
            """))
            conn.commit()
            
            # secondary_property_idフィールドも確認して追加
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'property_merge_history'
                AND column_name = 'secondary_property_id'
            """))
            
            if not result.fetchone():
                print("\nsecondary_property_idフィールドも追加...")
                conn.execute(text("""
                    ALTER TABLE property_merge_history 
                    ADD COLUMN secondary_property_id INTEGER
                """))
                conn.commit()
            
            # reverted_at, reverted_byフィールドも確認して追加
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'property_merge_history'
                AND column_name IN ('reverted_at', 'reverted_by')
            """))
            
            existing_columns = [row[0] for row in result]
            
            if 'reverted_at' not in existing_columns:
                print("\nreverted_atフィールドを追加...")
                conn.execute(text("""
                    ALTER TABLE property_merge_history 
                    ADD COLUMN reverted_at TIMESTAMP
                """))
                conn.commit()
            
            if 'reverted_by' not in existing_columns:
                print("\nreverted_byフィールドを追加...")
                conn.execute(text("""
                    ALTER TABLE property_merge_history 
                    ADD COLUMN reverted_by VARCHAR(100)
                """))
                conn.commit()
            
            # 最終的なテーブル構造を確認
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'property_merge_history'
                ORDER BY ordinal_position
            """))
            
            print("\n更新後のテーブル構造:")
            for row in result:
                print(f"  {row[0]:<30} {row[1]}")
            
            print("\n✓ フィールドの追加が完了しました")
            
        except Exception as e:
            print(f"\n✗ エラーが発生しました: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    add_merge_details_field()