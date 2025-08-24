#!/usr/bin/env python
"""
エラー管理テーブルの構造を更新するスクリプト
"""
import os
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')

from sqlalchemy import create_engine, text
from backend.app.database import engine
from backend.app.models import Base, PropertyValidationError

def update_tables():
    """テーブル構造を更新"""
    
    print("テーブル構造を更新します...")
    
    # 1. PropertyValidationErrorテーブルを作成
    print("\n1. PropertyValidationErrorテーブルを作成...")
    PropertyValidationError.__table__.create(engine, checkfirst=True)
    print("   → 完了")
    
    # 2. price_mismatch_historyテーブルのカラムを確認・修正
    print("\n2. price_mismatch_historyテーブルを確認...")
    with engine.connect() as conn:
        # テーブルが存在するか確認
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'price_mismatch_history'
            )
        """))
        table_exists = result.scalar()
        
        if table_exists:
            # カラムを確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'price_mismatch_history'
                ORDER BY ordinal_position
            """))
            columns = [row[0] for row in result]
            print(f"   既存のカラム: {columns}")
            
            # property_listing_idカラムが存在する場合は、新しい構造に移行
            if 'property_listing_id' in columns:
                print("   → 古い構造のテーブルを新しい構造に移行します...")
                
                # 古いテーブルをバックアップ
                conn.execute(text("""
                    ALTER TABLE price_mismatch_history 
                    RENAME TO price_mismatch_history_old
                """))
                conn.commit()
                print("   → 古いテーブルをバックアップしました")
                
                # 新しいテーブルを作成
                conn.execute(text("""
                    CREATE TABLE price_mismatch_history (
                        id SERIAL PRIMARY KEY,
                        source_site VARCHAR(50) NOT NULL,
                        site_property_id VARCHAR(500) NOT NULL,
                        property_url VARCHAR(500),
                        list_price INTEGER NOT NULL,
                        detail_price INTEGER NOT NULL,
                        detected_at TIMESTAMP DEFAULT NOW(),
                        attempted_at TIMESTAMP DEFAULT NOW(),
                        retry_after TIMESTAMP DEFAULT NOW() + INTERVAL '7 days',
                        retry_count INTEGER DEFAULT 0,
                        is_resolved BOOLEAN DEFAULT FALSE,
                        resolution_note TEXT,
                        UNIQUE(source_site, site_property_id)
                    )
                """))
                
                # インデックスを作成
                conn.execute(text("""
                    CREATE INDEX idx_price_mismatch_source ON price_mismatch_history(source_site);
                    CREATE INDEX idx_price_mismatch_retry ON price_mismatch_history(retry_after);
                    CREATE INDEX idx_price_mismatch_resolved ON price_mismatch_history(is_resolved);
                    CREATE INDEX idx_price_mismatch_detected ON price_mismatch_history(detected_at);
                """))
                conn.commit()
                print("   → 新しいテーブルを作成しました")
                
                # 古いデータがあれば移行（可能な範囲で）
                conn.execute(text("""
                    INSERT INTO price_mismatch_history (
                        source_site, site_property_id, property_url, 
                        list_price, detail_price, detected_at
                    )
                    SELECT 
                        pl.source_site,
                        pl.site_property_id,
                        pl.url,
                        pmh.list_price,
                        pmh.detail_price,
                        pmh.detected_at
                    FROM price_mismatch_history_old pmh
                    JOIN property_listings pl ON pmh.property_listing_id = pl.id
                    ON CONFLICT (source_site, site_property_id) DO NOTHING
                """))
                conn.commit()
                print("   → データを移行しました")
                
                # 古いテーブルを削除
                conn.execute(text("DROP TABLE price_mismatch_history_old"))
                conn.commit()
                print("   → 古いテーブルを削除しました")
            else:
                print("   → テーブル構造は既に新しい形式です")
        else:
            # テーブルが存在しない場合は作成
            print("   → テーブルが存在しないため作成します...")
            conn.execute(text("""
                CREATE TABLE price_mismatch_history (
                    id SERIAL PRIMARY KEY,
                    source_site VARCHAR(50) NOT NULL,
                    site_property_id VARCHAR(500) NOT NULL,
                    property_url VARCHAR(500),
                    list_price INTEGER NOT NULL,
                    detail_price INTEGER NOT NULL,
                    detected_at TIMESTAMP DEFAULT NOW(),
                    attempted_at TIMESTAMP DEFAULT NOW(),
                    retry_after TIMESTAMP DEFAULT NOW() + INTERVAL '7 days',
                    retry_count INTEGER DEFAULT 0,
                    is_resolved BOOLEAN DEFAULT FALSE,
                    resolution_note TEXT,
                    UNIQUE(source_site, site_property_id)
                )
            """))
            
            # インデックスを作成
            conn.execute(text("""
                CREATE INDEX idx_price_mismatch_source ON price_mismatch_history(source_site);
                CREATE INDEX idx_price_mismatch_retry ON price_mismatch_history(retry_after);
                CREATE INDEX idx_price_mismatch_resolved ON price_mismatch_history(is_resolved);
                CREATE INDEX idx_price_mismatch_detected ON price_mismatch_history(detected_at);
            """))
            conn.commit()
            print("   → テーブルを作成しました")
    
    print("\n✅ テーブル構造の更新が完了しました")
    
    # 各テーブルの件数を表示
    with engine.connect() as conn:
        for table_name in ['url_404_retries', 'price_mismatch_history', 'property_validation_errors']:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = result.scalar()
            print(f"   {table_name}: {count}件")

if __name__ == "__main__":
    update_tables()