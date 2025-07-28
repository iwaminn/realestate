import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
import os
from abc import ABC, abstractmethod
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import jaconv

from .constants import SourceSite
from ..database import SessionLocal
from ..models import (
    Building, MasterProperty, PropertyListing, 
    ListingPriceHistory, PropertyImage, BuildingExternalId, Url404Retry
)
from ..utils.building_normalizer import BuildingNameNormalizer
from ..utils.property_hasher import PropertyHasher
from ..utils.majority_vote_updater import MajorityVoteUpdater
from ..utils.exceptions import TaskPausedException, TaskCancelledException
import time as time_module
from ..utils.debug_logger import debug_log


class BaseScraper(ABC):
    """スクレイパーの基底クラス"""
    
    def __init__(self, source_site: Union[str, SourceSite], force_detail_fetch: bool = False, max_properties: Optional[int] = None):
        # 文字列の場合はSourceSiteに変換（後方互換性）
        if isinstance(source_site, str):
            self.source_site = SourceSite.from_string(source_site)
        else:
            self.source_site = source_site
        self.force_detail_fetch = force_detail_fetch
        self.max_properties = max_properties
        self.session = SessionLocal()
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logger = self._setup_logger()
        self.normalizer = BuildingNameNormalizer()
        self.property_hasher = PropertyHasher()
        self.majority_updater = MajorityVoteUpdater(self.session)
        
        # スマートスクレイピング設定
        self.detail_refetch_days = self._get_detail_refetch_days()
        self.enable_smart_scraping = self._get_smart_scraping_enabled()
        
        # プロパティカウンター（制限用）
        self._property_count = 0
        
        # スクレイピング遅延（秒）
        self.delay = float(os.getenv('SCRAPER_DELAY', '1'))
        
        # スクレイピング統計
        self._scraping_stats = {
            'properties_found': 0,
            'properties_processed': 0,
            'properties_attempted': 0,
            'detail_fetched': 0,
            'detail_skipped': 0,
            'new_listings': 0,  # 新規物件
            'price_updated': 0,  # 価格更新があった物件
            'refetched_unchanged': 0,  # 再取得したが変更なし
            'other_updates': 0,  # 価格以外の項目が更新された物件
            'detail_fetch_failed': 0,
            'save_failed': 0,  # 詳細取得は成功したが保存に失敗した件数
            'price_missing': 0,
            'building_info_missing': 0,
            'other_errors': 0
        }
        
        # 一時停止・再開用の状態変数
        self._collected_properties = []
        self._current_page = 1
        self._processed_count = 0
    
    def _setup_logger(self) -> logging.Logger:
        """ロガーのセットアップ"""
        logger = logging.getLogger(f'scraper.{self.source_site}')
        logger.setLevel(logging.INFO)
        
        # コンソールハンドラーがなければ追加
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def _get_detail_refetch_days(self) -> int:
        """詳細再取得の日数を取得"""
        # 環境変数から設定を取得
        # スクレイパー固有の設定を優先
        env_key = f'SCRAPER_{self.source_site.upper()}_DETAIL_REFETCH_DAYS'
        specific_days = os.getenv(env_key)
        if specific_days:
            return int(specific_days)
        
        # 共通設定
        common_days = os.getenv('SCRAPER_DETAIL_REFETCH_DAYS', '90')
        return int(common_days)
    
    def _get_smart_scraping_enabled(self) -> bool:
        """スマートスクレイピングが有効かどうかを取得"""
        # 環境変数から設定を取得（デフォルトは有効）
        env_key = f'SCRAPER_{self.source_site.upper()}_SMART_SCRAPING'
        specific_setting = os.getenv(env_key)
        if specific_setting is not None:
            return specific_setting.lower() in ('true', '1', 'yes', 'on')
        
        # 共通設定
        common_setting = os.getenv('SCRAPER_SMART_SCRAPING', 'true')
        return common_setting.lower() in ('true', '1', 'yes', 'on')
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得してBeautifulSoupオブジェクトを返す"""
        try:
            time.sleep(2)  # レート制限対策
            response = self.http_session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # 404エラーの場合は特別処理
                self.logger.warning(f"404 Not Found: {url}")
                self._handle_404_error(url)
            else:
                self.logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None
    
    @abstractmethod
    def get_search_url(self, area_code: str, page: int = 1) -> str:
        """検索URLを生成（各スクレイパーで実装）"""
        pass
    
    @abstractmethod
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析（各スクレイパーで実装）"""
        pass
    
    @abstractmethod
    def parse_property_detail(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件詳細を解析（各スクレイパーで実装）"""
        pass
    
    @abstractmethod
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（各スクレイパーで実装）"""
        pass
    
    def common_scrape_area_logic(self, area_code: str, max_pages: int = None) -> Dict[str, Any]:
        """エリアの物件をスクレイピングする共通ロジック（価格変更ベースのスマートスクレイピング対応）"""
        self.logger.info(f"スクレイピング開始: エリア={area_code}, 最大物件数={self.max_properties}")
        
        # デバッグ：フラグの状態を確認
        if hasattr(self, 'pause_flag'):
            self.logger.info(f"[DEBUG] common_scrape_area_logic開始時 - pause_flag exists: {self.pause_flag is not None}")
            debug_log(f"[{self.source_site}] common_scrape_area_logic開始 - pause_flag exists: {self.pause_flag is not None}")
            if self.pause_flag:
                self.logger.info(f"[DEBUG] pause_flag ID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
                debug_log(f"[{self.source_site}] pause_flag ID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
        else:
            self.logger.info("[DEBUG] pause_flag attribute not found!")
            debug_log(f"[{self.source_site}] pause_flag attribute not found!")
        
        total_properties = 0
        detail_fetched = 0
        skipped = 0
        errors = 0
        
        # 再開時の状態チェック
        self.logger.info(f"[DEBUG] 再開チェック: phase={self._scraping_stats.get('phase')}, collected={len(self._collected_properties)}, page={self._current_page}, processed={self._processed_count}")
        debug_log(f"[{self.source_site}] 再開チェック: phase={self._scraping_stats.get('phase')}, collected={len(self._collected_properties)}, page={self._current_page}, processed={self._processed_count}")
        
        if self._scraping_stats.get('phase') == 'processing' and self._collected_properties:
            # 処理フェーズから再開
            self.logger.info(f"処理フェーズから再開: 処理済み={self._processed_count}/{len(self._collected_properties)}件")
            all_properties = self._collected_properties
            page = self._current_page
            # 処理フェーズから再開の場合は収集をスキップ
            skip_collection = True
        elif self._scraping_stats.get('phase') == 'collecting' and self._collected_properties:
            # 収集フェーズから再開
            self.logger.info(f"収集フェーズから再開: ページ={self._current_page}, 収集済み={len(self._collected_properties)}件")
            all_properties = self._collected_properties
            page = self._current_page
            skip_collection = False
        else:
            skip_collection = False
            # 既存の変数を使用（set_resume_stateで設定された可能性があるため）
            all_properties = self._collected_properties if self._collected_properties else []
            page = self._current_page if self._current_page > 0 else 1
            
            # 統計が空の場合のみリセット
            if not self._scraping_stats:
                # プロパティカウンターをリセット
                self._property_count = 0
                
                # 統計をリセット
                self._scraping_stats = {
                    'properties_found': 0,
                    'properties_processed': 0,
                    'properties_attempted': 0,
                    'detail_fetched': 0,
                    'detail_skipped': 0,
                    'new_listings': 0,  # 新規物件
                    'price_updated': 0,  # 価格更新があった物件
                    'refetched_unchanged': 0,  # 再取得したが変更なし
                    'other_updates': 0,  # 価格以外の項目が更新された物件
                    'detail_fetch_failed': 0,
                    'save_failed': 0,  # 詳細取得は成功したが保存に失敗した件数
                    'price_missing': 0,
                    'building_info_missing': 0,
                    'other_errors': 0
                }
        
        # 収集フェーズの場合
        # 処理フェーズから再開する場合は収集をスキップ
        print(f"[DEBUG-RESUME-CHECK] phase={self._scraping_stats.get('phase')}, collected_properties={len(self._collected_properties) if self._collected_properties else 0}")
        if not (self._scraping_stats.get('phase') == 'processing' and self._collected_properties):
            # 第1段階：全ページから物件情報を収集
            self.logger.info("第1段階: 物件一覧を収集中...")
            consecutive_empty_pages = 0
            max_consecutive_empty = 2  # 2ページ連続で物件がない場合は終了
            seen_urls = set()  # 既に発見した物件のURLを記録
            previous_page_urls = set()  # 前ページの物件URL
            duplicate_page_count = 0  # 完全に重複したページの連続回数
            
            # 収集フェーズを示すフラグ
            self._scraping_stats['phase'] = 'collecting'  # 第1段階: 収集中
            
            while True:
                self.logger.info(f"[DEBUG] 収集ループ開始: page={page}")
                debug_log(f"[{self.source_site}] 収集ループ開始: page={page}")
                
                # 一時停止チェック
                if hasattr(self, 'pause_flag'):
                    self.logger.info(f"[DEBUG] pause_flag exists: {self.pause_flag is not None}, ID: {id(self.pause_flag) if self.pause_flag else 'None'}")
                    debug_log(f"[{self.source_site}] pause_flag exists: {self.pause_flag is not None}")
                    if self.pause_flag:
                        self.logger.info(f"[DEBUG] pause_flag is_set: {self.pause_flag.is_set()}")
                        debug_log(f"[{self.source_site}] pause_flag is_set: {self.pause_flag.is_set()}")
                if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
                    self.logger.info("タスクが一時停止されました（収集フェーズ）")
                    # 現在の収集状態を保存
                    self._collected_properties = all_properties
                    self._current_page = page
                    
                    # 一時停止フラグがクリアされるまで待機
                    self.logger.info(f"一時停止フラグがクリアされるまで待機中... フラグID: {id(self.pause_flag)}")
                    debug_log(f"[{self.source_site}] 一時停止フラグがクリアされるまで待機中... フラグID: {id(self.pause_flag)}")
                    wait_count = 0
                    # 初回のフラグ状態を記録
                    initial_flag_state = self.pause_flag.is_set()
                    self.logger.info(f"[DEBUG] Initial pause flag state: {initial_flag_state}")
                    debug_log(f"[{self.source_site}] Initial pause flag state: {initial_flag_state}")
                    
                    # タイムアウト設定（300秒 = 5分）
                    pause_timeout = 300
                    while self.pause_flag.is_set():
                        # キャンセルチェック
                        if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                            raise TaskCancelledException("Task cancelled during pause")
                        time_module.sleep(0.1)
                        wait_count += 1
                        if wait_count % 50 == 0:  # 5秒ごとにログ出力
                            self.logger.info(f"待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                            debug_log(f"[{self.source_site}] 待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                        # タイムアウトチェック
                        if wait_count >= pause_timeout * 10:  # wait_countは0.1秒単位
                            self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                            raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
                    
                    self.logger.info(f"一時停止が解除されました。処理を再開します... (待機時間: {wait_count/10}秒)")
                    debug_log(f"[{self.source_site}] 一時停止が解除されました。処理を再開します... (待機時間: {wait_count/10}秒)")
                    # 処理を継続（ループは中断しない）
                
                # 最大物件数に達した場合は終了
                if self.max_properties and len(all_properties) >= self.max_properties:
                    self.logger.info(f"最大物件数 {self.max_properties} に達したため終了")
                    break
                
                # 安全のため、あまりにも多くのページを取得しないようにする
                max_pages = 200  # 最大ページ数の設定
                if page > max_pages:
                    self.logger.warning(f"{max_pages}ページを超えたため終了")
                    break
                
                try:
                    # 検索URLを生成
                    url = self.get_search_url(area_code, page)
                    self.logger.info(f"ページ {page} を取得中: {url}")
                    debug_log(f"[{self.source_site}] ページ {page} を取得中: {url}")
                    
                    # ページを取得
                    self.logger.info(f"[DEBUG] fetch_page呼び出し前")
                    debug_log(f"[{self.source_site}] fetch_page呼び出し前")
                    soup = self.fetch_page(url)
                    self.logger.info(f"[DEBUG] fetch_page呼び出し後")
                    debug_log(f"[{self.source_site}] fetch_page呼び出し後")
                    if not soup:
                        self.logger.warning(f"ページ {page} の取得に失敗")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_consecutive_empty:
                            self.logger.info("連続してページ取得に失敗したため終了")
                            break
                        page += 1
                        continue
                    
                    # 物件一覧を解析
                    self.logger.info(f"[DEBUG] parse_property_list呼び出し前")
                    debug_log(f"[{self.source_site}] parse_property_list呼び出し前")
                    properties = self.parse_property_list(soup)
                    self.logger.info(f"[DEBUG] parse_property_list呼び出し後: {len(properties) if properties else 0}件")
                    debug_log(f"[{self.source_site}] parse_property_list呼び出し後: {len(properties) if properties else 0}件")
                    if not properties:
                        self.logger.info(f"ページ {page}: 物件が見つかりませんでした")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_consecutive_empty:
                            self.logger.info("これ以上物件がないため終了")
                            break
                        page += 1
                        continue
                    
                    # 物件が見つかった場合
                    consecutive_empty_pages = 0
                    self.logger.info(f"ページ {page}: {len(properties)} 件の物件を検出")
                    
                    # 現在のページの物件URLを収集
                    current_page_urls = set()
                    new_properties = []
                    duplicate_count = 0
                    
                    for prop in properties:
                        prop_url = prop.get('url', '')
                        if prop_url:
                            current_page_urls.add(prop_url)
                            if prop_url not in seen_urls:
                                new_properties.append(prop)
                                seen_urls.add(prop_url)
                            else:
                                duplicate_count += 1
                    
                    # ページの重複チェック
                    if current_page_urls and current_page_urls == previous_page_urls:
                        duplicate_page_count += 1
                        self.logger.warning(f"ページ {page}: 前ページと完全に同じ内容です（ページング失敗の可能性）")
                        if duplicate_page_count >= 2:
                            self.logger.error("2ページ連続で同じ内容のため、ページング処理を終了します")
                            break
                    else:
                        duplicate_page_count = 0
                    
                    previous_page_urls = current_page_urls
                    
                    if duplicate_count > 0:
                        self.logger.info(f"ページ {page}: {duplicate_count} 件の重複物件を除外")
                    
                    if not new_properties:
                        self.logger.info(f"ページ {page}: すべて既出の物件でした")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_consecutive_empty:
                            self.logger.info("新規物件が見つからないため終了")
                            break
                    else:
                        # 最大物件数を考慮して物件を追加
                        if self.max_properties:
                            remaining = self.max_properties - len(all_properties)
                            if remaining <= 0:
                                break
                            if remaining < len(new_properties):
                                all_properties.extend(new_properties[:remaining])
                                self.logger.info(f"最大物件数に達したため、{remaining} 件のみ追加")
                                # リアルタイムで統計を更新
                                self._scraping_stats['properties_found'] = len(all_properties)
                                break
                            else:
                                all_properties.extend(new_properties)
                        else:
                            all_properties.extend(new_properties)
                    
                    # リアルタイムで統計を更新
                    self._scraping_stats['properties_found'] = len(all_properties)
                    self.logger.info(f"現在の物件発見数: {len(all_properties)} 件")
                    
                    page += 1
                    self.logger.info(f"[DEBUG] ループ終了、次のページ: {page}")
                    debug_log(f"[{self.source_site}] ループ終了、次のページ: {page}")
                    
                except (TaskPausedException, TaskCancelledException):
                    # タスクの一時停止・キャンセル例外は再スロー
                    raise
                except Exception as e:
                    self.logger.error(f"ページ {page} の処理中にエラー: {e}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_consecutive_empty:
                        self.logger.error("連続してエラーが発生したため終了")
                        break
                    page += 1
                    continue
            
            # 収集フェーズ終了後のクリーンアップ
            self.logger.info(f"[DEBUG] 収集ループ終了")
            debug_log(f"[{self.source_site}] 収集ループ終了")
            # 収集した物件数を記録
            self._scraping_stats['properties_found'] = len(all_properties)
            self.logger.info(f"第1段階完了: 合計 {len(all_properties)} 件の物件を収集")
            debug_log(f"[{self.source_site}] 第1段階完了: 合計 {len(all_properties)} 件の物件を収集")
        else:
            # 処理フェーズから再開した場合
            self.logger.info(f"収集フェーズをスキップ（既に {len(all_properties)} 件収集済み）")
            debug_log(f"[{self.source_site}] 収集フェーズをスキップ（既に {len(all_properties)} 件収集済み）")
        
        # 一時停止チェック（収集フェーズと処理フェーズの間）
        self.logger.info(f"[DEBUG] 処理フェーズ開始前の一時停止チェック")
        debug_log(f"[{self.source_site}] 処理フェーズ開始前の一時停止チェック")
        if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
            self.logger.info(f"[{self.source_site}] タスクが一時停止されました（フェーズ間）")
            debug_log(f"[{self.source_site}] タスクが一時停止されました（フェーズ間）")
            # 現在の状態を保存
            self._collected_properties = all_properties
            self._current_page = page
            
            # 一時停止フラグがクリアされるまで待機
            self.logger.info(f"一時停止フラグがクリアされるまで待機中（フェーズ間）... フラグID: {id(self.pause_flag)}")
            debug_log(f"[{self.source_site}] 一時停止フラグがクリアされるまで待機中（フェーズ間）... フラグID: {id(self.pause_flag)}")
            wait_count = 0
            # タイムアウト設定（300秒 = 5分）
            pause_timeout = 300
            while self.pause_flag.is_set():
                # キャンセルチェック
                if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                    raise TaskCancelledException("Task cancelled during pause")
                time_module.sleep(0.1)
                wait_count += 1
                if wait_count % 50 == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"フェーズ間待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                    debug_log(f"[{self.source_site}] フェーズ間待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                # タイムアウトチェック
                if wait_count >= pause_timeout * 10:
                    self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                    raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
            
            self.logger.info(f"一時停止が解除されました（フェーズ間）。処理を再開します... (待機時間: {wait_count/10}秒)")
            debug_log(f"[{self.source_site}] 一時停止が解除されました（フェーズ間）。処理を再開します... (待機時間: {wait_count/10}秒)")
        
        # 処理対象数を設定（収集した物件数と処理上限数の小さい方）
        # 注意: ここでは「処理予定数」を設定している。実際の処理数は後で更新される
        expected_to_process = min(len(all_properties), self.max_properties) if self.max_properties else len(all_properties)
        self._scraping_stats['properties_processed'] = expected_to_process
        
        # 第2段階：収集した物件を処理
        self.logger.info(f"第2段階: {self._scraping_stats['properties_processed']} 件の物件を処理中...")
        debug_log(f"[{self.source_site}] 第2段階: {self._scraping_stats['properties_processed']} 件の物件を処理中...")
        
        # 処理フェーズを示すフラグ
        self._scraping_stats['phase'] = 'processing'  # 第2段階: 処理中
        
        self.logger.info(f"[DEBUG] 処理フェーズのループ開始")
        debug_log(f"[{self.source_site}] 処理フェーズのループ開始")
        
        for i, property_data in enumerate(all_properties):
            # 既に処理済みの物件はスキップ（再開時）
            if i < self._processed_count:
                continue
            
            # ループの開始をログ出力
            if i % 10 == 0:  # 10件ごとにログ
                self.logger.info(f"[DEBUG] 処理中: {i}/{len(all_properties)}件目")
                debug_log(f"[{self.source_site}] 処理中: {i}/{len(all_properties)}件目")
            
            # 一時停止チェック
            if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
                self.logger.info(f"[{self.source_site}] タスクが一時停止されました（処理フェーズ）")
                # 現在の処理状態を保存
                self._processed_count = i
                self._collected_properties = all_properties  # 収集済み物件も保存
                
                # 一時停止フラグがクリアされるまで待機
                self.logger.info(f"一時停止フラグがクリアされるまで待機中（処理フェーズ）... フラグID: {id(self.pause_flag)}")
                debug_log(f"[{self.source_site}] 処理フェーズで一時停止検出。待機開始... フラグID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
                wait_count = 0
                # タイムアウト設定（300秒 = 5分）
                pause_timeout = 300
                while self.pause_flag.is_set():
                    # キャンセルチェック
                    if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                        raise TaskCancelledException("Task cancelled during pause")
                    time_module.sleep(0.1)
                    wait_count += 1
                    if wait_count % 50 == 0:  # 5秒ごとにログ出力
                        self.logger.info(f"処理フェーズ待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                        debug_log(f"[{self.source_site}] 処理フェーズ待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                    # タイムアウトチェック
                    if wait_count >= pause_timeout * 10:
                        self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                        raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
                
                self.logger.info(f"一時停止が解除されました（処理フェーズ）。処理を再開します... (待機時間: {wait_count/10}秒)")
                debug_log(f"[{self.source_site}] 処理フェーズで一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
                # 処理を継続（ループは中断しない）
            
            # 最大物件数に達した場合は終了
            if self.max_properties and self._property_count >= self.max_properties:
                self.logger.info(f"最大物件数 {self.max_properties} に達したため処理を終了")
                break
                
            # キャンセルチェック（各物件処理前）
            if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                self.logger.info("タスクがキャンセルされました（処理フェーズ）")
                raise TaskCancelledException("Task cancelled during processing phase")
            
            # 進捗表示
            if i % 10 == 0:
                progress = (i / len(all_properties)) * 100
                self.logger.info(f"進捗: {i}/{len(all_properties)} ({progress:.1f}%)")
            
            # 各物件の処理前にもデバッグログ
            debug_log(f"[{self.source_site}] 物件 {i} の処理開始...")
            
            try:
                self._scraping_stats['properties_attempted'] += 1
                
                # 必須フィールドの確認
                if not property_data.get('url'):
                    self.logger.warning(f"物件 {i+1}: URLがありません")
                    self._scraping_stats['other_errors'] += 1
                    continue
                
                # サイトごとの固有処理（process_property_dataメソッドを実装）
                if hasattr(self, 'process_property_data'):
                    # 既存の掲載情報を確認（site_property_idで検索）
                    existing_listing = None
                    site_property_id = property_data.get('site_property_id')
                    
                    if site_property_id:
                        self.logger.info(f"[DEBUG] DB確認中: site_property_id={site_property_id}")
                        existing_listing = self.session.query(PropertyListing).filter(
                            PropertyListing.site_property_id == site_property_id,
                            PropertyListing.source_site == self.source_site
                        ).first()
                        self.logger.info(f"[DEBUG] DB確認完了: existing={existing_listing is not None}")
                    else:
                        # site_property_idがない場合は従来通りURLで検索（後方互換性）
                        self.logger.info(f"[DEBUG] site_property_idがないためURLで確認: {property_data['url']}")
                        existing_listing = self.session.query(PropertyListing).filter(
                            PropertyListing.url == property_data['url'],
                            PropertyListing.source_site == self.source_site
                        ).first()
                        self.logger.info(f"[DEBUG] DB確認完了: existing={existing_listing is not None}")
                    
                    # 価格変更ベースのスマートスクレイピング対応
                    self.logger.info(f"[DEBUG] process_property_data呼び出し前 - 物件 {i}")
                    processed = self.process_property_data(property_data, existing_listing)
                    self.logger.info(f"[DEBUG] process_property_data呼び出し後 - 物件 {i}, processed={processed}")
                    
                    # 全ての物件をカウント
                    total_properties += 1
                    self._property_count += 1
                    
                    # 各物件を正確に3つのカテゴリーに分類
                    # 1. 詳細取得成功（保存の成否に関わらず）
                    if property_data.get('detail_fetched', False):
                        detail_fetched += 1
                        self._scraping_stats['detail_fetched'] += 1
                        self.logger.info(f"詳細取得成功: URL={property_data.get('url', '不明')}, property_saved={property_data.get('property_saved', 'None')}, update_type={property_data.get('update_type', 'None')}")
                    
                    # 2. 詳細取得失敗（エラー）
                    elif property_data.get('detail_fetch_attempted', False) and not property_data.get('detail_fetched', False):
                        # 詳細取得を試みたが失敗した
                        # これはエラーなので、detail_skippedにはカウントしない
                        self.logger.info(f"詳細取得失敗（エラー）: URL={property_data.get('url', '不明')}")
                    
                    # 3. 詳細スキップ（正常）
                    else:
                        skipped += 1
                        self._scraping_stats['detail_skipped'] += 1
                        self.logger.info(f"詳細スキップ: URL={property_data.get('url', '不明')}, skipped={skipped}")
                    
                    # 保存結果と更新タイプに基づく統計更新（詳細取得の有無に関わらず）
                    if property_data.get('property_saved', False) and 'update_type' in property_data:
                        update_type = property_data['update_type']
                        self.logger.info(f"統計更新: URL={property_data.get('url', '不明')}, update_type={update_type}")
                        
                        # 詳細取得の有無に関わらず統計を更新
                        if update_type == 'new':
                            self._scraping_stats['new_listings'] += 1
                        elif update_type == 'price_changed' or update_type == 'price_updated':
                            self._scraping_stats['price_updated'] += 1
                        elif update_type == 'refetched_unchanged':
                            self._scraping_stats['refetched_unchanged'] += 1
                        elif update_type == 'skipped':
                            # 詳細をスキップした場合は何もカウントしない（更新ではないため）
                            pass
                        elif update_type == 'other_updates':
                            self._scraping_stats['other_updates'] += 1
                        else:
                            # 未知のupdate_type
                            self._scraping_stats['other_updates'] += 1
                            self.logger.warning(f"未知のupdate_type: {update_type}, URL={property_data.get('url', '不明')}")
                    elif property_data.get('property_saved') is False:
                        # 保存失敗の場合（Noneはキャンセルなので除外）
                        if property_data.get('detail_fetched', False):
                            # 詳細を取得したが保存に失敗した場合は、保存失敗としてカウント
                            self._scraping_stats['save_failed'] = self._scraping_stats.get('save_failed', 0) + 1
                            self.logger.info(f"物件保存失敗（詳細取得済み）: URL={property_data.get('url', '不明')}, この時点でdetail_fetched={detail_fetched}, 統計={self._scraping_stats['detail_fetched']}")
                        else:
                            # 詳細を取得していない場合（スキップした場合）は統計カウント外
                            self.logger.info(f"物件保存失敗（詳細未取得）: URL={property_data.get('url', '不明')}")
                    elif property_data.get('property_saved') is None:
                        # キャンセルされた場合（統計に含めない）
                        self.logger.info(f"物件処理がキャンセルされました: URL={property_data.get('url', '不明')}")
                    else:
                        # property_savedフラグが設定されていない、またはupdate_typeが設定されていない場合
                        if property_data.get('detail_fetched', False):
                            # 詳細を取得したが、統計が更新されていない
                            self.logger.warning(
                                f"詳細取得したが統計が更新されていない: "
                                f"URL={property_data.get('url', '不明')}, "
                                f"property_saved={property_data.get('property_saved', 'None')}, "
                                f"update_type={property_data.get('update_type', 'None')}"
                            )
                            # 不明としてカウント
                            self._scraping_stats['unknown'] = self._scraping_stats.get('unknown', 0) + 1
                else:
                    # 従来の処理（後方互換性）
                    self.save_property(property_data)
                    total_properties += 1
                    self._property_count += 1
                    # properties_processedは処理対象数なので、ここではインクリメントしない
                    
                # ループの最後でも処理位置を更新
                self._processed_count = i + 1
                debug_log(f"[{self.source_site}] 物件 {i} の処理完了。次の処理位置: {self._processed_count}")
                
                # 最後の物件の場合、特別なログを出力
                if i == len(all_properties) - 1:
                    self.logger.info(f"[DEBUG] 最後の物件({i})の処理完了。統計: detail_fetched={detail_fetched}, detail_skipped={skipped}, エラー={self._scraping_stats.get('detail_fetch_failed', 0) + self._scraping_stats.get('save_failed', 0)}, 合計={detail_fetched + skipped + self._scraping_stats.get('detail_fetch_failed', 0) + self._scraping_stats.get('save_failed', 0)}")
            
            except TaskPausedException as e:
                # タスクの一時停止例外は再スロー
                self.logger.info(f"物件 {i+1}: タスクが一時停止されました - {type(e).__name__}: {e}")
                debug_log(f"[{self.source_site}] 物件 {i} で一時停止例外検出: {type(e).__name__}: {e}")
                raise
            except TaskCancelledException as e:
                # タスクがキャンセルされた場合は、現在の物件までで処理を終了
                self.logger.info(f"物件 {i+1}: タスクがキャンセルされました - 処理を終了します")
                debug_log(f"[{self.source_site}] 物件 {i} でキャンセル検出: 処理を終了")
                # 未処理の物件はエラーとしてカウントしない
                break
            except Exception as e:
                # デバッグ用：例外の型を記録
                error_type_name = type(e).__name__
                self.logger.error(f"物件 {i+1} の処理中にエラー ({error_type_name}): {e}")
                errors += 1
                self._scraping_stats['other_errors'] += 1
                continue
            
            # 定期的にコミット
            if total_properties % 10 == 0:
                self.session.commit()
        
        # 最終コミット
        self.session.commit()
        
        # 実際の処理済み件数で統計を更新
        self._scraping_stats['properties_processed'] = total_properties
        
        # 完了フェーズを設定
        self._scraping_stats['phase'] = 'completed'  # 完了
        
        result = {
            'total_properties': total_properties,
            'detail_fetched': detail_fetched,
            'skipped': skipped,
            'errors': errors,
            'detail_fetch_failed': self._scraping_stats.get('detail_fetch_failed', 0)
        }
        
        # 詳細な統計ログ
        self.logger.info(
            f"スクレイピング完了: 合計={total_properties}件, "
            f"詳細取得={detail_fetched}件, スキップ={skipped}件, エラー={errors}件"
        )
        
        # 詳細取得の内訳を表示
        if detail_fetched > 0:
            save_failed = self._scraping_stats.get('save_failed', 0)
            new_listings = self._scraping_stats.get('new_listings', 0)
            price_updated = self._scraping_stats.get('price_updated', 0) 
            other_updates = self._scraping_stats.get('other_updates', 0)
            refetched_unchanged = self._scraping_stats.get('refetched_unchanged', 0)
            
            # 合計を計算
            accounted_for = new_listings + price_updated + other_updates + refetched_unchanged + save_failed
            unaccounted = detail_fetched - accounted_for
            
            breakdown = (
                f"詳細取得{detail_fetched}件の内訳: "
                f"新規={new_listings}件, "
                f"価格更新={price_updated}件, "
                f"その他更新={other_updates}件, "
                f"再取得(変更なし)={refetched_unchanged}件"
            )
            if save_failed > 0:
                breakdown += f", 保存失敗={save_failed}件"
            if unaccounted > 0:
                breakdown += f", 不明={unaccounted}件"
            self.logger.info(breakdown)
            
            # 不明な件数がある場合は警告
            if unaccounted > 0:
                self.logger.warning(f"詳細取得したが統計に含まれていない物件が{unaccounted}件あります")
        
        self.logger.info(f"[DEBUG] common_scrape_area_logic終了、結果を返却")
        debug_log(f"[{self.source_site}] common_scrape_area_logic終了、結果を返却")
        
        return result
    
    def _check_pause_flag(self):
        """一時停止フラグをチェックし、必要に応じて待機（内部メソッド）"""
        if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
            self.logger.info(f"[{self.source_site}] タスクが一時停止されました（詳細処理中）")
            debug_log(f"[{self.source_site}] 詳細処理中に一時停止検出。待機開始...")
            
            # 一時停止フラグがクリアされるまで待機
            wait_count = 0
            # タイムアウト設定（300秒 = 5分）
            pause_timeout = 300
            while self.pause_flag.is_set():
                if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                    raise TaskCancelledException("Task cancelled during pause")
                time_module.sleep(0.1)
                wait_count += 1
                if wait_count % 50 == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"詳細処理待機中... {wait_count/10}秒経過")
                    debug_log(f"[{self.source_site}] 詳細処理待機中... {wait_count/10}秒経過")
                # タイムアウトチェック
                if wait_count >= pause_timeout * 10:
                    self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                    raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
            
            self.logger.info(f"一時停止が解除されました（詳細処理中）。処理を再開... (待機時間: {wait_count/10}秒)")
            debug_log(f"[{self.source_site}] 詳細処理で一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
    
    def process_property_with_detail_check(
        self, 
        property_data: Dict[str, Any], 
        existing_listing: Optional[PropertyListing],
        parse_detail_func,
        save_property_func
    ) -> bool:
        """物件処理の共通ロジック（価格変更ベースの詳細取得判定）"""
        
        # 基本情報のログ
        building_name = property_data.get('building_name', '不明')
        price = property_data.get('price', '不明')
        
        print(f"\n処理中: {building_name}")
        print(f"  URL: {property_data.get('url', '')}")
        print(f"  価格: {price}万円" if price != '不明' else "  価格: 不明")
        
        # 詳細取得の判定
        needs_detail = False
        
        if self.force_detail_fetch:
            needs_detail = True
            print("  → 強制詳細取得モード")
        elif not existing_listing:
            needs_detail = True
            print("  → 新規物件のため詳細取得")
        else:
            # 既存物件の場合、価格変更をチェック
            if not self.enable_smart_scraping:
                needs_detail = True
                print("  → スマートスクレイピング無効のため詳細取得")
            else:
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
                    # 価格変更がない場合は、最終取得日をチェック
                    if existing_listing.detail_fetched_at:
                        days_since_fetch = (datetime.now() - existing_listing.detail_fetched_at).days
                        if days_since_fetch >= self.detail_refetch_days:
                            needs_detail = True
                            print(f"  → {days_since_fetch}日経過のため詳細再取得")
                        else:
                            print(f"  → 詳細取得から{days_since_fetch}日経過（スキップ）")
                    else:
                        needs_detail = True
                        print("  → 詳細未取得のため取得")
        
        # 詳細取得
        if needs_detail:
            # 404エラーでスキップすべきかチェック
            if self._should_skip_url_due_to_404(property_data['url']):
                print("  → 404エラー履歴のためスキップ")
                property_data['detail_fetched'] = False
                property_data['detail_fetch_attempted'] = True
                self._scraping_stats['detail_fetch_failed'] += 1
                return False
            
            # 詳細取得前に一時停止チェック
            self._check_pause_flag()
            
            print("  → 詳細ページを取得中...")
            try:
                detail_data = parse_detail_func(property_data['url'])
            except TaskCancelledException:
                # キャンセル例外は再スロー
                raise
            except Exception as e:
                # その他のエラーはNoneとして扱う
                self.logger.error(f"詳細取得中にエラー: {e}")
                detail_data = None
            
            if detail_data:
                # 詳細データをマージ
                property_data.update(detail_data)
                property_data['detail_fetched'] = True
                self._last_detail_fetched = True  # フラグを記録
                print("  → 詳細取得成功")
            else:
                print("  → 詳細取得失敗")
                property_data['detail_fetched'] = False
                self._last_detail_fetched = False  # フラグを記録
                self._scraping_stats['detail_fetch_failed'] += 1
                # 詳細取得失敗も統計カウントのために明示的に設定
                property_data['detail_fetch_attempted'] = True
                
                # エラーログを記録
                if hasattr(self, '_save_error_log'):
                    self._save_error_log({
                        'url': property_data.get('url', '不明'),
                        'reason': '詳細ページの取得に失敗',
                        'building_name': property_data.get('building_name', ''),
                        'price': property_data.get('price', '')
                    })
                
                # 詳細取得に失敗した場合は保存処理をスキップ
                property_data['property_saved'] = False
                return False
        else:
            property_data['detail_fetched'] = False
            self._last_detail_fetched = False  # フラグを記録
        
        # 物件保存前に一時停止チェック
        try:
            self._check_pause_flag()
        except TaskCancelledException:
            # キャンセル時は保存失敗としてカウントしない
            property_data['property_saved'] = None  # 保存失敗でもなく成功でもない
            raise
        
        # 物件を保存（共通の例外処理付き）
        saved = self._save_property_with_error_handling(property_data, existing_listing, save_property_func)
        
        return saved
    
    def _save_property_with_error_handling(
        self, 
        property_data: Dict[str, Any], 
        existing_listing: Optional[PropertyListing],
        save_property_func
    ):
        """物件保存の共通例外処理"""
        try:
            # 保存関数を呼び出し
            if hasattr(save_property_func, '__self__') and save_property_func.__self__ == self:
                # インスタンスメソッドの場合
                saved = save_property_func(property_data, existing_listing)
            else:
                # ラムダや関数の場合
                saved = save_property_func(property_data, existing_listing)
            
            property_data['property_saved'] = saved
            return saved
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            print(f"  → エラー: {e}")
            import traceback
            traceback.print_exc()
            property_data['property_saved'] = False
            return False
    
    def add_property_images(self, listing: PropertyListing, image_urls: List[str]):
        """物件画像を追加"""
        # 既存の画像を削除
        self.session.query(PropertyImage).filter_by(property_listing_id=listing.id).delete()
        
        # 新しい画像を追加
        for i, url in enumerate(image_urls):
            image = PropertyImage(
                property_listing_id=listing.id,
                image_url=url,
                display_order=i
            )
            self.session.add(image)
    
    def validate_property_data(self, property_data: Dict[str, Any]) -> bool:
        """物件データの妥当性をチェック"""
        # 必須フィールドのチェック
        if not property_data.get('building_name'):
            self.logger.warning(f"建物名がありません: URL={property_data.get('url', '不明')}")
            return False
        
        if not property_data.get('price'):
            self.logger.warning(f"価格情報がありません: URL={property_data.get('url', '不明')}, building_name={property_data.get('building_name', '不明')}")
            return False
        
        # 価格の妥当性チェック
        price = property_data.get('price', 0)
        if price < 100 or price > 10000000:  # 100万円未満または100億円超
            self.logger.warning(f"価格が異常です: {price}万円, URL={property_data.get('url', '不明')}")
            return False
        
        # 面積の妥当性チェック
        area = property_data.get('area', 0)
        if area and (area < 10 or area > 500):  # 10㎡未満または500㎡超
            self.logger.warning(f"面積が異常です: {area}㎡")
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
    
    def get_search_key_for_building(self, building_name: str) -> str:
        """建物検索用のキーを生成（最小限の正規化）"""
        # 全角英数字→半角
        key = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
        # スペースと記号の正規化
        key = re.sub(r'[\s　・－―～〜]+', '', key)
        # 大文字統一
        key = key.upper()
        # 末尾の棟表記を除去（検索時のみ）
        key = re.sub(r'(EAST|WEST|NORTH|SOUTH|E|W|N|S|東|西|南|北)?棟$', '', key)
        return key
    
    def find_existing_building_by_key(self, search_key: str, address: str = None) -> Optional[Building]:
        """検索キーで既存の建物を探す"""
        # canonical_nameで直接検索（高速）
        building = self.session.query(Building).filter(
            Building.canonical_name == search_key
        ).first()
        
        if building:
            # アドレスが指定されている場合は、アドレスも確認
            if address and building.address != address:
                # アドレスが異なる場合は、同じcanonical_nameでアドレスが一致する建物を探す
                building_with_address = self.session.query(Building).filter(
                    Building.canonical_name == search_key,
                    Building.address == address
                ).first()
                if building_with_address:
                    return building_with_address
            return building
        
        return None
    
    def get_or_create_building(self, building_name: str, address: str = None, external_property_id: str = None, 
                               built_year: int = None, total_floors: int = None, basement_floors: int = None,
                               total_units: int = None, structure: str = None, land_rights: str = None, 
                               parking_info: str = None) -> Tuple[Optional[Building], Optional[str]]:
        """建物を取得または作成（改善版：元の建物名を保持）"""
        if not building_name:
            return None, None
        
        # 元の建物名を保存
        original_building_name = building_name
        
        # 外部IDがある場合は先に検索
        if external_property_id:
            existing_external = self.session.query(BuildingExternalId).filter(
                BuildingExternalId.source_site == self.source_site,
                BuildingExternalId.external_id == external_property_id
            ).first()
            
            if existing_external:
                # 既存の建物を使用
                building = self.session.query(Building).get(existing_external.building_id)
                if building:
                    print(f"[既存] 外部IDで建物を発見: {building.normalized_name} (ID: {building.id})")
                    # 建物名から部屋番号を抽出
                    _, extracted_room_number = self.normalizer.extract_room_number(building_name)
                    
                    # 建物情報を更新（より詳細な情報があれば）
                    updated = False
                    if address and not building.address:
                        building.address = address
                        updated = True
                    if built_year and not building.built_year:
                        building.built_year = built_year
                        updated = True
                    if total_floors and not building.total_floors:
                        building.total_floors = total_floors
                        updated = True
                    if basement_floors is not None and building.basement_floors is None:
                        building.basement_floors = basement_floors
                        updated = True
                    if updated:
                        self.session.flush()
                    
                    return building, extracted_room_number
                else:
                    # 外部IDは存在するが建物が見つからない（データ不整合）
                    print(f"[WARNING] 外部ID {external_property_id} に紐づく建物ID {existing_external.building_id} が存在しません")
                    # 孤立した外部IDレコードを削除
                    self.session.delete(existing_external)
                    self.session.flush()
                    print(f"[INFO] 孤立した外部IDレコードを削除しました")
        
        # 建物名から部屋番号を抽出（内部処理用）
        clean_building_name, extracted_room_number = self.normalizer.extract_room_number(building_name)
        
        # 比較用の検索キーを生成（最小限の正規化）
        search_key = self.get_search_key_for_building(clean_building_name)
        
        # デバッグログ
        print(f"[DEBUG] 建物検索: 元の名前='{original_building_name}', 検索キー='{search_key}'")
        
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
                return building, extracted_room_number
            else:
                # 新規作成（住所必須）
                print(f"[WARNING] 広告文タイトルで新規建物作成: {building_name} at {address}")
                # 建物名は元の名前を使用（多数決で後で決定される）
                normalized_name = original_building_name
        else:
            # 通常の建物名の場合
            # 既存の建物を検索
            building = self.find_existing_building_by_key(search_key, address)
            
            if building:
                print(f"[INFO] 既存建物を発見: {building.normalized_name} (ID: {building.id})")
                
                # 建物情報を更新（より詳細な情報があれば）
                updated = False
                if built_year and not building.built_year:
                    building.built_year = built_year
                    updated = True
                if total_floors and not building.total_floors:
                    building.total_floors = total_floors
                    updated = True
                if basement_floors is not None and building.basement_floors is None:
                    building.basement_floors = basement_floors
                    updated = True
                if total_units and not building.total_units:
                    building.total_units = total_units
                    updated = True
                if structure and not building.structure:
                    building.structure = structure
                    updated = True
                if land_rights and not building.land_rights:
                    building.land_rights = land_rights
                    updated = True
                if parking_info and not building.parking_info:
                    building.parking_info = parking_info
                    updated = True
                
                if updated:
                    self.session.flush()
                
                # 外部IDを追加（既存の建物でも、外部IDが未登録の場合は追加）
                if external_property_id:
                    existing_external_id = self.session.query(BuildingExternalId).filter(
                        BuildingExternalId.building_id == building.id,
                        BuildingExternalId.source_site == self.source_site,
                        BuildingExternalId.external_id == external_property_id
                    ).first()
                    
                    if not existing_external_id:
                        try:
                            external_id = BuildingExternalId(
                                building_id=building.id,
                                source_site=self.source_site,
                                external_id=external_property_id
                            )
                            self.session.add(external_id)
                            self.session.flush()
                            print(f"[INFO] 既存建物に外部IDを追加: building_id={building.id}, external_id={external_property_id}")
                        except Exception as e:
                            # 外部ID追加時のエラーをキャッチ
                            self.session.rollback()
                            print(f"[WARNING] 外部ID追加エラー: {e}")
                            # 既に別の建物に紐付いている可能性をチェック
                            existing = self.session.query(BuildingExternalId).filter(
                                BuildingExternalId.source_site == self.source_site,
                                BuildingExternalId.external_id == external_property_id
                            ).first()
                            if existing:
                                print(f"[WARNING] 外部ID {external_property_id} は既に建物ID {existing.building_id} に紐付いています")
                
                return building, extracted_room_number
            
            # 新規建物の場合、元の名前を使用
            normalized_name = original_building_name
        
        # 新規建物を作成
        print(f"[INFO] 新規建物を作成: {normalized_name}")
        building = Building(
            normalized_name=normalized_name,  # 元の名前を使用
            canonical_name=search_key,        # 検索キーを保存
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
        
        # 外部IDを追加（ある場合）
        if external_property_id:
            # 既存の外部IDをチェック
            existing_external_id = self.session.query(BuildingExternalId).filter(
                BuildingExternalId.building_id == building.id,
                BuildingExternalId.source_site == self.source_site,
                BuildingExternalId.external_id == external_property_id
            ).first()
            
            if not existing_external_id:
                try:
                    external_id = BuildingExternalId(
                        building_id=building.id,
                        source_site=self.source_site,
                        external_id=external_property_id
                    )
                    self.session.add(external_id)
                    self.session.flush()
                except Exception as e:
                    # 外部ID追加時のエラーをキャッチ
                    self.session.rollback()
                    print(f"[WARNING] 新規建物への外部ID追加エラー: {e}")
                    # 既に別の建物に紐付いている可能性をチェック
                    existing = self.session.query(BuildingExternalId).filter(
                        BuildingExternalId.source_site == self.source_site,
                        BuildingExternalId.external_id == external_property_id
                    ).first()
                    if existing:
                        print(f"[WARNING] 外部ID {external_property_id} は既に建物ID {existing.building_id} に紐付いています")
        
        return building, extracted_room_number
    
    def get_or_create_master_property(self, building: Building, room_number: str = None,
                                    floor_number: int = None, area: float = None,
                                    layout: str = None, direction: str = None,
                                    balcony_area: float = None, url: str = None) -> MasterProperty:
        """マスター物件を取得または作成"""
        # プロパティハッシュを計算
        property_hash = self.property_hasher.calculate_hash(
            building_id=building.id,
            floor_number=floor_number,
            area=area,
            layout=layout,
            direction=direction
        )
        
        # 既存のマスター物件を検索
        master_property = self.session.query(MasterProperty).filter(
            MasterProperty.property_hash == property_hash
        ).first()
        
        if master_property:
            # 既存物件の情報を更新（より詳細な情報があれば）
            updated = False
            if room_number and not master_property.room_number:
                master_property.room_number = room_number
                updated = True
            if floor_number and not master_property.floor_number:
                master_property.floor_number = floor_number
                updated = True
            if area and not master_property.area:
                master_property.area = area
                updated = True
            if layout and not master_property.layout:
                master_property.layout = layout
                updated = True
            if direction and not master_property.direction:
                master_property.direction = direction
                updated = True
            if balcony_area and not master_property.balcony_area:
                master_property.balcony_area = balcony_area
                updated = True
            
            if updated:
                self.session.flush()
            
            return master_property
        
        # 新規作成
        master_property = MasterProperty(
            building_id=building.id,
            room_number=room_number,
            floor_number=floor_number,
            area=area,
            layout=layout,
            direction=direction,
            balcony_area=balcony_area,
            property_hash=property_hash
        )
        self.session.add(master_property)
        self.session.flush()
        
        return master_property
    
    def create_or_update_listing(self, master_property: MasterProperty, url: str, title: str,
                               price: int, agency_name: str = None, site_property_id: str = None,
                               description: str = None, station_info: str = None, features: str = None,
                               management_fee: int = None, repair_fund: int = None,
                               published_at: datetime = None, first_published_at: datetime = None,
                               **kwargs) -> tuple[PropertyListing, str]:
        """掲載情報を作成または更新"""
        # 既存の掲載を検索（master_property_idでも絞り込む）
        listing = self.session.query(PropertyListing).filter(
            PropertyListing.master_property_id == master_property.id,
            PropertyListing.url == url,
            PropertyListing.source_site == self.source_site
        ).first()
        
        # 同じURLで別の物件が存在する場合の処理
        if not listing:
            existing_with_same_url = self.session.query(PropertyListing).filter(
                PropertyListing.url == url,
                PropertyListing.source_site == self.source_site
            ).first()
            
            if existing_with_same_url:
                # 同じURLで別の物件が存在する場合
                if existing_with_same_url.master_property_id != master_property.id:
                    # 別の物件の場合、古い方を非アクティブにする
                    print(f"  → 同じURLで別の物件が存在 (旧物件ID: {existing_with_same_url.master_property_id})")
                    existing_with_same_url.is_active = False
                    existing_with_same_url.delisted_at = datetime.now()
                    self.session.flush()
                else:
                    # 同じ物件の場合は、既存のレコードを使用
                    listing = existing_with_same_url
                    print(f"  → 同じ物件の既存レコード発見 (ID: {listing.id})")
        
        update_type = 'new'  # デフォルトは新規
        
        if listing:
            # 更新タイプを判定
            price_changed = False
            other_changed = False
            old_price = listing.current_price  # 更新前の価格を保存（ログ用）
            
            # 価格が変更されている場合は履歴を記録
            if listing.current_price != price:
                price_changed = True
                price_history = ListingPriceHistory(
                    property_listing_id=listing.id,
                    price=price,
                    recorded_at=datetime.now()
                )
                self.session.add(price_history)
                
                # 現在価格を更新
                listing.current_price = price
                listing.price_updated_at = datetime.now()
            
            # その他の情報を更新（変更を追跡）
            if listing.title != title:
                other_changed = True
            listing.title = title
            
            if agency_name and listing.agency_name != agency_name:
                other_changed = True
            listing.agency_name = agency_name or listing.agency_name
            
            if site_property_id and listing.site_property_id != site_property_id:
                other_changed = True
            listing.site_property_id = site_property_id or listing.site_property_id
            
            if description and listing.description != description:
                other_changed = True
            listing.description = description or listing.description
            
            if station_info and listing.station_info != station_info:
                other_changed = True
            listing.station_info = station_info or listing.station_info
            
            if features and listing.features != features:
                other_changed = True
            listing.features = features or listing.features
            
            if management_fee is not None and listing.management_fee != management_fee:
                other_changed = True
            listing.management_fee = management_fee if management_fee is not None else listing.management_fee
            
            if repair_fund is not None and listing.repair_fund != repair_fund:
                other_changed = True
            listing.repair_fund = repair_fund if repair_fund is not None else listing.repair_fund
            
            listing.is_active = True
            listing.last_confirmed_at = datetime.now()
            listing.detail_fetched_at = datetime.now()  # 詳細取得時刻を更新
            
            # 更新タイプを判定
            if price_changed:
                update_type = 'price_updated'
                print(f"  → 既存物件を価格更新: {old_price}万円 → {price}万円")
            elif other_changed:
                update_type = 'other_updates'
                print(f"  → 既存物件を更新（価格以外の変更）")
            else:
                update_type = 'refetched_unchanged'
                print(f"  → 既存物件を確認（変更なし）")
            
            # published_atの更新（より新しい日付があれば）
            if published_at and (not listing.published_at or published_at > listing.published_at):
                listing.published_at = published_at
            
            # 追加の属性を更新
            for key, value in kwargs.items():
                if hasattr(listing, key) and value is not None:
                    setattr(listing, key, value)
        else:
            # 新規作成
            try:
                listing = PropertyListing(
                    master_property_id=master_property.id,
                    source_site=self.source_site,
                    url=url,
                    title=title,
                    current_price=price,
                    agency_name=agency_name,
                    site_property_id=site_property_id,
                    description=description,
                    station_info=station_info,
                    features=features,
                    management_fee=management_fee,
                    repair_fund=repair_fund,
                    is_active=True,
                    published_at=published_at,
                    first_published_at=first_published_at or published_at or datetime.now(),
                    price_updated_at=datetime.now(),
                    last_confirmed_at=datetime.now(),
                    detail_fetched_at=datetime.now(),  # 詳細取得時刻を設定
                    **kwargs
                )
                self.session.add(listing)
                self.session.flush()
            except Exception as e:
                # URL重複エラーの場合は、再度検索して既存レコードを使用
                if "property_listings_url_key" in str(e):
                    self.session.rollback()
                    print(f"  → URL重複エラー検出。既存レコードを再検索...")
                    
                    # 再度検索（他のプロセスが同時に作成した可能性）
                    listing = self.session.query(PropertyListing).filter(
                        PropertyListing.url == url,
                        PropertyListing.source_site == self.source_site
                    ).first()
                    
                    if listing:
                        print(f"  → 既存レコード発見 (ID: {listing.id}, 物件ID: {listing.master_property_id})")
                        if listing.master_property_id != master_property.id:
                            # 別の物件の場合は、古い方を非アクティブにする
                            print(f"  → 別の物件のため、古い方を非アクティブ化")
                            listing.is_active = False
                            listing.delisted_at = datetime.now()
                            self.session.flush()
                            
                            # 新しいレコードを作成（再試行）
                            listing = PropertyListing(
                                master_property_id=master_property.id,
                                source_site=self.source_site,
                                url=url,
                                title=title,
                                current_price=price,
                                agency_name=agency_name,
                                site_property_id=site_property_id,
                                description=description,
                                station_info=station_info,
                                features=features,
                                management_fee=management_fee,
                                repair_fund=repair_fund,
                                is_active=True,
                                published_at=published_at,
                                first_published_at=first_published_at or published_at or datetime.now(),
                                price_updated_at=datetime.now(),
                                last_confirmed_at=datetime.now(),
                                detail_fetched_at=datetime.now(),
                                **kwargs
                            )
                            self.session.add(listing)
                            self.session.flush()
                        else:
                            # 同じ物件の場合は、既存のレコードを更新
                            update_type = 'existing'
                            print(f"  → 同じ物件の既存レコードを更新")
                    else:
                        # それでも見つからない場合はエラーを再発生
                        raise
                else:
                    # その他のエラーは再発生
                    raise
            
            # 初回価格履歴を記録
            price_history = ListingPriceHistory(
                property_listing_id=listing.id,
                price=price,
                recorded_at=datetime.now()
            )
            self.session.add(price_history)
            
            # 新規作成の場合、update_typeを'new'に設定
            update_type = 'new'
            print(f"  → 新規物件として登録")
        
        # 掲載情報の登録・更新後、建物名と物件情報を多数決で更新
        if master_property:
            try:
                # 物件情報を多数決で更新
                self.majority_updater.update_master_property_by_majority(master_property)
                self.session.flush()  # 変更を確定
            except Exception as e:
                # エラーが発生しても処理は続行（ログに記録）
                self.logger.warning(f"物件情報の更新に失敗しました (property_id={master_property.id}): {e}")
                
            # 建物名と建物情報を多数決で更新
            if master_property.building_id:
                try:
                    # 建物情報を多数決で更新
                    building = self.session.query(Building).get(master_property.building_id)
                    if building:
                        self.majority_updater.update_building_by_majority(building)
                    
                    # 建物名を多数決で更新
                    self.majority_updater.update_building_name_by_majority(master_property.building_id)
                    self.session.flush()  # 変更を確定
                except Exception as e:
                    # エラーが発生しても処理は続行（ログに記録）
                    self.logger.warning(f"建物情報の更新に失敗しました (building_id={master_property.building_id}): {e}")
                
                # 物件の表示用建物名を多数決で更新
                try:
                    self.majority_updater.update_property_building_name_by_majority(master_property.id)
                    self.session.flush()  # 変更を確定
                except Exception as e:
                    # エラーが発生しても処理は続行（ログに記録）
                    self.logger.warning(f"物件建物名の更新に失敗しました (property_id={master_property.id}): {e}")
        
        return listing, update_type
    
    def update_master_property_by_majority(self, master_property: MasterProperty):
        """マスター物件の情報を多数決で更新"""
        self.majority_updater.update_master_property_by_majority(master_property)
    
    def get_scraping_stats(self) -> Dict[str, int]:
        """スクレイピング統計を取得"""
        return self._scraping_stats.copy()
    
    def get_resume_state(self) -> Dict[str, Any]:
        """再開用の状態を取得"""
        return {
            'phase': self._scraping_stats.get('phase', 'collecting'),
            'current_page': self._current_page,
            'collected_properties': self._collected_properties,
            'processed_count': self._processed_count,
            'stats': self._scraping_stats.copy()
        }
    
    def set_resume_state(self, state: Dict[str, Any]):
        """再開用の状態を設定"""
        print(f"[DEBUG-SET-RESUME-CALLED] Called with state: {state is not None}")
        if state:
            print(f"[DEBUG-SET-RESUME-STATE] phase={state.get('phase')}, current_page={state.get('current_page')}, collected_count={len(state.get('collected_properties', []))}, processed_count={state.get('processed_count')}")
            self._scraping_stats['phase'] = state.get('phase', 'collecting')
            self._current_page = state.get('current_page', 1)
            self._collected_properties = state.get('collected_properties', [])
            self._processed_count = state.get('processed_count', 0)
            if 'stats' in state:
                self._scraping_stats.update(state['stats'])
            self.logger.info(f"再開状態を設定: phase={self._scraping_stats['phase']}, page={self._current_page}, collected={len(self._collected_properties)}, processed={self._processed_count}")
            print(f"[DEBUG-SET-RESUME-AFTER] phase={self._scraping_stats['phase']}, page={self._current_page}, collected={len(self._collected_properties)}, processed={self._processed_count}")
    
    
    def validate_html_structure(self, soup, required_selectors: dict) -> bool:
        """HTML構造の検証"""
        for name, selector in required_selectors.items():
            if not soup.select_one(selector):
                self.logger.warning(f"必須要素が見つかりません: {name} ({selector})")
                return False
        return True
    
    def _handle_404_error(self, url: str):
        """404エラーのURLを記録"""
        try:
            # 既存のレコードを確認
            retry_record = self.session.query(Url404Retry).filter(
                Url404Retry.url == url,
                Url404Retry.source_site == self.source_site.value
            ).first()
            
            if retry_record:
                # エラー回数を増加
                retry_record.error_count += 1
                retry_record.last_error_at = datetime.now()
                
                # 再試行間隔を計算（エラー回数に基づく）
                retry_hours = self._calculate_retry_interval(retry_record.error_count)
                
                self.logger.info(
                    f"404エラー再発生 (回数: {retry_record.error_count}, "
                    f"次回再試行までの最小間隔: {retry_hours}時間)"
                )
            else:
                # 新規レコードを作成
                retry_record = Url404Retry(
                    url=url,
                    source_site=self.source_site.value,
                    error_count=1
                )
                self.session.add(retry_record)
                self.logger.info("404エラーを記録 (初回、次回再試行は2時間後以降)")
            
            self.session.commit()
            
        except Exception as e:
            self.logger.error(f"404エラー記録中にエラー: {e}")
            self.session.rollback()
    
    def _calculate_retry_interval(self, error_count: int) -> int:
        """エラー回数に基づいて再試行間隔（時間）を計算"""
        # 1回目: 2時間、2回目: 4時間、3回目: 8時間... 最大1024時間
        return min(2 ** error_count, 1024)
    
    def _should_skip_url_due_to_404(self, url: str) -> bool:
        """URLが404エラーで再試行待機中かチェック"""
        try:
            retry_record = self.session.query(Url404Retry).filter(
                Url404Retry.url == url,
                Url404Retry.source_site == self.source_site.value
            ).first()
            
            if retry_record:
                # 最後のエラーからの経過時間を計算
                hours_since_error = (datetime.now() - retry_record.last_error_at).total_seconds() / 3600
                required_interval = self._calculate_retry_interval(retry_record.error_count)
                
                if hours_since_error < required_interval:
                    hours_until_retry = required_interval - hours_since_error
                    self.logger.info(
                        f"404エラーのためスキップ (エラー回数: {retry_record.error_count}, "
                        f"再試行まで: {hours_until_retry:.1f}時間)"
                    )
                    return True
                else:
                    self.logger.info(
                        f"404エラー再試行可能 (エラー回数: {retry_record.error_count}, "
                        f"最後のエラーから: {hours_since_error:.1f}時間経過)"
                    )
            
            return False
            
        except Exception as e:
            self.logger.error(f"404エラーチェック中にエラー: {e}")
            return False

    def save_property_common(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存する共通メソッド"""
        try:
            # 詳細取得をスキップした場合の処理
            if not property_data.get('detail_fetched', False) and existing_listing:
                # 既存物件の最終確認日時のみ更新
                existing_listing.last_scraped_at = datetime.now()
                existing_listing.last_confirmed_at = datetime.now()
                self.session.commit()
                print(f"  → 既存物件の最終確認日時を更新 (ID: {existing_listing.id})")
                # update_typeを設定（詳細をスキップした場合は変更なし）
                property_data['update_type'] = 'skipped'  # 'refetched_unchanged'ではなく'skipped'を使用
                property_data['property_saved'] = True
                return True
            
            # データの妥当性チェック
            if not self.validate_property_data(property_data):
                # 失敗理由の特定とログ記録
                url = property_data.get('url', '不明')
                failure_reason = ""
                
                if not property_data.get('price'):
                    self._scraping_stats['price_missing'] += 1
                    failure_reason = "価格情報なし"
                elif not property_data.get('building_name'):
                    self._scraping_stats['building_info_missing'] += 1
                    failure_reason = "建物名なし"
                else:
                    self._scraping_stats['other_errors'] += 1
                    failure_reason = "その他の必須情報不足"
                
                # エラーログを記録
                self.logger.error(f"物件保存失敗 - {failure_reason}: URL={url}")
                print(f"  → 保存失敗: {failure_reason} (URL: {url})")
                
                # 管理画面用のエラーログを記録
                if hasattr(self, '_save_error_log'):
                    self._save_error_log({
                        'url': url,
                        'reason': failure_reason,
                        'building_name': property_data.get('building_name', ''),
                        'price': property_data.get('price', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                
                # 保存失敗フラグを設定
                property_data['property_saved'] = False
                # save_failedもカウント（フロントエンドで必要）
                # ただし、これは追加情報として扱い、メインの統計には含めない
                if property_data.get('detail_fetched', False):
                    # 詳細取得済みの保存失敗のみカウント
                    self._scraping_stats['save_failed'] = self._scraping_stats.get('save_failed', 0) + 1
                return False
            
            # 建物を取得または作成
            building, extracted_room_number = self.get_or_create_building(
                building_name=property_data.get('building_name'),
                address=property_data.get('address'),
                external_property_id=property_data.get('site_property_id'),
                built_year=property_data.get('built_year'),
                total_floors=property_data.get('total_floors'),
                basement_floors=property_data.get('basement_floors'),
                total_units=property_data.get('total_units'),
                structure=property_data.get('structure'),
                land_rights=property_data.get('land_rights'),
                parking_info=property_data.get('parking_info')
            )
            
            if not building:
                self.logger.warning("建物の作成に失敗しました")
                # エラーログを記録
                if hasattr(self, '_save_error_log'):
                    self._save_error_log({
                        'url': property_data.get('url', '不明'),
                        'reason': '建物の作成に失敗',
                        'building_name': property_data.get('building_name', ''),
                        'price': property_data.get('price', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                property_data['property_saved'] = False
                # save_failedは上位の処理でカウントされるため、ここではカウントしない
                return False
            
            # 部屋番号の処理
            room_number = property_data.get('room_number', extracted_room_number)
            
            # マスター物件を取得または作成
            master_property = self.get_or_create_master_property(
                building=building,
                room_number=room_number,
                floor_number=property_data.get('floor_number'),
                area=property_data.get('area'),
                layout=property_data.get('layout'),
                direction=property_data.get('direction'),
                balcony_area=property_data.get('balcony_area'),
                url=property_data.get('url')
            )
            
            # summary_remarksをMasterPropertyに保存
            if property_data.get('summary_remarks') and not master_property.summary_remarks:
                master_property.summary_remarks = property_data.get('summary_remarks')
                self.session.flush()
            
            # 掲載情報を作成または更新
            listing, update_type = self.create_or_update_listing(
                master_property=master_property,
                url=property_data.get('url'),
                title=property_data.get('title', property_data.get('building_name', '')),
                price=property_data.get('price'),
                agency_name=property_data.get('agency_name'),
                site_property_id=property_data.get('site_property_id'),
                description=property_data.get('description'),
                station_info=property_data.get('station_info'),
                features=property_data.get('features'),
                management_fee=property_data.get('management_fee'),
                repair_fund=property_data.get('repair_fund'),
                published_at=property_data.get('published_at'),
                first_published_at=property_data.get('first_published_at'),
                remarks=property_data.get('remarks'),
                # summary_remarksはMasterPropertyのフィールドなので、PropertyListingには渡さない
                agency_tel=property_data.get('agency_tel')
            )
            
            # 更新タイプをproperty_dataに設定（外部で使用するため）
            property_data['update_type'] = update_type
            
            # 保存成功フラグを設定
            property_data['property_saved'] = True
            
            # 画像を追加
            if property_data.get('images'):
                self.add_property_images(listing, property_data['images'])
            
            # 定期的にコミット
            if hasattr(self, '_property_count') and self._property_count % 10 == 0:
                self.session.commit()
            
            return True
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            # トランザクションエラーの場合はロールバック
            if self.session:
                self.session.rollback()
            
            self.logger.error(f"物件保存エラー: {e}")
            import traceback
            traceback.print_exc()
            
            # エラーログを記録
            url = property_data.get('url', '不明')
            building_name = property_data.get('building_name', '')
            price = property_data.get('price', '')
            
            self.logger.error(f"物件保存失敗 - システムエラー: URL={url}, 建物名={building_name}, 価格={price}")
            print(f"  → 保存失敗: システムエラー - {str(e)[:100]} (URL: {url})")
            
            # 管理画面用のエラーログを記録
            if hasattr(self, '_save_error_log'):
                self._save_error_log({
                    'url': url,
                    'reason': f'システムエラー: {str(e)[:200]}',
                    'building_name': building_name,
                    'price': str(price) if price else '',
                    'timestamp': datetime.now().isoformat()
                })
            
            # 保存失敗フラグを設定
            property_data['property_saved'] = False
            return False
    
    def __del__(self):
        """デストラクタ"""
        if hasattr(self, 'session'):
            self.session.close()
        if hasattr(self, 'http_session'):
            self.http_session.close()


def is_advertising_text(text: str) -> bool:
    """広告的なテキストかどうかを判定"""
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
    ]
    
    # いずれかのパターンにマッチしたら広告文と判定
    for pattern in ad_patterns:
        if re.search(pattern, text):
            return True
    
    # 建物名として短すぎる場合も広告文と判定
    if len(text) < 3:
        return True
    
    return False