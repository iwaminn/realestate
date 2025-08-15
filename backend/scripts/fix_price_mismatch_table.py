#!/usr/bin/env python
"""
price_mismatch_historyテーブルを修正するスクリプト
"""
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from backend.app.database import engine

def fix_price_mismatch_table():
    """price_mismatch_historyテーブルを再作成"""
    
    with engine.connect() as conn:
        # トランザクション開始
        trans = conn.begin()
        
        try:
            # 既存のテーブルを削除（存在する場合）
            print("既存のprice_mismatch_historyテーブルを削除中...")
            conn.execute(text("DROP TABLE IF EXISTS price_mismatch_history CASCADE"))
            
            # 新しいテーブルを作成
            print("新しいprice_mismatch_historyテーブルを作成中...")
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
            print("インデックスを作成中...")
            conn.execute(text("CREATE INDEX idx_price_mismatch_source ON price_mismatch_history(source_site)"))
            conn.execute(text("CREATE INDEX idx_price_mismatch_detected ON price_mismatch_history(detected_at)"))
            conn.execute(text("CREATE INDEX idx_price_mismatch_retry ON price_mismatch_history(retry_after)"))
            conn.execute(text("CREATE INDEX idx_price_mismatch_resolved ON price_mismatch_history(is_resolved)"))
            
            # コミット
            trans.commit()
            print("✅ price_mismatch_historyテーブルの修正が完了しました")
            
        except Exception as e:
            trans.rollback()
            print(f"❌ エラーが発生しました: {e}")
            raise

if __name__ == "__main__":
    fix_price_mismatch_table()