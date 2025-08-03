import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
import os
import json
from abc import ABC, abstractmethod
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text, Table, MetaData
import jaconv

from .constants import SourceSite
from ..config.scraping_config import PAUSE_TIMEOUT_SECONDS
from ..database import SessionLocal
from ..models import (
    Building, MasterProperty, PropertyListing, 
    ListingPriceHistory, PropertyImage, BuildingExternalId, Url404Retry
)
from ..utils.building_normalizer import BuildingNameNormalizer
from ..utils.property_hasher import PropertyHasher
from ..utils.majority_vote_updater import MajorityVoteUpdater
from ..utils.exceptions import TaskPausedException, TaskCancelledException, MaintenanceException
import time as time_module
from ..utils.debug_logger import debug_log


class BaseScraper(ABC):
    """スクレイパーの基底クラス"""
    
    # 定数の定義
    DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    DEFAULT_SCRAPER_DELAY = 1.0  # 秒
    DEFAULT_DETAIL_REFETCH_DAYS = 90
    DEFAULT_SMART_SCRAPING = True
    
    # エラー閾値
    DEFAULT_CRITICAL_ERROR_RATE = 0.5  # 50%
    DEFAULT_CRITICAL_ERROR_COUNT = 10
    DEFAULT_CONSECUTIVE_ERRORS = 5
    
    # ページング設定
    MAX_PAGES = 200  # 最大ページ数
    MAX_CONSECUTIVE_EMPTY_PAGES = 2  # 連続して空のページの最大数
    
    # タイムアウト設定
    PAUSE_CHECK_INTERVAL = 0.1  # 秒
    PAUSE_LOG_INTERVAL = 50  # 5秒ごとにログ（50 * 0.1秒）
    
    # エラーキャッシュ設定
    ERROR_CACHE_HOURS = 12  # エラーキャッシュの有効期間（時間）
    
    # HTML要素の欠落検出設定
    MISSING_ELEMENT_THRESHOLD = 3  # 要素が連続して欠落した場合の閾値
    CRITICAL_MISSING_THRESHOLD = 5  # 致命的な要素の欠落閾値
    
    # 疑わしい更新の検出設定
    SUSPICIOUS_UPDATE_THRESHOLD = 5  # 疑わしい更新の連続数閾値
    AREA_CHANGE_THRESHOLD = 0.7  # 面積変更の閾値（70%）
    PRICE_CHANGE_THRESHOLD = 0.7  # 価格変更の閾値（70%）
    
    def __init__(self, source_site: Union[str, SourceSite], force_detail_fetch: bool = False, max_properties: Optional[int] = None, ignore_error_history: bool = False):
        # 文字列の場合はSourceSiteに変換（後方互換性）
        if isinstance(source_site, str):
            self.source_site = SourceSite.from_string(source_site)
        else:
            self.source_site = source_site
        self.force_detail_fetch = force_detail_fetch
        self.max_properties = max_properties
        self.ignore_error_history = ignore_error_history
        self.session = SessionLocal()
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': self.DEFAULT_USER_AGENT
        })
        # SSL証明書検証の設定（gt-www.livable.co.jpのSSL証明書問題対応）
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.logger = self._setup_logger()
        self.normalizer = BuildingNameNormalizer()
        self.property_hasher = PropertyHasher()
        self.majority_updater = MajorityVoteUpdater(self.session)
        
        # スマートスクレイピング設定
        self.detail_refetch_days = self._get_detail_refetch_days()
        self.enable_smart_scraping = self._get_smart_scraping_enabled()
        
        # 進捗更新コールバック
        self._progress_callback = None
        
        # プロパティカウンター（制限用）
        self._property_count = 0
        
        # スクレイピング遅延（秒）
        self.delay = float(os.getenv('SCRAPER_DELAY', str(self.DEFAULT_SCRAPER_DELAY)))
        
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
            'other_errors': 0,
            # 建物名取得の統計（HTML構造変更の検知用）
            'building_name_from_table': 0,  # テーブルから正常に取得
            'building_name_missing': 0,  # 建物名が取得できなかった（エラー）
            'building_name_missing_new': 0,  # 建物名取得エラー（初回検出）
            'building_name_error_skipped': 0,  # 建物名エラーでスキップした件数
            # HTML構造変更の総合統計
            'html_structure_errors': {},  # {field_name: count} 形式で各フィールドのエラー数を記録
            'html_structure_errors_new': {},  # 新規エラーのみ
            'missing_elements': {},  # {element_description: count} 重要なHTML要素の欠落をカウント
        }
        
        # 一時停止・再開用の状態変数
        self._collected_properties = []
        self._current_page = 1
        self._processed_count = 0
        
        # 汎用的な項目別エラーキャッシュ（全スクレイパー共通）
        self._field_error_cache = {}  # {field_name: {url: timestamp}}
        
        # エラー閾値設定（安全装置）
        self._error_thresholds = {
            'critical_error_rate': float(os.getenv('SCRAPER_CRITICAL_ERROR_RATE', str(self.DEFAULT_CRITICAL_ERROR_RATE))),
            'critical_error_count': int(os.getenv('SCRAPER_CRITICAL_ERROR_COUNT', str(self.DEFAULT_CRITICAL_ERROR_COUNT))),
            'consecutive_errors': int(os.getenv('SCRAPER_CONSECUTIVE_ERRORS', str(self.DEFAULT_CONSECUTIVE_ERRORS)))
        }
        self._consecutive_error_count = 0  # 連続エラーカウンター
        
        # セレクタ検証統計
        self._selector_stats = {}  # {selector: {'success': 0, 'fail': 0}}
        self._page_structure_errors = 0  # ページ構造エラーカウント
    
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
        common_days = os.getenv('SCRAPER_DETAIL_REFETCH_DAYS', str(self.DEFAULT_DETAIL_REFETCH_DAYS))
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
        # 前回のエラー情報をクリア
        self._last_fetch_error = None
        
        try:
            time.sleep(2)  # レート制限対策
            
            # gt-www.livable.co.jpドメインの場合はSSL検証を無効化
            verify_ssl = True
            if 'gt-www.livable.co.jp' in url:
                verify_ssl = False
                self.logger.info(f"SSL検証を無効化: {url}")
            
            response = self.http_session.get(url, timeout=30, allow_redirects=True, verify=verify_ssl)
            
            # リダイレクトが発生した場合のログ
            if response.history:
                final_url = response.url
                if url != final_url:
                    self.logger.info(f"リダイレクト検出: {url} -> {final_url}")
            
            response.raise_for_status()
            
            # レスポンスを解析
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # メンテナンスページの検出
            if self._is_maintenance_page(soup):
                raise MaintenanceException(f"{self.source_site}は現在メンテナンス中です")
            
            return soup
        except (TaskPausedException, TaskCancelledException, MaintenanceException):
            # タスクの一時停止・キャンセル・メンテナンス例外は再スロー
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # 404エラーの場合は特別処理
                self.logger.warning(f"404 Not Found: {url}")
                self._handle_404_error(url)
                # 404エラー情報を保存（詳細取得で使用）
                self._last_fetch_error = {
                    'type': '404',
                    'status_code': 404,
                    'url': url
                }
            elif e.response.status_code == 503:
                # 503 Service Unavailableの場合はメンテナンスと判定
                self.logger.error(f"503 Service Unavailable: {url}")
                raise MaintenanceException(f"{self.source_site}は現在サービス中断中です (503)")
            else:
                self.logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
                # その他のHTTPエラー情報を保存
                self._last_fetch_error = {
                    'type': 'http_error',
                    'status_code': e.response.status_code,
                    'url': url
                }
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"接続エラー - サーバーに接続できません: {url} - {type(e).__name__}: {str(e)}")
            return None
        except requests.exceptions.Timeout as e:
            self.logger.error(f"タイムアウトエラー - サーバーが応答しません: {url} - {type(e).__name__}: {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"リクエストエラー: {url} - {type(e).__name__}: {str(e)}")
            return None
        except Exception as e:
            import traceback
            self.logger.error(f"予期しないエラーが発生しました: {url} - {type(e).__name__}: {str(e)}")
            self.logger.debug(f"詳細なスタックトレース:\n{traceback.format_exc()}")
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
        self.current_area_code = area_code  # 現在スクレイピング中のエリアを記録
        
        # デバッグ：フラグの状態を確認
        self._debug_pause_flag_state()
        
        total_properties = 0
        detail_fetched = 0
        skipped = 0
        errors = 0
        
        # 再開時の状態チェック
        all_properties, page, skip_collection = self._check_resume_state()
        
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
                
                # タスクの存在とキャンセルチェック
                if self._is_cancelled():
                    self.logger.info("タスクがキャンセルされました（収集フェーズ）")
                    raise TaskCancelledException("Task cancelled during collecting phase")
                
                # 一時停止チェック
                self._handle_pause_if_needed(all_properties, page, "収集フェーズ")
                
                # 終了条件チェック
                if self._should_stop_collection(all_properties, page):
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
                    
                    # 物件の収集と重複チェック
                    current_page_urls, new_properties, duplicate_count = self._process_page_properties(
                        properties, seen_urls
                    )
                    
                    # ページの重複チェック
                    if self._check_duplicate_pages(current_page_urls, previous_page_urls, page, duplicate_page_count):
                        break
                    duplicate_page_count = 0 if current_page_urls != previous_page_urls else duplicate_page_count + 1
                    previous_page_urls = current_page_urls
                    
                    # 新規物件の処理
                    should_break = self._handle_new_properties(
                        new_properties, all_properties, duplicate_count, page, consecutive_empty_pages
                    )
                    if should_break:
                        break
                    
                    # リアルタイムで統計を更新
                    self._scraping_stats['properties_found'] = len(all_properties)
                    self.logger.info(f"現在の物件発見数: {len(all_properties)} 件")
                    
                    # 一覧ページ取得ごとに進捗を更新
                    self._update_progress()
                    
                    page += 1
                    self.logger.info(f"[DEBUG] ループ終了、次のページ: {page}")
                    debug_log(f"[{self.source_site}] ループ終了、次のページ: {page}")
                    
                except (TaskPausedException, TaskCancelledException):
                    # タスクの一時停止・キャンセル例外は再スロー
                    raise
                except MaintenanceException as e:
                    # メンテナンス例外の場合は即座に終了
                    self.logger.error(f"メンテナンスを検出: {e}")
                    # エラーログを記録
                    if hasattr(self, '_save_error_log'):
                        self._save_error_log({
                            'url': url,
                            'reason': str(e),
                            'timestamp': datetime.now().isoformat()
                        })
                    # サーキットブレーカーとして即座にスクレイピングを中断
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
        self._handle_pause_if_needed(all_properties, page, "フェーズ間")
        
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
            
            # 処理範囲の確認
            if self.max_properties and i >= self.max_properties:
                self.logger.info(f"処理上限 {self.max_properties} に達したため終了")
                break
            
            # ループの開始をログ出力
            if i % 10 == 0:  # 10件ごとにログ
                self.logger.info(f"[DEBUG] 処理中: {i}/{len(all_properties)}件目")
                debug_log(f"[{self.source_site}] 処理中: {i}/{len(all_properties)}件目")
            
            # 一時停止チェック
            self._handle_processing_pause_if_needed(all_properties, i)
            
            # 最大物件数に達した場合は終了
            if self.max_properties and self._property_count >= self.max_properties:
                self.logger.info(f"最大物件数 {self.max_properties} に達したため処理を終了")
                break
                
            # キャンセルチェック（各物件処理前）
            if self._is_cancelled():
                self.logger.info("タスクがキャンセルされました（処理フェーズ）")
                raise TaskCancelledException("Task cancelled during processing phase")
            
            # 進捗表示（都度表示）
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
                    total_properties += 1  # 処理件数としてカウント
                    skipped += 1  # スキップとしてカウント
                    self._scraping_stats['detail_skipped'] += 1  # スキップとしてカウント
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
                    
                    # HTML構造エラーの既知物件をスキップ（全スクレイパー共通）
                    if self.has_critical_field_errors(property_data['url']):
                        print(f"  → HTML構造エラー（既知）のためスキップ")
                        self.logger.debug(f"HTML構造エラー（既知）のためスキップ: {property_data['url']}")
                        
                        # スキップ処理（詳細取得なし）
                        property_data['detail_fetched'] = False
                        property_data['detail_fetch_attempted'] = False
                        property_data['skip_reason'] = 'html_structure_error'
                        
                        # 統計を更新
                        self._scraping_stats['building_name_error_skipped'] += 1  # 互換性のため残す
                        if 'html_structure_error_skipped' not in self._scraping_stats:
                            self._scraping_stats['html_structure_error_skipped'] = 0
                        self._scraping_stats['html_structure_error_skipped'] += 1
                        
                        # 既存物件の場合は最終確認日時を更新
                        if existing_listing:
                            try:
                                existing_listing.last_confirmed_at = datetime.now()
                                self.session.flush()
                            except Exception as e:
                                self.logger.warning(f"最終確認日時の更新に失敗: {e}")
                        
                        processed = True
                    else:
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
                    
                    # 各物件処理後に進捗を更新（リアルタイム更新）
                    self._update_progress()
                    
                    # 重要フィールドのエラー率をチェック（安全装置）
                    if self.check_critical_error_threshold():
                        error_msg = "重要フィールドのエラー率が閾値を超えました。スクレイピングを中止します。"
                        self.logger.critical(error_msg)
                        raise Exception(error_msg)
                    
                    # 保存結果と更新タイプに基づく統計更新（詳細取得の有無に関わらず）
                    if property_data.get('property_saved', False) and 'update_type' in property_data:
                        update_type = property_data['update_type']
                        self.logger.info(f"統計更新: URL={property_data.get('url', '不明')}, update_type={update_type}, force_detail_fetch={self.force_detail_fetch}")
                        
                        # 詳細取得の有無に関わらず統計を更新
                        if update_type == 'new':
                            self._scraping_stats['new_listings'] += 1
                        elif update_type == 'price_changed' or update_type == 'price_updated':
                            self._scraping_stats['price_updated'] += 1
                        elif update_type == 'refetched_unchanged':
                            self._scraping_stats['refetched_unchanged'] += 1
                            self.logger.info(f"再取得（変更なし）カウント: refetched_unchanged={self._scraping_stats['refetched_unchanged']}")
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
                            # 詳細を取得したが保存に失敗した場合
                            # save_failedは既にvalidate_property_dataまたはsave_property_commonでカウント済みなので、ここではカウントしない
                            self.logger.info(f"物件保存失敗（詳細取得済み）: URL={property_data.get('url', '不明')}, この時点でdetail_fetched={detail_fetched}, 統計={self._scraping_stats['detail_fetched']}")
                        else:
                            # 詳細を取得していない場合（スキップした場合）は統計カウント外
                            self.logger.info(f"物件保存失敗（詳細未取得）: URL={property_data.get('url', '不明')}")
                    elif property_data.get('property_saved') is None:
                        # キャンセルされた場合（統計に含めない）
                        self.logger.info(f"物件処理がキャンセルされました: URL={property_data.get('url', '不明')}")
                    else:
                        # property_savedフラグが設定されていない、またはupdate_typeが設定されていない場合
                        self.logger.warning(f"統計更新されず: URL={property_data.get('url', '不明')}, "
                                          f"property_saved={property_data.get('property_saved')}, "
                                          f"update_type={property_data.get('update_type', 'なし')}, "
                                          f"detail_fetched={property_data.get('detail_fetched', False)}")
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
                    total_errors = self._scraping_stats.get('detail_fetch_failed', 0) + self._scraping_stats.get('save_failed', 0) + self._scraping_stats.get('other_errors', 0)
                    total_counted = detail_fetched + skipped + self._scraping_stats.get('detail_fetch_failed', 0)
                    self.logger.info(f"[DEBUG] 最後の物件({i})の処理完了。統計: detail_fetched={detail_fetched}, detail_skipped={skipped}, detail_fetch_failed={self._scraping_stats.get('detail_fetch_failed', 0)}, save_failed={self._scraping_stats.get('save_failed', 0)}, other_errors={self._scraping_stats.get('other_errors', 0)}, 合計={total_counted} (期待値={total_properties})")
            
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
                total_properties += 1  # 処理件数としてカウント
                self._scraping_stats['detail_fetch_failed'] += 1  # 詳細取得失敗としてカウント
                
                # エラーログを記録
                if hasattr(self, '_save_error_log'):
                    self._save_error_log({
                        'url': property_data.get('url', '不明'),
                        'reason': f'物件処理エラー ({error_type_name}): {str(e)[:200]}',
                        'building_name': property_data.get('building_name', ''),
                        'price': str(property_data.get('price', '')),
                        'timestamp': datetime.now().isoformat()
                    })
                
                # トランザクションエラーの場合はロールバック
                if "current transaction is aborted" in str(e) or "InFailedSqlTransaction" in str(e):
                    try:
                        self.session.rollback()
                        self.logger.info("トランザクションをロールバックしました")
                    except:
                        pass
                continue
            
            # 定期的にコミット（トランザクションがアクティブな場合のみ）
            if total_properties % 10 == 0:
                try:
                    if self.session.in_transaction():
                        self.session.commit()
                except Exception as e:
                    self.logger.warning(f"定期コミットエラー: {e}")
                    # エラーが発生しても処理を続行
        
        # 最終コミット（トランザクションがアクティブな場合のみ）
        try:
            if self.session.in_transaction():
                self.session.commit()
        except Exception as e:
            self.logger.warning(f"最終コミットエラー: {e}")
        
        # properties_processedとtotal_propertiesの一致を確認
        if self._scraping_stats['properties_processed'] != total_properties:
            self.logger.warning(
                f"処理件数の不一致: properties_processed={self._scraping_stats['properties_processed']}, "
                f"total_properties={total_properties}"
            )
        
        # 最終進捗更新（100%の状態を確実に送信）
        self._update_progress()
        
        # 完了フェーズを設定
        self._scraping_stats['phase'] = 'completed'  # 完了
        
        result = {
            'total_properties': total_properties,
            'detail_fetched': detail_fetched,
            'skipped': skipped,
            'errors': errors,
            'detail_fetch_failed': self._scraping_stats.get('detail_fetch_failed', 0),
            # 並列スクレイピング用の統計情報を追加
            'total': total_properties,  # 後方互換性のため
            'new': self._scraping_stats.get('new_listings', 0),
            'updated': self._scraping_stats.get('price_updated', 0) + self._scraping_stats.get('other_updates', 0),
            # 詳細な統計情報も含める
            'properties_found': self._scraping_stats.get('properties_found', 0),
            'properties_processed': self._scraping_stats.get('properties_processed', 0),  # 処理予定数を追加
            'properties_attempted': self._scraping_stats.get('properties_attempted', total_properties),
            'new_listings': self._scraping_stats.get('new_listings', 0),
            'price_updated': self._scraping_stats.get('price_updated', 0),
            'other_updates': self._scraping_stats.get('other_updates', 0),
            'refetched_unchanged': self._scraping_stats.get('refetched_unchanged', 0),
            'save_failed': self._scraping_stats.get('save_failed', 0),
            'price_missing': self._scraping_stats.get('price_missing', 0),
            'building_info_missing': self._scraping_stats.get('building_info_missing', 0),
            'other_errors': self._scraping_stats.get('other_errors', 0),
            # 建物名取得の統計
            'building_name_from_table': self._scraping_stats.get('building_name_from_table', 0),
            'building_name_missing': self._scraping_stats.get('building_name_missing', 0),
            # 重複警告の統計
            'duplicate_properties': getattr(self, '_duplicate_property_count', 0),
            # 価格不一致の統計
            'price_mismatch': self._scraping_stats.get('price_mismatch', 0)
        }
        
        # 詳細な統計ログ
        detail_fetch_failed = self._scraping_stats.get('detail_fetch_failed', 0)
        other_errors = self._scraping_stats.get('other_errors', 0)
        duplicate_count = getattr(self, '_duplicate_property_count', 0)
        total_calculated = detail_fetched + skipped + detail_fetch_failed
        self.logger.info(
            f"スクレイピング完了: 処理総数={total_properties}件 "
            f"(詳細取得成功={detail_fetched}件, 詳細スキップ={skipped}件, 詳細取得失敗={detail_fetch_failed}件) "
            f"計算合計={total_calculated}件"
        )
        
        # 重複警告があれば表示
        if duplicate_count > 0:
            self.logger.warning(f"重複物件警告: {duplicate_count}件の物件が複数エリアに掲載されていました（正常な動作です）")
        if total_properties != total_calculated:
            self.logger.warning(f"統計の不一致: 処理総数({total_properties}) != 計算合計({total_calculated})")
        if other_errors > 0:
            self.logger.info(f"その他のエラー（URLなしなど）: {other_errors}件")
        
        # 価格不一致があれば表示
        price_mismatch_count = self._scraping_stats.get('price_mismatch', 0)
        if price_mismatch_count > 0:
            self.logger.error(f"価格不一致エラー: {price_mismatch_count}件の物件で一覧と詳細の価格が異なりました（更新をスキップ）")
        
        # HTML構造エラーの統計を表示（全スクレイパー共通）
        html_errors = self._scraping_stats.get('html_structure_errors', {})
        html_errors_new = self._scraping_stats.get('html_structure_errors_new', {})
        
        # SUUMOの後方互換性：建物名専用の統計
        if self.source_site == 'suumo':
            table_count = self._scraping_stats.get('building_name_from_table', 0)
            missing_count = self._scraping_stats.get('building_name_missing', 0)
            missing_new_count = self._scraping_stats.get('building_name_missing_new', 0)
            error_skipped_count = self._scraping_stats.get('building_name_error_skipped', 0)
            
            # 建物名の統計（後方互換性のため）
            if table_count > 0 or missing_count > 0 or error_skipped_count > 0:
                self.logger.info(f"建物名取得: テーブルから{table_count}件、取得失敗{missing_count}件、エラースキップ{error_skipped_count}件")
                
                # 新規エラーのみを重大エラーとして扱う
                if missing_new_count > 0:
                    self.logger.error(
                        f"重大エラー: {missing_new_count}件の物件で新たに建物名が取得できませんでした。"
                        "HTML構造が変更された可能性があります。早急な対応が必要です。"
                    )
                elif missing_count > 0:
                    # 既知のエラーは情報レベルで記録
                    self.logger.info(
                        f"建物名取得エラー: {missing_count}件（うち新規{missing_new_count}件、既知{missing_count - missing_new_count}件）"
                    )
        
        # フィールド別エラー統計（全スクレイパー共通）
        if html_errors:
            self.logger.info("HTML構造エラー詳細:")
            for field, count in html_errors.items():
                new_count = html_errors_new.get(field, 0)
                if new_count > 0:
                    self.logger.error(
                        f"  {field}: {count}件（うち新規{new_count}件） - HTML構造変更の可能性あり"
                    )
                else:
                    self.logger.info(f"  {field}: {count}件（既知のエラー）")
        
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
    
    def _debug_pause_flag_state(self):
        """一時停止フラグの状態をデバッグ出力"""
        if hasattr(self, 'pause_flag'):
            self.logger.info(f"[DEBUG] common_scrape_area_logic開始時 - pause_flag exists: {self.pause_flag is not None}")
            debug_log(f"[{self.source_site}] common_scrape_area_logic開始 - pause_flag exists: {self.pause_flag is not None}")
            if self.pause_flag:
                self.logger.info(f"[DEBUG] pause_flag ID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
                debug_log(f"[{self.source_site}] pause_flag ID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
        else:
            self.logger.info("[DEBUG] pause_flag attribute not found!")
            debug_log(f"[{self.source_site}] pause_flag attribute not found!")
    
    def _check_resume_state(self) -> Tuple[List[Dict[str, Any]], int, bool]:
        """再開時の状態をチェックし、適切な状態を返す"""
        self.logger.info(f"[DEBUG] 再開チェック: phase={self._scraping_stats.get('phase')}, collected={len(self._collected_properties)}, page={self._current_page}, processed={self._processed_count}")
        debug_log(f"[{self.source_site}] 再開チェック: phase={self._scraping_stats.get('phase')}, collected={len(self._collected_properties)}, page={self._current_page}, processed={self._processed_count}")
        
        if self._scraping_stats.get('phase') == 'processing' and self._collected_properties:
            # 処理フェーズから再開
            self.logger.info(f"処理フェーズから再開: 処理済み={self._processed_count}/{len(self._collected_properties)}件")
            return self._collected_properties, self._current_page, True
        elif self._scraping_stats.get('phase') == 'collecting' and self._collected_properties:
            # 収集フェーズから再開
            self.logger.info(f"収集フェーズから再開: ページ={self._current_page}, 収集済み={len(self._collected_properties)}件")
            return self._collected_properties, self._current_page, False
        else:
            # 新規開始またはリセット
            all_properties = self._collected_properties if self._collected_properties else []
            page = self._current_page if self._current_page > 0 else 1
            
            # 統計が空の場合のみリセット
            if not self._scraping_stats:
                self._reset_scraping_stats()
            
            return all_properties, page, False
    
    def _reset_scraping_stats(self):
        """スクレイピング統計をリセット"""
        self._property_count = 0
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
    
    def _handle_pause_if_needed(self, all_properties: List[Dict[str, Any]], page: int, phase_name: str):
        """一時停止フラグをチェックし、必要に応じて待機"""
        if hasattr(self, 'pause_flag'):
            self.logger.info(f"[DEBUG] pause_flag exists: {self.pause_flag is not None}, ID: {id(self.pause_flag) if self.pause_flag else 'None'}")
            debug_log(f"[{self.source_site}] pause_flag exists: {self.pause_flag is not None}")
            if self.pause_flag:
                self.logger.info(f"[DEBUG] pause_flag is_set: {self.pause_flag.is_set()}")
                debug_log(f"[{self.source_site}] pause_flag is_set: {self.pause_flag.is_set()}")
        
        if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
            self.logger.info(f"タスクが一時停止されました（{phase_name}）")
            # 現在の状態を保存
            self._collected_properties = all_properties
            self._current_page = page
            
            # 一時停止フラグがクリアされるまで待機
            self.logger.info(f"一時停止フラグがクリアされるまで待機中（{phase_name}）... フラグID: {id(self.pause_flag)}")
            debug_log(f"[{self.source_site}] 一時停止フラグがクリアされるまで待機中（{phase_name}）... フラグID: {id(self.pause_flag)}")
            
            wait_count = 0
            initial_flag_state = self.pause_flag.is_set()
            self.logger.info(f"[DEBUG] Initial pause flag state: {initial_flag_state}")
            debug_log(f"[{self.source_site}] Initial pause flag state: {initial_flag_state}")
            
            # タイムアウト設定
            pause_timeout = PAUSE_TIMEOUT_SECONDS
            while self.pause_flag.is_set():
                # キャンセルチェック
                if self._is_cancelled():
                    raise TaskCancelledException("Task cancelled during pause")
                time_module.sleep(self.PAUSE_CHECK_INTERVAL)
                wait_count += 1
                if wait_count % self.PAUSE_LOG_INTERVAL == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"{phase_name}待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                    debug_log(f"[{self.source_site}] {phase_name}待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                # タイムアウトチェック
                if wait_count >= pause_timeout * 10:  # wait_countは0.1秒単位
                    self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒（{pause_timeout/60:.0f}分）を超えたため処理を中断")
                    raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds ({pause_timeout/60:.0f} minutes)")
            
            self.logger.info(f"一時停止が解除されました（{phase_name}）。処理を再開します... (待機時間: {wait_count/10}秒)")
            debug_log(f"[{self.source_site}] 一時停止が解除されました（{phase_name}）。処理を再開します... (待機時間: {wait_count/10}秒)")
    
    def _should_stop_collection(self, all_properties: List[Dict[str, Any]], page: int) -> bool:
        """収集を停止すべきか判定"""
        # 最大物件数に達した場合
        if self.max_properties and len(all_properties) >= self.max_properties:
            self.logger.info(f"最大物件数 {self.max_properties} に達したため終了")
            return True
        
        # 最大ページ数を超えた場合
        if page > self.MAX_PAGES:
            self.logger.warning(f"{self.MAX_PAGES}ページを超えたため終了")
            return True
        
        return False
    
    def _process_page_properties(self, properties: List[Dict[str, Any]], seen_urls: set) -> Tuple[set, List[Dict[str, Any]], int]:
        """ページの物件を処理し、重複をチェック"""
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
        
        return current_page_urls, new_properties, duplicate_count
    
    def _check_duplicate_pages(self, current_page_urls: set, previous_page_urls: set, page: int, duplicate_page_count: int) -> bool:
        """ページの重複をチェックし、終了すべきか判定"""
        if current_page_urls and current_page_urls == previous_page_urls:
            self.logger.warning(f"ページ {page}: 前ページと完全に同じ内容です（ページング失敗の可能性）")
            if duplicate_page_count >= 1:  # 2回目の重複
                self.logger.error("2ページ連続で同じ内容のため、ページング処理を終了します")
                return True
        return False
    
    def _handle_new_properties(self, new_properties: List[Dict[str, Any]], all_properties: List[Dict[str, Any]], 
                             duplicate_count: int, page: int, consecutive_empty_pages: int) -> bool:
        """新規物件の処理と統計更新"""
        if duplicate_count > 0:
            self.logger.info(f"ページ {page}: {duplicate_count} 件の重複物件を除外")
        
        if not new_properties:
            self.logger.info(f"ページ {page}: すべて既出の物件でした")
            if consecutive_empty_pages + 1 >= self.MAX_CONSECUTIVE_EMPTY_PAGES:
                self.logger.info("新規物件が見つからないため終了")
                return True
        else:
            # 最大物件数を考慮して物件を追加
            if self.max_properties:
                remaining = self.max_properties - len(all_properties)
                if remaining <= 0:
                    return True
                if remaining < len(new_properties):
                    all_properties.extend(new_properties[:remaining])
                    self.logger.info(f"最大物件数に達したため、{remaining} 件のみ追加")
                    self._scraping_stats['properties_found'] = len(all_properties)
                    return True
                else:
                    all_properties.extend(new_properties)
            else:
                all_properties.extend(new_properties)
        
        return False
    
    def _handle_processing_pause_if_needed(self, all_properties: List[Dict[str, Any]], index: int):
        """処理フェーズ中の一時停止チェック"""
        if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
            self.logger.info(f"[{self.source_site}] タスクが一時停止されました（処理フェーズ）")
            # 現在の処理状態を保存
            self._processed_count = index
            self._collected_properties = all_properties  # 収集済み物件も保存
            
            # 一時停止フラグがクリアされるまで待機
            self.logger.info(f"一時停止フラグがクリアされるまで待機中（処理フェーズ）... フラグID: {id(self.pause_flag)}")
            debug_log(f"[{self.source_site}] 処理フェーズで一時停止検出。待機開始... フラグID: {id(self.pause_flag)}, is_set: {self.pause_flag.is_set()}")
            
            wait_count = 0
            pause_timeout = 300  # 5分
            while self.pause_flag.is_set():
                # キャンセルチェック
                if self._is_cancelled():
                    raise TaskCancelledException("Task cancelled during pause")
                time_module.sleep(self.PAUSE_CHECK_INTERVAL)
                wait_count += 1
                if wait_count % self.PAUSE_LOG_INTERVAL == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"処理フェーズ待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                    debug_log(f"[{self.source_site}] 処理フェーズ待機中... {wait_count/10}秒経過。フラグ状態: {self.pause_flag.is_set()}")
                # タイムアウトチェック
                if wait_count >= pause_timeout * 10:
                    self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                    raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
            
            self.logger.info(f"一時停止が解除されました（処理フェーズ）。処理を再開します... (待機時間: {wait_count/10}秒)")
            debug_log(f"[{self.source_site}] 処理フェーズで一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
    
    def set_progress_callback(self, callback):
        """進捗更新コールバックを設定"""
        self._progress_callback = callback
    
    def _update_progress(self):
        """進捗をコールバックに通知"""
        if hasattr(self, '_progress_callback') and self._progress_callback:
            stats = {
                'properties_found': self._scraping_stats.get('properties_found', 0),
                'properties_processed': self._scraping_stats.get('properties_processed', 0),  # 処理予定数を追加
                'properties_attempted': self._scraping_stats.get('properties_attempted', 0),
                'processed': self._scraping_stats.get('properties_attempted', 0),
                'new': self._scraping_stats.get('new_listings', 0),
                'new_listings': self._scraping_stats.get('new_listings', 0),  # フロントエンド互換性のため
                'updated': self._scraping_stats.get('price_updated', 0) + self._scraping_stats.get('other_updates', 0),
                'price_updated': self._scraping_stats.get('price_updated', 0),  # 価格更新を個別に追加
                'other_updates': self._scraping_stats.get('other_updates', 0),  # その他更新を個別に追加
                'refetched_unchanged': self._scraping_stats.get('refetched_unchanged', 0),  # 再取得（変更なし）を追加
                'detail_fetched': self._scraping_stats.get('detail_fetched', 0),
                'detail_skipped': self._scraping_stats.get('detail_skipped', 0),
                'errors': self._scraping_stats.get('detail_fetch_failed', 0) + self._scraping_stats.get('save_failed', 0) + self._scraping_stats.get('other_errors', 0),
                'price_missing': self._scraping_stats.get('price_missing', 0),
                'building_info_missing': self._scraping_stats.get('building_info_missing', 0)
            }
            try:
                self._progress_callback(stats)
            except Exception as e:
                self.logger.warning(f"進捗コールバックエラー: {e}")
    
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
        site_id = property_data.get('site_property_id', '不明')
        
        # デバッグ: 特定の物件の詳細情報
        if site_id in ['C13252J13', 'C13249B30']:
            self.logger.info(f"DEBUG: 処理開始 - ID: {site_id}, existing_listing: {existing_listing is not None}")
            if existing_listing:
                self.logger.info(f"DEBUG: existing_listing.detail_fetched_at = {existing_listing.detail_fetched_at}")
        
        print(f"\n処理中: {building_name}")
        print(f"  URL: {property_data.get('url', '')}")
        print(f"  価格: {price}万円" if price != '不明' else "  価格: 不明")
        
        # 詳細取得の判定
        needs_detail = False
        
        # デバッグ: 特定の物件の判定詳細
        if site_id in ['C13252J13', 'C13249B30']:
            self.logger.info(f"DEBUG: 判定開始 - force_detail_fetch: {self.force_detail_fetch}, "
                           f"existing_listing: {existing_listing is not None}")
        
        if self.force_detail_fetch:
            needs_detail = True
            print("  → 強制詳細取得モード")
            if site_id in ['C13252J13', 'C13249B30']:
                self.logger.info(f"DEBUG: {site_id} - 強制詳細取得モードのため詳細取得")
        elif not existing_listing:
            needs_detail = True
            print("  → 新規物件のため詳細取得")
            if site_id in ['C13252J13', 'C13249B30']:
                self.logger.info(f"DEBUG: {site_id} - 新規物件のため詳細取得")
        else:
            # 既存物件の場合、価格変更をチェック
            if not self.enable_smart_scraping:
                needs_detail = True
                print("  → スマートスクレイピング無効のため詳細取得")
            else:
                # 価格が変更されているかチェック
                price_changed = False
                if site_id in ['C13252J13', 'C13249B30']:
                    self.logger.info(f"DEBUG: {site_id} - property_data.keys(): {list(property_data.keys())}")
                    self.logger.info(f"DEBUG: {site_id} - price in property_data: {'price' in property_data}, value: {property_data.get('price')}")
                
                if 'price' in property_data and property_data['price'] is not None:
                    if site_id in ['C13252J13', 'C13249B30']:
                        self.logger.info(f"DEBUG: {site_id} - 価格比較: DB={existing_listing.current_price}, 一覧={property_data['price']}")
                    
                    if existing_listing.current_price != property_data['price']:
                        price_changed = True
                        print(f"  → 価格変更検出: {existing_listing.current_price}万円 → {property_data['price']}万円")
                        if site_id in ['C13252J13', 'C13249B30']:
                            self.logger.info(f"DEBUG: {site_id} - 価格変更検出！")
                else:
                    if site_id in ['C13252J13', 'C13249B30']:
                        self.logger.info(f"DEBUG: {site_id} - 価格情報なし、詳細取得へ")
                
                # 価格変更があれば詳細を取得、なければ通常の判定
                if price_changed:
                    needs_detail = True
                else:
                    # 価格変更がない場合は、最終取得日をチェック
                    if existing_listing.detail_fetched_at:
                        # タイムゾーンを考慮した日数計算
                        from datetime import timezone
                        now = datetime.now(timezone.utc) if existing_listing.detail_fetched_at.tzinfo else datetime.now()
                        days_since_fetch = (now - existing_listing.detail_fetched_at).days
                        
                        # デバッグ情報
                        self.logger.info(f"詳細取得判定 - ID: {existing_listing.site_property_id}, "
                                       f"detail_fetched_at: {existing_listing.detail_fetched_at}, "
                                       f"now: {now}, days_since: {days_since_fetch}, "
                                       f"refetch_days: {self.detail_refetch_days}")
                        
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
            # 価格不一致履歴でスキップすべきかチェック
            if site_id and self._should_skip_due_to_price_mismatch(site_id):
                print("  → 価格不一致履歴のためスキップ")
                property_data['detail_fetched'] = False
                property_data['detail_fetch_attempted'] = False
                property_data['update_type'] = 'skipped'
                property_data['property_saved'] = True
                return True
            
            # 404エラーでスキップすべきかチェック（強制詳細取得モードでない、かつエラー履歴無視モードでない場合のみ）
            if not self.force_detail_fetch and not self.ignore_error_history and self._should_skip_url_due_to_404(property_data['url']):
                print("  → 404エラー履歴のためスキップ")
                property_data['detail_fetched'] = False
                property_data['detail_fetch_attempted'] = False  # 404エラー履歴によるスキップは試行とみなさない
                # 404エラー履歴によるスキップは詳細取得失敗にカウントしない
                # self._scraping_stats['detail_fetch_failed'] += 1
                
                # 404エラー履歴によるスキップはエラーログに記録しない
                # （正常な動作なので、エラーとして扱わない）
                # if hasattr(self, '_save_error_log'):
                #     self._save_error_log({
                #         'url': property_data.get('url', '不明'),
                #         'reason': '404エラー履歴のためスキップ',
                #         'building_name': property_data.get('building_name', ''),
                #         'price': property_data.get('price', ''),
                #         'timestamp': datetime.now().isoformat()
                #     })
                
                # スキップとして処理を継続
                property_data['update_type'] = 'skipped'
                property_data['property_saved'] = True  # エラーではなく正常なスキップとして扱う
                return True  # Falseではなく True を返す
            
            # 検証エラーでスキップすべきかチェック（強制詳細取得モードでない、かつエラー履歴無視モードでない場合のみ）
            if not self.force_detail_fetch and not self.ignore_error_history and self._should_skip_url_due_to_validation_error(property_data['url']):
                print("  → 検証エラー履歴のためスキップ")
                property_data['detail_fetched'] = False
                property_data['detail_fetch_attempted'] = False  # 検証エラー履歴によるスキップは試行とみなさない
                # 検証エラー履歴によるスキップも詳細取得失敗にカウントしない
                # （正常な動作なので、エラーとして扱わない）
                
                # スキップとして処理を継続
                property_data['update_type'] = 'skipped'
                property_data['property_saved'] = True  # エラーではなく正常なスキップとして扱う
                return True  # Falseではなく True を返す
            
            # 強制詳細取得モードまたはエラー履歴無視モードで404/検証エラーがある場合のログ出力
            if self.force_detail_fetch or self.ignore_error_history:
                if self._should_skip_url_due_to_404(property_data['url']):
                    if self.force_detail_fetch:
                        print("  → 404エラー履歴があるが、強制詳細取得モードのため処理を継続")
                        self.logger.info(f"404エラー履歴を無視して強制詳細取得: {property_data['url']}")
                    else:
                        print("  → 404エラー履歴があるが、エラー履歴無視モードのため処理を継続")
                        self.logger.info(f"404エラー履歴を無視して詳細取得: {property_data['url']}")
                elif self._should_skip_url_due_to_validation_error(property_data['url']):
                    if self.force_detail_fetch:
                        print("  → 検証エラー履歴があるが、強制詳細取得モードのため処理を継続")
                        self.logger.info(f"検証エラー履歴を無視して強制詳細取得: {property_data['url']}")
                    else:
                        print("  → 検証エラー履歴があるが、エラー履歴無視モードのため処理を継続")
                        self.logger.info(f"検証エラー履歴を無視して詳細取得: {property_data['url']}")
            
            # 詳細取得前に一時停止チェック
            self._check_pause_flag()
            
            print("  → 詳細ページを取得中...")
            detail_error_info = None
            # 前回のエラー情報をクリア
            self._last_detail_error = None
            
            try:
                # parse_detail_funcにproperty_dataを渡す（建物名などの情報を含む）
                # 関数のシグネチャを確認して適切に呼び出す
                import inspect
                sig = inspect.signature(parse_detail_func)
                if 'property_data_from_list' in sig.parameters:
                    # HOMESスクレイパーのように一覧データを受け取る場合
                    detail_data = parse_detail_func(property_data['url'], property_data)
                else:
                    # 従来のスクレイパー（URLのみ）
                    detail_data = parse_detail_func(property_data['url'])
            except TaskCancelledException:
                # キャンセル例外は再スロー
                raise
            except Exception as e:
                # その他のエラーはNoneとして扱う
                import traceback
                self.logger.error(f"詳細取得中にエラー: {property_data['url']} - {type(e).__name__}: {str(e)}")
                self.logger.error(f"エラーの詳細:\n{traceback.format_exc()}")
                detail_data = None
                # エラー情報を保存（後でログ記録に使用）
                detail_error_info = {
                    'type': 'exception',
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
            
            if detail_data:
                # 価格不一致チェック（共通処理として実装）
                list_price = property_data.get('price')
                detail_price = detail_data.get('price')
                
                if list_price and detail_price and list_price != detail_price:
                    # 価格不一致を検出
                    price_diff = abs(list_price - detail_price)
                    price_diff_rate = price_diff / list_price if list_price > 0 else 0
                    
                    self.logger.warning(
                        f"価格不一致を検出: {building_name} - "
                        f"一覧: {list_price}万円, 詳細: {detail_price}万円 "
                        f"(差額: {price_diff}万円, {price_diff_rate:.1%})"
                    )
                    
                    # 価格不一致として記録
                    self._record_price_mismatch(
                        property_data['url'],
                        property_data.get('site_property_id', ''),
                        list_price,
                        detail_price
                    )
                    
                    # 価格不一致の統計を更新
                    if 'price_mismatch' not in self._scraping_stats:
                        self._scraping_stats['price_mismatch'] = 0
                    self._scraping_stats['price_mismatch'] += 1
                    
                    # エラーログを記録
                    if hasattr(self, '_save_error_log'):
                        self._save_error_log({
                            'url': property_data.get('url', '不明'),
                            'reason': f'価格不一致: 一覧 {list_price}万円, 詳細 {detail_price}万円',
                            'building_name': building_name,
                            'price': f'{list_price} → {detail_price}',
                            'timestamp': datetime.now().isoformat(),
                            'site_property_id': property_data.get('site_property_id', ''),
                            'source_site': self.source_site.value
                        })
                    
                    # 更新をスキップ
                    print(f"  → 価格不一致のため更新をスキップ (一覧: {list_price}万円, 詳細: {detail_price}万円)")
                    property_data['detail_fetched'] = False
                    self._last_detail_fetched = False
                    self._scraping_stats['detail_fetch_failed'] += 1
                    property_data['detail_fetch_attempted'] = True
                    property_data['property_saved'] = False
                    return False
                
                # 建物名不一致チェック（一覧ページから建物名が取得されている場合のみ）
                list_building_name = property_data.get('building_name_from_list')
                detail_building_name = detail_data.get('building_name')
                
                if list_building_name and detail_building_name:
                    # 建物名の一致を確認（詳細ページの建物名と一覧ページの建物名を比較）
                    is_verified, verified_name = self.verify_building_names_match(detail_building_name, list_building_name)
                    
                    if not is_verified:
                        # 建物名が一致しない場合の警告
                        self.logger.warning(
                            f"建物名不一致を検出: {property_data.get('url')} - "
                            f"一覧: {list_building_name}, 詳細: {detail_building_name}"
                        )
                        
                        # エラーログを記録
                        if hasattr(self, '_save_error_log'):
                            self._save_error_log({
                                'url': property_data.get('url', '不明'),
                                'reason': f'建物名不一致: 一覧「{list_building_name}」, 詳細「{detail_building_name}」',
                                'building_name': list_building_name,
                                'price': property_data.get('price', ''),
                                'timestamp': datetime.now().isoformat(),
                                'site_property_id': property_data.get('site_property_id', ''),
                                'source_site': self.source_site.value
                            })
                        
                        # 更新をスキップ
                        print(f"  → 建物名不一致のため更新をスキップ (一覧: {list_building_name}, 詳細: {detail_building_name})")
                        property_data['detail_fetched'] = False
                        self._last_detail_fetched = False
                        self._scraping_stats['detail_fetch_failed'] += 1
                        property_data['detail_fetch_attempted'] = True
                        property_data['property_saved'] = False
                        return False
                    else:
                        # 建物名が確認できた場合は、確認された名前を使用
                        if verified_name:
                            detail_data['building_name'] = verified_name
                            self.logger.info(f"建物名を一覧ページの名前で確認: {verified_name}")
                
                # 価格と建物名が一致している場合は通常通り処理
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
                
                # エラー情報がない場合（バリデーションエラーなど）の情報を取得
                if not detail_error_info:
                    # 最後のエラーメッセージを取得（バリデーションエラーなど）
                    detail_error_info = getattr(self, '_last_detail_error', None)
                    self.logger.info(f"[DEBUG] _last_detail_error から取得: {detail_error_info}")
                
                # デバッグ: エラーログ記録の条件を確認
                self.logger.info(f"[DEBUG] エラーログ記録条件 - hasattr(_save_error_log): {hasattr(self, '_save_error_log')}, detail_error_info: {detail_error_info is not None}")
                
                # エラーログを一箇所で記録
                if hasattr(self, '_save_error_log'):
                    if detail_error_info:
                        error_reason = '詳細ページの取得に失敗'
                        
                        # エラータイプに応じてメッセージを構築
                        if detail_error_info.get('type') == 'validation':
                            error_reason = detail_error_info.get('reason', error_reason)
                        elif detail_error_info.get('type') == '404_error':
                            # 404エラーの場合は特別なメッセージ
                            error_reason = '404エラー: 物件ページが見つかりません'
                        elif detail_error_info.get('type') == 'exception':
                            error_type = detail_error_info.get('error_type', '')
                            error_msg = detail_error_info.get('error_message', '')
                            if error_type:
                                error_reason = f'{error_reason} ({error_type}): {error_msg}'
                            else:
                                error_reason = f'{error_reason}: {error_msg}'
                        
                        self._save_error_log({
                            'url': property_data.get('url', '不明'),
                            'reason': error_reason,
                            'building_name': detail_error_info.get('building_name', property_data.get('building_name', '')),
                            'price': detail_error_info.get('price', property_data.get('price', '')),
                            'timestamp': datetime.now().isoformat(),
                            'site_property_id': detail_error_info.get('site_property_id', property_data.get('site_property_id', '')),
                            'source_site': self.source_site.value
                        })
                    else:
                        # エラー情報がない場合でも最低限のログを記録
                        self.logger.warning(f"[DEBUG] 詳細エラー情報がないため、最低限のエラーログを記録")
                        self._save_error_log({
                            'url': property_data.get('url', '不明'),
                            'reason': '詳細ページの取得に失敗（詳細情報なし）',
                            'building_name': property_data.get('building_name', ''),
                            'price': str(property_data.get('price', '')),
                            'timestamp': datetime.now().isoformat(),
                            'site_property_id': property_data.get('site_property_id', ''),
                            'source_site': self.source_site.value
                        })
                
                # 詳細取得に失敗した場合は保存処理をスキップ
                property_data['property_saved'] = False
                return False
        else:
            property_data['detail_fetched'] = False
            self._last_detail_fetched = False  # フラグを記録
            
            # 詳細を取得しない場合、既存の情報を補完
            if existing_listing and existing_listing.master_property:
                # 必須情報を既存データから補完
                if 'building_name' not in property_data or not property_data['building_name']:
                    property_data['building_name'] = existing_listing.master_property.building.normalized_name
                if 'area' not in property_data or not property_data['area']:
                    property_data['area'] = existing_listing.master_property.area
                if 'layout' not in property_data or not property_data['layout']:
                    property_data['layout'] = existing_listing.master_property.layout
                if 'floor_number' not in property_data or property_data.get('floor_number') is None:
                    property_data['floor_number'] = existing_listing.master_property.floor_number
        
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
        from .data_normalizer import validate_price, validate_area, validate_floor_number
        
        url = property_data.get('url', '不明')
        building_name = property_data.get('building_name', '不明')
        
        # 検証エラーの詳細を収集
        validation_errors = []
        
        # 必須フィールドのチェック
        if not property_data.get('building_name'):
            validation_errors.append("建物名が未取得")
            self.logger.warning(f"建物名がありません: URL={url}")
        
        if not property_data.get('price'):
            validation_errors.append("価格が未取得")
            self.logger.warning(f"価格情報がありません: URL={url}, building_name={building_name}")
        
        # site_property_idを必須項目として追加
        if not property_data.get('site_property_id'):
            validation_errors.append("サイト物件IDが未取得")
            self.logger.warning(f"サイト物件IDがありません: URL={url}, building_name={building_name}")
        
        # 住所は詳細ページから取得する場合があるため、一覧ページでは必須ではない
        # 詳細ページ取得後に再度チェックされる
        if not property_data.get('address') and property_data.get('detail_fetched', False):
            # 詳細ページを取得したのに住所がない場合のみエラー
            validation_errors.append("住所が未取得（詳細取得後）")
            self.logger.warning(f"詳細取得後も住所情報がありません: URL={url}, building_name={building_name}")
        
        # 価格の妥当性チェック（data_normalizerのvalidate_priceを使用）
        price = property_data.get('price', 0)
        if price and not validate_price(price):
            validation_errors.append(f"価格が範囲外: {price}万円（許容範囲: 100万円〜100億円）")
            self.logger.warning(f"価格が異常です: {price}万円, URL={url}")
        
        # 面積の妥当性チェック（data_normalizerのvalidate_areaを使用）
        area = property_data.get('area', 0)
        if area and not validate_area(area):
            validation_errors.append(f"面積が範囲外: {area}㎡（許容範囲: 10㎡〜500㎡）")
            self.logger.warning(f"面積が異常です: {area}㎡, URL={url}")
            # 面積超過エラーフラグを設定
            property_data['_validation_error_type'] = 'area_exceeded'
        
        # 階数の妥当性チェック（data_normalizerのvalidate_floor_numberを使用）
        floor_number = property_data.get('floor_number')
        total_floors = property_data.get('total_floors')
        if floor_number is not None and not validate_floor_number(floor_number, total_floors):
            validation_errors.append(f"階数の整合性エラー: {floor_number}階/{total_floors}階建て")
            self.logger.warning(
                f"階数の整合性エラー: {floor_number}階/"
                f"{total_floors}階建て, URL={url}"
            )
        
        # エラーがある場合は詳細ログを出力
        if validation_errors:
            self.logger.error(
                f"物件データ検証エラー - "
                f"URL: {url}, "
                f"建物名: {building_name}, "
                f"エラー詳細: {'; '.join(validation_errors)}"
            )
            # エラー詳細を保存して、呼び出し元で利用できるようにする
            property_data['_validation_errors'] = validation_errors
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
    
    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str, 
                                   threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """一覧ページで取得した建物名と詳細ページで取得した建物名が一致するか確認
        
        Args:
            detail_building_name: 詳細ページから取得した建物名
            building_name_from_list: 一覧ページから取得した建物名
            threshold: 類似度の閾値（0.0-1.0）
            
        Returns:
            (建物名が確認できたか, 確認された建物名またはNone)
        """
        if not building_name_from_list or not detail_building_name:
            return False, None
            
        # 正規化（スペース、記号を除去）
        normalized_list_name = re.sub(r'[\s　・－―～〜]+', '', building_name_from_list)
        normalized_detail_name = re.sub(r'[\s　・－―～〜]+', '', detail_building_name)
        
        # 完全一致（正規化後）
        if normalized_list_name.lower() == normalized_detail_name.lower():
            self.logger.info(f"建物名が一致（完全一致）: {building_name_from_list}")
            return True, detail_building_name
            
        # 部分一致（建物名の主要部分が含まれているか）
        # 例：「グランドヒルズ東京タワー」→「グランドヒルズ」が含まれていればOK
        main_parts = re.split(r'[・\s　]', building_name_from_list)
        significant_parts = [part for part in main_parts if len(part) >= 3]  # 3文字以上の部分
        
        if significant_parts:
            matched_count = sum(1 for part in significant_parts 
                              if part.lower() in detail_building_name.lower())
            match_ratio = matched_count / len(significant_parts)
            
            if match_ratio >= threshold:
                self.logger.info(
                    f"建物名が一致（部分一致 {match_ratio:.0%}）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
                
        self.logger.warning(
            f"建物名が一致しません: 一覧「{building_name_from_list}」、詳細「{detail_building_name}」"
        )
        return False, None
    
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
        
        # デバッグログ
        self.logger.info(f"Property hash calculation: building_id={building.id}, floor={floor_number}, "
                        f"area={area}, layout={layout}, direction={direction}, hash={property_hash}")
        
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
        
        try:
            self.session.flush()
        except Exception as e:
            # 重複エラーの場合はロールバックして再検索
            if "duplicate key value violates unique constraint" in str(e):
                self.logger.warning(f"Duplicate property_hash detected, rolling back and retrying: {property_hash}")
                self.session.rollback()
                
                # 再度検索
                master_property = self.session.query(MasterProperty).filter(
                    MasterProperty.property_hash == property_hash
                ).first()
                
                if master_property:
                    self.logger.info(f"Found existing master property after rollback: id={master_property.id}")
                    return master_property
                else:
                    # それでも見つからない場合はエラーを再発生
                    raise
            else:
                # その他のエラーは再発生
                raise
        
        return master_property
    
    def create_or_update_listing(self, master_property: MasterProperty, url: str, title: str,
                               price: int, agency_name: str = None, site_property_id: str = None,
                               description: str = None, station_info: str = None, features: str = None,
                               management_fee: int = None, repair_fund: int = None,
                               published_at: datetime = None, first_published_at: datetime = None,
                               **kwargs) -> tuple[PropertyListing, str]:
        """掲載情報を作成または更新"""
        # site_property_idがある場合は、それを使って既存の掲載を検索
        if site_property_id:
            listing = self.session.query(PropertyListing).filter(
                PropertyListing.source_site == self.source_site,
                PropertyListing.site_property_id == site_property_id
            ).first()
        else:
            # site_property_idがない場合は、URLとmaster_property_idで検索
            listing = self.session.query(PropertyListing).filter(
                PropertyListing.master_property_id == master_property.id,
                PropertyListing.url == url,
                PropertyListing.source_site == self.source_site
            ).first()
        
        # 既存の掲載が見つかった場合、URLが変わっているかチェック
        if listing and listing.url != url:
            # URLの実質的な違いを判定（site_property_idが同じ場合は軽微な変更として扱う）
            if site_property_id:
                # site_property_idが同じなら、URLの変更は記録するが警告レベルを下げる
                self.logger.debug(f"物件のURL形式が異なります（同一物件）: {listing.url} → {url}")
                # 最新のURLに更新（アクセス可能性を保つため）
                listing.url = url
                # URL変更カウントは増やさない（統計を汚染しないため）
            else:
                # site_property_idがない場合は、重要な変更として扱う
                self.logger.info(f"物件のURLが変更されました: {listing.url} → {url}")
                listing.url = url
                if not hasattr(self, '_url_changed_count'):
                    self._url_changed_count = 0
                self._url_changed_count += 1
        
        # 同じURLで別の物件が存在する場合の処理（site_property_idベースで検索した場合のみ）
        if not listing and site_property_id:
            existing_with_same_url = self.session.query(PropertyListing).filter(
                PropertyListing.url == url,
                PropertyListing.source_site == self.source_site
            ).first()
            
            if existing_with_same_url:
                # 同じURLで別の物件が存在する場合
                if existing_with_same_url.master_property_id != master_property.id:
                    # 別の物件の場合、古い方を非アクティブにする
                    self.logger.info(f"同じURLで別の物件が存在 (旧物件ID: {existing_with_same_url.master_property_id})")
                    existing_with_same_url.is_active = False
                    existing_with_same_url.delisted_at = datetime.now()
                    self.session.flush()
                else:
                    # 同じ物件の場合は、既存のレコードを使用
                    listing = existing_with_same_url
                    self.logger.debug(f"同じ物件の既存レコード発見 (ID: {listing.id})")
        
        # 重要フィールドの保護：NULL値や異常値での更新を防止
        # kwargs から物件属性を取得
        listing_floor_number = kwargs.get('listing_floor_number')
        listing_area = kwargs.get('listing_area')
        listing_layout = kwargs.get('listing_layout')
        listing_direction = kwargs.get('listing_direction')
        listing_total_floors = kwargs.get('listing_total_floors')
        
        # 既存物件の更新時、重要フィールドがNULLまたは異常値の場合は警告
        prevent_null_updates = os.getenv('SCRAPER_PREVENT_NULL_UPDATES', 'false').lower() == 'true'
        
        if listing and listing.is_active:
            suspicious_update = False
            warning_messages = []
            
            # 階数チェック（既存値があるのにNULLになる場合）
            if listing_floor_number is None and listing.listing_floor_number is not None:
                warning_messages.append(f"階数が削除されようとしています（{listing.listing_floor_number}階→NULL）")
                suspicious_update = True
                # NULL更新を防止する設定の場合、既存値を保持
                if prevent_null_updates:
                    listing_floor_number = listing.listing_floor_number
            
            # 面積チェック（既存値があるのにNULLになる、または70%以上の変動）
            if listing_area is None and listing.listing_area is not None:
                warning_messages.append(f"面積が削除されようとしています（{listing.listing_area}㎡→NULL）")
                suspicious_update = True
                # NULL更新を防止する設定の場合、既存値を保持
                if prevent_null_updates:
                    listing_area = listing.listing_area
            elif listing_area is not None and listing.listing_area is not None:
                area_change_rate = abs(listing_area - listing.listing_area) / listing.listing_area
                if area_change_rate > 0.7:  # 70%以上の変動（正当な変更の可能性を考慮）
                    warning_messages.append(f"面積が大幅に変更されようとしています（{listing.listing_area}㎡→{listing_area}㎡、{area_change_rate:.0%}の変動）")
                    suspicious_update = True
            
            # 価格チェック（70%以上の変動、ただし価格変更は比較的一般的なので閾値を高めに）
            if price and listing.current_price:
                price_change_rate = abs(price - listing.current_price) / listing.current_price
                if price_change_rate > 0.7:  # 70%以上の変動
                    warning_messages.append(f"価格が大幅に変更されようとしています（{listing.current_price}万円→{price}万円、{price_change_rate:.0%}の変動）")
                    suspicious_update = True
            
            # 疑わしい更新の場合
            if suspicious_update:
                for msg in warning_messages:
                    self.logger.warning(f"[疑わしい更新検出] {msg} - URL: {url}")
                
                # エラー統計を更新
                if 'suspicious_updates' not in self._scraping_stats:
                    self._scraping_stats['suspicious_updates'] = 0
                self._scraping_stats['suspicious_updates'] += 1
                
                # 連続して疑わしい更新が発生した場合は例外を発生
                suspicious_threshold = int(os.getenv('SCRAPER_SUSPICIOUS_UPDATE_THRESHOLD', '5'))
                if self._scraping_stats.get('suspicious_updates', 0) >= suspicious_threshold:
                    raise Exception(
                        f"連続して{suspicious_threshold}件の疑わしい更新を検出しました。"
                        f"HTML構造が変更された可能性があります。"
                        f"最新の警告: {warning_messages[0]}"
                    )
        
        update_type = 'new'  # デフォルトは新規
        
        if listing:
            # 更新タイプを判定
            price_changed = False
            other_changed = False
            old_price = listing.current_price  # 更新前の価格を保存（ログ用）
            changed_fields = []  # 変更されたフィールドを記録
            
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
                changed_fields.append('タイトル')
            listing.title = title
            
            if agency_name and listing.agency_name != agency_name:
                other_changed = True
                changed_fields.append('不動産会社')
            listing.agency_name = agency_name or listing.agency_name
            
            if site_property_id and listing.site_property_id != site_property_id:
                # NULLから値が設定される場合と、既存値が変更される場合を区別
                if listing.site_property_id is None:
                    # NULLから新規設定される場合は、重要な変更ではないのでログのみ
                    self.logger.debug(f"サイト物件IDを新規設定: {site_property_id}")
                else:
                    # 既存値が変更される場合は重要な変更
                    other_changed = True
                    changed_fields.append(f'サイト物件ID({listing.site_property_id}→{site_property_id})')
            listing.site_property_id = site_property_id or listing.site_property_id
            
            if description and listing.description != description:
                other_changed = True
                changed_fields.append('説明文')
            listing.description = description or listing.description
            
            if station_info and listing.station_info != station_info:
                other_changed = True
                changed_fields.append('駅情報')
            listing.station_info = station_info or listing.station_info
            
            if features and listing.features != features:
                other_changed = True
                changed_fields.append('特徴')
            listing.features = features or listing.features
            
            if management_fee is not None and listing.management_fee != management_fee:
                other_changed = True
                old_fee = listing.management_fee
                changed_fields.append(f'管理費({old_fee or 0}円→{management_fee}円)')
            listing.management_fee = management_fee if management_fee is not None else listing.management_fee
            
            if repair_fund is not None and listing.repair_fund != repair_fund:
                other_changed = True
                old_fund = listing.repair_fund
                changed_fields.append(f'修繕積立金({old_fund or 0}円→{repair_fund}円)')
            listing.repair_fund = repair_fund if repair_fund is not None else listing.repair_fund
            
            # 建物名の変更をチェック
            listing_building_name = kwargs.get('listing_building_name')
            if listing_building_name and listing.listing_building_name != listing_building_name:
                old_building_name = listing.listing_building_name
                other_changed = True
                if old_building_name:
                    # 既存の建物名がある場合
                    changed_fields.append(f'建物名({old_building_name}→{listing_building_name})')
                    self.logger.info(f"建物名更新検出: {old_building_name} → {listing_building_name}")
                else:
                    # NULLから新規設定の場合
                    changed_fields.append(f'建物名(新規設定: {listing_building_name})')
                    self.logger.info(f"建物名新規設定: {listing_building_name}")
            
            listing.is_active = True
            listing.last_confirmed_at = datetime.now()
            listing.detail_fetched_at = datetime.now()  # 詳細取得時刻を更新
            
            # 更新タイプを判定
            update_details = None
            if price_changed:
                update_type = 'price_updated'
                self.logger.info(f"価格更新: {old_price}万円 → {price}万円 - {url}")
            elif other_changed:
                update_type = 'other_updates'
                update_details = ', '.join(changed_fields)  # 変更内容を記録
                self.logger.info(f"その他更新: {url} - 詳細: {update_details}")
            else:
                update_type = 'refetched_unchanged'
                self.logger.debug(f"変更なし: {url}")
            
            # published_atの更新（より新しい日付があれば）
            if published_at and (not listing.published_at or published_at > listing.published_at):
                listing.published_at = published_at
            
            # 追加の属性を更新（変更を追跡）
            for key, value in kwargs.items():
                if hasattr(listing, key) and value is not None:
                    old_value = getattr(listing, key)
                    if old_value != value:
                        # 特定のフィールドについて変更を記録
                        if key == 'listing_floor_number' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'所在階({old_value}階→{value}階)')
                        elif key == 'listing_area' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'面積({old_value}㎡→{value}㎡)')
                        elif key == 'listing_layout' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'間取り({old_value}→{value})')
                        elif key == 'listing_direction' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'方角({old_value}→{value})')
                        elif key == 'listing_total_floors' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'総階数({old_value}階→{value}階)')
                        elif key == 'listing_balcony_area' and old_value is not None:
                            other_changed = True
                            changed_fields.append(f'バルコニー面積({old_value}㎡→{value}㎡)')
                        else:
                            # その他のフィールドも変更を記録
                            # 除外するフィールド（これらは更新として扱わない）
                            excluded_fields = {
                                'remarks', 'agency_tel', 'detail_fetched_at', 'last_confirmed_at',
                                'is_active', 'price_updated_at', 'scraped_from_area'
                            }
                            
                            if not key.startswith('_') and key not in excluded_fields:
                                # フィールド名を日本語に変換
                                field_name_map = {
                                    'listing_address': '住所',
                                    'listing_building_name': '建物名',
                                    'agency_name': '不動産会社'
                                }
                                field_display_name = field_name_map.get(key, key)
                                
                                if old_value is not None:
                                    # 既存値がある場合の変更
                                    other_changed = True
                                    changed_fields.append(f'{field_display_name}({old_value}→{value})')
                                    self.logger.debug(f"フィールド変更検出: {key} ({old_value} → {value})")
                                elif key not in {'listing_building_name'}:  # 建物名は上で処理済み
                                    # NULLから新規設定の場合（重要なフィールドのみ）
                                    important_fields = {'listing_address', 'agency_name'}
                                    if key in important_fields:
                                        other_changed = True
                                        changed_fields.append(f'{field_display_name}(新規設定: {value})')
                                        self.logger.debug(f"フィールド新規設定: {key} = {value}")
                    setattr(listing, key, value)
            
            # 更新タイプを再判定（kwargsでの変更も含める）
            if other_changed and update_type == 'refetched_unchanged':
                update_type = 'other_updates'
                update_details = ', '.join(changed_fields)
                self.logger.info(f"その他更新（追加フィールド）: {url} - 詳細: {update_details}")
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
                    scraped_from_area=getattr(self, 'current_area_code', None),  # 現在のエリアコードを設定
                    **kwargs
                )
                self.session.add(listing)
                self.session.flush()
            except Exception as e:
                # URL重複エラーの場合は、再度検索して既存レコードを使用
                if "property_listings_url_key" in str(e):
                    self.session.rollback()
                    self.logger.debug(f"URL重複エラー検出。既存レコードを再検索...")
                    
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
                            self.logger.debug(f"同じ物件の既存レコードを更新")
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
            self.logger.info(f"新規登録: {price}万円 - {url}")
        
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
        
        # update_detailsがローカル変数でない場合のために初期化
        # update_detailsが定義されていない場合の処理
        if 'update_details' not in locals():
            # other_changedがTrueでchanged_fieldsがある場合は、update_detailsを生成
            if update_type == 'other_updates' and 'changed_fields' in locals() and changed_fields:
                update_details = ', '.join(changed_fields)
            else:
                update_details = None
        
        # デバッグログ
        if update_type == 'other_updates' and not update_details:
            self.logger.warning(f"その他更新と判定されたが詳細が空です - URL: {url}")
        
        return listing, update_type, update_details
    
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
    
    def _should_skip_url_due_to_404(self, url: str) -> bool:
        """404エラー履歴によりスキップすべきURLか判定"""
        try:
            retry_record = self.session.query(Url404Retry).filter(
                Url404Retry.url == url,
                Url404Retry.source_site == self.source_site.value
            ).first()
            
            if retry_record:
                # 再試行間隔を計算
                retry_hours = self._calculate_retry_interval(retry_record.error_count)
                hours_since_error = (datetime.now() - retry_record.last_error_at).total_seconds() / 3600
                
                if hours_since_error < retry_hours:
                    self.logger.debug(
                        f"404エラー履歴によりスキップ: {url} "
                        f"(エラー回数: {retry_record.error_count}, "
                        f"最終エラーから: {hours_since_error:.1f}時間, "
                        f"再試行間隔: {retry_hours}時間)"
                    )
                    return True
                else:
                    self.logger.debug(
                        f"404エラー履歴ありだが再試行可能: {url} "
                        f"(最終エラーから{hours_since_error:.1f}時間経過)"
                    )
                    return False
            return False
        except Exception as e:
            self.logger.error(f"404エラー履歴チェック中にエラー: {e}")
            return False
    
    def _should_skip_url_due_to_validation_error(self, url: str) -> bool:
        """検証エラー履歴によりスキップすべきURLか判定"""
        # 検証エラーテーブルが存在するか確認
        try:
            # validation_errorsテーブルが存在するか確認
            metadata = MetaData()
            metadata.reflect(bind=self.session.bind)
            if 'validation_errors' not in metadata.tables:
                return False
            
            # テーブルが存在する場合のみクエリ実行
            result = self.session.execute(
                text("""
                    SELECT error_count, last_error_at 
                    FROM validation_errors 
                    WHERE url = :url AND source_site = :site
                """),
                {'url': url, 'site': self.source_site.value}
            ).first()
            
            if result:
                error_count, last_error_at = result
                # 再試行間隔を計算（404エラーと同じロジック）
                retry_hours = self._calculate_retry_interval(error_count)
                hours_since_error = (datetime.now() - last_error_at).total_seconds() / 3600
                
                if hours_since_error < retry_hours:
                    self.logger.debug(
                        f"検証エラー履歴によりスキップ: {url} "
                        f"(エラー回数: {error_count}, "
                        f"最終エラーから: {hours_since_error:.1f}時間, "
                        f"再試行間隔: {retry_hours}時間)"
                    )
                    return True
                else:
                    self.logger.debug(
                        f"検証エラー履歴ありだが再試行可能: {url} "
                        f"(最終エラーから{hours_since_error:.1f}時間経過)"
                    )
                    return False
            return False
        except Exception as e:
            # テーブルが存在しない場合はスキップしない
            self.logger.debug(f"検証エラー履歴チェックスキップ: {e}")
            return False
    
    def _should_skip_due_to_price_mismatch(self, site_property_id: str) -> bool:
        """価格不一致履歴によりスキップすべきか判定"""
        # price_mismatch_retriesテーブルが存在するか確認
        try:
            metadata = MetaData()
            metadata.reflect(bind=self.session.bind)
            if 'price_mismatch_retries' not in metadata.tables:
                return False
            
            # テーブルが存在する場合のみクエリ実行
            result = self.session.execute(
                text("""
                    SELECT retry_days, recorded_at 
                    FROM price_mismatch_retries 
                    WHERE site_property_id = :site_id AND source_site = :site
                    ORDER BY recorded_at DESC
                    LIMIT 1
                """),
                {'site_id': site_property_id, 'site': self.source_site.value}
            ).first()
            
            if result:
                retry_days, recorded_at = result
                days_since_record = (datetime.now() - recorded_at).days
                
                if days_since_record < retry_days:
                    self.logger.debug(
                        f"価格不一致履歴によりスキップ: ID={site_property_id} "
                        f"(記録から{days_since_record}日経過, 再試行間隔: {retry_days}日)"
                    )
                    return True
            return False
        except Exception as e:
            self.logger.debug(f"価格不一致履歴チェックスキップ: {e}")
            return False
    
    def _calculate_retry_interval(self, error_count: int) -> int:
        """エラー回数に基づいて再試行間隔を計算（時間単位）"""
        if error_count <= 1:
            return 2  # 2時間
        elif error_count <= 3:
            return 24  # 1日
        elif error_count <= 5:
            return 72  # 3日
        else:
            return 168  # 7日
    
    def _handle_404_error(self, url: str):
        """404エラーのURLを記録"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、404エラーを記録しません: {url}")
            return
            
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
            
            # autoflushが有効な場合のみコミット
            if self.session.autoflush:
                self.session.commit()
            
        except Exception as e:
            self.logger.error(f"404エラー記録中にエラー: {e}")
            self.session.rollback()
    
    
    def _handle_validation_error(self, url: str, error_type: str, error_details: dict = None):
        """検証エラーのURLを記録"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、検証エラーを記録しません: {url}")
            return
            
        try:
            # SQLAlchemyで動的にテーブルを参照
            metadata = MetaData()
            validation_retry_table = Table('url_validation_error_retries', metadata, autoload_with=self.session.bind)
            
            # 既存のレコードを確認
            result = self.session.execute(
                validation_retry_table.select().where(
                    and_(
                        validation_retry_table.c.url == url,
                        validation_retry_table.c.source_site == self.source_site.value
                    )
                )
            ).first()
            
            if result:
                # エラー回数を更新
                self.session.execute(
                    validation_retry_table.update().where(
                        and_(
                            validation_retry_table.c.url == url,
                            validation_retry_table.c.source_site == self.source_site.value
                        )
                    ).values(
                        error_count=result.error_count + 1,
                        last_error_at=datetime.now(),
                        error_type=error_type,
                        error_details=json.dumps(error_details or {}, ensure_ascii=False)
                    )
                )
                
                # 再試行間隔を計算
                retry_hours = self._calculate_retry_interval(result.error_count + 1)
                
                self.logger.info(
                    f"検証エラー再発生 ({error_type}) - "
                    f"URL: {url}, 回数: {result.error_count + 1}, "
                    f"次回再試行までの最小間隔: {retry_hours}時間"
                )
            else:
                # 新規レコードを作成
                self.session.execute(
                    validation_retry_table.insert().values(
                        url=url,
                        source_site=self.source_site.value,
                        error_type=error_type,
                        error_details=json.dumps(error_details or {}, ensure_ascii=False),
                        error_count=1
                    )
                )
                self.logger.info(f"検証エラーを記録 ({error_type}) - URL: {url} (初回、次回再試行は2時間後以降)")
            
            # autoflushが有効な場合のみコミット
            if self.session.autoflush:
                self.session.commit()
            
        except Exception as e:
            self.logger.error(f"検証エラー記録中にエラー: {e}")
            self.session.rollback()
    
    
    def _record_price_mismatch(self, site_property_id: str, url: str, list_price: int, detail_price: int, retry_days: int = 7):
        """価格不一致を記録"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、価格不一致を記録しません: {site_property_id}")
            return
            
        try:
            sql = text("""
                INSERT INTO price_mismatch_history 
                (source_site, site_property_id, property_url, list_price, detail_price, retry_after)
                VALUES (:source_site, :site_property_id, :url, :list_price, :detail_price, 
                        NOW() + INTERVAL ':retry_days days')
                ON CONFLICT (source_site, site_property_id) 
                DO UPDATE SET 
                    list_price = :list_price,
                    detail_price = :detail_price,
                    attempted_at = NOW(),
                    retry_after = NOW() + INTERVAL ':retry_days days',
                    is_resolved = false
            """.replace(':retry_days', str(retry_days)))
            
            self.session.execute(sql, {
                'source_site': self.source_site.value,
                'site_property_id': site_property_id,
                'url': url,
                'list_price': list_price,
                'detail_price': detail_price
            })
            self.session.commit()
            
            self.logger.warning(
                f"価格不一致を記録 - ID: {site_property_id}, "
                f"一覧: {list_price}万円, 詳細: {detail_price}万円, "
                f"{retry_days}日間再取得をスキップ"
            )
            
        except Exception as e:
            self.logger.error(f"価格不一致記録中のエラー: {e}")
            self.session.rollback()
    
    
    
    def _is_paused(self) -> bool:
        """一時停止状態かどうかを確認（ファイルベースとメモリベース両方）"""
        # メモリベースのフラグチェック
        if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
            return True
        
        # ファイルベースのフラグチェック
        if hasattr(self, '_task_id') and self._task_id:
            pause_flags_dir = '/app/data/pause_flags'
            # タスク全体の一時停止ファイル
            task_pause_file = os.path.join(pause_flags_dir, f"{self._task_id}.pause")
            # スクレイパー個別の一時停止ファイル
            scraper_key = self.source_site.value.lower().replace(' ', '_').replace("'s", '')
            scraper_pause_file = os.path.join(pause_flags_dir, f"{self._task_id}_{scraper_key}.pause")
            
            if os.path.exists(task_pause_file) or os.path.exists(scraper_pause_file):
                return True
        
        return False
    
    def _is_cancelled(self) -> bool:
        """キャンセル状態かどうかを確認（メモリベースとデータベース両方）"""
        # メモリベースのフラグチェック
        if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
            return True
        
        # データベースベースのチェック（タスクIDがある場合）
        if hasattr(self, '_task_id') and self._task_id:
            try:
                from ..models_scraping_task import ScrapingTask
                task = self.session.query(ScrapingTask).filter(
                    ScrapingTask.task_id == self._task_id
                ).first()
                
                # タスクが存在しない場合は即座に停止
                if not task:
                    self.logger.error(f"タスク {self._task_id} がデータベースに存在しません。スクレイピングを停止します。")
                    return True
                
                # タスクの状態をチェック
                if task.status == 'cancelled':
                    self.logger.warning(f"タスク {self._task_id} がキャンセルされました。スクレイピングを停止します。")
                    return True
                elif task.status == 'paused':
                    # 一時停止状態の場合は停止しない（一時停止処理は別途実行される）
                    return False
                elif task.status in ['completed', 'error']:
                    self.logger.warning(f"タスク {self._task_id} の状態が '{task.status}' です。スクレイピングを停止します。")
                    return True
                elif task.status != 'running':
                    # その他の未知の状態
                    self.logger.warning(f"タスク {self._task_id} の状態が不正です: '{task.status}'。スクレイピングを停止します。")
                    return True
                    
            except Exception as e:
                self.logger.debug(f"Failed to check task cancellation status: {e}")
        
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
            
            # 詳細取得していない場合（新規物件なのに詳細取得失敗など）は妥当性チェックをスキップ
            if not property_data.get('detail_fetched', False):
                # 詳細取得失敗の場合は既にエラーカウント済みなので、ここでは追加カウントしない
                property_data['property_saved'] = False
                return False
            
            # データの妥当性チェック（詳細取得済みの場合のみ）
            if not self.validate_property_data(property_data):
                # 失敗理由の特定とログ記録
                url = property_data.get('url', '不明')
                failure_reason = ""
                validation_error_type = None
                validation_error_details = {}
                
                if not property_data.get('price'):
                    self._scraping_stats['price_missing'] += 1
                    failure_reason = "価格情報なし"
                    # フィールドエラーを記録
                    self.record_field_extraction_error('price', url, log_error=False)
                elif not property_data.get('building_name'):
                    self._scraping_stats['building_info_missing'] += 1
                    failure_reason = "建物名なし"
                    # フィールドエラーを記録
                    self.record_field_extraction_error('building_name', url, log_error=False)
                elif not property_data.get('site_property_id'):
                    self._scraping_stats['other_errors'] += 1
                    failure_reason = "サイト物件IDなし"
                    # フィールドエラーを記録
                    self.record_field_extraction_error('site_property_id', url, log_error=False)
                    # 詳細なデバッグ情報
                    self.logger.error(
                        f"サイト物件ID取得失敗 - URL: {url}, "
                        f"source_site: {self.source_site}, "
                        f"building_name: {property_data.get('building_name', '不明')}"
                    )
                elif not property_data.get('address') and property_data.get('detail_fetched', False):
                    # 詳細取得後も住所がない場合
                    self._scraping_stats['other_errors'] += 1
                    failure_reason = "詳細取得後も住所情報なし"
                    # フィールドエラーを記録
                    self.record_field_extraction_error('address', url, log_error=False)
                    # 詳細なデバッグ情報
                    self.logger.error(
                        f"住所取得失敗の詳細 - URL: {url}, "
                        f"source_site: {self.source_site}, "
                        f"building_name: {property_data.get('building_name', '不明')}, "
                        f"detail_fetched: {property_data.get('detail_fetched', False)}"
                    )
                else:
                    self._scraping_stats['other_errors'] += 1
                    missing_fields = []
                    # 面積と間取りもチェック
                    if not property_data.get('area'):
                        missing_fields.append('area')
                        self.record_field_extraction_error('area', url, log_error=False)
                    if not property_data.get('layout'):
                        missing_fields.append('layout')
                        self.record_field_extraction_error('layout', url, log_error=False)
                    
                    if missing_fields:
                        failure_reason = f"必須情報不足: {', '.join(missing_fields)}"
                    else:
                        # validate_property_dataでFalseが返されたが、個別チェックを通過した場合
                        # 検証エラーの詳細を取得
                        validation_errors = property_data.get('_validation_errors', [])
                        if validation_errors:
                            failure_reason = f"データ検証失敗: {'; '.join(validation_errors)}"
                        else:
                            failure_reason = "データ検証失敗（詳細はログ参照）"
                        # validate_property_dataで設定されたエラータイプを取得
                        validation_error_type = property_data.get('_validation_error_type', 'validation_failed')
                        # 追加の詳細情報を出力
                        self.logger.error(
                            f"データ検証失敗の追加情報 - "
                            f"URL: {url}, "
                            f"site_property_id: {property_data.get('site_property_id', 'なし')}, "
                            f"address: {property_data.get('address', 'なし')}, "
                            f"detail_fetched: {property_data.get('detail_fetched', False)}, "
                            f"価格: {property_data.get('price', 'なし')}万円, "
                            f"面積: {property_data.get('area', 'なし')}㎡, "
                            f"階数: {property_data.get('floor_number', 'なし')}階"
                        )
                    
                    # デバッグ情報を出力
                    self.logger.warning(
                        f"物件データ検証失敗 - URL: {url}, "
                        f"price: {property_data.get('price')}, "
                        f"building_name: {property_data.get('building_name')}, "
                        f"area: {property_data.get('area')}, "
                        f"layout: {property_data.get('layout')}, "
                        f"site_property_id: {property_data.get('site_property_id', 'なし')}"
                    )
                
                # エラーログを記録
                self.logger.error(f"物件保存失敗 - {failure_reason}: URL={url}")
                print(f"  → 保存失敗: {failure_reason} (URL: {url})")
                
                # 検証エラーの場合、再取得制御用に記録
                if validation_error_type and url and url != '不明':
                    # 面積超過の詳細情報を収集
                    if 'area_exceeded' in validation_error_type:
                        validation_error_details = {
                            'area': property_data.get('area'),
                            'building_name': property_data.get('building_name', ''),
                            'price': property_data.get('price', ''),
                            'failure_reason': failure_reason
                        }
                    self._handle_validation_error(url, validation_error_type, validation_error_details)
                
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
            listing, update_type, update_details = self.create_or_update_listing(
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
                agency_tel=property_data.get('agency_tel'),
                # 建物名を追加（物件独自の表示用建物名の多数決に使用）
                listing_building_name=property_data.get('building_name'),
                # 掲載サイトごとの物件属性
                listing_floor_number=property_data.get('floor_number'),
                listing_area=property_data.get('area'),
                listing_layout=property_data.get('layout'),
                listing_direction=property_data.get('direction'),
                listing_total_floors=property_data.get('total_floors'),
                listing_balcony_area=property_data.get('balcony_area'),
                listing_address=property_data.get('address')
            )
            
            # 更新タイプをproperty_dataに設定（外部で使用するため）
            property_data['update_type'] = update_type
            property_data['update_details'] = update_details
            
            # 保存成功フラグを設定
            property_data['property_saved'] = True
            
            # 画像を追加
            if property_data.get('images'):
                self.add_property_images(listing, property_data['images'])
            
            # サブクラス固有の処理のためのフック
            self._post_listing_creation_hook(listing, property_data)
            
            # 定期的にコミット（並列実行時はスキップ）
            if hasattr(self, '_property_count') and self._property_count % 10 == 0:
                # autoflushが有効な場合のみコミット
                if self.session.autoflush:
                    try:
                        self.session.commit()
                    except Exception as e:
                        self.logger.warning(f"定期コミットエラー: {e}")
            
            return True
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            # トランザクションエラーの場合はロールバック
            if self.session:
                try:
                    self.session.rollback()
                except:
                    pass
            
            # トランザクションエラーの場合は詳細ログを出さない
            if "current transaction is aborted" not in str(e) and "InFailedSqlTransaction" not in str(e):
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
    
    def _has_recent_field_error(self, field_name: str, url: str) -> bool:
        """特定フィールドで最近（24時間以内）にエラーが記録されているかチェック"""
        if field_name not in self._field_error_cache:
            return False
        
        if url in self._field_error_cache[field_name]:
            error_time = self._field_error_cache[field_name][url]
            hours_since_error = (datetime.now() - error_time).total_seconds() / 3600
            # 24時間以内のエラーは既知として扱う
            return hours_since_error < 24
        return False
    
    def _record_field_error(self, field_name: str, url: str):
        """フィールド別のエラーを記録"""
        if field_name not in self._field_error_cache:
            self._field_error_cache[field_name] = {}
        
        self._field_error_cache[field_name][url] = datetime.now()
        
        # キャッシュサイズ管理（各フィールドで500件まで）
        if len(self._field_error_cache[field_name]) > 500:
            now = datetime.now()
            old_urls = [
                u for u, t in self._field_error_cache[field_name].items()
                if (now - t).total_seconds() > 86400  # 24時間
            ]
            for u in old_urls:
                del self._field_error_cache[field_name][u]
    
    def has_critical_field_errors(self, url: str, critical_fields: Optional[List[str]] = None) -> bool:
        """重要項目でエラーが発生している物件かチェック
        
        Args:
            url: チェック対象のURL
            critical_fields: 重要フィールドのリスト（未指定の場合はデフォルト値を使用）
        
        Returns:
            エラーがある場合True
        """
        if critical_fields is None:
            # デフォルトの重要フィールド（各スクレイパーでオーバーライド可能）
            critical_fields = ['price', 'building_name', 'area', 'layout']
        
        for field in critical_fields:
            if self._has_recent_field_error(field, url):
                return True
        return False
    
    
    def check_critical_error_threshold(self) -> bool:
        """重要フィールドのエラー率をチェックし、閾値を超えた場合は例外を発生
        
        Returns:
            bool: 閾値を超えた場合True
        """
        # 重要フィールドのリスト（階数、面積、築年月を含む）
        critical_fields = ['floor_number', 'area', 'built_year', 'price', 'building_name']
        
        # 処理済み物件数が少ない場合はチェックしない
        if self._scraping_stats['properties_attempted'] < 5:
            return False
        
        # フィールド別のエラー率をチェック
        for field in critical_fields:
            error_count = self._scraping_stats.get('html_structure_errors', {}).get(field, 0)
            new_error_count = self._scraping_stats.get('html_structure_errors_new', {}).get(field, 0)
            
            # エラー率を計算
            error_rate = error_count / self._scraping_stats['properties_attempted']
            
            # 新規エラーが多い場合は特に警戒
            if new_error_count >= self._error_thresholds['consecutive_errors']:
                self.logger.critical(
                    f"重要フィールド '{field}' で連続{new_error_count}件の新規エラーを検出。"
                    f"HTML構造が変更された可能性があります。"
                )
                # 管理者への通知用にエラー情報を記録
                self._record_critical_error_alert(field, new_error_count, error_rate)
                return True
            
            # エラー率が閾値を超えた場合
            if error_rate >= self._error_thresholds['critical_error_rate'] and error_count >= self._error_thresholds['critical_error_count']:
                self.logger.critical(
                    f"重要フィールド '{field}' のエラー率が{error_rate:.1%}に達しました。"
                    f"（閾値: {self._error_thresholds['critical_error_rate']:.1%}）"
                )
                # 管理者への通知用にエラー情報を記録
                self._record_critical_error_alert(field, error_count, error_rate)
                return True
        
        return False
    
    def _record_critical_error_alert(self, field_name: str, error_count: int, error_rate: float):
        """重大エラーアラートをデータベースに記録
        
        Args:
            field_name: エラーが発生したフィールド名
            error_count: エラー件数
            error_rate: エラー率
        """
        try:
            from sqlalchemy import text
            
            sql = text("""
                INSERT INTO scraper_alerts 
                (source_site, alert_type, field_name, error_count, error_rate, message, created_at)
                VALUES 
                (:source_site, 'critical_field_error', :field_name, :error_count, :error_rate, :message, NOW())
            """)
            
            message = (
                f"{self.source_site}のスクレイパーで重要フィールド'{field_name}'の"
                f"エラー率が{error_rate:.1%}（{error_count}件）に達しました。"
                f"HTML構造の変更を確認してください。"
            )
            
            self.session.execute(sql, {
                'source_site': self.source_site,
                'field_name': field_name,
                'error_count': error_count,
                'error_rate': error_rate,
                'message': message
            })
            self.session.commit()
            
        except Exception as e:
            self.logger.error(f"アラート記録エラー: {e}")
            # テーブルが存在しない場合は作成を試みる
            if "relation \"scraper_alerts\" does not exist" in str(e):
                self._create_scraper_alerts_table()
                # リトライ
                try:
                    self.session.execute(sql, {
                        'source_site': self.source_site,
                        'field_name': field_name,
                        'error_count': error_count,
                        'error_rate': error_rate,
                        'message': message
                    })
                    self.session.commit()
                except Exception as retry_e:
                    self.logger.error(f"アラート記録リトライエラー: {retry_e}")
    
    def _create_scraper_alerts_table(self):
        """scraper_alertsテーブルを作成"""
        try:
            from sqlalchemy import text
            
            sql = text("""
                CREATE TABLE IF NOT EXISTS scraper_alerts (
                    id SERIAL PRIMARY KEY,
                    source_site VARCHAR(50) NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    field_name VARCHAR(50),
                    error_count INTEGER,
                    error_rate FLOAT,
                    message TEXT,
                    is_resolved BOOLEAN DEFAULT FALSE,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_scraper_alerts_unresolved 
                ON scraper_alerts(is_resolved, created_at DESC);
            """)
            
            self.session.execute(sql)
            self.session.commit()
            self.logger.info("scraper_alertsテーブルを作成しました")
            
        except Exception as e:
            self.logger.error(f"scraper_alertsテーブル作成エラー: {e}")
    
    def track_selector_usage(self, soup: BeautifulSoup, selector: str, field_name: str, required: bool = True) -> Optional[any]:
        """セレクタの使用を追跡し、要素を返す
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            field_name: フィールド名（ログ用）
            required: 必須要素かどうか
            
        Returns:
            見つかった要素（なければNone）
        """
        # セレクタ統計を初期化
        if selector not in self._selector_stats:
            self._selector_stats[selector] = {'success': 0, 'fail': 0, 'field': field_name}
        
        # 要素を検索
        element = soup.select_one(selector)
        
        if element:
            self._selector_stats[selector]['success'] += 1
            return element
        else:
            self._selector_stats[selector]['fail'] += 1
            
            # 必須要素が見つからない場合
            if required:
                fail_rate = self._selector_stats[selector]['fail'] / (
                    self._selector_stats[selector]['success'] + self._selector_stats[selector]['fail']
                )
                
                # エラー率が高い場合は警告
                if fail_rate > 0.5 and self._selector_stats[selector]['fail'] >= 5:
                    self.logger.warning(
                        f"セレクタ '{selector}' ({field_name}) の失敗率が{fail_rate:.0%}に達しました。"
                        f"HTML構造が変更された可能性があります。"
                    )
                    
                    # ページ構造エラーをカウント
                    self._page_structure_errors += 1
                    
                    # 連続でページ構造エラーが発生した場合
                    if self._page_structure_errors >= 3:
                        self._record_structure_change_alert(selector, field_name, fail_rate)
                        raise Exception(
                            f"HTML構造の変更を検出しました。"
                            f"セレクタ '{selector}' ({field_name}) が連続して見つかりません。"
                        )
            
            return None
    
    def track_selector_all(self, soup: BeautifulSoup, selector: str, field_name: str, min_expected: int = 1) -> List[any]:
        """複数要素のセレクタ使用を追跡
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            field_name: フィールド名（ログ用）
            min_expected: 期待される最小要素数
            
        Returns:
            見つかった要素のリスト
        """
        # セレクタ統計を初期化
        if selector not in self._selector_stats:
            self._selector_stats[selector] = {'success': 0, 'fail': 0, 'field': field_name}
        
        # 要素を検索
        elements = soup.select(selector)
        
        if len(elements) >= min_expected:
            self._selector_stats[selector]['success'] += 1
            return elements
        else:
            self._selector_stats[selector]['fail'] += 1
            
            fail_rate = self._selector_stats[selector]['fail'] / (
                self._selector_stats[selector]['success'] + self._selector_stats[selector]['fail']
            )
            
            # エラー率が高い場合は警告
            if fail_rate > 0.5 and self._selector_stats[selector]['fail'] >= 5:
                self.logger.warning(
                    f"セレクタ '{selector}' ({field_name}) で期待される要素数が不足。"
                    f"期待: {min_expected}個以上、実際: {len(elements)}個"
                )
                
                # ページ構造エラーをカウント
                self._page_structure_errors += 1
                
                # 連続でページ構造エラーが発生した場合
                if self._page_structure_errors >= 3:
                    self._record_structure_change_alert(selector, field_name, fail_rate)
                    raise Exception(
                        f"HTML構造の変更を検出しました。"
                        f"セレクタ '{selector}' ({field_name}) で十分な要素が見つかりません。"
                    )
            
            return elements
    
    def _record_structure_change_alert(self, selector: str, field_name: str, fail_rate: float):
        """HTML構造変更アラートを記録"""
        try:
            message = (
                f"{self.source_site}のスクレイパーでHTML構造の変更を検出しました。"
                f"セレクタ '{selector}' ({field_name}) の失敗率: {fail_rate:.0%}"
            )
            
            self._record_critical_error_alert(
                field_name=f"structure_{field_name}",
                error_count=self._selector_stats[selector]['fail'],
                error_rate=fail_rate
            )
        except Exception as e:
            self.logger.error(f"構造変更アラート記録エラー: {e}")
    
    def validate_page_structure(self, soup: BeautifulSoup, page_type: str = 'detail') -> bool:
        """ページの基本構造を検証
        
        Args:
            soup: BeautifulSoupオブジェクト
            page_type: 'list' または 'detail'
            
        Returns:
            構造が正常な場合True
        """
        # ページが空でないかチェック
        if not soup or not soup.body:
            self.logger.error(f"{page_type}ページが空です")
            return False
        
        # 基本的なHTMLタグの存在確認
        basic_tags = ['html', 'head', 'body']
        for tag in basic_tags:
            if not soup.find(tag):
                self.logger.error(f"{page_type}ページに{tag}タグがありません")
                return False
        
        # エラーページでないかチェック（一般的なエラーパターン）
        error_patterns = [
            'ページが見つかりません',
            '404',
            'Not Found',
            'エラーが発生しました',
            'メンテナンス中',
            '一時的にアクセスできません'
        ]
        
        page_text = soup.get_text()
        for pattern in error_patterns:
            if pattern in page_text:
                self.logger.warning(f"{page_type}ページがエラーページの可能性があります: {pattern}")
                return False
        
        return True
    
    def _is_maintenance_page(self, soup: BeautifulSoup) -> bool:
        """メンテナンスページかどうかを判定"""
        # メンテナンスを示すパターン
        maintenance_patterns = [
            'メンテナンス中',
            'システムメンテナンス',
            'サービス停止中',
            '一時的にサービスを停止',
            'maintenance',
            'service unavailable',
            'サイトメンテナンス',
            'アクセスが集中して',
            '混雑している',
            'しばらくお待ちください'
        ]
        
        page_text = soup.get_text().lower()
        for pattern in maintenance_patterns:
            if pattern.lower() in page_text:
                return True
        
        # titleタグもチェック
        title = soup.find('title')
        if title and title.text:
            title_text = title.text.lower()
            for pattern in maintenance_patterns:
                if pattern.lower() in title_text:
                    return True
        
        return False
    
    def track_missing_element(self, element_name: str, is_critical: bool = False):
        """重要なHTML要素の欠落を記録
        
        Args:
            element_name: 要素の説明（例: "価格テーブル", "物件情報セクション"）
            is_critical: 致命的な欠落かどうか
        """
        # 統計を更新
        if element_name not in self._scraping_stats['missing_elements']:
            self._scraping_stats['missing_elements'][element_name] = 0
        self._scraping_stats['missing_elements'][element_name] += 1
        
        count = self._scraping_stats['missing_elements'][element_name]
        
        # 連続して欠落している場合は警告
        if count >= 3:
            self.logger.warning(
                f"重要な要素 '{element_name}' が{count}回連続で見つかりません。"
                f"HTML構造が変更された可能性があります。"
            )
            
            # 致命的な要素が5回連続で欠落した場合
            if is_critical and count >= 5:
                self._record_critical_error_alert(
                    field_name=f"missing_{element_name}",
                    error_count=count,
                    error_rate=1.0  # 100%欠落
                )
                raise Exception(
                    f"致命的なHTML構造の変更を検出しました。"
                    f"'{element_name}' が{count}回連続で見つかりません。"
                )
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """site_property_idの妥当性を検証（共通部分）
        
        各スクレイパーでオーバーライドして、サイト固有の検証を追加してください。
        
        Args:
            site_property_id: 検証するID
            url: 物件URL（エラーログ用）
            
        Returns:
            bool: 妥当な場合True
        """
        if not site_property_id:
            self.logger.error(f"site_property_idが空です: URL={url}")
            return False
            
        # 明らかに不正な値の検証（共通）
        invalid_values = [
            'index', 'detail', 'property', 'mansion',
            'index.html', 'detail.html', 'property.html'
        ]
        
        if site_property_id.lower() in invalid_values:
            self.logger.error(
                f"site_property_idが不正な値です: '{site_property_id}' URL={url}"
            )
            return False
                
        # 最小長チェック（通常、物件IDは最低でも3文字以上）
        if len(site_property_id) < 3:
            self.logger.error(
                f"site_property_idが短すぎます: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            return False
            
        return True
    
    def validate_list_page_fields(self, property_data: Dict[str, Any]) -> bool:
        """一覧ページで取得した物件データの必須フィールドを検証
        
        一覧ページでは以下のフィールドが必須：
        - url: 詳細ページのURL
        - site_property_id: サイト内物件ID
        - price: 価格
        
        Args:
            property_data: 物件データ
            
        Returns:
            bool: 必須フィールドがすべて存在する場合True
        """
        required_fields = ['url', 'site_property_id', 'price']
        missing_fields = []
        
        for field in required_fields:
            if field not in property_data or property_data.get(field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            self.logger.warning(f"一覧ページで必須フィールドが取得できませんでした: {', '.join(missing_fields)}")
            return False
        
        return True
    
    def log_validation_error_and_return_none(self, property_data: Dict[str, Any], url: str, error_type: str = "詳細ページ検証エラー") -> None:
        """検証エラーの詳細を記録して None を返すヘルパーメソッド
        
        Args:
            property_data: 検証対象の物件データ
            url: 物件URL
            error_type: エラータイプ（デフォルト: "詳細ページ検証エラー"）
            
        Returns:
            None（常にNoneを返すため、return文で直接使用可能）
        """
        # フィールド名の日本語マッピング
        field_names_jp = {
            'site_property_id': '物件ID',
            'price': '価格',
            'building_name': '建物名',
            'address': '住所',
            'area': '面積',
            'layout': '間取り'
        }
        
        missing_fields = []
        missing_fields_jp = []
        required_fields = ['site_property_id', 'price', 'building_name', 'address', 'area', 'layout']
        for field in required_fields:
            if field not in property_data or property_data.get(field) is None:
                missing_fields.append(field)
                missing_fields_jp.append(field_names_jp.get(field, field))
        
        # エラー情報を保存（process_property_with_detail_checkで使用）
        self._last_detail_error = {
            'type': 'validation',
            'reason': f"{error_type}: 必須フィールド（{', '.join(missing_fields_jp)}）が取得できませんでした",
            'building_name': property_data.get('building_name', ''),
            'price': property_data.get('price', ''),
            'site_property_id': property_data.get('site_property_id', ''),
        }
        
        # ログにも出力（開発者向けは英語フィールド名も含める）
        self.logger.error(f"{error_type}: {url} - 必須フィールドが取得できませんでした: {', '.join(missing_fields)} ({', '.join(missing_fields_jp)})")
        
        return None
    
    def validate_detail_page_fields(self, property_data: Dict[str, Any], url: str = None) -> bool:
        """詳細ページで取得した物件データの必須フィールドを検証
        
        詳細ページでは以下のフィールドが必須：
        - site_property_id: サイト内物件ID（URLから抽出）
        - price: 価格
        - building_name: 建物名
        - address: 住所
        - area: 専有面積
        - layout: 間取り
        
        Args:
            property_data: 物件データ
            url: 物件URL（エラーログ用）
            
        Returns:
            bool: 必須フィールドがすべて存在する場合True
        """
        required_fields = ['site_property_id', 'price', 'building_name', 'address', 'area', 'layout']
        missing_fields = []
        
        for field in required_fields:
            if field not in property_data or property_data.get(field) is None:
                missing_fields.append(field)
        
        if missing_fields:
            url = url or property_data.get('url', '不明')
            for field in missing_fields:
                self.record_field_extraction_error(field, url)
            
            self.logger.error(f"詳細ページで必須フィールドが取得できませんでした: {', '.join(missing_fields)} - URL: {url}")
            return False
        
        return True
    
    
    def record_field_extraction_error(self, field_name: str, url: str, log_error: bool = True):
        """フィールド抽出エラーを記録し、統計を更新
        
        Args:
            field_name: フィールド名
            url: 物件URL
            log_error: エラーログを出力するか
        """
        # 新規エラーかチェック
        is_new_error = not self._has_recent_field_error(field_name, url)
        
        # エラーを記録
        self._record_field_error(field_name, url)
        
        # 統計を更新
        if 'html_structure_errors' not in self._scraping_stats:
            self._scraping_stats['html_structure_errors'] = {}
        if field_name not in self._scraping_stats['html_structure_errors']:
            self._scraping_stats['html_structure_errors'][field_name] = 0
        self._scraping_stats['html_structure_errors'][field_name] += 1
        
        if is_new_error:
            if 'html_structure_errors_new' not in self._scraping_stats:
                self._scraping_stats['html_structure_errors_new'] = {}
            if field_name not in self._scraping_stats['html_structure_errors_new']:
                self._scraping_stats['html_structure_errors_new'][field_name] = 0
            self._scraping_stats['html_structure_errors_new'][field_name] += 1
            
            if log_error:
                self.logger.error(
                    f"{field_name}が取得できませんでした。"
                    f"HTML構造の確認が必要です: {url}"
                )
        else:
            if log_error:
                self.logger.debug(f"{field_name}取得エラー（既知）: {url}")
    
    def log_detailed_error(self, error_type: str, url: str, exception: Exception, additional_info: Dict[str, Any] = None):
        """詳細なエラーログを出力する共通メソッド
        
        Args:
            error_type: エラーの種類（例: "詳細ページ解析エラー"）
            url: エラーが発生したURL
            exception: 発生した例外
            additional_info: 追加情報（任意）
        """
        import traceback
        
        # エラーメッセージを構築
        error_msg = f"{error_type}: {url} - {type(exception).__name__}: {str(exception)}"
        self.logger.error(error_msg)
        
        # スタックトレースを出力
        self.logger.error(f"詳細なスタックトレース:\n{traceback.format_exc()}")
        
        # 追加情報があれば出力
        if additional_info:
            self.logger.error(f"追加情報: {additional_info}")
        
        # エラーログを保存
        if hasattr(self, '_save_error_log'):
            error_info = {
                'url': url,
                'reason': error_msg,
                'error_type': type(exception).__name__,
                'error_detail': str(exception),
                'source_site': self.source_site.value,
                'timestamp': datetime.now().isoformat()
            }
            if additional_info:
                error_info.update(additional_info)
            self._save_error_log(error_info)
    
    def _save_error_log(self, error_info: Dict[str, Any]):
        """エラーログを保存（並列スクレイピングマネージャーと連携）"""
        self.logger.info(f"_save_error_log呼び出し: {error_info}")
        
        if hasattr(self, 'scraping_manager') and self.scraping_manager:
            # タスクIDを取得
            task_id = getattr(self, 'task_id', None)
            self.logger.info(f"task_id: {task_id}, scraping_manager: {self.scraping_manager}")
            
            if task_id:
                # エラーログエントリを作成（空文字やNoneを適切に処理）
                # エラーの詳細を含めたreasonを構築
                reason = error_info.get('reason') or '不明なエラー'
                # error_detailがreasonに既に含まれている場合は追加しない
                if error_info.get('error_detail') and error_info['error_detail'] not in reason:
                    if error_info.get('error_type'):
                        reason = f"{reason} - {error_info['error_type']}: {error_info['error_detail']}"
                    else:
                        reason = f"{reason}: {error_info['error_detail']}"
                elif error_info.get('error_type') and error_info['error_type'] not in reason:
                    reason = f"{reason} - {error_info['error_type']}"
                
                error_entry = {
                    'timestamp': error_info.get('timestamp', datetime.now().isoformat()),
                    'scraper': self.source_site.value,
                    'url': error_info.get('url') or '不明',
                    'reason': reason,
                    'building_name': error_info.get('building_name') or '',
                    'price': str(error_info.get('price', '')) if error_info.get('price') is not None else ''
                }
                # マネージャーのadd_error_logメソッドを呼び出す
                self.logger.info(f"add_error_log呼び出し: {error_entry}")
                self.scraping_manager.add_error_log(task_id, error_entry)
            else:
                self.logger.warning("task_idが設定されていません")
        else:
            self.logger.warning(f"scraping_managerが設定されていません: hasattr={hasattr(self, 'scraping_manager')}")
    
    def _save_warning_log(self, warning_info: Dict[str, Any]):
        """警告ログを保存（並列スクレイピングマネージャーと連携）"""
        self.logger.info(f"_save_warning_log呼び出し: {warning_info}")
        
        if hasattr(self, 'scraping_manager') and self.scraping_manager:
            # タスクIDを取得
            task_id = getattr(self, 'task_id', None)
            self.logger.info(f"task_id: {task_id}, scraping_manager: {self.scraping_manager}")
            
            if task_id:
                # 警告ログエントリを作成
                warning_entry = {
                    'timestamp': warning_info.get('timestamp', datetime.now().isoformat()),
                    'scraper': self.source_site.value,
                    'url': warning_info.get('url', '不明'),
                    'reason': warning_info.get('reason', '警告'),
                    'building_name': warning_info.get('building_name', ''),
                    'price': warning_info.get('price', ''),
                    'site_property_id': warning_info.get('site_property_id', '')
                }
                # マネージャーのadd_warning_logメソッドを呼び出す（存在する場合）
                if hasattr(self.scraping_manager, 'add_warning_log'):
                    self.logger.info(f"add_warning_log呼び出し: {warning_entry}")
                    self.scraping_manager.add_warning_log(task_id, warning_entry)
                else:
                    # 警告ログメソッドがない場合は、エラーログとして保存（互換性のため）
                    self.logger.info(f"add_warning_logがないため、add_error_log呼び出し: {warning_entry}")
                    self.scraping_manager.add_error_log(task_id, warning_entry)
            else:
                self.logger.warning("task_idが設定されていません")
        else:
            self.logger.warning(f"scraping_managerが設定されていません: hasattr={hasattr(self, 'scraping_manager')}")

    def _post_listing_creation_hook(self, listing: PropertyListing, property_data: Dict[str, Any]):
        """掲載情報作成後のフック（サブクラスでオーバーライド可能）"""
        pass

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