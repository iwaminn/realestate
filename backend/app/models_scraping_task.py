"""
スクレイピングタスク管理用のモデル定義
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, Float, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ScrapingTask(Base):
    """スクレイピングタスクの情報を管理するテーブル"""
    __tablename__ = "scraping_tasks"
    
    # 基本情報
    task_id = Column(String(50), primary_key=True, index=True)
    status = Column(String(20), nullable=False, default='running')  # running, completed, error, cancelled, paused
    
    # 実行パラメータ
    scrapers = Column(JSON, nullable=False)  # ['suumo', 'homes', ...]
    areas = Column(JSON, nullable=False)  # ['13101', '13102', ...]
    max_properties = Column(Integer, nullable=False, default=100)
    force_detail_fetch = Column(Boolean, nullable=False, default=False)
    
    # タイムスタンプ
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # 統計情報
    total_processed = Column(Integer, nullable=False, default=0)
    total_new = Column(Integer, nullable=False, default=0)
    total_updated = Column(Integer, nullable=False, default=0)
    total_errors = Column(Integer, nullable=False, default=0)
    elapsed_time = Column(Float, nullable=True)  # 秒単位
    
    # 詳細な進捗情報（JSON形式）
    progress_detail = Column(JSON, nullable=True)  # 各スクレイパー・エリアごとの進捗
    error_logs = Column(JSON, nullable=True)  # エラーログ
    logs = Column(JSON, nullable=True)  # 物件処理ログ（新規登録・更新など）
    
    # 追加の統計情報
    properties_found = Column(Integer, nullable=False, default=0)
    detail_fetched = Column(Integer, nullable=False, default=0)
    detail_skipped = Column(Integer, nullable=False, default=0)
    price_missing = Column(Integer, nullable=False, default=0)
    building_info_missing = Column(Integer, nullable=False, default=0)
    
    # 制御フラグ
    is_paused = Column(Boolean, nullable=False, default=False)
    is_cancelled = Column(Boolean, nullable=False, default=False)
    pause_requested_at = Column(DateTime, nullable=True)
    cancel_requested_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """辞書形式に変換"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'scrapers': self.scrapers,
            'areas': self.areas,
            'max_properties': self.max_properties,
            'force_detail_fetch': self.force_detail_fetch,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'total_processed': self.total_processed,
            'total_new': self.total_new,
            'total_updated': self.total_updated,
            'total_errors': self.total_errors,
            'elapsed_time': self.elapsed_time,
            'progress_detail': self.progress_detail,
            'error_logs': self.error_logs,
            'logs': self.logs,
            'properties_found': self.properties_found,
            'detail_fetched': self.detail_fetched,
            'detail_skipped': self.detail_skipped,
            'price_missing': self.price_missing,
            'building_info_missing': self.building_info_missing,
            'is_paused': self.is_paused,
            'is_cancelled': self.is_cancelled,
            'pause_requested_at': self.pause_requested_at.isoformat() if self.pause_requested_at else None,
            'cancel_requested_at': self.cancel_requested_at.isoformat() if self.cancel_requested_at else None
        }


class ScrapingTaskProgress(Base):
    """スクレイピングタスクの詳細な進捗情報"""
    __tablename__ = "scraping_task_progress"
    
    # 複合主キー
    task_id = Column(String(50), primary_key=True, index=True)
    scraper = Column(String(20), primary_key=True)
    area = Column(String(20), primary_key=True)
    
    # ステータス
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, error
    
    # タイムスタンプ
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    
    # 統計情報
    processed = Column(Integer, nullable=False, default=0)
    new_listings = Column(Integer, nullable=False, default=0)
    updated_listings = Column(Integer, nullable=False, default=0)
    errors = Column(Integer, nullable=False, default=0)
    
    # 詳細統計
    properties_found = Column(Integer, nullable=False, default=0)
    properties_attempted = Column(Integer, nullable=False, default=0)
    detail_fetched = Column(Integer, nullable=False, default=0)
    detail_skipped = Column(Integer, nullable=False, default=0)
    detail_fetch_failed = Column(Integer, nullable=False, default=0)
    price_updated = Column(Integer, nullable=False, default=0)
    other_updates = Column(Integer, nullable=False, default=0)
    refetched_unchanged = Column(Integer, nullable=False, default=0)
    save_failed = Column(Integer, nullable=False, default=0)
    price_missing = Column(Integer, nullable=False, default=0)
    building_info_missing = Column(Integer, nullable=False, default=0)
    
    def to_dict(self):
        """辞書形式に変換"""
        return {
            'task_id': self.task_id,
            'scraper': self.scraper,
            'area': self.area,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'processed': self.processed,
            'new': self.new_listings,
            'updated': self.updated_listings,
            'errors': self.errors,
            'properties_found': self.properties_found,
            'properties_attempted': self.properties_attempted,
            'detail_fetched': self.detail_fetched,
            'detail_skipped': self.detail_skipped,
            'detail_fetch_failed': self.detail_fetch_failed,
            'price_updated': self.price_updated,
            'other_updates': self.other_updates,
            'refetched_unchanged': self.refetched_unchanged,
            'save_failed': self.save_failed,
            'price_missing': self.price_missing,
            'building_info_missing': self.building_info_missing
        }