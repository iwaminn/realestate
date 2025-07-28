#!/usr/bin/env python3
"""
404エラーの再試行管理テーブルを作成
"""

import os
import sys
from datetime import datetime

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# データベース接続
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def create_404_retry_table():
    """404エラー再試行管理テーブルを作成"""
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS url_404_retries (
        id SERIAL PRIMARY KEY,
        url VARCHAR(512) NOT NULL,
        source_site VARCHAR(50) NOT NULL,
        first_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        error_count INTEGER NOT NULL DEFAULT 1,
        retry_interval_hours INTEGER NOT NULL DEFAULT 2,
        next_retry_after TIMESTAMP NOT NULL,
        is_permanently_invalid BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(url, source_site)
    );
    
    -- インデックスを作成
    CREATE INDEX IF NOT EXISTS idx_url_404_retries_next_retry ON url_404_retries(next_retry_after) WHERE NOT is_permanently_invalid;
    CREATE INDEX IF NOT EXISTS idx_url_404_retries_url_source ON url_404_retries(url, source_site);
    
    -- updated_atを自動更新するトリガー
    CREATE OR REPLACE FUNCTION update_url_404_retries_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS update_url_404_retries_updated_at_trigger ON url_404_retries;
    CREATE TRIGGER update_url_404_retries_updated_at_trigger
    BEFORE UPDATE ON url_404_retries
    FOR EACH ROW
    EXECUTE FUNCTION update_url_404_retries_updated_at();
    """
    
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()
        print("✅ url_404_retries テーブルを作成しました")

def add_sample_data():
    """サンプルデータを追加（テスト用）"""
    
    sample_sql = """
    INSERT INTO url_404_retries (url, source_site, error_count, retry_interval_hours, next_retry_after)
    VALUES 
        ('https://www.livable.co.jp/grantact/detail/TEST1', 'livable', 1, 2, CURRENT_TIMESTAMP + INTERVAL '2 hours'),
        ('https://www.livable.co.jp/grantact/detail/TEST2', 'livable', 3, 8, CURRENT_TIMESTAMP + INTERVAL '8 hours')
    ON CONFLICT (url, source_site) DO NOTHING;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(sample_sql))
        conn.commit()
        print(f"✅ サンプルデータを追加しました（{result.rowcount}件）")

if __name__ == "__main__":
    create_404_retry_table()
    
    # テーブルの情報を表示
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'url_404_retries'
            ORDER BY ordinal_position;
        """))
        
        print("\n📋 url_404_retries テーブルの構造:")
        for row in result:
            print(f"  - {row[0]}: {row[1]} (NULL: {row[2]}, DEFAULT: {row[3]})")