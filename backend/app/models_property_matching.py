"""
物件マッチングの曖昧なケースを記録するモデル
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class AmbiguousPropertyMatch(Base):
    """曖昧な物件マッチングの記録"""
    __tablename__ = "ambiguous_property_matches"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # スクレイピング情報
    source_site = Column(String(50), nullable=False)          # スクレイピング元サイト
    scraping_url = Column(Text)                               # スクレイピングしたURL
    scraping_data = Column(JSON)                              # スクレイピングしたデータ
    
    # 選択された物件
    selected_property_id = Column(Integer, ForeignKey("master_properties.id"))
    selection_reason = Column(Text)                           # 選択理由
    
    # 候補物件（複数）
    candidate_property_ids = Column(JSON)                     # 候補物件のIDリスト
    candidate_details = Column(JSON)                          # 各候補の詳細情報
    candidate_count = Column(Integer)                         # 候補数
    
    # マッチング条件
    building_id = Column(Integer, ForeignKey("buildings.id"))
    floor_number = Column(Integer)
    area = Column(Float)
    layout = Column(String(50))
    direction = Column(String(50))
    room_number = Column(String(50))
    
    # 信頼度と状態
    confidence_score = Column(Float)                          # マッチングの信頼度（0.0-1.0）
    is_reviewed = Column(Boolean, default=False)              # 管理者によるレビュー済みか
    is_correct = Column(Boolean)                              # レビュー結果：正しいマッチングか
    reviewed_by = Column(String(100))                         # レビュー者
    reviewed_at = Column(DateTime)                            # レビュー日時
    review_notes = Column(Text)                               # レビューノート
    
    # 学習機能の使用有無
    used_learning = Column(Boolean, default=False)            # 学習機能を使用したか
    learning_patterns = Column(JSON)                          # 使用した学習パターン
    
    # タイムスタンプ
    created_at = Column(DateTime, default=datetime.now)
    
    # リレーションシップ
    selected_property = relationship("MasterProperty", foreign_keys=[selected_property_id])
    building = relationship("Building")
    
    def to_dict(self):
        """辞書形式に変換"""
        return {
            'id': self.id,
            'source_site': self.source_site,
            'selected_property_id': self.selected_property_id,
            'candidate_count': self.candidate_count,
            'confidence_score': self.confidence_score,
            'is_reviewed': self.is_reviewed,
            'is_correct': self.is_correct,
            'floor_number': self.floor_number,
            'area': self.area,
            'layout': self.layout,
            'direction': self.direction,
            'room_number': self.room_number,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }