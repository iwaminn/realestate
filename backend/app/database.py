"""
データベース接続設定
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# データベースURL（環境変数から取得）
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://realestate:realestate_pass@localhost:5432/realestate"
)

# SQLite用のURLをPostgreSQL用に変換（互換性のため）
if DATABASE_URL.startswith("sqlite"):
    # SQLiteの場合はそのまま使用
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # PostgreSQLの場合
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

@contextmanager
def get_db_context():
    """データベースセッションを取得（コンテキストマネージャ）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db():
    """FastAPI依存性注入用のデータベースセッション"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """データベースの初期化"""
    Base.metadata.create_all(bind=engine)

def get_db_for_scraping():
    """スクレイピングタスク用のデータベースセッション（手動管理）"""
    return SessionLocal()