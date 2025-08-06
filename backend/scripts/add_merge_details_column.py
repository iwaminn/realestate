#!/usr/bin/env python3
"""
building_merge_historyテーブルにmerge_detailsカラムを追加し、
既存データに物件IDリストを含む詳細情報を設定する
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_database_url():
    """データベースURLを取得"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # デフォルトのDocker環境用URL
        database_url = "postgresql://realestate:realestate_pass@postgres:5432/realestate"
    return database_url

def add_merge_details_column():
    """merge_detailsカラムを追加し、既存データを更新"""
    
    # データベース接続
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # トランザクション開始
        trans = conn.begin()
        
        try:
            # カラムの存在確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'building_merge_history' 
                AND column_name = 'merge_details'
            """))
            
            if result.fetchone():
                print("✓ merge_detailsカラムは既に存在します")
            else:
                print("merge_detailsカラムを追加中...")
                conn.execute(text("""
                    ALTER TABLE building_merge_history 
                    ADD COLUMN IF NOT EXISTS merge_details JSON
                """))
                print("  ✓ merge_detailsカラムを追加しました")
            
            # 既存データの更新（merge_detailsがNULLの場合のみ）
            print("\n既存データの更新中...")
            
            # 既存の履歴を取得
            histories = conn.execute(text("""
                SELECT id, merged_building_id, merged_building_name, property_count
                FROM building_merge_history
                WHERE merge_details IS NULL
            """)).fetchall()
            
            if histories:
                print(f"  {len(histories)}件の履歴を更新します")
                
                for history in histories:
                    # 基本的な建物情報でmerge_detailsを作成
                    # （物件IDリストは新規データのみで記録される）
                    merge_details = {
                        "merged_buildings": [{
                            "id": history.merged_building_id,
                            "normalized_name": history.merged_building_name,
                            "properties_moved": history.property_count or 0,
                            "property_ids": []  # 既存データでは物件IDリストは不明
                        }],
                        "legacy_data": True,  # 旧形式のデータであることを示すフラグ
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    conn.execute(
                        text("""
                            UPDATE building_merge_history 
                            SET merge_details = :details
                            WHERE id = :history_id
                        """),
                        {"details": json.dumps(merge_details), "history_id": history.id}
                    )
                
                print(f"  ✓ {len(histories)}件の履歴を更新しました")
            else:
                print("  更新が必要な履歴はありません")
            
            trans.commit()
            print("\n✓ マイグレーションが完了しました")
            
        except Exception as e:
            trans.rollback()
            print(f"\n✗ エラーが発生しました: {e}")
            raise

def verify_migration():
    """マイグレーション結果を確認"""
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # merge_detailsがNULLでないレコード数を確認
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(merge_details) as with_details,
                COUNT(*) - COUNT(merge_details) as without_details
            FROM building_merge_history
        """)).fetchone()
        
        print("\n=== 検証結果 ===")
        print(f"総レコード数: {result.total}")
        print(f"merge_details設定済み: {result.with_details}")
        print(f"merge_details未設定: {result.without_details}")
        
        # サンプルデータを表示
        sample = conn.execute(text("""
            SELECT id, merged_building_name, merge_details
            FROM building_merge_history
            WHERE merge_details IS NOT NULL
            LIMIT 1
        """)).fetchone()
        
        if sample:
            print(f"\nサンプルデータ (ID: {sample.id}):")
            print(f"建物名: {sample.merged_building_name}")
            # PostgreSQLのJSONカラムは既にdictとして返される
            details = sample.merge_details if sample.merge_details else {}
            print(f"merge_details: {json.dumps(details, indent=2, ensure_ascii=False)}")

if __name__ == "__main__":
    print("=== building_merge_historyテーブルのmerge_detailsカラム追加 ===\n")
    add_merge_details_column()
    verify_migration()