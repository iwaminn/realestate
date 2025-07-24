"""
販売終了物件管理のための新しいフィールドを追加するマイグレーションスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトルートのパスを追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import engine
from sqlalchemy import text


def add_sold_property_fields():
    """マスター物件テーブルに販売終了関連のフィールドを追加"""
    
    with engine.connect() as conn:
        # トランザクション開始
        trans = conn.begin()
        try:
            # sold_at フィールドの追加
            try:
                conn.execute(text("""
                    ALTER TABLE master_properties
                    ADD COLUMN sold_at TIMESTAMP
                """))
                print("✅ sold_at フィールドを追加しました")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("ℹ️  sold_at フィールドは既に存在します")
                else:
                    raise
            
            # last_sale_price フィールドの追加
            try:
                conn.execute(text("""
                    ALTER TABLE master_properties
                    ADD COLUMN last_sale_price INTEGER
                """))
                print("✅ last_sale_price フィールドを追加しました")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("ℹ️  last_sale_price フィールドは既に存在します")
                else:
                    raise
            
            # インデックスの追加
            try:
                conn.execute(text("""
                    CREATE INDEX idx_master_properties_sold_at
                    ON master_properties(sold_at)
                    WHERE sold_at IS NOT NULL
                """))
                print("✅ sold_at インデックスを追加しました")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("ℹ️  sold_at インデックスは既に存在します")
                else:
                    raise
            
            trans.commit()
            print("\n✨ データベースの更新が完了しました")
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ エラーが発生しました: {e}")
            raise


if __name__ == "__main__":
    add_sold_property_fields()