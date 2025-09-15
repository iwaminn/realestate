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

# すべてのモデルを明示的にインポート（テーブル作成を保証）
from backend.app.models import (
    Building, BuildingExternalId,
    BuildingMergeHistory, BuildingMergeExclusion,
    MasterProperty, PropertyListing, ListingPriceHistory,
    PropertyMergeHistory, PropertyMergeExclusion,
    Url404Retry, ScraperAlert, PriceMismatchHistory
)
from backend.app.models_property_matching import AmbiguousPropertyMatch
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress

# UrlValidationErrorRetryモデルを確認
try:
    from backend.app.models import UrlValidationErrorRetry
except ImportError:
    # モデルが存在しない場合は無視
    pass


def init_schema():
    """v2スキーマのテーブルを作成"""
    print("データベーススキーマv2を初期化中...")
    
    # エンジンを作成
    engine = create_engine(DATABASE_URL)
    
    try:
        # 全てのテーブルを作成
        Base.metadata.create_all(bind=engine)
        
        # 実際に作成されたテーブルを動的に取得
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        print(f"✅ {len(tables)}個のテーブルが作成されました:")
        for table in sorted(tables):
            columns = inspector.get_columns(table)
            print(f"  - {table} ({len(columns)} columns)")
        
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
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica';"))
    
    # テーブルを削除
    Base.metadata.drop_all(bind=engine)
    
    # 外部キー制約を再度有効化
    with engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'origin';"))
    
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