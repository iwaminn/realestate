#!/usr/bin/env python3
"""
404エラーの再試行管理テーブルを再作成（シンプルな設計）
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

def recreate_404_retry_table():
    """404エラー再試行管理テーブルを再作成"""
    
    # 既存テーブルを削除
    drop_table_sql = "DROP TABLE IF EXISTS url_404_retries CASCADE;"
    
    # 新しいテーブルを作成
    create_table_sql = """
    CREATE TABLE url_404_retries (
        id SERIAL PRIMARY KEY,
        url VARCHAR(512) NOT NULL,
        source_site VARCHAR(50) NOT NULL,
        first_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        error_count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(url, source_site)
    );
    
    -- インデックスを作成
    CREATE INDEX idx_url_404_retries_url_source ON url_404_retries(url, source_site);
    CREATE INDEX idx_url_404_retries_last_error ON url_404_retries(last_error_at);
    
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
        conn.execute(text(drop_table_sql))
        conn.execute(text(create_table_sql))
        conn.commit()
        print("✅ url_404_retries テーブルを再作成しました")

if __name__ == "__main__":
    recreate_404_retry_table()
    
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