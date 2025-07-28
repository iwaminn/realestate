"""
データベースモデル定義 v2.0
重複排除と複数サイト管理に対応
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Index, Boolean, UniqueConstraint, JSON, Date, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

try:
    from .database import Base
    from .scrapers.constants import SourceSite
except ImportError:
    from backend.app.database import Base
    from backend.app.scrapers.constants import SourceSite


class Building(Base):
    """建物マスターテーブル"""
    __tablename__ = "buildings"
    
    id = Column(Integer, primary_key=True, index=True)
    normalized_name = Column(String(255), nullable=False)  # 標準化された建物名
    canonical_name = Column(String(255), index=True)       # 検索用の正規化名（内部使用）
    reading = Column(String(255), index=True)              # 読み仮名（ひらがな）
    address = Column(String(500))                          # 標準化された住所
    total_floors = Column(Integer)                         # 総階数（地上階数）
    basement_floors = Column(Integer)                      # 地下階数
    total_units = Column(Integer)                          # 総戸数
    built_year = Column(Integer)                           # 築年
    structure = Column(String(100))                        # 構造（RC造など）
    land_rights = Column(String(500))                      # 敷地の権利形態（所有権、定期借地権等）
    parking_info = Column(Text)                            # 駐車場情報
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    aliases = relationship("BuildingAlias", back_populates="building")
    properties = relationship("MasterProperty", back_populates="building")
    external_ids = relationship("BuildingExternalId", back_populates="building")
    
    __table_args__ = (
        Index('idx_buildings_normalized_name', 'normalized_name'),
        Index('idx_buildings_address', 'address'),
    )


class BuildingAlias(Base):
    """建物名エイリアステーブル"""
    __tablename__ = "building_aliases"
    
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(String(255), nullable=False)      # 実際に使われている建物名
    source = Column(String(50))                            # どのサイトで使われているか
    occurrence_count = Column(Integer, default=1)          # この表記の出現回数
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="aliases")
    
    __table_args__ = (
        Index('idx_building_aliases_alias_name', 'alias_name'),
        Index('idx_building_aliases_building_id', 'building_id'),
    )


class BuildingExternalId(Base):
    """建物の外部ID管理テーブル（現在は使用していない）"""
    __tablename__ = "building_external_ids"
    
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    source_site = Column(SQLEnum(SourceSite, values_callable=lambda obj: [e.value for e in obj]), nullable=False)  # スクレイピング対象サイト
    external_id = Column(String(255), nullable=False)     # サイト固有の建物ID
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="external_ids")
    
    __table_args__ = (
        UniqueConstraint('source_site', 'external_id', name='_site_external_id_uc'),
        Index('idx_building_external_ids_source_external', 'source_site', 'external_id'),
    )


class MasterProperty(Base):
    """物件マスターテーブル（重複排除済み）"""
    __tablename__ = "master_properties"
    
    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    room_number = Column(String(50))                      # 部屋番号
    floor_number = Column(Integer)                        # 階数
    area = Column(Float)                                  # 専有面積
    balcony_area = Column(Float)                          # バルコニー面積
    layout = Column(String(50))                           # 間取り
    direction = Column(String(50))                        # 方角
    summary_remarks = Column(Text)                        # 備考要約（全掲載サイトの備考を要約）
    property_hash = Column(String(255), unique=True)      # 建物ID+部屋番号のハッシュ
    resale_property_id = Column(Integer, ForeignKey("master_properties.id"))  # 再販の場合、前の物件ID
    is_resale = Column(Boolean, default=False)            # 買い取り再販フラグ
    sold_at = Column(DateTime)                            # 販売終了日（全掲載が終了した日）
    last_sale_price = Column(Integer)                     # 最終販売価格（販売終了時の価格）
    
    # 多数決で決定される情報
    management_fee = Column(Integer)                      # 管理費（月額・円）- 多数決で決定
    repair_fund = Column(Integer)                         # 修繕積立金（月額・円）- 多数決で決定
    station_info = Column(Text)                           # 交通情報 - 多数決で決定
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    building = relationship("Building", back_populates="properties")
    listings = relationship("PropertyListing", back_populates="master_property")
    
    __table_args__ = (
        Index('idx_master_properties_building_id', 'building_id'),
        Index('idx_master_properties_property_hash', 'property_hash'),
    )


class PropertyListing(Base):
    """物件掲載情報テーブル"""
    __tablename__ = "property_listings"
    
    id = Column(Integer, primary_key=True, index=True)
    master_property_id = Column(Integer, ForeignKey("master_properties.id", ondelete="CASCADE"), nullable=False)
    source_site = Column(SQLEnum(SourceSite, values_callable=lambda obj: [e.value for e in obj]), nullable=False)  # スクレイピング対象サイト
    site_property_id = Column(String(255))                # サイト内の物件ID
    url = Column(String(1000), nullable=False)  # uniqueは複合制約で定義
    title = Column(String(500))                           # 掲載タイトル
    description = Column(Text)                            # 物件説明
    
    # 掲載元情報
    agency_name = Column(String(255))                     # 仲介業者名
    agency_tel = Column(String(50))                       # 問い合わせ電話番号
    
    # 価格情報（最新）
    current_price = Column(Integer)                       # 現在の価格（万円）
    management_fee = Column(Integer)                      # 管理費
    repair_fund = Column(Integer)                         # 修繕積立金
    
    # その他の情報
    station_info = Column(Text)                           # 最寄り駅情報
    features = Column(Text)                               # 物件特徴
    remarks = Column(Text)                                # 物件備考（このサイトでの備考）
    
    # 掲載サイトごとの物件属性情報（多数決用）
    listing_floor_number = Column(Integer)                # この掲載での階数情報
    listing_area = Column(Float)                          # この掲載での専有面積
    listing_layout = Column(String(50))                   # この掲載での間取り
    listing_direction = Column(String(50))                # この掲載での方角
    listing_total_floors = Column(Integer)                # この掲載での総階数
    listing_building_structure = Column(String(100))      # この掲載での建物構造
    listing_built_year = Column(Integer)                  # この掲載での築年
    listing_balcony_area = Column(Float)                  # この掲載でのバルコニー面積
    listing_address = Column(Text)                        # この掲載での住所
    
    # 掲載状態
    is_active = Column(Boolean, default=True)             # 掲載中かどうか
    first_seen_at = Column(DateTime, server_default=func.now())
    last_scraped_at = Column(DateTime, server_default=func.now())
    last_fetched_at = Column(DateTime, server_default=func.now())  # 最終詳細取得日時
    published_at = Column(DateTime)                        # 情報提供日（サイトが表示している日付）
    first_published_at = Column(DateTime)                  # 情報公開日（物件情報が初めて公開された日）
    price_updated_at = Column(DateTime)                    # 価格改定日（最後に価格が変更された日）
    last_confirmed_at = Column(DateTime, server_default=func.now())  # 最終確認日時（スクレイピング時に更新）
    delisted_at = Column(DateTime)                        # 掲載終了日時
    
    # 詳細ページ取得管理
    detail_fetched_at = Column(DateTime)                  # 詳細ページを最後に取得した日時
    has_update_mark = Column(Boolean, default=False)      # 一覧ページで更新マークが検出されたか
    detail_info = Column(JSON)                            # 詳細ページから取得した追加情報
    list_update_date = Column(Date)                       # 一覧ページに表示される更新日
    sold_at = Column(DateTime)                            # 販売終了日（掲載が終了した日時）
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # リレーションシップ
    master_property = relationship("MasterProperty", back_populates="listings")
    price_history = relationship("ListingPriceHistory", back_populates="listing")
    images = relationship("PropertyImage", back_populates="listing")
    
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
    price = Column(Integer, nullable=False)               # 価格（万円）
    management_fee = Column(Integer)                      # 管理費
    repair_fund = Column(Integer)                         # 修繕積立金
    recorded_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    listing = relationship("PropertyListing", back_populates="price_history")
    
    __table_args__ = (
        Index('idx_listing_price_history_property_listing_id', 'property_listing_id'),
        Index('idx_listing_price_history_recorded_at', 'recorded_at'),
    )


class PropertyImage(Base):
    """物件画像テーブル"""
    __tablename__ = "property_images"
    
    id = Column(Integer, primary_key=True, index=True)
    property_listing_id = Column(Integer, ForeignKey("property_listings.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(1000))
    image_type = Column(String(50))                       # 外観、間取り図、室内など
    display_order = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    listing = relationship("PropertyListing", back_populates="images")
    
    __table_args__ = (
        Index('idx_property_images_property_listing_id', 'property_listing_id'),
    )


class BuildingMergeExclusion(Base):
    """建物統合候補除外テーブル"""
    __tablename__ = "building_merge_exclusions"
    
    id = Column(Integer, primary_key=True, index=True)
    building1_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    building2_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    excluded_by = Column(String(100))  # 除外したユーザー（将来の拡張用）
    reason = Column(Text)              # 除外理由
    created_at = Column(DateTime, server_default=func.now())
    
    # リレーションシップ
    building1 = relationship("Building", foreign_keys=[building1_id])
    building2 = relationship("Building", foreign_keys=[building2_id])
    
    __table_args__ = (
        UniqueConstraint('building1_id', 'building2_id', name='unique_building_exclusion'),
        Index('idx_building_merge_exclusions_buildings', 'building1_id', 'building2_id'),
    )


class BuildingMergeHistory(Base):
    """建物統合履歴テーブル"""
    __tablename__ = "building_merge_history"
    
    id = Column(Integer, primary_key=True, index=True)
    primary_building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    merged_building_ids = Column(JSON, nullable=False)  # 統合された建物IDのリスト
    moved_properties = Column(Integer, nullable=False)  # 移動した物件数
    merged_by = Column(String(100))                     # 統合したユーザー（将来の拡張用）
    merge_details = Column(JSON)                        # 統合時の詳細情報（エイリアス、外部IDなど）
    created_at = Column(DateTime, server_default=func.now())
    reverted_at = Column(DateTime)                      # 取り消し日時
    reverted_by = Column(String(100))                   # 取り消したユーザー
    
    # リレーションシップ
    primary_building = relationship("Building", foreign_keys=[primary_building_id])
    
    __table_args__ = (
        Index('idx_building_merge_history_primary', 'primary_building_id'),
        Index('idx_building_merge_history_created', 'created_at'),
    )


class PropertyMergeHistory(Base):
    """物件統合履歴テーブル"""
    __tablename__ = "property_merge_history"
    
    id = Column(Integer, primary_key=True, index=True)
    primary_property_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)
    secondary_property_id = Column(Integer, nullable=False)  # 統合された物件ID（削除済み）
    moved_listings = Column(Integer, default=0)             # 移動された掲載数
    merge_details = Column(JSON)                            # 統合の詳細情報（物件情報のバックアップ）
    merged_by = Column(String(100))                         # 統合実行者
    merged_at = Column(DateTime, server_default=func.now())
    reverted_at = Column(DateTime)                          # 取り消し日時
    reverted_by = Column(String(100))                       # 取り消し実行者
    
    # リレーションシップ
    primary_property = relationship("MasterProperty", backref="merge_histories")
    
    __table_args__ = (
        Index('idx_property_merge_history_primary', 'primary_property_id'),
        Index('idx_property_merge_history_created', 'merged_at'),
    )


class PropertyMergeExclusion(Base):
    """物件統合候補除外テーブル"""
    __tablename__ = "property_merge_exclusions"
    
    id = Column(Integer, primary_key=True, index=True)
    property1_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)
    property2_id = Column(Integer, ForeignKey("master_properties.id"), nullable=False)
    excluded_by = Column(String(100))  # 除外したユーザー
    reason = Column(Text)              # 除外理由
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


