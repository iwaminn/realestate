#!/usr/bin/env python
"""
すべての物件情報をクリアするスクリプト
警告: このスクリプトはすべての物件データを削除します！
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.database import SessionLocal


def clear_all_property_data(force=False):
    """すべての物件関連データを削除"""
    db = SessionLocal()
    
    try:
        if not force:
            print("警告: このスクリプトはすべての物件データを削除します！")
            print("本当に実行しますか？ (yes/no): ", end="")
            
            response = input().strip().lower()
            if response != "yes":
                print("キャンセルしました")
                return
        
        print("\nデータベースのクリアを開始します...")
        
        # 削除順序（外部キー依存関係を考慮）
        tables_to_clear = [
            "property_images",
            "listing_price_history",
            "property_listings",
            "master_properties",
            "building_aliases",
            "buildings"
        ]
        
        for table in tables_to_clear:
            try:
                # 各テーブルを個別のトランザクションで処理
                # 件数を確認
                result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                
                if count > 0:
                    print(f"  - {table}: {count}件のデータを削除中...")
                    # 外部キー制約を一時的に無効化
                    db.execute(text("SET session_replication_role = 'replica';"))
                    db.execute(text(f"DELETE FROM {table}"))
                    # 外部キー制約を再度有効化
                    db.execute(text("SET session_replication_role = 'origin';"))
                    db.commit()
                    print(f"    完了")
                else:
                    print(f"  - {table}: データなし")
                    
            except Exception as e:
                print(f"  - {table}: スキップ - {str(e).split('(')[0]}")
                db.rollback()
        
        print("\nすべての物件データを削除しました")
        
        # 削除後の確認
        print("\n=== 削除後の確認 ===")
        for table in tables_to_clear:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  - {table}: {count}件")
            except:
                pass
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    # コマンドライン引数で --force を指定した場合は確認をスキップ
    import argparse
    parser = argparse.ArgumentParser(description="すべての物件データをクリア")
    parser.add_argument("--force", action="store_true", help="確認なしで実行")
    args = parser.parse_args()
    
    clear_all_property_data(force=args.force)
