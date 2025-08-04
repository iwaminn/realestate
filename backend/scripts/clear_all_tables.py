#!/usr/bin/env python3
"""
データベースの全テーブルのデータをクリアするスクリプト
注意: このスクリプトはすべてのデータを削除します！
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import (
    Building, BuildingAlias, MasterProperty, PropertyListing,
    ListingPriceHistory, BuildingExternalId, BuildingMergeHistory,
    BuildingMergeExclusion, PropertyMergeHistory, PropertyMergeExclusion,
    Url404Retry
)
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
from sqlalchemy import text
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_all_tables():
    """全テーブルのデータをクリア"""
    session = SessionLocal()
    
    try:
        logger.info("=== データベースの全データ削除を開始 ===")
        
        # 外部キー制約を一時的に無効化
        session.execute(text("SET session_replication_role = 'replica';"))
        
        # 削除する順序（依存関係を考慮）
        tables_to_clear = [
            # スクレイピングタスク関連
            ScrapingTaskProgress,
            ScrapingTask,
            
            # 物件関連の履歴
            ListingPriceHistory,
            PropertyMergeExclusion,
            PropertyMergeHistory,
            
            # 物件関連
            PropertyListing,
            MasterProperty,
            
            # 建物関連の履歴
            BuildingMergeExclusion,
            BuildingMergeHistory,
            BuildingExternalId,
            BuildingAlias,
            
            # 建物
            Building,
            
            # その他
            Url404Retry,
        ]
        
        # 各テーブルのデータを削除
        for table_class in tables_to_clear:
            table_name = table_class.__tablename__
            try:
                count = session.query(table_class).count()
                if count > 0:
                    session.query(table_class).delete()
                    logger.info(f"✓ {table_name}: {count}件削除")
                else:
                    logger.info(f"- {table_name}: データなし")
            except Exception as e:
                logger.error(f"✗ {table_name}: エラー - {e}")
        
        # 外部キー制約を再度有効化
        session.execute(text("SET session_replication_role = 'origin';"))
        
        # シーケンスをリセット（PostgreSQL）
        logger.info("\n=== シーケンスのリセット ===")
        sequences = [
            'buildings_id_seq',
            'building_aliases_id_seq',
            'master_properties_id_seq',
            'property_listings_id_seq',
            'listing_price_history_id_seq',
            'building_external_ids_id_seq',
            'building_merge_history_id_seq',
            'building_merge_exclusions_id_seq',
            'property_merge_history_id_seq',
            'property_merge_exclusions_id_seq',
            'url_404_retries_id_seq',
            'scraping_tasks_id_seq',
            'scraping_task_progress_id_seq',
        ]
        
        for seq in sequences:
            try:
                session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                logger.info(f"✓ {seq}: リセット完了")
            except Exception as e:
                # シーケンスが存在しない場合はスキップ
                pass
        
        # コミット
        session.commit()
        logger.info("\n=== 全データの削除が完了しました ===")
        
        # 削除後の確認
        logger.info("\n=== 削除後の確認 ===")
        for table_class in tables_to_clear:
            count = session.query(table_class).count()
            logger.info(f"{table_class.__tablename__}: {count}件")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    import sys
    
    # コマンドライン引数で--forceが指定されている場合は確認をスキップ
    if "--force" in sys.argv:
        logger.info("--forceオプションが指定されたため、確認をスキップします")
        clear_all_tables()
        return
    
    print("\n" + "="*60)
    print("警告: このスクリプトはデータベースの全データを削除します！")
    print("この操作は元に戻すことができません。")
    print("="*60)
    
    response = input("\n本当に続行しますか？ (yes/N): ")
    if response.lower() != 'yes':
        logger.info("処理を中止しました")
        return
    
    # 二重確認
    response = input("もう一度確認します。本当にすべてのデータを削除してよろしいですか？ (yes/N): ")
    if response.lower() != 'yes':
        logger.info("処理を中止しました")
        return
    
    # 実行
    clear_all_tables()


if __name__ == "__main__":
    main()