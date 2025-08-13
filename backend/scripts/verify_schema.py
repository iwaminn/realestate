#!/usr/bin/env python3
"""
データベーススキーマの検証スクリプト
モデル定義と実際のテーブル構造が一致しているか確認
"""

import sys
import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import DATABASE_URL
from backend.app.models import Base

# すべてのモデルを明示的にインポート
from backend.app.models import (
    Building, BuildingAlias, BuildingExternalId,
    BuildingMergeHistory, BuildingMergeExclusion,
    MasterProperty, PropertyListing, ListingPriceHistory,
    PropertyMergeHistory, PropertyMergeExclusion,
    Url404Retry, ScraperAlert, PriceMismatchHistory
)
from backend.app.models_property_matching import AmbiguousPropertyMatch
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress


def verify_schema():
    """スキーマの検証"""
    print("=" * 60)
    print("データベーススキーマ検証")
    print("=" * 60)
    
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    
    # 期待されるテーブル（モデル定義から取得）
    expected_tables = set()
    for mapper in Base.registry.mappers:
        expected_tables.add(mapper.class_.__tablename__)
    
    # 実際のテーブル
    actual_tables = set(inspector.get_table_names())
    
    print(f"\n📊 期待されるテーブル数: {len(expected_tables)}")
    print(f"📊 実際のテーブル数: {len(actual_tables)}")
    
    # 不足しているテーブル
    missing_tables = expected_tables - actual_tables
    if missing_tables:
        print(f"\n❌ 不足しているテーブル ({len(missing_tables)}):")
        for table in sorted(missing_tables):
            print(f"  - {table}")
    else:
        print("\n✅ すべての期待されるテーブルが存在します")
    
    # 余分なテーブル
    extra_tables = actual_tables - expected_tables
    if extra_tables:
        print(f"\n⚠️  余分なテーブル ({len(extra_tables)}):")
        for table in sorted(extra_tables):
            print(f"  - {table}")
    
    # 重要なテーブルのカラム検証
    print("\n" + "=" * 60)
    print("重要なテーブルのカラム検証")
    print("=" * 60)
    
    critical_tables = {
        'scraping_tasks': ScrapingTask,
        'scraping_task_progress': ScrapingTaskProgress,
        'buildings': Building,
        'master_properties': MasterProperty,
        'property_listings': PropertyListing
    }
    
    for table_name, model_class in critical_tables.items():
        if table_name in actual_tables:
            print(f"\n📋 {table_name}:")
            
            # モデルから期待されるカラム
            expected_columns = set()
            for column in model_class.__table__.columns:
                expected_columns.add(column.name)
            
            # 実際のカラム
            actual_columns = set()
            for col in inspector.get_columns(table_name):
                actual_columns.add(col['name'])
            
            print(f"  期待: {len(expected_columns)} カラム")
            print(f"  実際: {len(actual_columns)} カラム")
            
            # 不足しているカラム
            missing_cols = expected_columns - actual_columns
            if missing_cols:
                print(f"  ❌ 不足: {', '.join(sorted(missing_cols))}")
            
            # 余分なカラム
            extra_cols = actual_columns - expected_columns
            if extra_cols:
                print(f"  ⚠️  余分: {', '.join(sorted(extra_cols))}")
            
            if not missing_cols and not extra_cols:
                print(f"  ✅ カラム構造が完全に一致")
    
    print("\n" + "=" * 60)
    print("検証完了")
    print("=" * 60)
    
    # 結果サマリー
    if not missing_tables and all(
        table_name not in actual_tables or 
        set(model_class.__table__.columns.keys()) == set(col['name'] for col in inspector.get_columns(table_name))
        for table_name, model_class in critical_tables.items()
    ):
        print("\n🎉 すべての検証に合格しました！")
        return True
    else:
        print("\n⚠️  一部の検証に失敗しました。上記の詳細を確認してください。")
        return False


if __name__ == "__main__":
    verify_schema()