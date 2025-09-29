#!/usr/bin/env python3
"""
不動産取引価格テーブルの作成
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from sqlalchemy import create_engine
from app.models import Base, TransactionPrice

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def create_table():
    """TransactionPriceテーブルを作成"""
    engine = create_engine(DATABASE_URL)

    # テーブルを作成（既存のテーブルはスキップ）
    Base.metadata.tables['transaction_prices'].create(engine, checkfirst=True)
    print("transaction_pricesテーブルを作成しました")

if __name__ == "__main__":
    create_table()