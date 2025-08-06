#!/usr/bin/env python
"""
建物統合履歴テーブルを物件統合履歴と同じ仕様に移行するスクリプト

既存の複数建物を一度に統合した履歴を、1対1の履歴に分割して保存し直す
"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.exc import SQLAlchemyError

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Base, get_db
from app.models import BuildingMergeHistory

# 環境変数からデータベースURLを取得
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def migrate_building_merge_history():
    """建物統合履歴を新しい形式に移行"""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("建物統合履歴の移行を開始します...")
        
        # 1. 新しいカラムを追加
        print("1. secondary_building_idカラムを追加...")
        try:
            db.execute(text("""
                ALTER TABLE building_merge_history 
                ADD COLUMN IF NOT EXISTS secondary_building_id INTEGER
            """))
            db.commit()
            print("   ✓ secondary_building_idカラムを追加しました")
        except Exception as e:
            print(f"   ! カラム追加時のエラー（既に存在する場合は無視）: {e}")
            db.rollback()
        
        # 2. 既存のデータを取得
        print("\n2. 既存の統合履歴を取得...")
        existing_records = db.query(BuildingMergeHistory).filter(
            BuildingMergeHistory.secondary_building_id.is_(None)
        ).all()
        print(f"   ✓ {len(existing_records)}件の履歴を処理します")
        
        # 3. 各レコードを処理
        new_records = []
        records_to_delete = []
        
        for record in existing_records:
            if hasattr(record, 'merged_building_ids') and record.merged_building_ids:
                merged_ids = record.merged_building_ids
                if isinstance(merged_ids, list) and len(merged_ids) > 0:
                    # 最初のIDで既存のレコードを更新
                    record.secondary_building_id = merged_ids[0]
                    
                    # 2つ目以降のIDで新しいレコードを作成
                    for i, building_id in enumerate(merged_ids[1:], 1):
                        # merge_detailsから該当する建物情報を取得
                        building_detail = None
                        if record.merge_details and "merged_buildings" in record.merge_details:
                            for detail in record.merge_details["merged_buildings"]:
                                if detail.get("id") == building_id:
                                    building_detail = detail
                                    break
                        
                        new_record = BuildingMergeHistory(
                            primary_building_id=record.primary_building_id,
                            secondary_building_id=building_id,
                            moved_properties=building_detail.get("properties_moved", 0) if building_detail else 0,
                            merged_by=record.merged_by,
                            merge_details={
                                "merged_buildings": [building_detail] if building_detail else [],
                                "original_batch": True,  # バッチ統合の一部であることを示すフラグ
                                "batch_index": i
                            },
                            created_at=record.created_at
                        )
                        new_records.append(new_record)
        
        # 4. 新しいレコードを保存
        if new_records:
            print(f"\n3. {len(new_records)}件の新しいレコードを作成...")
            db.add_all(new_records)
            db.commit()
            print("   ✓ 新しいレコードを保存しました")
        
        # 5. 既存レコードの更新
        print(f"\n4. {len(existing_records)}件の既存レコードを更新...")
        for record in existing_records:
            if hasattr(record, 'merged_building_ids') and record.merged_building_ids:
                # merge_detailsを更新して、最初の建物の情報のみを保持
                if record.merge_details and "merged_buildings" in record.merge_details:
                    first_building = None
                    for detail in record.merge_details["merged_buildings"]:
                        if detail.get("id") == record.secondary_building_id:
                            first_building = detail
                            break
                    
                    if first_building:
                        record.merge_details["merged_buildings"] = [first_building]
        
        db.commit()
        print("   ✓ 既存レコードを更新しました")
        
        # 6. インデックスを追加
        print("\n5. インデックスを追加...")
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_building_merge_history_secondary 
                ON building_merge_history(secondary_building_id)
            """))
            db.commit()
            print("   ✓ インデックスを追加しました")
        except Exception as e:
            print(f"   ! インデックス追加時のエラー（既に存在する場合は無視）: {e}")
            db.rollback()
        
        print("\n✅ 移行が完了しました！")
        
        # 統計情報を表示
        total_count = db.query(BuildingMergeHistory).count()
        print(f"\n統計情報:")
        print(f"  - 総レコード数: {total_count}")
        print(f"  - 新規作成: {len(new_records)}")
        print(f"  - 更新: {len(existing_records)}")
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_building_merge_history()