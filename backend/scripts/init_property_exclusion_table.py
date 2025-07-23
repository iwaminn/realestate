#!/usr/bin/env python3
"""
物件除外テーブルの初期化スクリプト
"""

import os
import sys
sys.path.append('/app')

from sqlalchemy import text
from backend.app.database import SessionLocal, engine
from backend.app.models import PropertyMergeExclusion

def init_property_exclusion_table():
    """物件除外テーブルを作成"""
    try:
        # テーブルの存在確認
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'property_merge_exclusions'
                )
            """))
            table_exists = result.scalar()
            
            if not table_exists:
                print("Creating property_merge_exclusions table...")
                # テーブルを作成
                PropertyMergeExclusion.__table__.create(engine)
                print("✅ property_merge_exclusions table created successfully")
            else:
                print("ℹ️ property_merge_exclusions table already exists")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    init_property_exclusion_table()