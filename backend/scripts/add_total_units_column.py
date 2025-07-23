#!/usr/bin/env python3
"""
建物テーブルに総戸数カラムを追加
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from backend.app.database import SessionLocal, engine

def add_total_units_column():
    """総戸数カラムを追加"""
    
    with engine.begin() as conn:
        # カラムが既に存在するか確認
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'buildings' 
            AND column_name = 'total_units'
        """))
        
        if result.fetchone():
            print("✅ total_unitsカラムは既に存在します")
            return
        
        # カラムを追加
        print("📝 total_unitsカラムを追加中...")
        conn.execute(text("""
            ALTER TABLE buildings 
            ADD COLUMN total_units INTEGER
        """))
        
        print("✅ total_unitsカラムが追加されました")

if __name__ == "__main__":
    add_total_units_column()