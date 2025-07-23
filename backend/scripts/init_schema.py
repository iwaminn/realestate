#!/usr/bin/env python3
"""
データベーススキーマv2の初期化スクリプト
PostgreSQL用
"""

import sys
import os
from sqlalchemy import create_engine

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import DATABASE_URL
from backend.app.models import Base


def init_schema():
    """v2スキーマのテーブルを作成"""
    print("データベーススキーマv2を初期化中...")
    
    # エンジンを作成
    engine = create_engine(DATABASE_URL)
    
    try:
        # 全てのテーブルを作成
        Base.metadata.create_all(bind=engine)
        
        print("✅ 以下のテーブルが作成されました:")
        print("  - buildings (建物マスター)")
        print("  - building_aliases (建物名エイリアス)")
        print("  - master_properties (物件マスター)")
        print("  - property_listings (物件掲載情報)")
        print("  - listing_price_history (掲載価格履歴)")
        print("  - property_images (物件画像)")
        print("  - properties (旧テーブル - 互換性用)")
        print("  - price_history (旧テーブル - 互換性用)")
        
        print("\n初期化が完了しました！")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        raise


def drop_tables():
    """v2スキーマのテーブルを削除（開発用）"""
    print("警告: これはv2スキーマの全テーブルを削除します！")
    response = input("続行しますか？ (yes/no): ")
    
    if response.lower() != "yes":
        print("キャンセルしました")
        return
    
    engine = create_engine(DATABASE_URL)
    
    # 外部キー制約を一時的に無効化（PostgreSQL）
    with engine.begin() as conn:
        conn.execute("SET session_replication_role = 'replica';")
    
    # テーブルを削除
    Base.metadata.drop_all(bind=engine)
    
    # 外部キー制約を再度有効化
    with engine.begin() as conn:
        conn.execute("SET session_replication_role = 'origin';")
    
    print("v2スキーマのテーブルが削除されました")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="データベーススキーマの初期化")
    parser.add_argument("--drop", action="store_true", help="既存のテーブルを削除")
    args = parser.parse_args()
    
    if args.drop:
        drop_tables()
    else:
        init_schema()