"""
物件情報と建物情報を多数決で更新するユーティリティ

このモジュールは既存のスクレイパーに組み込んで使用します
"""

from typing import Dict, List, Optional, Any
from collections import Counter
from sqlalchemy.orm import Session
from ..models import Building, MasterProperty, PropertyListing
import logging

logger = logging.getLogger(__name__)


class MajorityVoteUpdater:
    """多数決による情報更新クラス"""
    
    # サイトの優先順位（左が高優先度）
    SITE_PRIORITY = ['suumo', 'homes', 'rehouse', 'nomu']
    
    def __init__(self, session: Session):
        self.session = session
    
    @staticmethod
    def get_site_priority(site_name: str) -> int:
        """サイトの優先順位を取得（小さいほど高優先度）"""
        try:
            return MajorityVoteUpdater.SITE_PRIORITY.index(site_name.lower())
        except ValueError:
            return len(MajorityVoteUpdater.SITE_PRIORITY)  # 未知のサイトは最低優先度
    
    def get_majority_value(self, values_with_source: List[tuple], current_value: Any = None) -> Optional[Any]:
        """
        最頻値を取得する。同数の場合はサイト優先順位で決定
        
        Args:
            values_with_source: (値, ソースサイト名)のタプルのリスト
            current_value: 現在の値
            
        Returns:
            最頻値（Noneの場合もある）
        """
        # Noneや空文字を除外
        valid_items = [(v, s) for v, s in values_with_source if v is not None and v != '']
        if not valid_items:
            return current_value
        
        # 値の出現回数をカウント
        value_counter = Counter([v for v, _ in valid_items])
        max_count = max(value_counter.values())
        
        # 最頻値を取得
        most_common_values = [value for value, count in value_counter.items() if count == max_count]
        
        if len(most_common_values) == 1:
            # 最頻値が1つだけの場合
            return most_common_values[0]
        
        # 最頻値が複数ある場合、サイト優先順位で決定
        candidates = []
        for value in most_common_values:
            # この値を持つソースサイトを取得
            sources = [s for v, s in valid_items if v == value]
            # 最も優先度の高いサイトを特定
            best_priority = min(self.get_site_priority(s) for s in sources)
            candidates.append((value, best_priority))
        
        # 優先度順にソート
        candidates.sort(key=lambda x: x[1])
        
        return candidates[0][0]
    
    def collect_property_info_from_listings(self, master_property: MasterProperty) -> Dict[str, List[Any]]:
        """
        物件の全掲載情報から属性情報を収集する
        
        注：現在のデータ構造では、掲載情報から直接属性を取得できないため、
        将来的な拡張を想定した実装となっています
        """
        listings = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == master_property.id,
            PropertyListing.is_active == True
        ).all()
        
        info = {
            'floor_numbers': [],
            'areas': [],
            'layouts': [],
            'directions': [],
            'management_fees': [],
            'repair_funds': []
        }
        
        for listing in listings:
            # 管理費と修繕積立金は直接取得可能
            if listing.management_fee:
                info['management_fees'].append((listing.management_fee, listing.source_site))
            if listing.repair_fund:
                info['repair_funds'].append((listing.repair_fund, listing.source_site))
            
            # listing_*フィールドから情報を収集
            if hasattr(listing, 'listing_floor_number') and listing.listing_floor_number:
                info['floor_numbers'].append((listing.listing_floor_number, listing.source_site))
            if hasattr(listing, 'listing_area') and listing.listing_area:
                info['areas'].append((listing.listing_area, listing.source_site))
            if hasattr(listing, 'listing_layout') and listing.listing_layout:
                info['layouts'].append((listing.listing_layout, listing.source_site))
            if hasattr(listing, 'listing_direction') and listing.listing_direction:
                info['directions'].append((listing.listing_direction, listing.source_site))
        
        return info
    
    def update_master_property_by_majority(self, master_property: MasterProperty) -> bool:
        """
        物件情報を掲載情報の多数決で更新する
        
        Returns:
            更新があった場合True
        """
        info = self.collect_property_info_from_listings(master_property)
        updated = False
        
        # 各属性について多数決を取る
        
        # 階数の多数決
        if info['floor_numbers']:
            majority_floor = self.get_majority_value(info['floor_numbers'], master_property.floor_number)
            if majority_floor != master_property.floor_number:
                logger.info(f"物件ID {master_property.id} の階数を "
                          f"{master_property.floor_number} → {majority_floor} に更新")
                master_property.floor_number = majority_floor
                updated = True
        
        # 面積の多数決
        if info['areas']:
            majority_area = self.get_majority_value(info['areas'], master_property.area)
            if majority_area != master_property.area:
                logger.info(f"物件ID {master_property.id} の面積を "
                          f"{master_property.area} → {majority_area} に更新")
                master_property.area = majority_area
                updated = True
        
        # 間取りの多数決
        if info['layouts']:
            majority_layout = self.get_majority_value(info['layouts'], master_property.layout)
            if majority_layout != master_property.layout:
                logger.info(f"物件ID {master_property.id} の間取りを "
                          f"{master_property.layout} → {majority_layout} に更新")
                master_property.layout = majority_layout
                updated = True
        
        # 方角の多数決
        if info['directions']:
            majority_direction = self.get_majority_value(info['directions'], master_property.direction)
            if majority_direction != master_property.direction:
                logger.info(f"物件ID {master_property.id} の方角を "
                          f"{master_property.direction} → {majority_direction} に更新")
                master_property.direction = majority_direction
                updated = True
        
        # 管理費の多数決（現在はMasterPropertyに保存先がないため、ログのみ）
        if info['management_fees']:
            majority_mgmt_fee = self.get_majority_value(info['management_fees'], None)
            logger.info(f"物件ID {master_property.id} の管理費（参考）: {majority_mgmt_fee}")
        
        return updated
    
    def update_building_by_majority(self, building: Building) -> bool:
        """
        建物情報を物件情報の多数決で更新する
        
        Returns:
            更新があった場合True
        """
        properties = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == building.id
        ).all()
        
        if len(properties) <= 1:
            return False
        
        updated = False
        
        # 総階数の推定（物件の最大階数から）
        floor_numbers = [p.floor_number for p in properties if p.floor_number]
        if floor_numbers:
            estimated_total_floors = max(floor_numbers)
            if building.total_floors != estimated_total_floors:
                logger.info(f"建物 '{building.normalized_name}' の総階数を "
                          f"{building.total_floors} → {estimated_total_floors} に更新")
                building.total_floors = estimated_total_floors
                updated = True
        
        # 住所の多数決（通常は必要ないが、データ品質向上のため）
        # 現在のデータ構造では実装できません
        
        return updated
    
    def update_property_with_new_listing_info(self, master_property: MasterProperty, 
                                            listing_info: Dict[str, Any]) -> bool:
        """
        新しい掲載情報を追加する際に、多数決で物件情報を更新する
        
        このメソッドはスクレイパーから呼び出されることを想定しています
        
        Args:
            master_property: 更新対象の物件
            listing_info: 新しい掲載情報の属性
                - floor_number
                - area
                - layout
                - direction
                
        Returns:
            更新があった場合True
        """
        updated = False
        
        # 既存の掲載情報から属性を収集（将来的な実装）
        # 現在は新しい情報と既存の物件情報のみで判断
        
        # より詳細な情報で更新（現在の実装と同じ）
        if listing_info.get('floor_number') and not master_property.floor_number:
            master_property.floor_number = listing_info['floor_number']
            updated = True
        
        if listing_info.get('area') and not master_property.area:
            master_property.area = listing_info['area']
            updated = True
        
        if listing_info.get('layout') and not master_property.layout:
            master_property.layout = listing_info['layout']
            updated = True
        
        if listing_info.get('direction') and not master_property.direction:
            master_property.direction = listing_info['direction']
            updated = True
        
        return updated


def create_property_listing_attributes_table():
    """
    PropertyListingの属性情報を保存するための追加テーブルのDDL
    （将来的な拡張案）
    """
    return """
    CREATE TABLE property_listing_attributes (
        id SERIAL PRIMARY KEY,
        property_listing_id INTEGER NOT NULL REFERENCES property_listings(id) ON DELETE CASCADE,
        floor_number INTEGER,
        area FLOAT,
        layout VARCHAR(50),
        direction VARCHAR(50),
        total_floors INTEGER,
        balcony_area FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(property_listing_id)
    );
    
    CREATE INDEX idx_property_listing_attributes_listing_id ON property_listing_attributes(property_listing_id);
    """