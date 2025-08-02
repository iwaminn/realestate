#!/usr/bin/env python3
"""
検証エラー再試行管理テーブルを作成するスクリプト

このスクリプトは、検証エラーが発生した物件URLを記録し、
一定期間再取得しないようにするためのテーブルを作成します。
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text

# データベース接続
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@postgres:5432/realestate')


def create_validation_error_retry_table():
    """検証エラー再試行管理テーブルを作成"""
    engine = create_engine(DATABASE_URL)
    
    # テーブル作成SQL
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS url_validation_error_retries (
        id SERIAL PRIMARY KEY,
        url VARCHAR(512) NOT NULL,
        source_site VARCHAR(50) NOT NULL,
        error_type VARCHAR(100) NOT NULL,  -- 検証エラーの種類（area_exceeded, price_exceeded等）
        error_details TEXT,  -- エラーの詳細情報（JSON形式で保存）
        first_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_error_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        error_count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_url_source_site_validation UNIQUE (url, source_site)
    );
    """
    
    # インデックス作成SQL
    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_url_validation_error_retries_url_source ON url_validation_error_retries (url, source_site);",
        "CREATE INDEX IF NOT EXISTS idx_url_validation_error_retries_last_error ON url_validation_error_retries (last_error_at);",
        "CREATE INDEX IF NOT EXISTS idx_url_validation_error_retries_error_type ON url_validation_error_retries (error_type);"
    ]
    
    try:
        with engine.connect() as conn:
            # テーブル作成
            conn.execute(text(create_table_sql))
            conn.commit()
            print("✅ テーブル 'url_validation_error_retries' を作成しました")
            
            # インデックス作成
            for idx_sql in create_indexes_sql:
                conn.execute(text(idx_sql))
                conn.commit()
            print("✅ インデックスを作成しました")
            
            # テーブル情報を表示
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'url_validation_error_retries'
                ORDER BY ordinal_position;
            """))
            
            print("\n📋 テーブル構造:")
            print("-" * 80)
            print(f"{'カラム名':<25} {'データ型':<20} {'NULL許可':<10} {'デフォルト値':<20}")
            print("-" * 80)
            
            for row in result:
                null_str = "YES" if row.is_nullable == "YES" else "NO"
                default_str = str(row.column_default) if row.column_default else ""
                print(f"{row.column_name:<25} {row.data_type:<20} {null_str:<10} {default_str:<20}")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = create_validation_error_retry_table()
    sys.exit(exit_code)