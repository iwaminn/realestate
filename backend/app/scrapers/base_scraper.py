"""
ベーススクレイパークラス v2
新しいデータベース構造に対応
"""

import time
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from ..database import SessionLocal
from ..models import (
    Building, BuildingAlias, BuildingExternalId, MasterProperty, PropertyListing, 
    ListingPriceHistory, PropertyImage
)
from ..utils.building_normalizer import BuildingNameNormalizer
from ..utils.reading_generator import generate_reading
from ..utils.katakana_converter import english_to_katakana, has_english_words
from ..config.scraper_config import ScraperConfig
import re


def is_advertising_text(text):
    """広告文かどうかを判定"""
    if not text:
        return False
    
    # 広告文のパターン
    advertising_patterns = [
        r'≪.*≫',  # ≪≫で囲まれた文字
        r'【.*】',  # 【】で囲まれた文字
        r'！',      # 感嘆符
        r'即日',
        r'頭金',
        r'0円',
        r'案内',
        r'購入可',
        r'おすすめ',
        r'新着',
        r'送迎',
        r'サービス',
        r'実施中',
        r'可能です',
        r'ご.*[来店|見学|内覧]',
    ]
    
    for pattern in advertising_patterns:
        if re.search(pattern, text):
            return True
    
    return False


class BaseScraper:
    """スクレイパーの基底クラス（v2）"""
    
    def __init__(self, source_site: str, force_detail_fetch: bool = False, max_properties: int = None):
        self.source_site = source_site
        self.session = SessionLocal()
        self.normalizer = BuildingNameNormalizer()
        self.force_detail_fetch = force_detail_fetch  # 強制詳細取得フラグ
        self.max_properties = max_properties  # 最大取得件数
        
        # ロガーを設定
        self.logger = logging.getLogger(f'{__name__}.{source_site}')
        
        # 設定を読み込む
        config = ScraperConfig.get_scraper_specific_config(source_site)
        self.delay = config['delay']  # スクレイピング間隔（秒）
        self.detail_refetch_days = config['detail_refetch_days']  # 詳細ページ再取得間隔（日）
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
    
    def validate_property_data(self, property_data: Dict[str, Any]) -> bool:
        """物件データの妥当性を検証（安全設計）"""
        # 必須フィールドの確認
        required_fields = ['building_name', 'price']
        for field in required_fields:
            if field not in property_data or not property_data[field]:
                print(f"警告: 必須フィールド '{field}' が不足しています")
                return False
        
        # 建物名の妥当性チェック
        building_name = property_data['building_name']
        if len(building_name) < 3:
            print(f"警告: 建物名が短すぎます: '{building_name}'")
            return False
        
        # 汎用的な建物名を拒否
        generic_names = ['港区の物件', '物件', '東京都の物件', '不明']
        if building_name in generic_names:
            print(f"警告: 汎用的な建物名は使用できません: '{building_name}'")
            return False
        
        # 駅名だけの場合も拒否
        if any(word in building_name for word in ['駅 徒歩', 'メトロ', 'JR', '都営']):
            print(f"警告: 駅名は建物名として使用できません: '{building_name}'")
            return False
        
        # 価格の妥当性チェック
        price = property_data['price']
        if price < 100 or price > 10000000:  # 100万円未満または100億円超は異常
            print(f"警告: 価格が異常です: {price}万円")
            return False
        
        return True
    
    def select_best_building_name(self, candidates: List[str]) -> str:
        """複数の建物名候補から最適なものを選択"""
        if not candidates:
            return ""
        
        # 広告文でないものを優先
        non_ad_names = [name for name in candidates if not is_advertising_text(name)]
        if non_ad_names:
            candidates = non_ad_names
        
        # 表記の優先度（より正式な表記を優先）
        # 1. 漢字が多い
        # 2. 長い（省略されていない）
        # 3. カタカナ表記より漢字表記
        
        def score_name(name):
            score = 0
            # 漢字の数
            kanji_count = len(re.findall(r'[\u4e00-\u9fff]', name))
            score += kanji_count * 10
            
            # 文字数（省略されていない）
            score += len(name)
            
            # カタカナより漢字を優先
            if re.search(r'[\u4e00-\u9fff]', name):
                score += 50
                
            # 「…」で省略されている場合は減点
            if '…' in name:
                score -= 100
                
            return score
        
        # スコアが最も高い名前を選択
        best_name = max(candidates, key=score_name)
        return best_name

    def get_or_create_building(self, building_name: str, address: str = None, external_property_id: str = None, 
                               built_year: int = None, total_floors: int = None, basement_floors: int = None,
                               total_units: int = None, structure: str = None, land_rights: str = None, 
                               parking_info: str = None) -> Tuple[Optional[Building], Optional[str]]:
        """建物を取得または作成。建物と抽出された部屋番号のタプルを返す"""
        if not building_name:
            return None, None
        
        # 建物名から部屋番号を抽出
        clean_building_name, extracted_room_number = self.normalizer.extract_room_number(building_name)
        
        # 建物名を標準化
        normalized_name = self.normalizer.normalize(clean_building_name)
        
        # デバッグログ
        if built_year:
            print(f"[DEBUG] get_or_create_building called with built_year={built_year} for {building_name}")
        
        # 広告文の場合は特別な処理
        if is_advertising_text(building_name):
            # 広告文の場合は、住所が必須
            if not address:
                print(f"[WARNING] 広告文タイトルで住所がない: {building_name}")
                return None, extracted_room_number
            
            # 住所で既存の建物を検索
            building = self.session.query(Building).filter(
                Building.address == address
            ).first()
            
            if building:
                print(f"[INFO] 住所で既存建物を発見: {building.normalized_name} at {address}")
                # エイリアスを追加
                existing_alias = self.session.query(BuildingAlias).filter(
                    BuildingAlias.building_id == building.id,
                    BuildingAlias.alias_name == building_name
                ).first()
                
                if not existing_alias:
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=building_name,
                        source=self.source_site
                    )
                    self.session.add(alias)
                
                return building, extracted_room_number, extracted_room_number
            else:
                # 新規作成（住所必須）
                print(f"[WARNING] 広告文タイトルで新規建物作成: {building_name} at {address}")
                # 建物名は "Unknown Building" + 住所の一部にする
                import re
                # 住所から番地を抽出
                match = re.search(r'(\d+[-−]\d+[-−]?\d*)', address)
                if match:
                    normalized_name = f"物件_{match.group(1).replace('-', '_').replace('−', '_')}"
                else:
                    # 住所の最後の部分を使用
                    parts = address.split('区')
                    if len(parts) > 1:
                        normalized_name = f"物件_{parts[1][:10].strip()}"
                    else:
                        normalized_name = f"物件_{address[-10:].strip()}"
        
        # 通常の建物名の場合
        else:
            # まず、正規化された名前で直接検索
            building = self.session.query(Building).filter(
                Building.normalized_name == normalized_name
            ).first()
            
            # 見つからない場合は、類似する建物を検索
            if not building:
                # データベース内の全建物名を取得して類似度チェック
                # （ただし、同じ地区の建物に限定）
                from sqlalchemy import func
                potential_buildings = []
                
                if address:
                    # 住所から地区を抽出
                    district = address.split('区')[0] + '区' if '区' in address else None
                    if district:
                        # 同じ地区の建物を検索
                        similar_buildings = self.session.query(Building).filter(
                            Building.address.like(f'{district}%')
                        ).all()
                        
                        for candidate in similar_buildings:
                            # 類似度計算
                            similarity = self.normalizer.calculate_similarity(normalized_name, candidate.normalized_name)
                            
                            # ドットや空白の違いのみの場合は高い類似度になるはず
                            if similarity >= 0.95:  # 非常に高い類似度のみ
                                # 建物の構成要素をチェック（棟が異なる場合は除外）
                                comp1 = self.normalizer.extract_building_components(normalized_name)
                                comp2 = self.normalizer.extract_building_components(candidate.normalized_name)
                                
                                # 棟が明示的に異なる場合はスキップ
                                if comp1['unit'] and comp2['unit'] and comp1['unit'] != comp2['unit']:
                                    print(f"[INFO] 棟が異なるため除外: {normalized_name} (棟{comp1['unit']}) vs {candidate.normalized_name} (棟{comp2['unit']})")
                                    continue
                                    
                                potential_buildings.append((candidate, similarity))
                
                # 最も類似度の高い建物を選択
                if potential_buildings:
                    potential_buildings.sort(key=lambda x: x[1], reverse=True)
                    building = potential_buildings[0][0]
                    print(f"[INFO] 類似建物を発見: '{normalized_name}' → '{building.normalized_name}' (類似度: {potential_buildings[0][1]:.2f})")
            
            # 同じ建物名でも住所が異なる場合は別の建物として扱う
            if building and address and building.address and building.address != address:
                # 住所が大きく異なる場合（区が異なるなど）
                existing_district = building.address.split('区')[0] if '区' in building.address else building.address
                new_district = address.split('区')[0] if '区' in address else address
                
                if existing_district != new_district:
                    print(f"[INFO] 同名だが異なる地区の建物: {normalized_name}")
                    # 地区名を含めた建物名にする
                    district_name = new_district.split('都')[-1].strip() if '都' in new_district else new_district
                    normalized_name = f"{normalized_name}（{district_name}）"
                    
                    # 再検索
                    building = self.session.query(Building).filter(
                        Building.normalized_name == normalized_name
                    ).first()
            
            # エイリアスからも検索
            if not building:
                # 元の建物名でエイリアス検索
                alias = self.session.query(BuildingAlias).filter(
                    BuildingAlias.alias_name == building_name
                ).first()
                if alias:
                    building = alias.building
                else:
                    # 正規化された名前でもエイリアス検索
                    alias = self.session.query(BuildingAlias).filter(
                        BuildingAlias.alias_name == normalized_name
                    ).first()
                    if alias:
                        building = alias.building
        
        if not building:
            # 新規作成前に、もう一度類似建物をチェック
            # パフォーマンスのため、名前の一部が含まれる建物のみを対象とする
            final_check_buildings = []
            
            # 建物名の主要部分を抽出（最初の10文字程度）
            name_prefix = normalized_name[:10] if len(normalized_name) > 10 else normalized_name[:5]
            
            # 類似する可能性のある建物を検索
            potential_candidates = self.session.query(Building).filter(
                Building.normalized_name.like(f'%{name_prefix}%')
            ).all()
            
            for candidate in potential_candidates:
                similarity = self.normalizer.calculate_similarity(normalized_name, candidate.normalized_name)
                if similarity >= 0.95:  # 0.98から0.95に緩和（ドット・空白の違いを吸収）
                    # 建物の構成要素をチェック
                    comp1 = self.normalizer.extract_building_components(normalized_name)
                    comp2 = self.normalizer.extract_building_components(candidate.normalized_name)
                    
                    # 棟が明示的に異なる場合は除外
                    if comp1['unit'] and comp2['unit'] and comp1['unit'] != comp2['unit']:
                        continue
                    
                    # 住所もチェック
                    if address and candidate.address:
                        # 同じ区内なら同一建物の可能性が高い
                        if address.split('区')[0] == candidate.address.split('区')[0]:
                            final_check_buildings.append((candidate, similarity))
                    elif not address and not candidate.address:
                        # 両方住所がない場合も候補に含める
                        final_check_buildings.append((candidate, similarity))
            
            if final_check_buildings:
                # 最も類似度の高い建物を選択
                final_check_buildings.sort(key=lambda x: x[1], reverse=True)
                building = final_check_buildings[0][0]
                print(f"[INFO] 新規作成前に類似建物を発見: '{normalized_name}' → '{building.normalized_name}' (類似度: {final_check_buildings[0][1]:.3f})")
                
                # 元の建物名をエイリアスとして登録
                if clean_building_name != building.normalized_name:
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=clean_building_name,
                        source='SIMILARITY_MATCH'
                    )
                    self.session.add(alias)
                    print(f"[AUTO] エイリアス追加: {clean_building_name} → {building.normalized_name}")
            else:
                # 本当に新規作成
                # land_rightsが長すぎる場合は切り詰める（500文字まで）
                if land_rights and len(land_rights) > 500:
                    print(f"[WARNING] land_rights too long ({len(land_rights)} chars), truncating: {land_rights}")
                    land_rights = land_rights[:497] + "..."
                
                building = Building(
                    normalized_name=normalized_name,
                    reading=generate_reading(normalized_name),
                    address=address,
                    built_year=built_year,
                    total_floors=total_floors,
                    basement_floors=basement_floors,
                    total_units=total_units,
                    structure=structure,
                    land_rights=land_rights,
                    parking_info=parking_info
                )
                self.session.add(building)
                self.session.flush()
                print(f"[DEBUG] Created new building '{normalized_name}' with built_year={built_year}")
            
            # 英語名の建物の場合、カタカナエイリアスを自動生成
            if has_english_words(normalized_name):
                katakana_alias = english_to_katakana(normalized_name)
                if katakana_alias:
                    # カタカナエイリアスを追加
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=katakana_alias,
                        source='KATAKANA_AUTO'
                    )
                    self.session.add(alias)
                    print(f"[AUTO] カタカナエイリアス生成: {normalized_name} → {katakana_alias}")
                    
                    # カタカナエイリアスの読み仮名も生成
                    katakana_reading = generate_reading(katakana_alias)
                    if katakana_reading and katakana_reading != building.reading:
                        # カタカナエイリアスの読み仮名もエイリアスとして追加
                        reading_alias = BuildingAlias(
                            building_id=building.id,
                            alias_name=katakana_reading,
                            source='READING_AUTO'
                        )
                        self.session.add(reading_alias)
                        print(f"[AUTO] 読み仮名エイリアス生成: {katakana_alias} → {katakana_reading}")
        else:
            # 建物名の最適化（更新時）
            # 現在の建物名とエイリアスから全ての候補を収集
            all_names = [building.normalized_name]
            aliases = self.session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id
            ).all()
            all_names.extend([alias.alias_name for alias in aliases])
            
            # 新しい名前も候補に追加
            if building_name not in all_names:
                all_names.append(building_name)
            
            # 最適な建物名を選択
            best_name = self.select_best_building_name(all_names)
            best_normalized = self.normalizer.normalize(best_name)
            
            # 建物名が変更される場合
            if best_normalized != building.normalized_name:
                print(f"[建物名最適化] ID {building.id}: {building.normalized_name} -> {best_normalized}")
                
                # 既存の名前をエイリアスとして保存
                existing_alias = self.session.query(BuildingAlias).filter(
                    BuildingAlias.building_id == building.id,
                    BuildingAlias.alias_name == building.normalized_name
                ).first()
                
                if not existing_alias:
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=building.normalized_name,
                        source='SYSTEM'
                    )
                    self.session.add(alias)
                
                # 建物名を更新
                building.normalized_name = best_normalized
            
            # 既存の建物の情報を更新（より詳細な情報がある場合）
            if not building.reading:
                building.reading = generate_reading(normalized_name)
            if address and not building.address:
                building.address = address
                print(f"[DEBUG] Updated building '{normalized_name}' with address={address}")
            if built_year and not building.built_year:
                building.built_year = built_year
                print(f"[DEBUG] Updated building '{normalized_name}' with built_year={built_year}")
            elif built_year and building.built_year:
                print(f"[DEBUG] Building '{normalized_name}' already has built_year={building.built_year}, not updating to {built_year}")
            if total_floors and not building.total_floors:
                building.total_floors = total_floors
            if basement_floors is not None and not building.basement_floors:
                building.basement_floors = basement_floors
            if total_units and not building.total_units:
                building.total_units = total_units
                print(f"[DEBUG] Updated building '{normalized_name}' with total_units={total_units}")
            if structure and not building.structure:
                building.structure = structure
            if land_rights and not building.land_rights:
                # land_rightsが長すぎる場合は切り詰める（500文字まで）
                if len(land_rights) > 500:
                    print(f"[WARNING] land_rights too long ({len(land_rights)} chars), truncating: {land_rights}")
                    land_rights = land_rights[:497] + "..."
                building.land_rights = land_rights
            if parking_info and not building.parking_info:
                building.parking_info = parking_info
        
        # エイリアスを追加（既存でない場合）
        if building_name != normalized_name:
            existing_alias = self.session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id,
                BuildingAlias.alias_name == building_name,
                BuildingAlias.source == self.source_site
            ).first()
            
            if not existing_alias:
                alias = BuildingAlias(
                    building_id=building.id,
                    alias_name=building_name,
                    source=self.source_site
                )
                self.session.add(alias)
        
        return building, extracted_room_number
    
    def get_or_create_master_property(self, building: Building, room_number: str,
                                     floor_number: int = None, area: float = None,
                                     layout: str = None, direction: str = None,
                                     url: str = None) -> MasterProperty:
        """マスター物件を取得または作成（買い取り再販判定付き）"""
        # 物件ハッシュを生成（方角とURLも渡す）
        property_hash = self.generate_property_hash(
            building.id, room_number, floor_number, area, layout, direction, url
        )
        
        # 既存の物件を検索
        master_property = self.session.query(MasterProperty).filter(
            MasterProperty.property_hash == property_hash
        ).first()
        
        if not master_property:
            # 買い取り再販の可能性をチェック（60日以内に販売終了した類似物件があるか）
            resale_check = self.check_resale_property(building.id, floor_number, area, layout)
            
            # 新規作成
            master_property = MasterProperty(
                building_id=building.id,
                room_number=room_number,
                floor_number=floor_number,
                area=area,
                layout=layout,
                direction=direction,
                property_hash=property_hash,
                resale_property_id=resale_check['resale_property_id'],
                is_resale=resale_check['is_resale']
            )
            self.session.add(master_property)
            self.session.flush()
        else:
            # 既存物件の情報を更新（より詳細な情報がある場合）
            if floor_number and not master_property.floor_number:
                master_property.floor_number = floor_number
            if area and not master_property.area:
                master_property.area = area
            if layout and not master_property.layout:
                master_property.layout = layout
            if direction and not master_property.direction:
                master_property.direction = direction
        
        return master_property
    
    def update_master_property_by_majority(self, master_property: MasterProperty):
        """
        物件情報を掲載情報の多数決で更新
        新しい掲載情報を追加した後に呼び出される
        """
        # アクティブな掲載情報を取得
        listings = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == master_property.id,
            PropertyListing.is_active == True
        ).all()
        
        if len(listings) <= 1:
            return  # 掲載が1つ以下なら多数決の必要なし
        
        # サイト優先順位
        site_priority = {'suumo': 1, 'homes': 2, 'rehouse': 3, 'nomu': 4}
        
        def get_majority_value(attr_name):
            """特定の属性について多数決を取る"""
            values_with_source = []
            for listing in listings:
                value = getattr(listing, f'listing_{attr_name}', None)
                if value is not None:
                    values_with_source.append((value, listing.source_site))
            
            if not values_with_source:
                return None
            
            # 値の出現回数をカウント
            from collections import Counter
            value_counter = Counter([v for v, _ in values_with_source])
            max_count = max(value_counter.values())
            
            # 最頻値を取得
            most_common_values = [v for v, c in value_counter.items() if c == max_count]
            
            if len(most_common_values) == 1:
                return most_common_values[0]
            
            # 同数の場合はサイト優先順位で決定
            candidates = []
            for value in most_common_values:
                sources = [s for v, s in values_with_source if v == value]
                best_priority = min(site_priority.get(s, 999) for s in sources)
                candidates.append((value, best_priority))
            
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]
        
        # 各属性について多数決を実行
        updated = False
        
        for attr in ['floor_number', 'area', 'layout', 'direction']:
            majority_value = get_majority_value(attr)
            if majority_value is not None:
                current_value = getattr(master_property, attr)
                if current_value != majority_value:
                    setattr(master_property, attr, majority_value)
                    updated = True
                    print(f"  → {attr}: {current_value} → {majority_value} (多数決)")
        
        # バルコニー面積も多数決
        majority_balcony = get_majority_value('balcony_area')
        if majority_balcony is not None and master_property.balcony_area != majority_balcony:
            master_property.balcony_area = majority_balcony
            updated = True
            print(f"  → balcony_area: {master_property.balcony_area} → {majority_balcony} (多数決)")
        
        if updated:
            master_property.updated_at = datetime.now()
    
    def create_or_update_listing(self, master_property: MasterProperty,
                               url: str, title: str, price: int,
                               agency_name: str = None, 
                               site_property_id: str = None,
                               description: str = None,
                               station_info: str = None,
                               features: str = None,
                               management_fee: int = None,
                               repair_fund: int = None,
                               published_at: datetime = None,
                               first_published_at: datetime = None,
                               # 新規追加：掲載サイトごとの物件属性
                               listing_floor_number: int = None,
                               listing_area: float = None,
                               listing_layout: str = None,
                               listing_direction: str = None,
                               listing_total_floors: int = None,
                               listing_balcony_area: float = None,
                               listing_address: str = None) -> PropertyListing:
        """掲載情報を作成または更新"""
        # 既存の掲載を検索
        listing = self.session.query(PropertyListing).filter(
            PropertyListing.url == url
        ).first()
        
        if listing:
            # 既存掲載を更新
            listing.title = title
            listing.agency_name = agency_name
            listing.description = description
            listing.station_info = station_info
            listing.features = features
            listing.last_scraped_at = datetime.now()
            listing.last_fetched_at = datetime.now()
            listing.last_confirmed_at = datetime.now()  # 最終確認日時を更新
            
            # published_atが設定されていて、既存のものがない場合は更新
            if published_at and not listing.published_at:
                listing.published_at = published_at
            
            # first_published_atが設定されていて、既存のものがない場合は更新
            if first_published_at and not listing.first_published_at:
                listing.first_published_at = first_published_at
            
            # first_published_atがない場合は、published_atかfirst_seen_atの古い方を設定
            if not listing.first_published_at:
                if listing.published_at:
                    listing.first_published_at = min(listing.published_at, listing.first_seen_at)
                else:
                    listing.first_published_at = listing.first_seen_at
            
            # 掲載サイトごとの物件属性を更新
            if listing_floor_number is not None:
                listing.listing_floor_number = listing_floor_number
            if listing_area is not None:
                listing.listing_area = listing_area
            if listing_layout is not None:
                listing.listing_layout = listing_layout
            if listing_direction is not None:
                listing.listing_direction = listing_direction
            if listing_total_floors is not None:
                listing.listing_total_floors = listing_total_floors
            if listing_balcony_area is not None:
                listing.listing_balcony_area = listing_balcony_area
            if listing_address is not None:
                listing.listing_address = listing_address
            
            # 価格・管理費・修繕積立金のいずれかが変更された場合は履歴に記録
            price_changed = listing.current_price != price
            mgmt_fee_changed = listing.management_fee != management_fee
            repair_fund_changed = listing.repair_fund != repair_fund
            
            if price_changed or mgmt_fee_changed or repair_fund_changed:
                # 最新の価格履歴を取得して重複チェック
                latest_history = self.session.query(ListingPriceHistory).filter(
                    ListingPriceHistory.property_listing_id == listing.id
                ).order_by(ListingPriceHistory.recorded_at.desc()).first()
                
                # 最新履歴と異なる場合のみ記録
                should_record = True
                if latest_history:
                    if (latest_history.price == price and 
                        latest_history.management_fee == management_fee and
                        latest_history.repair_fund == repair_fund):
                        should_record = False
                
                if should_record:
                    price_history = ListingPriceHistory(
                        property_listing_id=listing.id,
                        price=price,
                        management_fee=management_fee,
                        repair_fund=repair_fund
                    )
                    self.session.add(price_history)
                    print(f"  → 価格更新: {listing.current_price}万円 → {price}万円")
                    
                    # 価格が変更された場合は価格改定日を更新
                    if listing.current_price != price:
                        listing.price_updated_at = datetime.now()
                
                # 現在価格を更新
                listing.current_price = price
                listing.management_fee = management_fee
                listing.repair_fund = repair_fund
        else:
            # 新規掲載を作成
            # first_published_atが指定されていない場合は、published_atかfirst_seen_atを使用
            if not first_published_at:
                first_published_at = published_at or datetime.now()
            
            listing = PropertyListing(
                master_property_id=master_property.id,
                source_site=self.source_site,
                site_property_id=site_property_id,
                url=url,
                title=title,
                description=description,
                agency_name=agency_name,
                current_price=price,
                management_fee=management_fee,
                repair_fund=repair_fund,
                station_info=station_info,
                features=features,
                published_at=published_at,  # 情報提供日を設定
                first_published_at=first_published_at,  # 情報公開日を設定
                price_updated_at=published_at or datetime.now(),  # 初回は情報提供日を価格改定日とする
                last_confirmed_at=datetime.now(),  # 初回確認日時を設定
                # 掲載サイトごとの物件属性
                listing_floor_number=listing_floor_number,
                listing_area=listing_area,
                listing_layout=listing_layout,
                listing_direction=listing_direction,
                listing_total_floors=listing_total_floors,
                listing_balcony_area=listing_balcony_area,
                listing_address=listing_address
            )
            self.session.add(listing)
            self.session.flush()
            
            # 初回価格を履歴に記録（価格が存在する場合のみ）
            if price is not None:
                price_history = ListingPriceHistory(
                    property_listing_id=listing.id,
                    price=price,
                    management_fee=management_fee,
                    repair_fund=repair_fund
                )
                self.session.add(price_history)
                print(f"  → 初回価格記録: {price}万円")
        
        # 買い取り再販のチェック（再販候補IDがある場合）
        if master_property.resale_property_id and not master_property.is_resale:
            self.check_and_update_resale_flag(master_property, price)
        
        return listing
    
    def add_property_images(self, listing: PropertyListing, image_urls: List[str]):
        """物件画像を追加"""
        # 既存の画像を削除
        self.session.query(PropertyImage).filter(
            PropertyImage.property_listing_id == listing.id
        ).delete()
        
        # 新しい画像を追加
        for i, url in enumerate(image_urls):
            image = PropertyImage(
                property_listing_id=listing.id,
                image_url=url,
                display_order=i
            )
            self.session.add(image)
    
    def mark_inactive_listings(self, active_urls: List[str]):
        """アクティブでない掲載を非アクティブにマーク（確認されなかった物件を削除済みとして記録）"""
        now = datetime.now()
        
        # 当該ソースサイトでアクティブな掲載のうち、今回のスクレイピングで見つからなかったものを検出
        if active_urls:
            inactive_listings = self.session.query(PropertyListing).filter(
                PropertyListing.source_site == self.source_site,
                PropertyListing.is_active == True,
                ~PropertyListing.url.in_(active_urls)
            ).all()
        else:
            # active_urlsが空の場合、全てを非アクティブに
            inactive_listings = self.session.query(PropertyListing).filter(
                PropertyListing.source_site == self.source_site,
                PropertyListing.is_active == True
            ).all()
        
        # 削除検出された物件を記録
        for listing in inactive_listings:
            listing.is_active = False
            listing.delisted_at = now
            print(f"  → 削除検出: {listing.title} (最終確認: {listing.last_confirmed_at})")
        
        # 今回確認されたURLのlast_confirmed_atも更新
        if active_urls:
            self.session.query(PropertyListing).filter(
                PropertyListing.source_site == self.source_site,
                PropertyListing.url.in_(active_urls)
            ).update({
                'last_confirmed_at': now
            })
        
        self.session.commit()
        
        if inactive_listings:
            print(f"\n{self.source_site}で {len(inactive_listings)} 件の物件が削除されました")
    
    def generate_property_hash(self, building_id: int, room_number: str, 
                             floor_number: int = None, area: float = None, 
                             layout: str = None, direction: str = None, url: str = None) -> str:
        """物件ハッシュを生成
        
        同一物件の判定基準：
        建物ID + 所在階 + 平米数（専有面積） + 間取り + 方角
        
        重要：
        - 部屋番号は使用しません（サイトによって公開状況が異なるため）
        - 方角も含めてハッシュを生成します
        - 方角だけが異なる場合は別物件として扱われますが、同一物件の可能性もあるため、
          管理画面の「物件重複管理」機能で人的に判断・統合する必要があります
        """
        # 部屋番号の有無に関わらず、統一的な基準でハッシュを生成
        floor_str = f"F{floor_number}" if floor_number else "F?"
        area_str = f"A{area:.1f}" if area else "A?"  # 小数点第1位まで
        layout_str = layout if layout else "L?"
        direction_str = f"D{direction}" if direction else "D?"
        data = f"{building_id}:{floor_str}_{area_str}_{layout_str}_{direction_str}"
        
        return hashlib.md5(data.encode()).hexdigest()
    
    def check_resale_property(self, building_id: int, floor_number: int = None, 
                            area: float = None, layout: str = None) -> dict:
        """買い取り再販物件かチェック
        
        60日以内に販売終了した類似物件があり、かつ価格が上昇している場合は買い取り再販と判定
        """
        from datetime import datetime, timedelta
        
        # デフォルトの結果
        result = {'resale_property_id': None, 'is_resale': False}
        
        # 必要な情報が揃っていない場合はチェックしない
        if not floor_number or not area or not layout:
            return result
        
        # 60日前の日時
        cutoff_date = datetime.now() - timedelta(days=60)
        
        # 同じ建物、同じ階、似た面積、同じ間取りの販売終了物件を検索
        similar_properties = self.session.query(MasterProperty).join(
            PropertyListing,
            MasterProperty.id == PropertyListing.master_property_id
        ).filter(
            MasterProperty.building_id == building_id,
            MasterProperty.floor_number == floor_number,
            MasterProperty.layout == layout,
            # 面積の誤差は0.5㎡以内
            MasterProperty.area.between(area - 0.5, area + 0.5),
            # 販売終了している
            PropertyListing.is_active == False,
            PropertyListing.sold_at != None,
            # 60日以内に販売終了
            PropertyListing.sold_at >= cutoff_date
        ).order_by(PropertyListing.sold_at.desc()).all()
        
        if similar_properties:
            # 最も最近販売終了した物件
            previous_property = similar_properties[0]
            
            # 前回の販売価格を取得
            last_listing = self.session.query(PropertyListing).filter(
                PropertyListing.master_property_id == previous_property.id,
                PropertyListing.sold_at != None
            ).order_by(PropertyListing.sold_at.desc()).first()
            
            if last_listing and last_listing.current_price:
                # この時点では新物件の価格がまだ分からないので、
                # とりあえず再販候補として記録
                result['resale_property_id'] = previous_property.id
                # is_resaleフラグは価格比較後に設定される
        
        return result
    
    def check_and_update_resale_flag(self, master_property: MasterProperty, current_price: int):
        """買い取り再販フラグを価格比較して更新"""
        if not master_property.resale_property_id or not current_price:
            return
        
        # 前の物件の最終販売価格を取得
        last_listing = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == master_property.resale_property_id,
            PropertyListing.sold_at != None
        ).order_by(PropertyListing.sold_at.desc()).first()
        
        if last_listing and last_listing.current_price:
            # 価格が上昇している場合は買い取り再販と判定
            if current_price > last_listing.current_price:
                master_property.is_resale = True
                print(f"  → 買い取り再販物件と判定（前回価格: {last_listing.current_price}万円 → 今回価格: {current_price}万円）")
    
    def should_skip_property(self, url: str) -> bool:
        """物件をスキップすべきか判定（90日スキップ機能は無効化）"""
        # 90日スキップ機能を無効化 - 常にFalseを返す
        return False
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"ページ取得エラー: {url} - {e}")
            return None
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング（サブクラスで実装）"""
        raise NotImplementedError
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析（サブクラスで実装）"""
        raise NotImplementedError
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析（サブクラスで実装）"""
        raise NotImplementedError
    
    def needs_detail_fetch(self, listing: PropertyListing) -> bool:
        """詳細ページの取得が必要かどうかを判定"""
        # 強制詳細取得モードの場合は常に取得
        if self.force_detail_fetch:
            return True
        
        # 新規物件の場合は常に詳細を取得
        if not listing.detail_fetched_at:
            return True
        
        # 更新マークがある場合は詳細を取得
        if listing.has_update_mark:
            return True
        
        # 指定日数以上詳細を取得していない場合は取得
        if listing.detail_fetched_at < datetime.now() - timedelta(days=self.detail_refetch_days):
            return True
        
        return False
    
    def update_listing_from_list(self, listing: PropertyListing, list_data: Dict[str, Any]):
        """一覧ページのデータで掲載情報を更新"""
        # 更新マークの状態を保存
        if 'has_update_mark' in list_data:
            listing.has_update_mark = list_data['has_update_mark']
        
        # 一覧ページに表示される更新日を保存
        if 'list_update_date' in list_data:
            listing.list_update_date = list_data['list_update_date']
    
    def fetch_and_update_detail(self, listing: PropertyListing) -> bool:
        """詳細ページを取得して情報を更新"""
        # この基底クラスでは実装しない（各スクレイパーでオーバーライド）
        raise NotImplementedError("Each scraper must implement fetch_and_update_detail method")