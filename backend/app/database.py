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
    # 並列スクレイピング用に接続プールサイズを増やす
    # pool_size: 常時保持する接続数
    # max_overflow: pool_sizeを超えて作成可能な追加接続数
    # pool_pre_ping: 接続の有効性を事前にチェック
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,  # デフォルト5から増加
        max_overflow=30,  # デフォルト10から増加
        pool_pre_ping=True  # 接続の有効性をチェック
    )

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
    """
    スクレイピングタスク用のデータベースセッション（手動管理）
    
    重要: スクレイパー専用の独立したセッションを作成します。
    これにより、他のコンポーネントのトランザクションエラーの影響を受けません。
    
    使用方法:
        session = get_db_for_scraping()
        try:
            # データベース操作
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()  # 必ずcloseすること
    """
    # 新しいセッションを作成して返す
    # autoflush=Falseでauto-flushを無効化し、明示的なコミットのみを使用
    session = SessionLocal()
    
    # セッションの状態をリセット（念のため）
    session.rollback()
    
    return session