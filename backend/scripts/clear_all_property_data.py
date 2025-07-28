#!/usr/bin/env python3
"""
すべての物件データをクリアするスクリプト

実行方法:
docker exec realestate-backend poetry run python /app/backend/scripts/clear_all_property_data.py

注意: このスクリプトはすべての物件データを削除します！
"""

import sys
import os

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app.database import engine, SessionLocal
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_all_property_data():
    """すべての物件データをクリア"""
    session = SessionLocal()
    
    try:
        # 確認メッセージ
        print("\n" + "="*60)
        print("警告: このスクリプトはすべての物件データを削除します！")
        print("以下のデータが削除されます:")
        print("- 物件画像 (property_images)")
        print("- 価格履歴 (listing_price_history)")
        print("- 物件掲載情報 (property_listings)")
        print("- 物件マスター (master_properties)")
        print("- 建物外部ID (building_external_ids)")
        print("- 建物情報 (buildings)")
        print("- 物件統合履歴 (property_merge_history)")
        print("- 物件除外履歴 (property_merge_exclusions)")
        print("="*60)
        
        # 確認プロンプトをスキップ（自動実行用）
        # response = input("\n本当に削除しますか? (yes/no): ")
        # if response.lower() != 'yes':
        #     print("処理を中止しました")
        #     return
        
        logger.info("物件データのクリアを開始します...")
        
        # 外部キー制約を一時的に無効化
        session.execute(text("SET session_replication_role = 'replica';"))
        
        # 削除順序（依存関係を考慮）
        tables_to_clear = [
            ('property_images', 'property_images'),
            ('listing_price_history', 'listing_price_history'),
            ('property_listings', 'property_listings'),
            ('property_merge_history', 'property_merge_history'),
            ('property_merge_exclusions', 'property_merge_exclusions'),
            ('master_properties', 'master_properties'),
            ('building_external_ids', 'building_external_ids'),
            ('buildings', 'buildings'),
        ]
        
        for table_name, display_name in tables_to_clear:
            try:
                # 現在の件数を取得
                result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                
                if count > 0:
                    # データを削除
                    session.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
                    session.commit()
                    logger.info(f"{display_name}: {count:,}件のデータを削除しました")
                else:
                    logger.info(f"{display_name}: データなし（スキップ）")
                    
            except Exception as e:
                logger.error(f"{display_name}の削除に失敗しました: {e}")
                raise
        
        # 外部キー制約を再度有効化
        session.execute(text("SET session_replication_role = 'origin';"))
        session.commit()
        
        # シーケンスをリセット（オプション）
        logger.info("IDシーケンスをリセットしています...")
        sequences_to_reset = [
            'buildings_id_seq',
            'master_properties_id_seq',
            'property_listings_id_seq',
            'listing_price_history_id_seq',
            'property_images_id_seq',
            'building_external_ids_id_seq',
            'property_merge_history_id_seq',
            'property_merge_exclusions_id_seq',
        ]
        
        for seq_name in sequences_to_reset:
            try:
                session.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH 1"))
                logger.info(f"シーケンス {seq_name} をリセットしました")
            except Exception as e:
                logger.warning(f"シーケンス {seq_name} のリセットに失敗しました（存在しない可能性があります）: {e}")
        
        session.commit()
        
        logger.info("すべての物件データのクリアが完了しました")
        
        # 最終確認
        print("\n" + "="*60)
        print("削除結果:")
        for table_name, display_name in tables_to_clear:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.scalar()
            print(f"  {display_name}: {count}件")
        print("="*60)
        
    except SQLAlchemyError as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    clear_all_property_data()


if __name__ == "__main__":
    main()