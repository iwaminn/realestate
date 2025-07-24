"""
ベーススクレイパークラス v2
新しいデータベース構造に対応
"""

import time
import hashlib
import requests
import threading
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
import os

from ..database import SessionLocal
from ..models import (
    Building, BuildingAlias, BuildingExternalId, MasterProperty, PropertyListing, 
    ListingPriceHistory, PropertyImage
)
from ..utils.building_normalizer import BuildingNameNormalizer
from ..utils.reading_generator import generate_reading
from ..utils.katakana_converter import english_to_katakana, has_english_words
from ..config.scraper_config import ScraperConfig
from ..utils.scraper_error_logger import ScraperErrorLogger
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
        
        # エラーログ専用のロガーを設定
        self.error_logger = ScraperErrorLogger(source_site)
        
        # 設定を読み込む
        config = ScraperConfig.get_scraper_specific_config(source_site)
        self.delay = config['delay']  # スクレイピング間隔（秒）
        self.detail_refetch_days = config['detail_refetch_days']  # 詳細ページ再取得間隔（日）
        
        # エラー追跡とサーキットブレーカー設定
        self.error_threshold = float(os.getenv('SCRAPER_ERROR_THRESHOLD', '0.5'))  # 50%のエラー率でストップ
        self.min_attempts_before_check = int(os.getenv('SCRAPER_MIN_ATTEMPTS', '10'))  # 最低10件処理してからチェック
        self.consecutive_error_limit = int(os.getenv('SCRAPER_CONSECUTIVE_ERROR_LIMIT', '10'))  # 連続10件のエラーでストップ
        self.consecutive_errors = 0
        self.circuit_breaker_enabled = os.getenv('SCRAPER_CIRCUIT_BREAKER', 'true').lower() == 'true'
        
        # エラー統計
        self.error_stats = {
            'total_attempts': 0,
            'total_errors': 0,
            'validation_errors': 0,
            'parsing_errors': 0,
            'saving_errors': 0,
            'detail_page_errors': 0,
        }
        
        # スクレイピング統計（管理画面用）
        self._scraping_stats = {
            'properties_found': 0,        # 一覧ページから発見した物件総数
            'properties_processed': 0,    # 処理対象とした物件数（max_properties制限後）
            'properties_attempted': 0,    # 実際に処理を試行した物件数
            'detail_fetched': 0,          # 詳細ページを取得した件数
            'detail_skipped': 0,          # 詳細ページ取得をスキップした件数
            'new_listings': 0,            # 新規登録した掲載数
            'updated_listings': 0,        # 更新した掲載数
            'detail_fetch_failed': 0,     # 詳細取得に失敗した数
            'save_failed': 0,             # 保存に失敗した数
            'price_missing': 0,           # 価格情報が取得できなかった数
            'building_info_missing': 0,   # 建物情報が不足していた数
            'other_errors': 0,            # その他のエラー数
        }
        self._stats_lock = threading.Lock()  # 統計のスレッドセーフアクセス用
    
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
    
    def check_circuit_breaker(self) -> None:
        """サーキットブレーカーのチェック - エラー率が閾値を超えた場合は例外を投げる"""
        if not self.circuit_breaker_enabled:
            return
            
        # 最低試行回数に達していない場合はチェックしない
        if self.error_stats['total_attempts'] < self.min_attempts_before_check:
            return
            
        # エラー率の計算
        error_rate = self.error_stats['total_errors'] / self.error_stats['total_attempts']
        
        if error_rate >= self.error_threshold:
            error_msg = (
                f"サーキットブレーカー作動: エラー率 {error_rate:.1%} が閾値 {self.error_threshold:.1%} を超えました。"
                f"（{self.error_stats['total_errors']}/{self.error_stats['total_attempts']} 件）"
            )
            self.logger.error(error_msg)
            self.error_logger.log_circuit_breaker_activation(
                error_rate=error_rate,
                total_errors=self.error_stats['total_errors'],
                total_attempts=self.error_stats['total_attempts']
            )
            raise Exception(error_msg)
        
        # 連続エラーチェック
        if self.consecutive_errors >= self.consecutive_error_limit:
            error_msg = (
                f"サーキットブレーカー作動: 連続エラー数 {self.consecutive_errors} が上限 {self.consecutive_error_limit} に達しました。"
            )
            self.logger.error(error_msg)
            self.error_logger.log_circuit_breaker_activation(
                error_rate=error_rate,
                total_errors=self.error_stats['total_errors'],
                total_attempts=self.error_stats['total_attempts'],
                consecutive_errors=self.consecutive_errors
            )
            raise Exception(error_msg)
    
    def record_success(self) -> None:
        """成功を記録"""
        self.error_stats['total_attempts'] += 1
        self.consecutive_errors = 0  # 連続エラーカウントをリセット
    
    def record_property_found(self, count: int = 1) -> None:
        """一覧から見つかった物件数を記録"""
        with self._stats_lock:
            self._scraping_stats['properties_found'] += count
    
    def record_property_processed(self, count: int = 1) -> None:
        """処理対象とした物件数を記録（max_properties制限後）"""
        with self._stats_lock:
            self._scraping_stats['properties_processed'] += count
    
    def record_property_attempted(self) -> None:
        """処理を試行した物件を記録"""
        with self._stats_lock:
            self._scraping_stats['properties_attempted'] += 1
    
    def record_property_scraped(self) -> None:
        """詳細取得に成功した物件を記録"""
        with self._stats_lock:
            self._scraping_stats['detail_fetched'] += 1
    
    def record_listing_created(self) -> None:
        """新規作成された掲載を記録"""
        with self._stats_lock:
            self._scraping_stats['new_listings'] += 1
    
    def record_listing_updated(self) -> None:
        """更新された掲載を記録"""
        with self._stats_lock:
            self._scraping_stats['updated_listings'] += 1
    
    def record_listing_skipped(self) -> None:
        """スキップされた掲載を記録"""
        with self._stats_lock:
            self._scraping_stats['detail_skipped'] += 1
    
    def record_save_failed(self) -> None:
        """保存失敗を記録"""
        with self._stats_lock:
            self._scraping_stats['save_failed'] += 1
    
    def record_detail_fetch_failed(self) -> None:
        """詳細取得失敗を記録"""
        with self._stats_lock:
            self._scraping_stats['detail_fetch_failed'] += 1
    
    def record_price_missing(self) -> None:
        """価格情報なしを記録"""
        with self._stats_lock:
            self._scraping_stats['price_missing'] += 1
    
    def record_building_info_missing(self) -> None:
        """建物情報なしを記録"""
        with self._stats_lock:
            self._scraping_stats['building_info_missing'] += 1
    
    def record_other_error(self) -> None:
        """その他のエラーを記録"""
        with self._stats_lock:
            self._scraping_stats['other_errors'] += 1
    
    def get_scraping_stats(self) -> Dict[str, int]:
        """スクレイピング統計を取得"""
        with self._stats_lock:
            return self._scraping_stats.copy()
    
    def get_stats(self) -> Dict[str, int]:
        """管理画面用の統計を取得（後方互換性のため）"""
        stats = self._scraping_stats.copy()
        # 旧形式の名前にマッピング
        return {
            'properties_found': stats.get('properties_found', 0),
            'properties_scraped': stats.get('properties_scraped', 0),
            'new_properties': stats.get('new_listings', 0),
            'updated_properties': stats.get('updated_listings', 0),
            'skipped_properties': stats.get('skipped_listings', 0),
            'price_missing': stats.get('price_missing', 0),
            'building_info_missing': stats.get('building_info_missing', 0),
            'detail_fetch_failed': stats.get('detail_fetch_failed', 0),
            'other_errors': stats.get('other_errors', 0)
        }
    
    def record_error(self, error_type: str = 'other', 
                    url: Optional[str] = None,
                    building_name: Optional[str] = None,
                    property_data: Optional[Dict[str, Any]] = None,
                    error: Optional[Exception] = None,
                    phase: str = "unknown") -> None:
        """エラーを記録（詳細なコンテキスト情報付き）"""
        self.error_stats['total_attempts'] += 1
        self.error_stats['total_errors'] += 1
        self.consecutive_errors += 1
        
        # エラータイプ別のカウント
        if error_type == 'validation':
            self.error_stats['validation_errors'] += 1
        elif error_type == 'parsing':
            self.error_stats['parsing_errors'] += 1
        elif error_type == 'saving':
            self.error_stats['saving_errors'] += 1
        elif error_type == 'detail_page':
            self.error_stats['detail_page_errors'] += 1
        
        # 詳細なエラー情報を記録
        self.error_logger.log_property_error(
            error_type=error_type,
            url=url,
            building_name=building_name,
            property_data=property_data,
            error=error,
            phase=phase
        )
        
        # サーキットブレーカーのチェック
        self.check_circuit_breaker()
    
    def validate_html_structure(self, soup: BeautifulSoup, required_selectors: Dict[str, str]) -> bool:
        """HTML構造の検証 - 必要な要素が存在するか確認"""
        missing_elements = []
        
        for name, selector in required_selectors.items():
            elements = soup.select(selector)
            if not elements:
                missing_elements.append(f"{name} ({selector})")
        
        if missing_elements:
            self.logger.warning(
                f"HTML構造が変更された可能性があります。"
                f"以下の要素が見つかりません: {', '.join(missing_elements)}"
            )
            
            # パースエラーの詳細を記録
            missing_selectors = [selector for _, selector in [(name, sel) for name, sel in required_selectors.items() if soup.select(sel) == []]]
            found_selectors = {name: len(soup.select(selector)) > 0 for name, selector in required_selectors.items()}
            
            self.error_logger.log_parsing_error(
                url=soup.get('data-url', 'unknown'),  # URLが利用可能な場合
                missing_selectors=missing_selectors,
                found_selectors=found_selectors
            )
            
            return False
            
        return True
    
    def enhanced_validate_property_data(self, property_data: Dict[str, Any]) -> bool:
        """強化された物件データ検証"""
        # 既存の検証を実行
        if not self.validate_property_data(property_data):
            return False
        
        # 追加の検証
        # 必須フィールドの詳細チェック
        essential_fields = {
            'url': lambda x: isinstance(x, str) and x.startswith('http'),
            'price': lambda x: isinstance(x, (int, float)) and 100 <= x <= 10000000,
            'building_name': lambda x: isinstance(x, str) and 3 <= len(x) <= 100,
            'area': lambda x: x is None or (isinstance(x, (int, float)) and 10 <= x <= 1000),
            'layout': lambda x: x is None or (isinstance(x, str) and len(x) <= 20),
            'floor_number': lambda x: x is None or (isinstance(x, int) and -5 <= x <= 100),
        }
        
        for field, validator in essential_fields.items():
            if field in property_data:
                try:
                    if not validator(property_data[field]):
                        self.logger.warning(f"フィールド '{field}' の値が無効です: {property_data[field]}")
                        return False
                except Exception as e:
                    self.logger.warning(f"フィールド '{field}' の検証中にエラー: {e}")
                    return False
        
        # データ整合性チェック
        if 'floor_number' in property_data and 'total_floors' in property_data:
            if property_data['floor_number'] and property_data['total_floors']:
                if property_data['floor_number'] > property_data['total_floors']:
                    self.logger.warning(
                        f"階数の整合性エラー: {property_data['floor_number']}階/"
                        f"{property_data['total_floors']}階建て"
                    )
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
                
                return building, extracted_room_number
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
                                     url: str = None, current_price: int = None) -> MasterProperty:
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
            # 買い取り再販の可能性をチェック
            resale_check = self.check_resale_property(building.id, floor_number, area, layout, current_price)
            
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
                               listing_address: str = None,
                               # カウント制御用フラグ
                               record_stats: bool = True) -> PropertyListing:
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
            
            # 更新の統計を記録（record_statsがTrueの場合のみ）
            if record_stats:
                self.record_listing_updated()
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
            
            # 新規作成の統計を記録（record_statsがTrueの場合のみ）
            if record_stats:
                self.record_listing_created()
        
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
    
    def get_existing_listings_map(self, urls: List[str]) -> Dict[str, PropertyListing]:
        """URLリストから既存の掲載情報をマップとして取得（N+1問題の解決）"""
        if not urls:
            return {}
        
        print(f"\n既存の掲載情報を取得中...")
        existing_listings_query = self.session.query(PropertyListing).filter(
            PropertyListing.url.in_(urls)
        )
        existing_listings_map = {listing.url: listing for listing in existing_listings_query}
        print(f"  → {len(existing_listings_map)} 件の既存掲載を発見")
        
        return existing_listings_map
    
    def common_scrape_area_logic(self, area_identifier: str, max_pages: int = 5):
        """共通のエリアスクレイピングロジック（Template Method Pattern）
        
        各スクレイパーは以下のメソッドを実装する必要があります：
        - get_search_url(area_identifier, page): 検索URLを生成
        - parse_property_list(soup): 物件一覧から情報を抽出
        - process_property_data(property_data, existing_listing): 個別の物件を処理
        """
        if self.force_detail_fetch:
            print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
        
        # ===== フェーズ1: 物件一覧の収集 =====
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            # 検索URLを生成（各スクレイパーで実装）
            search_url = self.get_search_url(area_identifier, page)
            print(f"URL: {search_url}")
            soup = self.fetch_page(search_url)
            
            if not soup:
                print(f"ページ {page} の取得に失敗しました")
                break
            
            # 物件情報を一覧から抽出（各スクレイパーで実装）
            properties = self.parse_property_list(soup)
            
            if not properties:
                print(f"ページ {page} に物件が見つかりません")
                break
            
            print(f"ページ {page} で {len(properties)} 件の物件を発見")
            
            # max_propertiesを超えないように調整
            if self.max_properties and len(all_properties) + len(properties) > self.max_properties:
                # 必要な分だけ取得
                remaining = self.max_properties - len(all_properties)
                properties = properties[:remaining]
                print(f"  → 最大取得件数に合わせて {remaining} 件のみ使用")
            
            # 一覧から見つかった物件数を記録
            self.record_property_found(len(properties))
            all_properties.extend(properties)
            
            # 最大件数に達した場合は終了
            if self.max_properties and len(all_properties) >= self.max_properties:
                print(f"最大取得件数（{self.max_properties}件）に達しました")
                break
            
            # ページ間で遅延
            time.sleep(self.delay)
        
        # 処理対象数を記録（実際に処理する数）
        actual_to_process = len(all_properties)
        print(f"\n収集完了: 合計 {actual_to_process} 件の物件を発見")
        self.record_property_processed(actual_to_process)
        
        # 既存の掲載を一括で取得してマップ化（N+1問題の解決）
        all_urls = [p['url'] for p in all_properties if p.get('url')]
        existing_listings_map = self.get_existing_listings_map(all_urls)
        
        # ===== フェーズ2: 詳細取得と保存 =====
        print(f"\n合計 {len(all_properties)} 件の物件を処理します...")
        
        saved_count = 0
        skipped_count = 0
        
        for i, property_data in enumerate(all_properties, 1):
            print(f"[{i}/{len(all_properties)}] {property_data.get('building_name', 'Unknown')}")
            
            # 処理を試行
            self.record_property_attempted()
            
            # URLがあれば処理可能
            if not property_data.get('url'):
                print(f"  → URLが不足、スキップ")
                skipped_count += 1
                self.record_other_error()
                continue
            
            try:
                # 既存の掲載をマップから取得
                existing_listing = existing_listings_map.get(property_data['url'])
                
                # 個別の物件を処理（各スクレイパーで実装）
                success = self.process_property_data(property_data, existing_listing)
                
                if success:
                    saved_count += 1
                else:
                    skipped_count += 1
                
            except Exception as e:
                print(f"  → エラー: {e}")
                self.record_error(
                    error_type='saving',
                    url=property_data.get('url'),
                    building_name=property_data.get('building_name'),
                    property_data=property_data,
                    error=e,
                    phase='save_property'
                )
                skipped_count += 1
                self.record_other_error()
                continue
        
        # 非アクティブな掲載をマーク（部分的なスクレイピングの場合はスキップ）
        if max_pages >= 30:  # 全体スクレイピングの閾値
            self.mark_inactive_listings(all_urls)
        else:
            print(f"部分スクレイピング（{max_pages}ページ）のため、非アクティブマーキングをスキップ")
        
        # 変更をコミット
        self.session.commit()
        
        # 統計情報を表示
        self.display_scraping_stats(saved_count)
        
        return saved_count
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（各スクレイパーでオーバーライド）"""
        raise NotImplementedError("各スクレイパーでprocess_property_dataメソッドを実装してください")
    
    def handle_skipped_listing(self, existing_listing: PropertyListing, reason: str = "detail_skipped") -> bool:
        """詳細取得をスキップした既存掲載の処理を統一的に行う
        
        Args:
            existing_listing: 既存の掲載情報
            reason: スキップ理由（'detail_skipped', 'no_update_mark'など）
            
        Returns:
            bool: 処理成功（スキップは成功として扱う）
        """
        if existing_listing:
            # 最終確認日時だけは更新（物件がまだアクティブであることを記録）
            existing_listing.last_confirmed_at = datetime.now()
            self.session.flush()
        
        # スキップカウントを記録（更新カウントは増やさない）
        self.record_listing_skipped()
        
        return True  # スキップは成功として扱う
    
    def save_property_common(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件を保存する共通処理（詳細データ取得済みを前提）
        
        各スクレイパーから呼び出される共通保存処理。
        この時点で property_data には詳細ページのデータが含まれていることを前提とする。
        
        Args:
            property_data: 完全な物件情報（詳細ページのデータ含む）
            existing_listing: 既存の掲載情報（あれば）
            
        Returns:
            bool: 保存成功かどうか
        """
        try:
            # データ検証
            if not self.enhanced_validate_property_data(property_data):
                validation_errors = []
                if not property_data.get('building_name'):
                    validation_errors.append('建物名が不足')
                if not property_data.get('price'):
                    validation_errors.append('価格が不足')
                
                self.record_error(
                    error_type='validation',
                    url=property_data.get('url'),
                    building_name=property_data.get('building_name'),
                    property_data=property_data,
                    phase='enhanced_validation'
                )
                
                # バリデーションエラーの詳細を記録
                if validation_errors:
                    self.error_logger.log_validation_error(
                        property_data=property_data,
                        validation_errors=validation_errors,
                        url=property_data.get('url')
                    )
                return False
            
            # 価格が取得できているか確認
            if not property_data.get('price'):
                print(f"  → 価格情報が取得できませんでした")
                self.record_price_missing()
                self.record_error(
                    error_type='validation',
                    url=property_data.get('url'),
                    building_name=property_data.get('building_name'),
                    property_data=property_data,
                    phase='price_validation'
                )
                return False
            
            print(f"  価格: {property_data.get('price')}万円")
            print(f"  間取り: {property_data.get('layout', '不明')}")
            print(f"  面積: {property_data.get('area', '不明')}㎡")
            print(f"  階数: {property_data.get('floor_number', '不明')}階")
            
            # 建物を取得または作成
            building, extracted_room_number = self.get_or_create_building(
                property_data.get('building_name', ''),
                property_data.get('address', ''),
                built_year=property_data.get('built_year'),
                total_floors=property_data.get('total_floors'),
                basement_floors=property_data.get('basement_floors'),
                total_units=property_data.get('total_units'),
                structure=property_data.get('structure'),
                land_rights=property_data.get('land_rights'),
                parking_info=property_data.get('parking_info')
            )
            
            if not building:
                print(f"  → 建物情報が不足")
                self.record_building_info_missing()
                self.record_error(
                    error_type='validation',
                    url=property_data.get('url'),
                    building_name=property_data.get('building_name'),
                    property_data=property_data,
                    phase='building_creation'
                )
                return False
            
            # 部屋番号の決定（抽出された部屋番号を優先）
            room_number = property_data.get('room_number', '')
            if extracted_room_number and not room_number:
                room_number = extracted_room_number
                print(f"  → 建物名から部屋番号を抽出: {room_number}")
            
            # マスター物件を取得または作成
            master_property = self.get_or_create_master_property(
                building=building,
                room_number=room_number,
                floor_number=property_data.get('floor_number'),
                area=property_data.get('area'),
                layout=property_data.get('layout'),
                direction=property_data.get('direction'),
                url=property_data.get('url'),
                current_price=property_data.get('price')
            )
            
            # バルコニー面積を設定
            if property_data.get('balcony_area'):
                master_property.balcony_area = property_data['balcony_area']
            
            # 掲載情報を作成または更新
            listing = self.create_or_update_listing(
                master_property=master_property,
                url=property_data.get('url', ''),
                title=property_data.get('title', property_data.get('building_name', '')),
                price=property_data.get('price'),
                agency_name=property_data.get('agency_name'),
                site_property_id=property_data.get('site_property_id', ''),
                description=property_data.get('description'),
                station_info=property_data.get('station_info'),
                management_fee=property_data.get('management_fee'),
                repair_fund=property_data.get('repair_fund'),
                published_at=property_data.get('published_at'),
                first_published_at=property_data.get('first_published_at'),
                # 掲載サイトごとの物件属性
                listing_floor_number=property_data.get('floor_number'),
                listing_area=property_data.get('area'),
                listing_layout=property_data.get('layout'),
                listing_direction=property_data.get('direction'),
                listing_total_floors=property_data.get('total_floors'),
                listing_balcony_area=property_data.get('balcony_area'),
                listing_address=property_data.get('address')
            )
            
            # agency_telとremarksは別途設定
            if property_data.get('agency_tel'):
                listing.agency_tel = property_data['agency_tel']
            if property_data.get('remarks'):
                listing.remarks = property_data['remarks']
            
            # 一覧ページの情報で更新（新着・更新マークなど）
            self.update_listing_from_list(listing, property_data)
            
            # 画像を追加
            if property_data.get('image_urls'):
                self.add_property_images(listing, property_data['image_urls'])
            
            # 詳細情報を保存
            if property_data.get('detail_info'):
                listing.detail_info = property_data['detail_info']
            listing.detail_fetched_at = datetime.now()
            
            # 多数決による物件情報更新
            self.update_master_property_by_majority(master_property)
            
            print(f"  → 保存完了")
            self.record_success()
            
            return True
            
        except Exception as e:
            print(f"  → エラー: {e}")
            import traceback
            traceback.print_exc()
            self.record_error(
                error_type='saving',
                url=property_data.get('url'),
                building_name=property_data.get('building_name'),
                property_data=property_data,
                error=e,
                phase='save_property'
            )
            self.record_save_failed()
            return False
    
    def process_property_with_detail_check(self, 
                                          property_data: Dict[str, Any], 
                                          existing_listing: Optional[PropertyListing],
                                          parse_detail_func: callable,
                                          save_property_func: callable) -> bool:
        """詳細取得の必要性をチェックしてから物件を処理する共通メソッド
        
        Args:
            property_data: 一覧ページから取得した物件情報
            existing_listing: 既存の掲載情報（あれば）
            parse_detail_func: 詳細ページを解析する関数
            save_property_func: 物件を保存する関数
            
        Returns:
            bool: 処理成功かどうか
        """
        url = property_data.get('url')
        if not url:
            print(f"  → URLが不足")
            self.record_other_error()
            return False
        
        print(f"  URL: {url}")
        
        # 詳細ページの取得が必要かチェック
        needs_detail = True
        if existing_listing:
            # property_dataに更新マークがある場合は、existing_listingに反映
            if 'has_update_mark' in property_data:
                existing_listing.has_update_mark = property_data['has_update_mark']
            
            # 価格が変更されているかチェック
            price_changed = False
            if 'price' in property_data and property_data['price'] is not None:
                if existing_listing.current_price != property_data['price']:
                    price_changed = True
                    print(f"  → 価格変更検出: {existing_listing.current_price}万円 → {property_data['price']}万円")
            
            # 価格変更があれば詳細を取得、なければ通常の判定
            if price_changed:
                needs_detail = True
            else:
                needs_detail = self.needs_detail_fetch(existing_listing)
                if not needs_detail:
                    print(f"  → 詳細ページの取得をスキップ（最終取得: {existing_listing.detail_fetched_at}）")
                    return self.handle_skipped_listing(existing_listing, "detail_skipped")
        
        # 詳細ページから全ての情報を取得
        detail_data = parse_detail_func(url)
        if not detail_data:
            print(f"  → 詳細ページの取得に失敗しました")
            self.record_detail_fetch_failed()
            return False
        
        # 詳細データで property_data を更新
        property_data.update(detail_data)
        # 詳細取得成功を記録
        self.record_property_scraped()
        
        # 物件を保存
        return save_property_func(property_data, existing_listing)
    
    def display_scraping_stats(self, saved_count: int):
        """スクレイピング統計を表示"""
        stats = self.get_scraping_stats()
        print(f"\nスクレイピング完了:")
        print(f"  物件発見数: {stats['properties_found']} 件（一覧ページから発見）")
        print(f"  処理対象数: {stats['properties_processed']} 件（max_properties制限後）")
        print(f"  処理試行数: {stats['properties_attempted']} 件")
        print(f"  詳細取得数: {stats['detail_fetched']} 件")
        print(f"  詳細スキップ数: {stats['detail_skipped']} 件")
        print(f"  新規登録数: {stats['new_listings']} 件")
        print(f"  更新数: {stats['updated_listings']} 件")
        print(f"  保存成功数: {saved_count} 件")
        
        # エラー統計
        error_count = (stats['detail_fetch_failed'] + stats['price_missing'] + 
                      stats['building_info_missing'] + stats['save_failed'] + 
                      stats['other_errors'])
        if error_count > 0:
            print(f"\nエラー統計:")
            if stats['detail_fetch_failed'] > 0:
                print(f"  詳細取得失敗: {stats['detail_fetch_failed']} 件")
            if stats['price_missing'] > 0:
                print(f"  価格情報なし: {stats['price_missing']} 件")
            if stats['building_info_missing'] > 0:
                print(f"  建物情報不足: {stats['building_info_missing']} 件")
            if stats['save_failed'] > 0:
                print(f"  保存失敗: {stats['save_failed']} 件")
            if stats['other_errors'] > 0:
                print(f"  その他エラー: {stats['other_errors']} 件")
            print(f"  エラー合計: {error_count} 件")
    
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
                            area: float = None, layout: str = None, 
                            current_price: int = None) -> dict:
        """買い取り再販物件かチェック
        
        1ヶ月以上前に販売終了した類似物件があり、かゔ10%以上価格が上昇している場合は買い取り再販と判定
        """
        from datetime import datetime, timedelta
        
        # デフォルトの結果
        result = {'resale_property_id': None, 'is_resale': False}
        
        # 必要な情報が揃っていない場合はチェックしない
        if not floor_number or not area or not layout:
            return result
        
        # 1ヶ月前の日時
        one_month_ago = datetime.now() - timedelta(days=30)
        
        # 同じ建物、同じ階、似た面積、同じ間取りの販売終了物件を検索
        similar_properties = self.session.query(MasterProperty).filter(
            MasterProperty.building_id == building_id,
            MasterProperty.floor_number == floor_number,
            MasterProperty.layout == layout,
            # 面積の誤差は0.5㎡以内
            MasterProperty.area.between(area - 0.5, area + 0.5),
            # 販売終了している
            MasterProperty.sold_at != None,
            # 1ヶ月以上前に販売終了
            MasterProperty.sold_at < one_month_ago
        ).order_by(MasterProperty.sold_at.desc()).all()
        
        if similar_properties:
            # 最も最近販売終了した物件
            previous_property = similar_properties[0]
            
            # 前回の最終販売価格を取得
            if previous_property.last_sale_price and current_price:
                # 10%以上の価格上昇かチェック
                price_increase_rate = (current_price - previous_property.last_sale_price) / previous_property.last_sale_price
                
                if price_increase_rate >= 0.1:  # 10%以上の上昇
                    result['resale_property_id'] = previous_property.id
                    result['is_resale'] = True
                    print(f"  → 買い取り再販物件と判定: 前回{previous_property.last_sale_price}万円 → 今回{current_price}万円 ({price_increase_rate*100:.1f}%上昇)")
        
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
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
        
        # 指定日数以上詳細を取得していない場合は取得
        if listing.detail_fetched_at < datetime.now() - timedelta(days=self.detail_refetch_days):
            return True
        
        return False
    
    def process_property_with_smart_scraping(self, property_data: Dict[str, Any], 
                                           get_detail_func: callable,
                                           save_func: callable) -> bool:
        """スマートスクレイピングを使用して物件を処理
        
        Args:
            property_data: 一覧ページから取得した物件情報
            get_detail_func: 詳細ページを取得する関数 (urlを引数に取る)
            save_func: 物件を保存する関数 (property_dataを引数に取る)
            
        Returns:
            bool: 保存に成功したかどうか
        """
        url = property_data.get('url')
        if not url:
            return False
            
        try:
            # 既存の掲載を確認
            from ..models import PropertyListing
            existing_listing = self.session.query(PropertyListing).filter(
                PropertyListing.url == url
            ).first()
            
            # 詳細ページの取得が必要かチェック
            needs_detail = True
            if existing_listing and not self.force_detail_fetch:
                needs_detail = self.needs_detail_fetch(existing_listing)
                if not needs_detail:
                    print(f"  → 詳細ページの取得をスキップ（最終取得: {existing_listing.detail_fetched_at}）")
                    # 最終確認日時だけは更新（物件がまだアクティブであることを記録）
                    existing_listing.last_confirmed_at = datetime.now()
                    self.session.flush()
                    self.record_listing_skipped()
                    return True  # スキップは成功として扱う
            
            # 詳細ページを取得
            detail_data = get_detail_func(url)
            if detail_data:
                self.record_property_scraped()
                # 一覧ページのデータとマージ
                property_data.update(detail_data)
                
                # データベースに保存
                return save_func(property_data)
            else:
                self.record_detail_fetch_failed()
                return False
                
        except Exception as e:
            logger.error(f"スマートスクレイピングエラー: {e}")
            self.record_detail_fetch_failed()
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