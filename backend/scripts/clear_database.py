#!/usr/bin/env python3
"""
データベースをクリアするスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal, engine, Base
from backend.app.models import *
from sqlalchemy import text

def clear_database():
    """データベースをクリア"""
    session = SessionLocal()
    try:
        print("=== データベースをクリアします ===")
        
        # 外部キー制約を一時的に無効化
        session.execute(text("SET session_replication_role = 'replica';"))
        
        # 各テーブルのデータを削除（依存関係の逆順）
        tables_to_clear = [
            'property_images',
            'listing_price_history',
            'property_listings',
            'master_properties',
            'building_external_ids',
            'building_aliases',
            'buildings'
        ]
        
        for table in tables_to_clear:
            try:
                result = session.execute(text(f"DELETE FROM {table}"))
                count = result.rowcount
                print(f"{table}: {count}件削除")
            except Exception as e:
                print(f"{table}: エラー - {e}")
        
        # 外部キー制約を再度有効化
        session.execute(text("SET session_replication_role = 'origin';"))
        
        # シーケンスをリセット
        sequences = [
            'buildings_id_seq',
            'building_aliases_id_seq', 
            'building_external_ids_id_seq',
            'master_properties_id_seq',
            'property_listings_id_seq',
            'listing_price_history_id_seq',
            'property_images_id_seq'
        ]
        
        for seq in sequences:
            try:
                session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
                print(f"{seq}: リセット")
            except Exception as e:
                print(f"{seq}: エラー - {e}")
        
        session.commit()
        print("\n✅ データベースのクリア完了")
        
        # 確認
        print("\n=== テーブルの状態を確認 ===")
        for table in tables_to_clear:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"{table}: {count}件")
            
    except Exception as e:
        print(f"エラー: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    clear_database()