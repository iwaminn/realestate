#!/usr/bin/env python3
"""
価格不一致履歴テーブルを追加するスクリプト
一覧ページと詳細ページで価格が異なる物件を記録し、一定期間再取得をスキップするため
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import CreateTable
from backend.app.models import Base

# データベース接続
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://realestate:realestate_pass@localhost:5432/realestate"
)
engine = create_engine(DATABASE_URL)


def create_price_mismatch_history_table():
    """価格不一致履歴テーブルを作成"""
    
    # SQLを直接実行してテーブルを作成
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS price_mismatch_history (
        id SERIAL PRIMARY KEY,
        source_site VARCHAR(50) NOT NULL,
        site_property_id VARCHAR(100) NOT NULL,
        property_url TEXT NOT NULL,
        list_price INTEGER NOT NULL,
        detail_price INTEGER NOT NULL,
        attempted_at TIMESTAMP NOT NULL DEFAULT NOW(),
        retry_after TIMESTAMP NOT NULL,
        is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
        resolved_at TIMESTAMP,
        UNIQUE(source_site, site_property_id)
    );
    
    -- インデックスを作成
    CREATE INDEX IF NOT EXISTS idx_price_mismatch_history_site_id 
    ON price_mismatch_history(source_site, site_property_id);
    
    CREATE INDEX IF NOT EXISTS idx_price_mismatch_history_retry 
    ON price_mismatch_history(retry_after);
    
    CREATE INDEX IF NOT EXISTS idx_price_mismatch_history_resolved 
    ON price_mismatch_history(is_resolved);
    """
    
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()
        print("✅ price_mismatch_historyテーブルを作成しました")


def add_sample_data():
    """サンプルデータを追加（オプション）"""
    sample_sql = """
    -- 既存のサンプルデータをクリア
    DELETE FROM price_mismatch_history WHERE site_property_id IN ('TEST001', 'TEST002');
    
    -- サンプルデータを追加
    INSERT INTO price_mismatch_history 
    (source_site, site_property_id, property_url, list_price, detail_price, retry_after)
    VALUES 
    ('livable', 'TEST001', 'https://www.livable.co.jp/test/001/', 5000, 5500, NOW() + INTERVAL '7 days'),
    ('livable', 'TEST002', 'https://www.livable.co.jp/test/002/', 10000, 11000, NOW() + INTERVAL '7 days')
    ON CONFLICT (source_site, site_property_id) DO NOTHING;
    """
    
    with engine.connect() as conn:
        conn.execute(text(sample_sql))
        conn.commit()
        print("✅ サンプルデータを追加しました")


def show_table_info():
    """テーブル情報を表示"""
    info_sql = """
    SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_name = 'price_mismatch_history'
    ORDER BY ordinal_position;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(info_sql))
        print("\n📋 price_mismatch_historyテーブルの構造:")
        print("-" * 80)
        for row in result:
            print(f"{row[0]:<20} {row[1]:<15} NULL: {row[2]:<5} DEFAULT: {row[3] or 'なし'}")


if __name__ == "__main__":
    print("価格不一致履歴テーブルの作成を開始します...")
    
    try:
        # テーブルを作成
        create_price_mismatch_history_table()
        
        # テーブル情報を表示
        show_table_info()
        
        # サンプルデータを追加するか確認
        if len(sys.argv) > 1 and sys.argv[1] == "--with-sample":
            add_sample_data()
        
        print("\n✅ 処理が完了しました")
        
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)