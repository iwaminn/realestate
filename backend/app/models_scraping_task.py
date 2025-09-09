"""
スクレイピングタスク管理用のモデル定義
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, Float, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .models import Base


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
    last_progress_at = Column(DateTime, nullable=True)  # 最終進捗更新時刻
    
    # 統計情報
    total_processed = Column(Integer, nullable=False, default=0)
    total_new = Column(Integer, nullable=False, default=0)
    total_updated = Column(Integer, nullable=False, default=0)
    total_errors = Column(Integer, nullable=False, default=0)
    elapsed_time = Column(Float, nullable=True)  # 秒単位
    
    # 詳細な進捗情報（JSON形式）
    progress_detail = Column(JSON, nullable=True)  # 各スクレイパー・エリアごとの進捗
    # ログはScrapingTaskLogテーブルで管理するため、ここでは削除
    
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
    
    # リレーションシップ
    progress_records = relationship("ScrapingTaskProgress", cascade="all, delete-orphan", back_populates="task")
    logs = relationship("ScrapingTaskLog", cascade="all, delete-orphan", back_populates="task")
    
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
            'last_progress_at': self.last_progress_at.isoformat() if self.last_progress_at else None,
            'total_processed': self.total_processed,
            'total_new': self.total_new,
            'total_updated': self.total_updated,
            'total_errors': self.total_errors,
            'elapsed_time': self.elapsed_time,
            'progress_detail': self.progress_detail,
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
    task_id = Column(String(50), ForeignKey('scraping_tasks.task_id', ondelete='CASCADE'), primary_key=True, index=True)
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
    
    # リレーションシップ
    task = relationship("ScrapingTask", back_populates="progress_records")
    
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


class ScrapingTaskLog(Base):
    """スクレイピングタスクのログを管理するテーブル"""
    __tablename__ = "scraping_task_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(50), ForeignKey('scraping_tasks.task_id', ondelete='CASCADE'), nullable=False, index=True)
    log_type = Column(String(20), nullable=False)  # property_update, error, warning
    timestamp = Column(DateTime, nullable=False, default=datetime.now)
    message = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)  # 詳細情報（辞書形式）
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    
    # リレーションシップ
    task = relationship("ScrapingTask", back_populates="logs")

