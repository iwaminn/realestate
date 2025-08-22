#!/usr/bin/env python3
"""
MasterPropertyテーブルにlatest_price_change_atカラムを追加し、
既存データの価格改定日を設定するマイグレーションスクリプト
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')

from sqlalchemy import text
from backend.app.database import SessionLocal
from backend.app.models import MasterProperty

def add_latest_price_change_column():
    """latest_price_change_atカラムを追加"""
    db = SessionLocal()
    try:
        # カラムが既に存在するか確認
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'master_properties' 
            AND column_name = 'latest_price_change_at'
        """))
        
        if result.fetchone():
            print("latest_price_change_atカラムは既に存在します")
            return False
            
        # カラムを追加
        print("latest_price_change_atカラムを追加中...")
        db.execute(text("""
            ALTER TABLE master_properties 
            ADD COLUMN latest_price_change_at TIMESTAMP
        """))
        db.commit()
        print("カラムを追加しました")
        
        # インデックスを作成
        print("インデックスを作成中...")
        db.execute(text("""
            CREATE INDEX idx_master_properties_latest_price_change_at 
            ON master_properties(latest_price_change_at DESC)
        """))
        db.commit()
        print("インデックスを作成しました")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"エラーが発生しました: {e}")
        raise
    finally:
        db.close()

def populate_latest_price_change_dates():
    """既存データの価格改定日を設定"""
    db = SessionLocal()
    try:
        print("既存データの価格改定日を計算中...")
        
        # 各物件の最新価格変更日を取得して更新
        update_query = text("""
            WITH latest_changes AS (
                SELECT 
                    pl.master_property_id,
                    MAX(lph.recorded_at) as latest_change_at
                FROM property_listings pl
                JOIN listing_price_history lph ON lph.property_listing_id = pl.id
                WHERE EXISTS (
                    -- 価格変更があったレコードのみ
                    SELECT 1 FROM listing_price_history lph2
                    WHERE lph2.property_listing_id = lph.property_listing_id
                    AND lph2.recorded_at < lph.recorded_at
                    AND lph2.price != lph.price
                )
                GROUP BY pl.master_property_id
            )
            UPDATE master_properties mp
            SET latest_price_change_at = lc.latest_change_at
            FROM latest_changes lc
            WHERE mp.id = lc.master_property_id
        """)
        
        result = db.execute(update_query)
        db.commit()
        
        updated_count = result.rowcount
        print(f"{updated_count}件の物件の価格改定日を設定しました")
        
        # 更新されなかった物件の数を確認
        no_change_count = db.query(MasterProperty).filter(
            MasterProperty.latest_price_change_at.is_(None)
        ).count()
        print(f"価格改定履歴のない物件: {no_change_count}件")
        
    except Exception as e:
        db.rollback()
        print(f"エラーが発生しました: {e}")
        raise
    finally:
        db.close()

def main():
    print("=== 価格改定日カラム追加スクリプト ===")
    print(f"実行時刻: {datetime.now()}")
    
    # カラムを追加
    column_added = add_latest_price_change_column()
    
    if column_added:
        # 既存データを更新
        populate_latest_price_change_dates()
    else:
        # カラムが既に存在する場合も、データの更新は実行
        response = input("既存データを再計算しますか？ (y/n): ")
        if response.lower() == 'y':
            populate_latest_price_change_dates()
    
    print("完了しました")

if __name__ == "__main__":
    main()