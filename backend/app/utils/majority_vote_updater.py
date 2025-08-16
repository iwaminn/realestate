"""
物件情報と建物情報を多数決で更新するユーティリティ

このモジュールは既存のスクレイパーに組み込んで使用します
"""

from typing import Dict, List, Optional, Any, Tuple
from collections import Counter
from datetime import datetime, timedelta
from sqlalchemy import func, and_, String
from sqlalchemy.orm import Session
from ..models import Building, MasterProperty, PropertyListing, ListingPriceHistory
import logging

logger = logging.getLogger(__name__)


class MajorityVoteUpdater:
    """多数決による情報更新クラス"""
    
    # サイトの優先順位（左が高優先度）
    SITE_PRIORITY = ['suumo', 'homes', 'rehouse', 'nomu', '東急リバブル']
    
    def __init__(self, session: Session):
        self.session = session
    
    @staticmethod
    def get_site_priority(site_name: str) -> int:
        """サイトの優先順位を取得（小さいほど高優先度）"""
        try:
            return MajorityVoteUpdater.SITE_PRIORITY.index(site_name.lower())
        except ValueError:
            return len(MajorityVoteUpdater.SITE_PRIORITY)  # 未知のサイトは最低優先度
    
    def get_majority_value_with_normalization(self, values_with_source: List[tuple], current_value: Any = None, 
                                             value_type: str = None) -> Optional[Any]:
        """
        正規化してから最頻値を取得する。同数の場合はサイト優先順位で決定
        
        Args:
            values_with_source: (値, ソースサイト名)のタプルのリスト
            current_value: 現在の値
            value_type: 値のタイプ（'address', 'layout', 'direction', 'station_info'など）
            
        Returns:
            最頻値（Noneの場合もある）
        """
        # Noneや空文字を除外
        valid_items = [(v, s) for v, s in values_with_source if v is not None and v != '']
        if not valid_items:
            return current_value
        
        # 値のタイプに応じて正規化
        normalized_groups = {}  # {正規化値: [(元の値, ソース)]}
        
        if value_type == 'address':
            # 住所の正規化
            from backend.app.utils.address_normalizer import AddressNormalizer
            normalizer = AddressNormalizer()
            for value, source in valid_items:
                normalized = normalizer.normalize_for_comparison(value)
                if normalized not in normalized_groups:
                    normalized_groups[normalized] = []
                normalized_groups[normalized].append((value, source))
                
        elif value_type == 'layout':
            # 間取りの正規化
            from backend.app.scrapers import normalize_layout
            for value, source in valid_items:
                normalized = normalize_layout(value) or value  # 正規化失敗時は元の値
                if normalized not in normalized_groups:
                    normalized_groups[normalized] = []
                normalized_groups[normalized].append((value, source))
                
        elif value_type == 'direction':
            # 方角の正規化
            from backend.app.scrapers import normalize_direction
            for value, source in valid_items:
                normalized = normalize_direction(value) or value  # 正規化失敗時は元の値
                if normalized not in normalized_groups:
                    normalized_groups[normalized] = []
                normalized_groups[normalized].append((value, source))
                
        elif value_type == 'station_info':
            # 駅情報の正規化（スペースや改行を統一）
            import re
            for value, source in valid_items:
                # 複数の空白文字を1つに統一、改行を統一
                normalized = re.sub(r'\s+', ' ', value.strip())
                normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
                if normalized not in normalized_groups:
                    normalized_groups[normalized] = []
                normalized_groups[normalized].append((value, source))
                
        else:
            # その他の値は正規化なし（数値など）
            for value, source in valid_items:
                if value not in normalized_groups:
                    normalized_groups[value] = []
                normalized_groups[value].append((value, source))
        
        # 各正規化グループの出現回数をカウント
        group_counts = {}
        for normalized, items in normalized_groups.items():
            group_counts[normalized] = len(items)
        
        # 最も多いグループを選択
        max_count = max(group_counts.values())
        most_common_groups = [normalized for normalized, count in group_counts.items() if count == max_count]
        
        if len(most_common_groups) == 1:
            # 最頻グループが1つの場合、そのグループ内で最もサイト優先度の高い値を返す
            best_group = most_common_groups[0]
            return self._select_best_from_group(normalized_groups[best_group])
        
        # 最頻グループが複数ある場合、サイト優先順位で決定
        candidates = []
        for normalized in most_common_groups:
            best_value = self._select_best_from_group(normalized_groups[normalized])
            # このグループの最高優先度を取得
            sources = [s for v, s in normalized_groups[normalized]]
            best_priority = min(self.get_site_priority(s) for s in sources)
            candidates.append((best_value, best_priority))
        
        # 優先度順にソート
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    
    def _select_best_from_group(self, items: List[tuple]) -> Any:
        """
        同じ正規化グループ内で最も適切な値を選択
        サイト優先度が最も高いものを選択
        """
        if not items:
            return None
        
        # サイト優先度でソート
        sorted_items = sorted(items, key=lambda x: self.get_site_priority(x[1]))
        return sorted_items[0][0]
    
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
    
    def get_price_range(self, prices_with_source: List[tuple]) -> Optional[Tuple[int, int]]:
        """
        価格の範囲（最小値〜最大値）を取得する
        
        Args:
            prices_with_source: (価格, ソースサイト名)のタプルのリスト
            
        Returns:
            (最小価格, 最大価格)のタプル、価格がない場合はNone
        """
        # Noneや0を除外
        valid_prices = [p for p, _ in prices_with_source if p is not None and p > 0]
        if not valid_prices:
            return None
        
        return (min(valid_prices), max(valid_prices))
    
    def collect_property_info_from_listings(self, master_property: MasterProperty, 
                                            include_inactive: bool = False) -> Dict[str, List[Any]]:
        """
        物件の掲載情報から属性情報を収集する
        
        Args:
            master_property: 対象の物件
            include_inactive: 非アクティブな掲載も含めるかどうか
        
        Returns:
            属性ごとの値とソースのリスト
        """
        # アクティブな掲載情報があるかチェック
        active_listings = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == master_property.id,
            PropertyListing.is_active == True
        ).all()
        
        if active_listings:
            # アクティブな掲載がある場合は、それらのみを使用
            listings = active_listings
        elif include_inactive and master_property.sold_at:
            # 全て非アクティブで販売終了している場合、1週間以内の掲載を使用
            one_week_ago = master_property.sold_at - timedelta(days=7)
            listings = self.session.query(PropertyListing).filter(
                PropertyListing.master_property_id == master_property.id,
                PropertyListing.last_confirmed_at >= one_week_ago
            ).all()
        else:
            # それ以外の場合は全ての掲載を使用
            listings = self.session.query(PropertyListing).filter(
                PropertyListing.master_property_id == master_property.id
            ).all()
        
        info = {
            'floor_numbers': [],
            'areas': [],
            'layouts': [],
            'directions': [],
            'balcony_areas': [],
            'management_fees': [],
            'repair_funds': [],
            'station_infos': [],
            'parking_infos': [],
            'addresses': [],
            'prices': []  # 価格情報も収集
        }
        
        for listing in listings:
            # 管理費と修繕積立金
            if listing.management_fee:
                info['management_fees'].append((listing.management_fee, listing.source_site))
            if listing.repair_fund:
                info['repair_funds'].append((listing.repair_fund, listing.source_site))
            
            # 駅情報
            if listing.station_info:
                info['station_infos'].append((listing.station_info, listing.source_site))
            
            # 価格情報
            if listing.current_price:
                info['prices'].append((listing.current_price, listing.source_site))
            
            # listing_*フィールドから情報を収集（将来的な拡張用）
            if hasattr(listing, 'listing_floor_number') and listing.listing_floor_number:
                info['floor_numbers'].append((listing.listing_floor_number, listing.source_site))
            if hasattr(listing, 'listing_area') and listing.listing_area:
                info['areas'].append((listing.listing_area, listing.source_site))
            if hasattr(listing, 'listing_layout') and listing.listing_layout:
                info['layouts'].append((listing.listing_layout, listing.source_site))
            if hasattr(listing, 'listing_direction') and listing.listing_direction:
                info['directions'].append((listing.listing_direction, listing.source_site))
            if hasattr(listing, 'listing_balcony_area') and listing.listing_balcony_area:
                info['balcony_areas'].append((listing.listing_balcony_area, listing.source_site))
            if hasattr(listing, 'listing_address') and listing.listing_address:
                info['addresses'].append((listing.listing_address, listing.source_site))
            if hasattr(listing, 'listing_parking_info') and listing.listing_parking_info:
                info['parking_infos'].append((listing.listing_parking_info, listing.source_site))
        
        return info
    
    def update_master_property_by_majority(self, master_property: MasterProperty) -> bool:
        """
        物件情報を掲載情報の多数決で更新する
        
        Returns:
            更新があった場合True
        """
        # 販売終了物件の場合は非アクティブも含める
        include_inactive = master_property.sold_at is not None
        info = self.collect_property_info_from_listings(master_property, include_inactive)
        updated = False
        
        # 更新予定の値を保持（ユニーク制約チェック用）
        new_floor_number = master_property.floor_number
        new_area = master_property.area
        new_layout = master_property.layout
        new_direction = master_property.direction
        
        # 各属性について多数決を取る
        
        # 階数の多数決
        if info['floor_numbers']:
            majority_floor = self.get_majority_value(info['floor_numbers'], master_property.floor_number)
            if majority_floor != master_property.floor_number:
                new_floor_number = majority_floor
        
        # 面積の多数決
        if info['areas']:
            majority_area = self.get_majority_value(info['areas'], master_property.area)
            if majority_area != master_property.area:
                new_area = majority_area
        
        # 間取りの多数決（正規化あり）
        if info['layouts']:
            majority_layout = self.get_majority_value_with_normalization(
                info['layouts'], master_property.layout, value_type='layout'
            )
            if majority_layout != master_property.layout:
                new_layout = majority_layout
        
        # 方角の多数決（正規化あり）
        if info['directions']:
            majority_direction = self.get_majority_value_with_normalization(
                info['directions'], master_property.direction, value_type='direction'
            )
            if majority_direction != master_property.direction:
                new_direction = majority_direction
        
        # ユニーク制約違反をチェック
        if (new_floor_number != master_property.floor_number or 
            new_area != master_property.area or 
            new_layout != master_property.layout or 
            new_direction != master_property.direction):
            
            # 同じ組み合わせの物件が既に存在するかチェック（自分自身を除く）
            from sqlalchemy import and_
            existing_property = self.session.query(MasterProperty).filter(
                and_(
                    MasterProperty.building_id == master_property.building_id,
                    MasterProperty.floor_number == new_floor_number,
                    MasterProperty.area == new_area,
                    MasterProperty.layout == new_layout,
                    MasterProperty.direction == new_direction,
                    MasterProperty.id != master_property.id  # 自分自身を除外
                )
            ).first()
            
            if existing_property:
                logger.warning(
                    f"物件ID {master_property.id} の多数決更新をスキップ: "
                    f"更新後の属性が物件ID {existing_property.id} と重複 "
                    f"(建物ID: {master_property.building_id}, 階数: {new_floor_number}, "
                    f"面積: {new_area}㎡, 間取り: {new_layout}, 方角: {new_direction})"
                )
                # ユニーク制約違反の場合は、階数・面積・間取り・方角の更新をスキップ
                # ただし、それ以外の属性は更新可能
            else:
                # ユニーク制約違反がない場合のみ更新
                if new_floor_number != master_property.floor_number:
                    logger.info(f"物件ID {master_property.id} の階数を "
                              f"{master_property.floor_number} → {new_floor_number} に更新")
                    master_property.floor_number = new_floor_number
                    updated = True
                
                if new_area != master_property.area:
                    logger.info(f"物件ID {master_property.id} の面積を "
                              f"{master_property.area} → {new_area} に更新")
                    master_property.area = new_area
                    updated = True
                
                if new_layout != master_property.layout:
                    logger.info(f"物件ID {master_property.id} の間取りを "
                              f"{master_property.layout} → {new_layout} に更新")
                    master_property.layout = new_layout
                    updated = True
                
                if new_direction != master_property.direction:
                    logger.info(f"物件ID {master_property.id} の方角を "
                              f"{master_property.direction} → {new_direction} に更新")
                    master_property.direction = new_direction
                    updated = True
        
        # バルコニー面積の多数決（ユニーク制約に含まれない）
        if info['balcony_areas']:
            majority_balcony_area = self.get_majority_value(info['balcony_areas'], master_property.balcony_area)
            if majority_balcony_area != master_property.balcony_area:
                logger.info(f"物件ID {master_property.id} のバルコニー面積を "
                          f"{master_property.balcony_area} → {majority_balcony_area} に更新")
                master_property.balcony_area = majority_balcony_area
                updated = True
        
        # 管理費の多数決（ユニーク制約に含まれない）
        if info['management_fees']:
            majority_mgmt_fee = self.get_majority_value(info['management_fees'], master_property.management_fee)
            if majority_mgmt_fee != master_property.management_fee:
                logger.info(f"物件ID {master_property.id} の管理費を "
                          f"{master_property.management_fee} → {majority_mgmt_fee} に更新")
                master_property.management_fee = majority_mgmt_fee
                updated = True
        
        # 修繕積立金の多数決（ユニーク制約に含まれない）
        if info['repair_funds']:
            majority_repair_fund = self.get_majority_value(info['repair_funds'], master_property.repair_fund)
            if majority_repair_fund != master_property.repair_fund:
                logger.info(f"物件ID {master_property.id} の修繕積立金を "
                          f"{master_property.repair_fund} → {majority_repair_fund} に更新")
                master_property.repair_fund = majority_repair_fund
                updated = True
        
        # 交通情報の多数決（ユニーク制約に含まれない、正規化あり）
        if info['station_infos']:
            majority_station = self.get_majority_value_with_normalization(
                info['station_infos'], master_property.station_info, value_type='station_info'
            )
            if majority_station != master_property.station_info:
                logger.info(f"物件ID {master_property.id} の交通情報を更新")
                master_property.station_info = majority_station
                updated = True
        
        # 駐車場情報の多数決（ユニーク制約に含まれない）
        if info['parking_infos']:
            majority_parking = self.get_majority_value(info['parking_infos'], master_property.parking_info)
            if majority_parking != master_property.parking_info:
                logger.info(f"物件ID {master_property.id} の駐車場情報を更新")
                master_property.parking_info = majority_parking
                updated = True
        
        return updated
    
    def update_building_by_majority(self, building: Building) -> bool:
        """
        建物情報を掲載情報の多数決で更新する（建物名を含むすべての属性）
        
        Returns:
            更新があった場合True
        """
        # まず建物名を更新（特殊な重み付けロジックが必要なため）
        name_updated = self.update_building_name_by_majority(building)
        
        # 建物に関連する全ての掲載情報から建物属性を収集
        building_info = self.collect_building_info_from_listings(building.id)
        updated = name_updated  # 建物名が更新された場合はTrueから開始
        
        # 住所の多数決（正規化あり）
        if building_info['addresses']:
            majority_address = self.get_majority_value_with_normalization(
                building_info['addresses'], building.address, value_type='address'
            )
            if majority_address != building.address:
                logger.info(f"建物 '{building.normalized_name}' の住所を更新")
                building.address = majority_address
                
                # 正規化住所も更新
                if hasattr(building, 'normalized_address'):
                    from backend.app.utils.address_normalizer import AddressNormalizer
                    normalizer = AddressNormalizer()
                    building.normalized_address = normalizer.normalize_for_comparison(majority_address)
                
                updated = True
        
        # 総階数の多数決
        if building_info['total_floors']:
            majority_total_floors = self.get_majority_value(building_info['total_floors'], building.total_floors)
            if majority_total_floors != building.total_floors:
                logger.info(f"建物 '{building.normalized_name}' の総階数を "
                          f"{building.total_floors} → {majority_total_floors} に更新")
                building.total_floors = majority_total_floors
                updated = True
        
        # 築年の多数決
        if building_info['built_years']:
            majority_built_year = self.get_majority_value(building_info['built_years'], building.built_year)
            if majority_built_year != building.built_year:
                logger.info(f"建物 '{building.normalized_name}' の築年を "
                          f"{building.built_year} → {majority_built_year} に更新")
                building.built_year = majority_built_year
                updated = True
        
        # 築月の多数決
        if building_info['built_months']:
            majority_built_month = self.get_majority_value(building_info['built_months'], building.built_month)
            if majority_built_month != building.built_month:
                logger.info(f"建物 '{building.normalized_name}' の築月を "
                          f"{building.built_month} → {majority_built_month} に更新")
                building.built_month = majority_built_month
                updated = True
        
        # 構造の多数決
        if building_info['structures']:
            majority_structure = self.get_majority_value(building_info['structures'], building.construction_type)
            if majority_structure != building.construction_type:
                logger.info(f"建物 '{building.normalized_name}' の構造を更新")
                building.construction_type = majority_structure
                updated = True
        
        # 地下階数の多数決
        if building_info['basement_floors']:
            majority_basement_floors = self.get_majority_value(building_info['basement_floors'], building.basement_floors)
            if majority_basement_floors != building.basement_floors:
                logger.info(f"建物 '{building.normalized_name}' の地下階数を "
                          f"{building.basement_floors} → {majority_basement_floors} に更新")
                building.basement_floors = majority_basement_floors
                updated = True
        
        # 敷地権利形態の多数決
        if building_info['land_rights']:
            majority_land_rights = self.get_majority_value(building_info['land_rights'], building.land_rights)
            if majority_land_rights != building.land_rights:
                logger.info(f"建物 '{building.normalized_name}' の敷地権利形態を更新")
                building.land_rights = majority_land_rights
                updated = True
        
        # 交通情報の多数決（建物レベル、正規化あり）
        if building_info['station_infos']:
            majority_station_info = self.get_majority_value_with_normalization(
                building_info['station_infos'], building.station_info, value_type='station_info'
            )
            if majority_station_info != building.station_info:
                logger.info(f"建物 '{building.normalized_name}' の交通情報を更新")
                building.station_info = majority_station_info
                updated = True
        
        # 総戸数の多数決
        if building_info.get('total_units'):
            majority_total_units = self.get_majority_value(building_info['total_units'], building.total_units)
            if majority_total_units != building.total_units:
                logger.info(f"建物 '{building.normalized_name}' の総戸数を "
                          f"{building.total_units} → {majority_total_units} に更新")
                building.total_units = majority_total_units
                updated = True
        
        return updated
    
    def collect_building_info_from_listings(self, building_id: int) -> Dict[str, List[Any]]:
        """
        建物に関連する全ての掲載情報から建物属性を収集
        
        Args:
            building_id: 建物ID
            
        Returns:
            属性ごとの値とソースのリスト
        """
        # アクティブな掲載情報があるかチェック
        active_listings_exist = self.session.query(PropertyListing).join(
            MasterProperty
        ).filter(
            MasterProperty.building_id == building_id,
            PropertyListing.is_active == True
        ).first() is not None
        
        # 掲載情報を取得
        if active_listings_exist:
            # アクティブな掲載のみ
            listings = self.session.query(PropertyListing).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building_id,
                PropertyListing.is_active == True
            ).all()
        else:
            # 全ての掲載（販売終了物件を含む）
            listings = self.session.query(PropertyListing).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building_id
            ).all()
        
        info = {
            'addresses': [],
            'total_floors': [],
            'built_years': [],
            'built_months': [],
            'structures': [],
            'basement_floors': [],
            'land_rights': [],
            'station_infos': [],
            'total_units': []
        }
        
        for listing in listings:
            # listing_*フィールドから情報を収集
            if hasattr(listing, 'listing_address') and listing.listing_address:
                info['addresses'].append((listing.listing_address, listing.source_site))
            if hasattr(listing, 'listing_total_floors') and listing.listing_total_floors:
                info['total_floors'].append((listing.listing_total_floors, listing.source_site))
            if hasattr(listing, 'listing_built_year') and listing.listing_built_year:
                info['built_years'].append((listing.listing_built_year, listing.source_site))
            if hasattr(listing, 'listing_built_month') and listing.listing_built_month:
                info['built_months'].append((listing.listing_built_month, listing.source_site))
            if hasattr(listing, 'listing_building_structure') and listing.listing_building_structure:
                info['structures'].append((listing.listing_building_structure, listing.source_site))
            if hasattr(listing, 'listing_basement_floors') and listing.listing_basement_floors:
                info['basement_floors'].append((listing.listing_basement_floors, listing.source_site))
            if hasattr(listing, 'listing_land_rights') and listing.listing_land_rights:
                info['land_rights'].append((listing.listing_land_rights, listing.source_site))
            if hasattr(listing, 'listing_station_info') and listing.listing_station_info:
                info['station_infos'].append((listing.listing_station_info, listing.source_site))
            if hasattr(listing, 'listing_total_units') and listing.listing_total_units:
                info['total_units'].append((listing.listing_total_units, listing.source_site))
        
        return info
    
    def update_building_name_by_majority(self, building_or_id) -> bool:
        """
        建物名を関連する掲載情報から直接多数決で決定
        
        Args:
            building_or_id: 建物オブジェクトまたは建物ID
            
        Returns:
            更新があった場合True
        """
        # 建物オブジェクトまたはIDを処理
        if isinstance(building_or_id, int):
            building_id = building_or_id
            building = self.session.query(Building).filter_by(id=building_id).first()
            if not building:
                return False
        else:
            building = building_or_id
            building_id = building.id
        
        # property_listings から直接建物名を取得
        # アクティブな掲載情報があるかチェック
        active_listings = self.session.query(
            PropertyListing.listing_building_name,
            PropertyListing.source_site,
            func.count(PropertyListing.id).label('count')
        ).join(
            MasterProperty
        ).filter(
            MasterProperty.building_id == building_id,
            PropertyListing.is_active == True,
            PropertyListing.listing_building_name.isnot(None)
        ).group_by(
            PropertyListing.listing_building_name,
            PropertyListing.source_site
        ).all()
        
        if active_listings:
            # アクティブな掲載情報から建物名を取得
            building_name_votes = active_listings
        else:
            # 全ての掲載が非アクティブの場合
            one_week_ago = datetime.now() - timedelta(days=7)
            
            # 販売終了から1週間以内の掲載情報を取得
            recent_listings = self.session.query(
                PropertyListing.listing_building_name,
                PropertyListing.source_site,
                func.count(PropertyListing.id).label('count')
            ).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building_id,
                MasterProperty.sold_at.isnot(None),
                MasterProperty.sold_at >= one_week_ago,
                PropertyListing.listing_building_name.isnot(None)
            ).group_by(
                PropertyListing.listing_building_name,
                PropertyListing.source_site
            ).all()
            
            if recent_listings:
                building_name_votes = recent_listings
            else:
                # 販売終了から1週間以上経過している場合は、全ての掲載情報を使用
                all_listings = self.session.query(
                    PropertyListing.listing_building_name,
                    PropertyListing.source_site,
                    func.count(PropertyListing.id).label('count')
                ).join(
                    MasterProperty
                ).filter(
                    MasterProperty.building_id == building_id,
                    PropertyListing.listing_building_name.isnot(None)
                ).group_by(
                    PropertyListing.listing_building_name,
                    PropertyListing.source_site
                ).all()
                
                building_name_votes = all_listings
        
        if not building_name_votes:
            # 掲載情報から建物名が取得できない場合
            return False
        
        # 重み付け投票の準備
        # 正規化してグループ化するための辞書
        normalized_groups = {}  # {正規化名: {元の名前: 重み}}
        
        # 建物名を正規化してグループ化
        # SUUMOスクレイパーを使用（正規化関数のため）
        from backend.app.scrapers.suumo_scraper import SuumoScraper
        scraper = SuumoScraper()
        
        for building_name, source_site, count in building_name_votes:
            # 基本的な重み（出現回数）
            weight = count
            
            # ソースによる重み付け（優先度の高いサイトほど高い重み）
            site_priority = self.get_site_priority(str(source_site))
            if site_priority < len(self.SITE_PRIORITY):
                # 優先度が高いサイトには追加の重みを付与
                weight *= (len(self.SITE_PRIORITY) - site_priority + 1)
            
            # 広告文っぽい名前は重みを下げる
            if self._is_advertising_text(building_name):
                weight *= 0.1
            
            # 建物名を正規化
            normalized_name = scraper.normalize_building_name(building_name)
            
            # グループ化して集計
            if normalized_name not in normalized_groups:
                normalized_groups[normalized_name] = {}
            
            if building_name in normalized_groups[normalized_name]:
                normalized_groups[normalized_name][building_name] += weight
            else:
                normalized_groups[normalized_name][building_name] = weight
        
        # 最も重みの高い正規化グループを選択
        if normalized_groups:
            # 各グループの合計重みを計算
            group_weights = {}
            for normalized_name, original_names in normalized_groups.items():
                group_weights[normalized_name] = sum(original_names.values())
            
            # 最も重みの高いグループを選択
            best_normalized = max(group_weights.items(), key=lambda x: x[1])[0]
            
            # そのグループ内で最も使用頻度の高い元の表記を選択
            best_name = max(normalized_groups[best_normalized].items(), key=lambda x: x[1])[0]
            
            # デバッグ用：正規化による集約効果をログ出力
            if len(normalized_groups[best_normalized]) > 1:
                logger.debug(
                    f"建物名の正規化により表記ゆれを集約: {list(normalized_groups[best_normalized].keys())} → '{best_name}'"
                )
            
            # 現在の名前と異なる場合は更新
            if best_name != building.normalized_name:
                # ログ出力用に投票結果を整形
                vote_summary = {}
                for orig_names in normalized_groups.values():
                    for name, weight in orig_names.items():
                        vote_summary[name] = vote_summary.get(name, 0) + weight
                
                logger.info(
                    f"建物名更新: '{building.normalized_name}' → '{best_name}' "
                    f"(ID: {building_id}, 正規化グループ数: {len(normalized_groups)}, "
                    f"votes: {dict(sorted(vote_summary.items(), key=lambda x: x[1], reverse=True)[:5])})"
                )
                building.normalized_name = best_name
                return True
        
        return False
    
    def update_property_building_name_by_majority(self, property_id: int) -> bool:
        """
        物件の表示用建物名を関連する掲載情報から多数決で決定
        
        Args:
            property_id: 物件ID
            
        Returns:
            更新があった場合True
        """
        property_obj = self.session.query(MasterProperty).filter_by(id=property_id).first()
        if not property_obj:
            return False
        
        # 正規化してグループ化するための辞書
        normalized_groups = {}  # {正規化名: {元の名前: 重み}}
        
        # 共通の建物名正規化関数を使用
        from backend.app.utils.building_name_normalizer import normalize_building_name
        
        # アクティブな掲載情報があるかチェック
        active_listings = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == property_id,
            PropertyListing.is_active == True
        ).all()
        
        if active_listings:
            # アクティブな掲載情報から建物名を取得
            for listing in active_listings:
                if listing.listing_building_name:
                    # ソースによる重み付け
                    weight = self.get_site_priority_weight(listing.source_site)
                    
                    # 広告文っぽい名前は重みを下げる
                    if self._is_advertising_text(listing.listing_building_name):
                        weight *= 0.1
                    
                    # 建物名を正規化
                    normalized_name = normalize_building_name(listing.listing_building_name)
                    
                    # グループ化して集計
                    if normalized_name not in normalized_groups:
                        normalized_groups[normalized_name] = {}
                    
                    if listing.listing_building_name in normalized_groups[normalized_name]:
                        normalized_groups[normalized_name][listing.listing_building_name] += weight
                    else:
                        normalized_groups[normalized_name][listing.listing_building_name] = weight
        else:
            # すべて非アクティブの場合、最近の掲載情報を使用
            recent_listings = self.session.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_id,
                PropertyListing.listing_building_name.isnot(None)
            ).order_by(PropertyListing.last_scraped_at.desc()).limit(10).all()
            
            for listing in recent_listings:
                if listing.listing_building_name:
                    # ソースによる重み付け
                    weight = self.get_site_priority_weight(listing.source_site)
                    
                    # 広告文っぽい名前は重みを下げる
                    if self._is_advertising_text(listing.listing_building_name):
                        weight *= 0.1
                    
                    # 建物名を正規化
                    normalized_name = normalize_building_name(listing.listing_building_name)
                    
                    # グループ化して集計
                    if normalized_name not in normalized_groups:
                        normalized_groups[normalized_name] = {}
                    
                    if listing.listing_building_name in normalized_groups[normalized_name]:
                        normalized_groups[normalized_name][listing.listing_building_name] += weight
                    else:
                        normalized_groups[normalized_name][listing.listing_building_name] = weight
        
        # 最も重みの高い正規化グループを選択
        if normalized_groups:
            # 各グループの合計重みを計算
            group_weights = {}
            for normalized_name, original_names in normalized_groups.items():
                group_weights[normalized_name] = sum(original_names.values())
            
            # 最も重みの高いグループを選択
            best_normalized = max(group_weights.items(), key=lambda x: x[1])[0]
            
            # そのグループ内で最も使用頻度の高い元の表記を選択
            best_name = max(normalized_groups[best_normalized].items(), key=lambda x: x[1])[0]
            
            # デバッグ用：正規化による集約効果をログ出力
            if len(normalized_groups[best_normalized]) > 1:
                logger.debug(
                    f"物件建物名の正規化により表記ゆれを集約: {list(normalized_groups[best_normalized].keys())} → '{best_name}'"
                )
            
            # 現在の名前と異なる場合、またはNoneの場合は更新
            if property_obj.display_building_name != best_name:
                # ログ出力用に投票結果を整形
                vote_summary = {}
                for orig_names in normalized_groups.values():
                    for name, weight in orig_names.items():
                        vote_summary[name] = vote_summary.get(name, 0) + weight
                
                logger.info(
                    f"物件建物名更新: '{property_obj.display_building_name}' → '{best_name}' "
                    f"(物件ID: {property_id}, 正規化グループ数: {len(normalized_groups)}, "
                    f"votes: {dict(sorted(vote_summary.items(), key=lambda x: x[1], reverse=True)[:3])})"
                )
                property_obj.display_building_name = best_name
                self.session.flush()  # 変更を即座に反映
                return True
        elif property_obj.display_building_name is None:
            # 掲載情報がない場合でも、建物の正規化名を使用
            building = self.session.query(Building).filter_by(id=property_obj.building_id).first()
            if building and building.normalized_name:
                logger.info(
                    f"物件建物名を建物マスターから設定: '{building.normalized_name}' "
                    f"(物件ID: {property_id}, 建物ID: {building.id})"
                )
                property_obj.display_building_name = building.normalized_name
                self.session.flush()
                return True
        
        return False
    
    def get_site_priority_weight(self, source_site: str) -> int:
        """サイト優先度に基づく重みを取得"""
        site_priority = self.get_site_priority(source_site)
        # 優先度が高いサイトほど大きい重み
        return len(self.SITE_PRIORITY) - site_priority
    
    def _is_advertising_text(self, text: str) -> bool:
        """広告的なテキストかどうかを判定"""
        import re
        
        if not text:
            return False
        
        # 広告的なパターン
        ad_patterns = [
            r'徒歩\d+分',
            r'駅.*\d+分',
            r'の中古マンション',
            r'新築',
            r'分譲',
            r'賃貸',
            r'[0-9,]+万円',
            r'\d+LDK',
            r'\d+階建',
            r'築\d+年',
            # 階数を含む建物名も広告文として扱う
            r'\d+階$',  # 末尾に「○階」（スペースは不要）
            r'\d+階部分',  # 「○階部分」
            r'\d+階角部屋',  # 「○階角部屋」
            r'地下\d+階',  # 「地下○階」
            r'×\d+階',  # 「×14階」のようなパターン
            r'〜.*〜$',  # 「〜ブランズ赤坂〜」のような広告的な表現
            # 駅名のみの場合
            r'^[^\s]+駅\s+徒歩',
            r'^東京メトロ',
            r'^JR[^\s]+線',
            r'^都営[^\s]+線',
        ]
        
        # いずれかのパターンにマッチしたら広告文と判定
        for pattern in ad_patterns:
            if re.search(pattern, text):
                return True
        
        # 建物名として短すぎる場合も広告文と判定
        if len(text) < 3:
            return True
        
        return False
    
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
    
    def get_price_votes_for_sold_property(
        self, 
        property_id: int, 
        sold_at: datetime, 
        days_before: int = 7
    ) -> Dict[int, int]:
        """
        販売終了前の指定日数間の価格をカウントして多数決用のデータを取得
        
        Args:
            property_id: 物件ID
            sold_at: 販売終了日時
            days_before: 何日前までのデータを対象とするか（デフォルト7日）
        
        Returns:
            価格とその出現回数の辞書 {価格: 回数}
        """
        start_date = sold_at - timedelta(days=days_before)
        
        # 該当期間の価格履歴を取得
        price_counts = self.session.query(
            ListingPriceHistory.price,
            func.count(ListingPriceHistory.id).label('count')
        ).join(
            PropertyListing,
            PropertyListing.id == ListingPriceHistory.property_listing_id
        ).filter(
            PropertyListing.master_property_id == property_id,
            ListingPriceHistory.recorded_at >= start_date,
            ListingPriceHistory.recorded_at <= sold_at
        ).group_by(
            ListingPriceHistory.price
        ).all()
        
        return {price: count for price, count in price_counts}
    
    def get_majority_price_for_sold_property(self, price_votes: Dict[int, int]) -> Optional[int]:
        """
        多数決で最も多い価格を決定
        同数の場合は高い方の価格を採用（より保守的な価格設定）
        
        Args:
            price_votes: 価格とその出現回数の辞書
        
        Returns:
            多数決で決定した価格
        """
        if not price_votes:
            return None
        
        # 出現回数でソート（同数の場合は価格が高い方を優先）
        sorted_prices = sorted(
            price_votes.items(), 
            key=lambda x: (x[1], x[0]), 
            reverse=True
        )
        
        return sorted_prices[0][0]
    
    def update_sold_property_price(self, property_id: int) -> Optional[Tuple[int, int]]:
        """
        特定の販売終了物件の価格を多数決で更新
        
        Args:
            property_id: 物件ID
        
        Returns:
            (old_price, new_price) のタプル、更新不要の場合はNone
        """
        property = self.session.query(MasterProperty).filter(
            MasterProperty.id == property_id,
            MasterProperty.sold_at.isnot(None)
        ).first()
        
        if not property:
            logger.warning(f"Property {property_id} not found or not sold")
            return None
        
        # 価格の投票を取得
        price_votes = self.get_price_votes_for_sold_property(
            property.id, 
            property.sold_at
        )
        
        if not price_votes:
            logger.warning(f"No price history found for property {property_id} in the 7 days before sold_at")
            return None
        
        # 多数決で価格を決定
        majority_price = self.get_majority_price_for_sold_property(price_votes)
        
        if majority_price and majority_price != property.last_sale_price:
            old_price = property.last_sale_price
            property.last_sale_price = majority_price
            
            logger.info(
                f"Property {property_id}: Updated last_sale_price from "
                f"{old_price} to {majority_price} "
                f"(votes: {price_votes})"
            )
            
            return (old_price, majority_price)
        
        return None
    
    def update_all_sold_property_prices(self) -> List[Tuple[int, int, int]]:
        """
        すべての販売終了物件の価格を多数決で更新
        
        Returns:
            更新された物件情報リスト [(property_id, old_price, new_price)]
        """
        # 販売終了物件を取得
        sold_properties = self.session.query(MasterProperty).filter(
            MasterProperty.sold_at.isnot(None)
        ).all()
        
        updates = []
        
        for property in sold_properties:
            result = self.update_sold_property_price(property.id)
            if result:
                updates.append((property.id, result[0], result[1]))
        
        logger.info(f"Updated {len(updates)} sold property prices by majority vote")
        
        return updates


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