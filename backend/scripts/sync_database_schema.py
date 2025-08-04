#!/usr/bin/env python3
"""
データベーススキーマとORMモデルを同期するスクリプト
モデルに定義されているが実際のテーブルに存在しないカラムを検出し、追加する
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import Base
from sqlalchemy import text, inspect
from sqlalchemy.types import String, Integer, Boolean, Float, DateTime, Date, Text, JSON
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_sqlalchemy_type_to_sql(column_type):
    """SQLAlchemyの型をPostgreSQLの型に変換"""
    type_mapping = {
        String: lambda t: f"VARCHAR({t.length})" if hasattr(t, 'length') and t.length else "VARCHAR",
        Integer: lambda t: "INTEGER",
        Boolean: lambda t: "BOOLEAN",
        Float: lambda t: "DOUBLE PRECISION",
        DateTime: lambda t: "TIMESTAMP",
        Date: lambda t: "DATE",
        Text: lambda t: "TEXT",
        JSON: lambda t: "JSON",
    }
    
    for sqlalchemy_type, sql_func in type_mapping.items():
        if isinstance(column_type, sqlalchemy_type):
            return sql_func(column_type)
    
    # デフォルト
    return "TEXT"


def sync_table_schema(session, table_name, model_class):
    """特定のテーブルのスキーマを同期"""
    logger.info(f"\n=== {table_name} テーブルの同期開始 ===")
    
    # モデルのカラム情報を取得
    mapper = inspect(model_class)
    model_columns = {}
    
    for column in mapper.columns:
        model_columns[column.name] = {
            'type': column.type,
            'nullable': column.nullable,
            'default': column.default,
            'server_default': column.server_default
        }
    
    # データベースの実際のカラムを取得
    db_columns_query = text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name = :table_name
        ORDER BY ordinal_position
    """)
    
    db_columns = {}
    result = session.execute(db_columns_query, {"table_name": table_name})
    for row in result:
        db_columns[row.column_name] = {
            'data_type': row.data_type,
            'is_nullable': row.is_nullable
        }
    
    # モデルにあってデータベースにないカラムを検出
    missing_columns = set(model_columns.keys()) - set(db_columns.keys())
    
    if not missing_columns:
        logger.info("✓ スキーマは同期されています")
        return
    
    logger.info(f"以下のカラムが不足しています: {missing_columns}")
    
    # 不足しているカラムを追加
    for column_name in missing_columns:
        column_info = model_columns[column_name]
        sql_type = get_sqlalchemy_type_to_sql(column_info['type'])
        
        # ALTER TABLE文を構築
        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"
        
        # NULLABLEの設定
        if not column_info['nullable']:
            # NOT NULLの場合、デフォルト値が必要
            if column_info['server_default'] is not None:
                alter_sql += f" DEFAULT {column_info['server_default'].arg}"
            elif column_info['default'] is not None:
                # Pythonのデフォルト値を使用
                default_value = column_info['default'].arg
                if isinstance(default_value, str):
                    alter_sql += f" DEFAULT '{default_value}'"
                else:
                    alter_sql += f" DEFAULT {default_value}"
            alter_sql += " NOT NULL"
        else:
            # server_defaultがある場合は追加
            if column_info['server_default'] is not None:
                alter_sql += f" DEFAULT {column_info['server_default'].arg}"
        
        try:
            session.execute(text(alter_sql))
            session.commit()
            logger.info(f"✓ カラム追加成功: {column_name} ({sql_type})")
        except Exception as e:
            session.rollback()
            logger.error(f"✗ カラム追加失敗: {column_name} - {e}")


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 同期対象のテーブル
        tables_to_sync = [
            ('buildings', 'Building'),
            ('building_aliases', 'BuildingAlias'),
            ('master_properties', 'MasterProperty'),
            ('property_listings', 'PropertyListing'),
            ('listing_price_history', 'ListingPriceHistory'),
            ('property_images', 'PropertyImage'),
            ('building_external_ids', 'BuildingExternalId'),
            ('scraping_tasks', 'ScrapingTask'),
            ('building_merge_history', 'BuildingMergeHistory'),
            ('property_merge_history', 'PropertyMergeHistory'),
            ('url_404_retries', 'Url404Retry'),
            ('scraper_alerts', 'ScraperAlert'),
            ('price_mismatch_history', 'PriceMismatchHistory'),
        ]
        
        # 各テーブルを同期
        for table_name, model_name in tables_to_sync:
            # モデルクラスを動的に取得
            from backend.app import models
            model_class = getattr(models, model_name, None)
            
            if model_class:
                sync_table_schema(session, table_name, model_class)
            else:
                logger.warning(f"モデル {model_name} が見つかりません")
        
        logger.info("\n=== スキーマ同期完了 ===")
        
        # 最終確認：PropertyListingの全カラムを表示
        logger.info("\nPropertyListingテーブルの最終確認:")
        columns_query = text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'property_listings' 
            ORDER BY ordinal_position
        """)
        
        result = session.execute(columns_query)
        for row in result:
            logger.info(f"  - {row.column_name}: {row.data_type}")
        
    except Exception as e:
        logger.error(f"エラー発生: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()