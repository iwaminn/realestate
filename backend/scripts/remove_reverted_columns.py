#!/usr/bin/env python3
"""
building_merge_historyテーブルから不要なreverted_at, reverted_byカラムを削除
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

# データベースURL取得
def get_database_url():
    """データベースURLを取得"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # デフォルトのDocker環境用URL
        database_url = "postgresql://realestate:realestate_pass@postgres:5432/realestate"
    return database_url

def remove_reverted_columns():
    """reverted_at, reverted_byカラムを削除"""
    
    # データベース接続
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # トランザクション開始
        trans = conn.begin()
        
        try:
            # カラムの存在確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'building_merge_history' 
                AND column_name IN ('reverted_at', 'reverted_by')
            """))
            
            existing_columns = [row[0] for row in result]
            
            if not existing_columns:
                print("✓ reverted_at, reverted_byカラムは既に削除されています")
                return
            
            print(f"削除対象カラム: {', '.join(existing_columns)}")
            
            # カラムを削除
            for column in existing_columns:
                print(f"  - {column}カラムを削除中...")
                conn.execute(text(f"""
                    ALTER TABLE building_merge_history 
                    DROP COLUMN IF EXISTS {column}
                """))
                print(f"    ✓ {column}カラムを削除しました")
            
            trans.commit()
            print("\n✓ すべてのカラムの削除が完了しました")
            
        except Exception as e:
            trans.rollback()
            print(f"\n✗ エラーが発生しました: {e}")
            raise

if __name__ == "__main__":
    print("=== building_merge_historyテーブルの不要カラム削除 ===\n")
    remove_reverted_columns()