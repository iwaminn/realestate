#!/usr/bin/env python3
"""
データベースの既存テーブルのデータをクリアするスクリプト
"""

import os
import sys
from sqlalchemy import create_engine, text
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)


def clear_existing_tables():
    """既存テーブルのデータをクリア"""
    
    # 外部キー制約を一時的に無効化してから削除
    truncate_sql = """
    -- 外部キー制約を一時的に無効化
    SET session_replication_role = 'replica';
    
    -- 既存テーブルをTRUNCATE（IDもリセット）
    TRUNCATE TABLE 
        price_mismatch_history,
        scraper_alerts,
        url_404_retries,
        property_merge_exclusions,
        property_merge_history,
        building_merge_exclusions,
        building_merge_history,
        scraping_tasks,
        building_external_ids,
        property_images,
        listing_price_history,
        property_listings,
        master_properties,
        buildings
    RESTART IDENTITY CASCADE;
    
    -- 外部キー制約を再度有効化
    SET session_replication_role = 'origin';
    """
    
    with engine.connect() as conn:
        conn.execute(text(truncate_sql))
        conn.commit()
        logger.info("既存テーブルのデータをクリアしました")


def show_table_counts():
    """各テーブルのレコード数を表示"""
    
    tables = [
        'buildings',
        'master_properties',
        'property_listings',
        'listing_price_history',
        'property_images',
        'building_external_ids',
        'scraping_tasks',
        'building_merge_history',
        'building_merge_exclusions',
        'property_merge_history',
        'property_merge_exclusions',
        'url_404_retries',
        'scraper_alerts',
        'price_mismatch_history'
    ]
    
    logger.info("\n各テーブルのレコード数:")
    
    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                logger.info(f"  {table}: {count} 件")
            except Exception as e:
                logger.error(f"  {table}: エラー - {e}")
                # トランザクションをロールバック
                conn.rollback()


def main():
    """メイン処理"""
    try:
        # 現在の状態を表示
        logger.info("=== クリア前の状態 ===")
        show_table_counts()
        
        # クリア実行（確認なしで実行）
        logger.info("\nデータをクリアしています...")
        clear_existing_tables()
        
        # クリア後の状態を表示
        logger.info("\n=== クリア後の状態 ===")
        show_table_counts()
        
        logger.info("\n処理が完了しました")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()