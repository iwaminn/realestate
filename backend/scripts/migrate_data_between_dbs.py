#!/usr/bin/env python3
"""
realestate_dbからrealestateデータベースへデータを移行するスクリプト
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# データベース接続設定
SOURCE_DB_URL = "postgresql://realestate:realestate_pass@localhost:5432/realestate_db"
TARGET_DB_URL = "postgresql://realestate:realestate_pass@localhost:5432/realestate"

def migrate_data():
    """realestate_dbからrealestateへデータを移行"""
    
    # エンジンとセッションの作成
    source_engine = create_engine(SOURCE_DB_URL)
    target_engine = create_engine(TARGET_DB_URL)
    
    try:
        # テーブル一覧
        tables = [
            'buildings',
            'building_aliases', 
            'building_external_ids',
            'master_properties',
            'property_listings',
            'listing_price_history',
            'property_images'
        ]
        
        with source_engine.connect() as source_conn:
            with target_engine.connect() as target_conn:
                for table in tables:
                    logger.info(f"移行中: {table}")
                    
                    # ソースからデータを取得
                    result = source_conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    source_count = result.scalar()
                    
                    if source_count == 0:
                        logger.info(f"  {table}: データなし")
                        continue
                    
                    # ターゲットの既存データをクリア
                    target_conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    target_conn.commit()
                    
                    # データをコピー
                    # pg_dumpとpsqlを使用してデータを移行
                    dump_cmd = f"docker exec realestate-postgres pg_dump -U realestate -d realestate_db -t {table} --data-only"
                    restore_cmd = f"docker exec -i realestate-postgres psql -U realestate -d realestate"
                    
                    import subprocess
                    dump_process = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.PIPE)
                    restore_process = subprocess.Popen(restore_cmd, shell=True, stdin=dump_process.stdout)
                    dump_process.stdout.close()
                    restore_process.communicate()
                    
                    # 移行後のデータ数を確認
                    result = target_conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    target_count = result.scalar()
                    
                    logger.info(f"  {table}: {source_count} → {target_count} 件")
                    
                logger.info("シーケンスをリセット中...")
                # シーケンスをリセット
                sequences = [
                    ('buildings_id_seq', 'buildings'),
                    ('building_aliases_id_seq', 'building_aliases'),
                    ('building_external_ids_id_seq', 'building_external_ids'),
                    ('master_properties_id_seq', 'master_properties'),
                    ('property_listings_id_seq', 'property_listings'),
                    ('listing_price_history_id_seq', 'listing_price_history'),
                    ('property_images_id_seq', 'property_images')
                ]
                
                for seq_name, table_name in sequences:
                    try:
                        target_conn.execute(text(f"SELECT setval('{seq_name}', (SELECT MAX(id) FROM {table_name}))"))
                        target_conn.commit()
                    except Exception as e:
                        logger.warning(f"シーケンス {seq_name} のリセットに失敗: {e}")
                
        logger.info("データ移行が完了しました！")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    migrate_data()