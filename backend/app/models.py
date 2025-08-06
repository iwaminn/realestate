"""
SQLAlchemyのモデル定義（v2スキーマ）
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Date, JSON, UniqueConstraint, Index, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Building(Base):
    """建物マスターテーブル"""
    __tablename__ = "buildings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 建物基本情報
    normalized_name = Column(String(200), nullable=False)     # 正規化された建物名（多数決で決定）
    canonical_name = Column(String(200))                       # 検索用正規化名（2025年1月追加）
    reading = Column(String(255))                              # 読み仮名（カタカナ）
    address = Column(String(500))                              # 住所（詳細）
    normalized_address = Column(String(500))                   # 正規化された住所（比較用）
    total_floors = Column(Integer)                             # 総階数
    basement_floors = Column(Integer)                          # 地下階数
    built_year = Column(Integer)                               # 築年
    built_month = Column(Integer)                              # 築月
    construction_type = Column(String(100))                    # 構造（RC造など）
    land_rights = Column(String(500))                          # 敷地の権利形態
    station_info = Column(Text)                                # 交通情報（建物レベル）
    
    # 管理情報
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    properties = relationship("MasterProperty", back_populates="building")
    external_ids = relationship("BuildingExternalId", back_populates="building")
    aliases = relationship("BuildingAlias", back_populates="building")
    
    __table_args__ = (
        Index('idx_buildings_normalized_name', 'normalized_name'),
        Index('idx_buildings_canonical_name', 'canonical_name'),
        Index('idx_buildings_address', 'address'),
        Index('idx_buildings_normalized_address', 'normalized_address'),
        Index('idx_buildings_canonical_normalized_addr', 'canonical_name', 'normalized_address'),
        Index('idx_buildings_built_year', 'built_year'),
    )


class BuildingAlias(Base):
    """建物エイリアステーブル"""
    __tablename__ = "building_aliases"
    
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(String(200), nullable=False)          # エイリアス名
    alias_type = Column(String(50))                           # エイリアスタイプ（例: 'english', 'katakana', 'abbreviation'）
    source_site = Column(String(50))                          # どのサイトで使用されているか
    is_primary = Column(Boolean, default=False)               # 主要なエイリアスかどうか
    confidence_score = Column(Float)                           # 信頼度スコア
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="aliases")
    
    __table_args__ = (
        UniqueConstraint('building_id', 'alias_name', name='unique_building_alias'),
        Index('idx_building_aliases_name', 'alias_name'),
        Index('idx_building_aliases_building', 'building_id'),
        Index('idx_building_aliases_type', 'alias_type'),
    )


class MasterProperty(Base):
    """物件マスターテーブル（重複排除済み）"""
    __tablename__ = "master_properties"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 建物との関連
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False, index=True)
    
    # 物件識別情報
    room_number = Column(String(50))                          # 部屋番号
    property_hash = Column(String(64), nullable=True)  # 物件の一意識別ハッシュ（非推奨、将来削除予定）
    
    # 物件基本情報（各掲載から集約）
    floor_number = Column(Integer)                            # 階数（所在階）
    area = Column(Float)                                      # 専有面積（㎡）
    balcony_area = Column(Float)                              # バルコニー面積（㎡）
    layout = Column(String(20))                               # 間取り（例: 1LDK）
    direction = Column(String(20))                            # 方角（例: 南向き）
    
    # 物件付属情報（多数決で決定）
    management_fee = Column(Integer)                          # 管理費（月額・円）
    repair_fund = Column(Integer)                             # 修繕積立金（月額・円）
    station_info = Column(Text)                               # 交通情報（物件レベル）
    parking_info = Column(Text)                               # 駐車場情報（物件レベル）
    
    # 建物名関連（物件ごとに異なる場合がある）
    display_building_name = Column(String(200))               # 表示用建物名（多数決で決定）
    
    # 販売情報
    sold_at = Column(DateTime)                                # 販売終了日（全掲載が終了した時点）
    final_price = Column(Integer)                             # 最終販売価格（販売終了前の最頻値）
    
    # 管理情報
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="properties")
    listings = relationship("PropertyListing", back_populates="master_property")
    
    __table_args__ = (
        Index('idx_master_properties_building_id', 'building_id'),
        Index('idx_master_properties_floor_number', 'floor_number'),
        Index('idx_master_properties_layout', 'layout'),
        Index('idx_master_properties_property_hash', 'property_hash'),
    )


class PropertyListing(Base):
    """物件掲載情報テーブル（サイト・業者別）"""
    __tablename__ = "property_listings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # マスター物件との関連
    master_property_id = Column(Integer, ForeignKey("master_properties.id", ondelete="CASCADE"), nullable=False)
    
    # 掲載元情報
    source_site = Column(String(50), nullable=False)         # 掲載サイト（SUUMO, LIFULL HOME'Sなど）
    site_property_id = Column(String(100), nullable=False)    # サイト内での物件ID
    url = Column(String(500), nullable=False)                 # 物件詳細URL
    
    # 掲載情報
    title = Column(String(500))                               # 物件タイトル
    current_price = Column(Integer)                           # 現在の価格（万円）
    
    # 詳細情報（サイトごとに異なる可能性がある項目）
    station_info = Column(Text)                               # 交通（駅からの距離など）
    description = Column(Text)                                # 物件説明
    management_company = Column(String(200))                  # 管理会社
    management_fee = Column(Integer)                          # 管理費
    repair_fund = Column(Integer)                             # 修繕積立金
    
    # サイト特有の情報
    agency_name = Column(String(200))                         # 取扱不動産会社
    agency_tel = Column(String(50))                           # 不動産会社電話番号
    remarks = Column(Text)                                    # 備考・その他情報
    summary_remarks = Column(Text)                            # 備考要約（LLMで生成）
    
    # 物件掲載上の詳細（実際の値と異なる可能性）
    listing_building_name = Column(String(200))               # 掲載上の建物名（サイト表記）
    listing_floor_number = Column(Integer)                    # 掲載上の階数
    listing_area = Column(Float)                              # 掲載上の面積
    listing_layout = Column(String(20))                       # 掲載上の間取り
    listing_direction = Column(String(20))                    # 掲載上の方角
    listing_total_floors = Column(Integer)                    # 掲載上の総階数
    listing_building_structure = Column(String(100))          # 掲載上の建物構造
    listing_built_year = Column(Integer)                      # 掲載上の築年
    listing_built_month = Column(Integer)                     # 掲載上の築月
    listing_balcony_area = Column(Float)                      # 掲載上のバルコニー面積
    listing_address = Column(Text)                            # 掲載上の住所
    listing_basement_floors = Column(Integer)                 # 掲載上の地下階数
    listing_land_rights = Column(String(500))                 # 掲載上の敷地権利形態
    listing_parking_info = Column(Text)                       # 掲載上の駐車場情報
    listing_station_info = Column(Text)                       # 掲載上の交通情報
    
    # スクレイピング情報
    scraped_from_area = Column(String(20))                    # どのエリアのスクレイピングで取得されたか
    
    # 掲載状態
    is_active = Column(Boolean, default=True)                 # 掲載中かどうか
    first_seen_at = Column(DateTime, server_default=func.now())
    last_scraped_at = Column(DateTime, server_default=func.now())
    last_fetched_at = Column(DateTime, server_default=func.now())  # 最終詳細取得日時
    published_at = Column(DateTime)                            # 情報提供日（サイトが表示している日付）
    first_published_at = Column(DateTime)                      # 情報公開日（物件情報が初めて公開された日）
    price_updated_at = Column(DateTime)                        # 価格改定日（最後に価格が変更された日）
    last_confirmed_at = Column(DateTime, server_default=func.now())  # 最終確認日時（スクレイピング時に更新）
    delisted_at = Column(DateTime)                            # 掲載終了日時
    
    # 詳細ページ取得管理
    detail_fetched_at = Column(DateTime)                      # 詳細ページを最後に取得した日時
    detail_info = Column(JSON)                                # 詳細ページから取得した追加情報
    list_update_date = Column(Date)                           # 一覧ページに表示される更新日
    sold_at = Column(DateTime)                                # 販売終了日（掲載が終了した日時）
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    master_property = relationship("MasterProperty", back_populates="listings")
    price_history = relationship("ListingPriceHistory", back_populates="listing")
    
    __table_args__ = (
        UniqueConstraint('source_site', 'site_property_id', name='property_listings_site_property_unique'),
        Index('idx_property_listings_master_property_id', 'master_property_id'),
        Index('idx_property_listings_source_site', 'source_site'),
        Index('idx_property_listings_is_active', 'is_active'),
        Index('idx_property_listings_url_source', 'url', 'source_site'),
        Index('idx_property_listings_site_property_source', 'site_property_id', 'source_site'),
    )


class ListingPriceHistory(Base):
    """掲載価格履歴テーブル"""
    __tablename__ = "listing_price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    property_listing_id = Column(Integer, ForeignKey("property_listings.id", ondelete="CASCADE"), nullable=False)
    price = Column(Integer, nullable=False)                   # 価格（万円）
    management_fee = Column(Integer)                          # 管理費
    repair_fund = Column(Integer)                             # 修繕積立金
    recorded_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    listing = relationship("PropertyListing", back_populates="price_history")
    
    __table_args__ = (
        Index('idx_listing_price_history_property_listing_id', 'property_listing_id'),
        Index('idx_listing_price_history_recorded_at', 'recorded_at'),
    )


class BuildingExternalId(Base):
    """建物外部IDテーブル（各サイトの建物IDを管理）
    
    重複建物の防止のために実際に使用されています。
    各不動産サイト固有の建物IDを記録し、同じ建物が複数回登録されることを防ぎます。
    """
    __tablename__ = "building_external_ids"
    
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    source_site = Column(String(50), nullable=False)         # サイト名
    external_id = Column(String(100), nullable=False)        # 外部ID
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="external_ids")
    
    __table_args__ = (
        UniqueConstraint('source_site', 'external_id', name='unique_building_external_id'),
        Index('idx_building_external_ids_building_id', 'building_id'),
        Index('idx_building_external_ids_source_external', 'source_site', 'external_id'),
    )


class ScrapingTask(Base):
    """スクレイピングタスク管理テーブル"""
    __tablename__ = "scraping_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(50), nullable=False)           # 'scrape', 'detail_fetch' など
    source_site = Column(String(50), nullable=False)         # SUUMO, LIFULL HOME'S など
    area = Column(String(100))                                # スクレイピング対象エリア
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, failed
    progress = Column(Integer, default=0)                     # 進捗率（0-100）
    current_page = Column(Integer, default=0)                 # 現在のページ番号
    total_pages = Column(Integer, default=0)                  # 総ページ数
    total_items = Column(Integer, default=0)                  # 総アイテム数
    processed_items = Column(Integer, default=0)              # 処理済みアイテム数
    new_items = Column(Integer, default=0)                    # 新規登録数
    updated_items = Column(Integer, default=0)                # 更新数
    failed_items = Column(Integer, default=0)                 # 失敗数
    is_paused = Column(Boolean, default=False)               # 一時停止フラグ
    is_cancelled = Column(Boolean, default=False)            # キャンセルフラグ
    priority = Column(Integer, default=0)                     # 優先度
    error_message = Column(Text)                              # エラーメッセージ
    result_summary = Column(JSON)                             # 結果サマリー
    started_at = Column(DateTime)                             # 開始時刻
    completed_at = Column(DateTime)                           # 完了時刻
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_scraping_tasks_status', 'status'),
        Index('idx_scraping_tasks_source_site', 'source_site'),
        Index('idx_scraping_tasks_created_at', 'created_at'),
    )


class BuildingMergeHistory(Base):
    """建物統合履歴テーブル"""
    __tablename__ = "building_merge_history"
    
    id = Column(Integer, primary_key=True, index=True)
    primary_building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)  # 旧フィールド（互換性のため残す）
    merged_building_id = Column(Integer, nullable=False)      # 統合された建物ID（削除済み）
    merged_building_name = Column(String(200))                # 統合された建物名（正規化済み）
    canonical_merged_name = Column(Text)                      # 検索キー（照合用）
    merged_by = Column(String(100))                           # 統合実行者
    merged_at = Column(DateTime, server_default=func.now())
    reason = Column(Text)                                     # 統合理由
    property_count = Column(Integer)                          # 統合時の物件数
    merge_details = Column(JSON)                              # 統合詳細（物件IDリスト含む）
    
    # ハイブリッド方式用の新フィールド
    direct_primary_building_id = Column(Integer, ForeignKey("buildings.id"))  # 直接の統合先
    final_primary_building_id = Column(Integer, ForeignKey("buildings.id"))    # 最終的な統合先（検索用キャッシュ）
    merge_depth = Column(Integer, default=0)                  # 統合の深さ（チェーンの階層）
    
    # リレーションシップ
    primary_building = relationship("Building", foreign_keys=[primary_building_id])
    direct_primary_building = relationship("Building", foreign_keys=[direct_primary_building_id])
    final_primary_building = relationship("Building", foreign_keys=[final_primary_building_id])
    
    __table_args__ = (
        Index('idx_building_merge_history_primary', 'primary_building_id'),
        Index('idx_building_merge_history_merged', 'merged_building_id'),
        Index('idx_building_merge_history_merged_at', 'merged_at'),
        Index('idx_building_merge_history_canonical', 'canonical_merged_name'),  # 検索用インデックス追加
        Index('idx_building_merge_history_final_primary', 'final_primary_building_id'),  # 最終統合先用インデックス
        Index('idx_building_merge_history_direct_primary', 'direct_primary_building_id'),  # 直接統合先用インデックス
    )


class BuildingMergeExclusion(Base):
    """建物統合候補除外テーブル"""
    __tablename__ = "building_merge_exclusions"
    
    id = Column(Integer, primary_key=True, index=True)
    building1_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    building2_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    excluded_by = Column(String(100))                         # 除外したユーザー
    reason = Column(Text)                                     # 除外理由
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    building1 = relationship("Building", foreign_keys=[building1_id])
    building2 = relationship("Building", foreign_keys=[building2_id])
    
    __table_args__ = (
        UniqueConstraint('building1_id', 'building2_id', name='unique_building_exclusion'),
        Index('idx_building_merge_exclusions_buildings', 'building1_id', 'building2_id'),
    )


class PropertyMergeHistory(Base):
    """物件統合履歴テーブル"""
    __tablename__ = "property_merge_history"
    
    id = Column(Integer, primary_key=True, index=True)
    primary_property_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)  # 旧フィールド（互換性のため残す）
    merged_property_id = Column(Integer, nullable=False)      # 統合された物件ID（削除済み）
    moved_listings = Column(Integer)                          # 移動した掲載情報数
    merge_details = Column(JSON)                              # 統合の詳細情報
    merged_by = Column(String(100))                           # 統合実行者
    merged_at = Column(DateTime, server_default=func.now())
    reason = Column(Text)                                     # 統合理由
    listing_count = Column(Integer)                           # 統合時の掲載数
    
    # ハイブリッド方式用の新フィールド
    direct_primary_property_id = Column(Integer, ForeignKey("master_properties.id"))  # 直接の統合先
    final_primary_property_id = Column(Integer, ForeignKey("master_properties.id"))    # 最終的な統合先（検索用キャッシュ）
    merge_depth = Column(Integer, default=0)                  # 統合の深さ（チェーンの階層）
    
    # リレーションシップ
    primary_property = relationship("MasterProperty", foreign_keys=[primary_property_id])
    direct_primary_property = relationship("MasterProperty", foreign_keys=[direct_primary_property_id])
    final_primary_property = relationship("MasterProperty", foreign_keys=[final_primary_property_id])
    
    __table_args__ = (
        Index('idx_property_merge_history_primary', 'primary_property_id'),
        Index('idx_property_merge_history_created', 'merged_at'),
        Index('idx_property_merge_history_final_primary', 'final_primary_property_id'),  # 最終統合先用インデックス
        Index('idx_property_merge_history_direct_primary', 'direct_primary_property_id'),  # 直接統合先用インデックス
    )


class PropertyMergeExclusion(Base):
    """物件統合候補除外テーブル"""
    __tablename__ = "property_merge_exclusions"
    
    id = Column(Integer, primary_key=True, index=True)
    property1_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)
    property2_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)
    excluded_by = Column(String(100))                         # 除外したユーザー
    reason = Column(Text)                                     # 除外理由
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    property1 = relationship("MasterProperty", foreign_keys=[property1_id])
    property2 = relationship("MasterProperty", foreign_keys=[property2_id])
    
    __table_args__ = (
        UniqueConstraint('property1_id', 'property2_id', name='unique_property_exclusion'),
        Index('idx_property_merge_exclusions_properties', 'property1_id', 'property2_id'),
    )


class Url404Retry(Base):
    """404エラーURL再試行管理テーブル"""
    __tablename__ = "url_404_retries"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(512), nullable=False)
    source_site = Column(String(50), nullable=False)
    first_error_at = Column(DateTime, nullable=False, server_default=func.now())
    last_error_at = Column(DateTime, nullable=False, server_default=func.now())
    error_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('url', 'source_site', name='unique_url_source_site'),
        Index('idx_url_404_retries_url_source', 'url', 'source_site'),
        Index('idx_url_404_retries_last_error', 'last_error_at'),
    )


class ScraperAlert(Base):
    """スクレイパーアラートテーブル"""
    __tablename__ = "scraper_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    source_site = Column(String(50), nullable=False)
    alert_type = Column(String(50), nullable=False)          # 'critical_fields_error', 'html_structure_change', etc
    severity = Column(String(20), nullable=False)            # 'high', 'medium', 'low'
    message = Column(Text, nullable=False)
    details = Column(JSON)                                    # 詳細情報（エラー率、影響範囲など）
    is_active = Column(Boolean, default=True)                # アラートがアクティブか
    resolved_at = Column(DateTime)                            # 解決日時
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_scraper_alerts_source_site', 'source_site'),
        Index('idx_scraper_alerts_is_active', 'is_active'),
        Index('idx_scraper_alerts_created_at', 'created_at'),
    )


class PriceMismatchHistory(Base):
    """価格不一致履歴テーブル"""
    __tablename__ = "price_mismatch_history"
    
    id = Column(Integer, primary_key=True, index=True)
    property_listing_id = Column(Integer, ForeignKey("property_listings.id"), nullable=False)
    list_price = Column(Integer, nullable=False)             # 一覧ページの価格
    detail_price = Column(Integer, nullable=False)           # 詳細ページの価格
    detected_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    listing = relationship("PropertyListing")
    
    __table_args__ = (
        Index('idx_price_mismatch_history_listing', 'property_listing_id'),
        Index('idx_price_mismatch_history_detected', 'detected_at'),
    )