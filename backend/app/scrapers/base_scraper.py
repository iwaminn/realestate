import re
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
from contextlib import contextmanager
import os
import json
from abc import ABC, abstractmethod
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text, Table, MetaData
import jaconv
from difflib import SequenceMatcher

from .constants import SourceSite
from ..config.scraping_config import PAUSE_TIMEOUT_SECONDS
from ..database import SessionLocal
from enum import Enum
from ..models import (
    Building, MasterProperty, PropertyListing, 
    ListingPriceHistory, BuildingExternalId, Url404Retry
)
from ..utils.building_normalizer import BuildingNameNormalizer
from ..utils.building_name_normalizer import (
    normalize_building_name as normalize_building_name_common,
    get_search_key_for_building as get_search_key_for_building_common,
    extract_room_number as extract_room_number_common
)
from ..utils.property_utils import update_earliest_listing_date
from ..utils.fuzzy_property_matcher import FuzzyPropertyMatcher

# BuildingListingNameManagerは循環インポートを避けるため遅延インポート
from ..utils.exceptions import TaskPausedException, TaskCancelledException, MaintenanceException
from ..utils.datetime_utils import get_utc_now
import time as time_module
from ..utils.debug_logger import debug_log
from .building_external_id_handler import BuildingExternalIdHandler


class BuildingNameVerificationMode(Enum):
    """建物名検証モード"""
    STRICT = "strict"  # 厳密一致（一覧と詳細が一致しない場合はエラー）
    PARTIAL = "partial"  # 部分一致（類似度で判定）
    MULTI_SOURCE = "multi_source"  # 複数箇所検証（詳細ページの複数箇所が一致すればOK）


class BaseScraper(ABC):
    """
    スクレイパーの基底クラス
    
    必須実装メソッド:
    - fetch_page(url): ページを取得してBeautifulSoupオブジェクトを返す
    - get_search_url(area, page): 検索URLを生成
    - parse_property_list(soup): 物件一覧をパース
    - parse_property_detail(soup, property_data): 物件詳細をパース
    
    オプショナルメソッド（サブクラスで実装可能）:
    - is_last_page(soup): 現在のページが最終ページかどうかを判定
        Returns: bool - 最終ページの場合True
        実装すると、404エラーを出す前にページング処理を終了できる
    - get_max_page_from_list(soup): 一覧ページから最大ページ数を取得
        Returns: Optional[int] - 最大ページ数
    """
    
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
    
    @contextmanager
    def transaction_scope(self):
        """
        トランザクションスコープを管理するコンテキストマネージャー
        
        使用例:
            with self.transaction_scope() as session:
                # データベース操作
                pass
            # ここで自動的にcommit/rollback/closeされる
        """
        from ..database import get_db_for_scraping
        session = get_db_for_scraping()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            # エラーはログに記録するが、再スローして呼び出し元で処理
            self.logger.debug(f"トランザクションエラー（ロールバック済み）: {e}")
            raise
        finally:
            session.close()

    def _handle_transaction_error(self, error: Exception, context: str) -> bool:
        """
        トランザクションエラーを処理する共通メソッド
        
        Args:
            error: 発生した例外
            context: エラーが発生したコンテキスト（ログ用）
            
        Returns:
            bool: セッションがリセットされた場合True、そうでない場合False
        """
        error_str = str(error)
        
        # InFailedSqlTransactionエラーの場合
        if ("current transaction is aborted" in error_str or 
            "InFailedSqlTransaction" in error_str or
            "rolled back due to a previous exception" in error_str):
            
            self.logger.debug(f"{context}: トランザクションエラーを検出しました（新しいトランザクション管理では自動回復）")
            # 新しいトランザクション管理では、次の操作で自動的に新しいトランザクションが開始される
            return True
        
        # その他のエラーはログに記録
        self.logger.warning(f"{context}: {error}")
        return False
    
    def __init__(self, source_site: Union[str, SourceSite], force_detail_fetch: bool = False, max_properties: Optional[int] = None, ignore_error_history: bool = False, task_id: Optional[str] = None):
        # 文字列の場合はSourceSiteに変換（後方互換性）
        if isinstance(source_site, str):
            self.source_site = SourceSite.from_string(source_site)
        else:
            self.source_site = source_site
        self.force_detail_fetch = force_detail_fetch
        self.max_properties = max_properties
        self.ignore_error_history = ignore_error_history
        
        # タスクID（データベースベースの一時停止・キャンセル管理用）
        self.task_id = task_id
        
        # 建物名の部分一致を許可するかどうか（デフォルト: False = 完全一致のみ）
        self.allow_partial_building_name_match = False
        
        # 建物名検証モード（デフォルト: STRICT）
        self.building_name_verification_mode = BuildingNameVerificationMode.STRICT
        
        # セッションは各メソッドで必要に応じて作成（コンテキストマネージャー使用）
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': self.DEFAULT_USER_AGENT
        })
        # SSL証明書検証の設定（gt-www.livable.co.jpのSSL証明書問題対応）
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.logger = self._setup_logger()
        self.normalizer = BuildingNameNormalizer()
        self.fuzzy_matcher = FuzzyPropertyMatcher()
        # majority_updaterは循環インポート回避のため削除
        # 必要に応じてメソッド内で動的にインポートして使用
        # BuildingExternalIdHandlerは遅延初期化（セッションが必要な時に作成）
        self.external_id_handler = None
        # BuildingListingNameManagerは遅延初期化
        self._listing_name_manager = None
        
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
        self._page_structure_errors = 0  # ページ構造エラーカウント  # ページ構造エラーカウント

    def _ensure_external_id_handler(self, session):
        """external_id_handlerを遅延初期化（必要な時だけ作成）"""
        if self.external_id_handler is None:
            self.external_id_handler = BuildingExternalIdHandler(session, self.logger)
        return self.external_id_handler

    def _check_task_status_from_db(self) -> dict:
        """データベースからタスクの状態を確認（新しいセッションで軽量クエリ）"""
        if not self.task_id:
            return {"is_paused": False, "is_cancelled": False}
        
        from ..models_scraping_task import ScrapingTask
        
        try:
            with self.transaction_scope() as session:
                # 必要なカラムのみ取得（軽量クエリ）
                result = session.query(
                    ScrapingTask.is_paused,
                    ScrapingTask.is_cancelled,
                    ScrapingTask.status
                ).filter(
                    ScrapingTask.task_id == self.task_id
                ).first()
                
                if not result:
                    # タスクが存在しない場合
                    return {"is_paused": False, "is_cancelled": False}
                
                # statusがcancelledの場合もキャンセル扱い
                is_cancelled = result.is_cancelled or result.status == 'cancelled'
                
                return {
                    "is_paused": result.is_paused,
                    "is_cancelled": is_cancelled
                }
                
        except Exception as e:
            self.logger.error(f"データベースからタスク状態を取得中にエラー: {e}")
            # エラー時は安全のため停止しない
            return {"is_paused": False, "is_cancelled": False}
    
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

    def update_stats(self, key: str, value: int = 1) -> None:
        """統計情報を更新"""
        if key not in self._scraping_stats:
            self._scraping_stats[key] = 0
        self._scraping_stats[key] += value
    
    def get_stats(self, key: str, default: Any = None) -> Any:
        """統計情報を取得"""
        return self._scraping_stats.get(key, default)
    
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
                self.log_warning('404 Not Found', url=url)
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
            # 接続エラー情報を保存
            self._last_fetch_error = {
                'type': 'connection_error',
                'error_message': str(e),
                'url': url
            }
            return None
        except requests.exceptions.Timeout as e:
            self.logger.error(f"タイムアウトエラー - サーバーが応答しません: {url} - {type(e).__name__}: {str(e)}")
            # タイムアウトエラー情報を保存
            self._last_fetch_error = {
                'type': 'timeout_error',
                'error_message': str(e),
                'url': url
            }
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"リクエストエラー: {url} - {type(e).__name__}: {str(e)}")
            # リクエストエラー情報を保存
            self._last_fetch_error = {
                'type': 'request_error',
                'error_message': str(e),
                'url': url
            }
            return None
        except Exception as e:
            import traceback
            self.logger.error(f"予期しないエラーが発生しました: {url} - {type(e).__name__}: {str(e)}")
            self.logger.debug(f"詳細なスタックトレース:\n{traceback.format_exc()}")
            # 予期しないエラー情報を保存
            self._last_fetch_error = {
                'type': 'unexpected_error',
                'error_message': str(e),
                'exception_type': type(e).__name__,
                'url': url
            }
            return None

    def _get_detailed_fetch_error_info(self, url: str) -> dict:
        """fetch_pageの失敗時に詳細なエラー情報を取得する
        
        Args:
            url: 取得に失敗したURL
            
        Returns:
            エラー詳細情報の辞書
        """
        error_info = {
            'url': url,
            'site': self.source_site.value
        }
        
        # 最後のfetch_pageエラー情報があれば追加
        if hasattr(self, '_last_fetch_error') and self._last_fetch_error:
            error_data = self._last_fetch_error
            
            if 'status_code' in error_data:
                error_info['http_status'] = error_data['status_code']
                
            if error_data.get('type') == '404':
                error_info['error_type'] = '404 Not Found'
            elif error_data.get('type') == 'http_error':
                error_info['error_type'] = f"HTTP {error_data['status_code']} Error"
            else:
                error_info['error_type'] = error_data.get('type', '不明なエラー')
        else:
            # エラー情報が保存されていない場合
            error_info['error_type'] = 'ネットワークエラーまたは予期しないエラー'
            
        return error_info
    
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
    
    def get_required_detail_fields(self) -> List[str]:
        """詳細ページで必須となるフィールドのリストを返す
        
        基底クラスでは共通必須フィールドを定義。
        派生クラスでオーバーライドして、必要に応じてフィールドを除外できる。
        
        Returns:
            List[str]: 必須フィールドのリスト
        """
        # 共通の必須フィールド（変更不可）
        common_required = ['site_property_id', 'price', 'building_name', 'address', 'area', 'built_year']
        
        # オプショナルなフィールド（派生クラスで除外可能）
        optional_required = self.get_optional_required_fields()
        
        return common_required + optional_required
    
    def get_optional_required_fields(self) -> List[str]:
        """オプショナルな必須フィールドのリストを返す
        
        派生クラスでオーバーライドして、スクレイパー固有の要件に対応できる。
        デフォルトでは間取り(layout)を必須とする。
        
        Returns:
            List[str]: オプショナルな必須フィールドのリスト
        """
        return ['layout']  # デフォルトでは間取りを必須とする

    def get_partial_required_fields(self) -> Dict[str, Dict[str, Any]]:
        """部分的必須フィールドの設定を返す
        
        部分的必須フィールドは、ある程度の欠損を許容するが、
        欠損率が閾値を超えた場合にエラーとするフィールド。
        
        Returns:
            Dict[str, Dict[str, Any]]: フィールド名をキーとする設定辞書
                - max_missing_rate: 許容する最大欠損率（0.0-1.0）
                - min_sample_size: 統計を評価する最小サンプル数
                - empty_values: 空とみなす値のリスト
        """
        return {}  # デフォルトでは部分的必須フィールドなし
    
    def scrape_area(self, area_code: str) -> Dict[str, Any]:
        """エリアの物件をスクレイピングする共通ロジック（価格変更ベースのスマートスクレイピング対応）"""
        self.logger.info(f"スクレイピング開始: エリア={area_code}, 最大物件数={self.max_properties}")
        self.current_area_code = area_code  # 現在スクレイピング中のエリアを記録
        
        # デバッグ：フラグの状態を確認

        
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
            max_page = None  # 最大ページ数（事前に取得できた場合）
            
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
                        # 詳細なエラー情報を含めた警告ログ
                        error_details = self._get_detailed_fetch_error_info(url)
                        self.log_warning(f'ページ {page} の取得に失敗', **error_details)
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_consecutive_empty:
                            self.logger.info("連続してページ取得に失敗したため終了（最終ページを超えた可能性があります）")
                            break
                        page += 1
                        continue
                    
                    # 物件一覧を解析
                    self.logger.info(f"[DEBUG] parse_property_list呼び出し前")
                    debug_log(f"[{self.source_site}] parse_property_list呼び出し前")
                    properties = self.parse_property_list(soup)
                    self.logger.info(f"[DEBUG] parse_property_list呼び出し後: {len(properties) if properties else 0}件")
                    debug_log(f"[{self.source_site}] parse_property_list呼び出し後: {len(properties) if properties else 0}件")
                    
                    # 最初のページで最大ページ数を取得（サブクラスで実装されている場合）
                    if page == 1 and max_page is None:
                        if hasattr(self, 'get_max_page_from_list') and callable(getattr(self, 'get_max_page_from_list')):
                            max_page = self.get_max_page_from_list(soup)
                            if max_page:
                                self.logger.info(f"最大ページ数を取得: {max_page}ページ")
                    
                    # ページ終端の判定フラグ
                    is_final_page = False
                    
                    # 最大ページ数が分かっている場合は、それを超えたら終了
                    if max_page and page >= max_page:
                        self.logger.info(f"最終ページ（{page}/{max_page}ページ）に到達しました")
                        is_final_page = True
                    
                    # サブクラスでページ終端判定メソッドが実装されている場合は使用
                    elif hasattr(self, 'is_last_page') and callable(getattr(self, 'is_last_page')):
                        if self.is_last_page(soup):
                            self.logger.info(f"最終ページ（{page}ページ）を検出しました")
                            is_final_page = True
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
                    
                    # 最終ページの場合は、現在のページの物件を処理した後で終了
                    if is_final_page:
                        self.logger.info(f"最終ページのため、このページの処理後に収集を終了します")
                        break
                    
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
                    self.log_error(str(e), url=url)
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
                    self.log_warning(f'物件 {i+1}: URLがありません')
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
                    
                    # 新しいセッションを作成して確認
                    from ..database import get_db_for_scraping
                    db_session = get_db_for_scraping()
                    try:
                        if site_property_id:
                            self.logger.info(f"[DEBUG] DB確認中: site_property_id={site_property_id}")
                            existing_listing = db_session.query(PropertyListing).filter(
                                PropertyListing.site_property_id == site_property_id,
                                PropertyListing.source_site == self.source_site
                            ).first()
                            self.logger.info(f"[DEBUG] DB確認完了: existing={existing_listing is not None}")
                        else:
                            # site_property_idがない場合は従来通りURLで検索（後方互換性）
                            self.logger.info(f"[DEBUG] site_property_idがないためURLで確認: {property_data['url']}")
                            existing_listing = db_session.query(PropertyListing).filter(
                                PropertyListing.url == property_data['url'],
                                PropertyListing.source_site == self.source_site
                            ).first()
                            self.logger.info(f"[DEBUG] DB確認完了: existing={existing_listing is not None}")
                    finally:
                        db_session.close()
                    
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
                            # 新しいトランザクションスコープで更新
                            from ..database import get_db_for_scraping
                            update_session = get_db_for_scraping()
                            try:
                                # existing_listingのIDを保存
                                listing_id = existing_listing.id
                                listing_master_property_id = existing_listing.master_property_id
                                
                                # セッションから再取得
                                existing_listing = update_session.query(PropertyListing).filter(
                                    PropertyListing.id == listing_id
                                ).first()
                                if not existing_listing:
                                    self.logger.warning(f"掲載情報の再取得に失敗: listing_id={listing_id}")
                                    continue
                                
                                existing_listing.last_confirmed_at = get_utc_now()
                                
                                # 非アクティブな掲載を再アクティブ化
                                if not existing_listing.is_active:
                                    existing_listing.is_active = True
                                    self.logger.debug(f"掲載を再開 (HTML構造エラースキップ) - ID: {listing_id}")
                                    
                                    # 物件が販売終了になっていた場合は販売再開
                                    # master_propertyを明示的に取得（lazy loadエラーを回避）
                                    if listing_master_property_id:
                                        master_prop = update_session.query(MasterProperty).filter(
                                            MasterProperty.id == listing_master_property_id
                                        ).first()
                                        if master_prop and master_prop.sold_at:
                                            master_prop.sold_at = None
                                            master_prop.final_price = None
                                            master_prop.final_price_updated_at = None
                                            self.logger.debug(f"物件を販売再開 (HTML構造エラースキップ) - 物件ID: {master_prop.id}")
                                
                                update_session.commit()
                                self.logger.debug(f"最終確認日時を正常に更新: listing_id={listing_id}")
                            except Exception as e:
                                update_session.rollback()
                                self.log_warning(f'最終確認日時の更新に失敗: {e}',
                                               url=property_data.get('url', '不明'))
                            finally:
                                update_session.close()
                        
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
                    
                    # 保存結果と更新タイプに基づく統計更新
                    # 詳細を取得した物件のみ内訳をカウント
                    if property_data.get('detail_fetched', False) and property_data.get('property_saved', False) and 'update_type' in property_data:
                        update_type = property_data['update_type']
                        self.logger.info(f"統計更新（詳細取得済み）: URL={property_data.get('url', '不明')}, update_type={update_type}")
                        
                        # 詳細取得済み物件の内訳を更新
                        if update_type == 'new':
                            self._scraping_stats['new_listings'] += 1
                        elif update_type == 'price_updated':
                            self._scraping_stats['price_updated'] += 1
                        elif update_type == 'refetched_unchanged':
                            self._scraping_stats['refetched_unchanged'] += 1
                            self.logger.info(f"再取得（変更なし）カウント: refetched_unchanged={self._scraping_stats['refetched_unchanged']}")
                        elif update_type == 'skipped':
                            # 詳細を取得したのにskippedは異常なケース
                            self.logger.warning(f"詳細取得済みなのにupdate_type=skipped: URL={property_data.get('url', '不明')}")
                        elif update_type == 'other_updates':
                            self._scraping_stats['other_updates'] += 1
                        elif update_type == 'existing':
                            # 既存レコードの更新（IntegrityError回避のケース）
                            self._scraping_stats['other_updates'] += 1
                            self.logger.debug(f"既存レコード更新をother_updatesとしてカウント: URL={property_data.get('url', '不明')}")
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
                
                # トランザクションエラーの場合（新しいトランザクション管理では各物件ごとに独立したトランザクション）
                if ("current transaction is aborted" in str(e) or 
                    "InFailedSqlTransaction" in str(e) or
                    "rolled back due to a previous exception" in str(e)):
                    # save_property_common内でトランザクションが管理されるため、ここでのロールバックは不要
                    self.logger.info("トランザクションエラーを検出しましたが、次の物件で新しいトランザクションが開始されます")
                continue
            
            # 定期的にコミット（新しいトランザクション管理では不要）
            # save_property_common内で各物件ごとにトランザクションが管理される
        
        # 最終コミット（新しいトランザクション管理では不要）
        # save_property_common内で各物件ごとにトランザクションが完結している
        final_commit_success = True
        
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
            self.log_warning(f'重複物件警告: {duplicate_count}件の物件が複数エリアに掲載されていました（正常な動作です）')
        if total_properties != total_calculated:
            self.log_warning(f'統計の不一致: 処理総数({total_properties}) != 計算合計({total_calculated})')
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
                self.log_warning(f'詳細取得したが統計に含まれていない物件が{unaccounted}件あります')
        
        self.logger.info(f"[DEBUG] scrape_area終了、結果を返却")
        debug_log(f"[{self.source_site}] scrape_area終了、結果を返却")
        
        return result
    

    
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
        """一時停止フラグをチェックし、必要に応じて待機（データベースベース）"""
        task_status = self._check_task_status_from_db()
        
        if task_status["is_cancelled"]:
            raise TaskCancelledException("Task cancelled")
        
        if task_status["is_paused"]:
            self.logger.info(f"タスクが一時停止されました（{phase_name}）")
            # 現在の状態を保存
            self._collected_properties = all_properties
            self._current_page = page
            
            # 一時停止フラグがクリアされるまで待機
            self.logger.info(f"一時停止フラグがクリアされるまで待機中（{phase_name}）...")
            debug_log(f"[{self.source_site}] 一時停止フラグがクリアされるまで待機中（{phase_name}）...")
            
            wait_count = 0
            # タイムアウト設定
            pause_timeout = PAUSE_TIMEOUT_SECONDS
            
            while True:
                time_module.sleep(self.PAUSE_CHECK_INTERVAL)
                wait_count += 1
                
                # 定期的にデータベースの状態を確認
                task_status = self._check_task_status_from_db()
                
                # キャンセルチェック
                if task_status["is_cancelled"]:
                    raise TaskCancelledException("Task cancelled during pause")
                
                if not task_status["is_paused"]:
                    break
                
                # ログ出力は5秒ごと
                if wait_count % self.PAUSE_LOG_INTERVAL == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"{phase_name}待機中... {wait_count/10}秒経過")
                    debug_log(f"[{self.source_site}] {phase_name}待機中... {wait_count/10}秒経過")
                
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
            self.log_warning(f'ページ {page}: 前ページと完全に同じ内容です（ページング失敗の可能性）')
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
        """処理フェーズ中の一時停止チェック（データベースベース）"""
        task_status = self._check_task_status_from_db()
        
        if task_status["is_cancelled"]:
            raise TaskCancelledException("Task cancelled")
        
        if task_status["is_paused"]:
            self.logger.info(f"[{self.source_site}] タスクが一時停止されました（処理フェーズ）")
            # 現在の処理状態を保存
            self._processed_count = index
            self._collected_properties = all_properties  # 収集済み物件も保存
            
            # 一時停止フラグがクリアされるまで待機
            self.logger.info(f"一時停止フラグがクリアされるまで待機中（処理フェーズ）...")
            debug_log(f"[{self.source_site}] 処理フェーズで一時停止検出。待機開始...")
            
            wait_count = 0
            pause_timeout = 300  # 5分
            
            while True:
                time_module.sleep(self.PAUSE_CHECK_INTERVAL)
                wait_count += 1
                
                # 定期的にデータベースの状態を確認
                task_status = self._check_task_status_from_db()
                
                # キャンセルチェック
                if task_status["is_cancelled"]:
                    raise TaskCancelledException("Task cancelled during pause")
                
                if not task_status["is_paused"]:
                    break
                
                # ログ出力は5秒ごと
                if wait_count % self.PAUSE_LOG_INTERVAL == 0:  # 5秒ごとにログ出力
                    self.logger.info(f"処理フェーズ待機中... {wait_count/10}秒経過")
                    debug_log(f"[{self.source_site}] 処理フェーズ待機中... {wait_count/10}秒経過")
                
                # タイムアウトチェック
                if wait_count >= pause_timeout * 10:
                    self.logger.warning(f"一時停止タイムアウト: {pause_timeout}秒を超えたため処理を中断")
                    raise TaskCancelledException(f"Pause timeout after {pause_timeout} seconds")
            
            self.logger.info(f"一時停止が解除されました（処理フェーズ）。処理を再開します... (待機時間: {wait_count/10}秒)")
            debug_log(f"[{self.source_site}] 処理フェーズで一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
    
    def set_progress_callback(self, callback):
        """進捗更新コールバックを設定"""
        self._progress_callback = callback
        self.logger.info(f"進捗コールバックが設定されました (task_id={self.task_id})")
    
    def _update_progress(self):
        """進捗をコールバックに通知"""
        if hasattr(self, '_progress_callback') and self._progress_callback:
            self.logger.info(f"進捗コールバックを呼び出します (task_id={self.task_id})")
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
        else:
            self.logger.info(f"進捗コールバックが設定されていません (task_id={self.task_id}, has_callback={hasattr(self, '_progress_callback')}, callback_value={getattr(self, '_progress_callback', None)})")
    
    def _check_pause_flag(self):
        """一時停止フラグをチェックし、必要に応じて待機（データベースベース）"""
        task_status = self._check_task_status_from_db()
        
        if task_status["is_cancelled"]:
            raise TaskCancelledException("Task cancelled")
        
        if task_status["is_paused"]:
            self.logger.info(f"[{self.source_site}] タスクが一時停止されました（詳細処理中）")
            debug_log(f"[{self.source_site}] 詳細処理中に一時停止検出。待機開始...")
            
            # 一時停止フラグがクリアされるまで待機
            wait_count = 0
            # タイムアウト設定（300秒 = 5分）
            pause_timeout = 300
            
            while True:
                time_module.sleep(0.1)
                wait_count += 1
                
                # 定期的にデータベースの状態を確認
                task_status = self._check_task_status_from_db()
                
                if task_status["is_cancelled"]:
                    raise TaskCancelledException("Task cancelled during pause")
                
                if not task_status["is_paused"]:
                    break
                
                # ログ出力は5秒ごと
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
                        # 建物名と物件情報を含む詳細ログ
                        building_name = existing_listing.listing_building_name or ''
                        # master_propertyとbuildingを明示的に取得（lazy loadエラーを回避）
                        master_prop = None
                        if existing_listing.master_property_id:
                            from ..database import get_db_for_scraping
                            temp_session = get_db_for_scraping()
                            try:
                                master_prop = temp_session.query(MasterProperty).filter(
                                    MasterProperty.id == existing_listing.master_property_id
                                ).first()
                                if master_prop and master_prop.building:
                                    building_name = master_prop.building.normalized_name or building_name
                            finally:
                                temp_session.close()
                        
                        detail_info = []
                        if master_prop:
                            mp = master_prop
                            if mp.floor_number:
                                detail_info.append(f"{mp.floor_number}階")
                            if mp.area:
                                detail_info.append(f"{mp.area}㎡")
                            if mp.layout:
                                detail_info.append(f"{mp.layout}")
                        
                        detail_str = ' / '.join(detail_info) if detail_info else ''
                        
                        # 建物名を含む自然なメッセージ
                        if building_name:
                            if detail_str:
                                print(f"  → 価格変更検出: {building_name} {detail_str} - {existing_listing.current_price}万円 → {property_data['price']}万円")
                            else:
                                print(f"  → 価格変更検出: {building_name} - {existing_listing.current_price}万円 → {property_data['price']}万円")
                        else:
                            if detail_str:
                                print(f"  → 価格変更検出: {detail_str} - {existing_listing.current_price}万円 → {property_data['price']}万円")
                            else:
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
                self.logger.warning(
                    f"価格不一致エラー履歴により詳細取得をスキップ: {property_data.get('url', '')} "
                    f"(物件ID: {site_id})"
                )
                property_data['detail_fetched'] = False
                property_data['detail_fetch_attempted'] = False
                property_data['update_type'] = 'skipped'
                property_data['property_saved'] = True
                return True
            
            # 404エラーでスキップすべきかチェック（強制詳細取得モードでない、かつエラー履歴無視モードでない場合のみ）
            if not self.force_detail_fetch and not self.ignore_error_history and self._should_skip_url_due_to_404(property_data['url']):
                print("  → 404エラー履歴のためスキップ")
                self.logger.warning(
                    f"404エラー履歴により詳細取得をスキップ: {property_data.get('url', '')} "
                    f"(物件ID: {site_id})"
                )
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
                self.logger.warning(
                    f"検証エラー履歴により詳細取得をスキップ: {property_data.get('url', '')} "
                    f"(物件ID: {site_id})"
                )
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
                    
                    # 価格不一致として記録
                    self._record_price_mismatch(
                        property_data.get('site_property_id', ''),
                        property_data['url'],
                        list_price,
                        detail_price
                    )
                    
                    # 価格不一致の統計を更新
                    if 'price_mismatch' not in self._scraping_stats:
                        self._scraping_stats['price_mismatch'] = 0
                    self._scraping_stats['price_mismatch'] += 1
                    
                    # エラーログを記録（価格不一致は重要なエラーとして扱う）
                    self.log_error(
                        f'価格不一致を検出: 一覧 {list_price}万円, 詳細 {detail_price}万円 (差額: {price_diff}万円, {price_diff_rate:.1%})',
                        url=property_data.get('url', '不明'),
                        building_name=building_name,
                        price=f'{list_price} → {detail_price}',
                        site_property_id=property_data.get('site_property_id', ''),
                        source_site=self.source_site.value
                    )
                    
                    # 更新をスキップ
                    print(f"  → 価格不一致のため更新をスキップ (一覧: {list_price}万円, 詳細: {detail_price}万円)")
                    property_data['detail_fetched'] = False
                    self._last_detail_fetched = False
                    self._scraping_stats['detail_fetch_failed'] += 1
                    property_data['detail_fetch_attempted'] = True
                    property_data['property_saved'] = False
                    return False
                
                # 建物名検証処理
                if not self.validate_building_name_from_detail(property_data, detail_data):
                    # 検証失敗の場合は更新をスキップ
                    print(f"  → 建物名検証失敗のため更新をスキップ")
                    property_data['detail_fetched'] = False
                    self._last_detail_fetched = False
                    self._scraping_stats['detail_fetch_failed'] += 1
                    property_data['detail_fetch_attempted'] = True
                    property_data['property_saved'] = False
                    return False
                
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
            # master_propertyを明示的に取得（lazy loadエラーを回避）
            if existing_listing and existing_listing.master_property_id:
                from ..database import get_db_for_scraping
                temp_session = get_db_for_scraping()
                try:
                    master_prop = temp_session.query(MasterProperty).filter(
                        MasterProperty.id == existing_listing.master_property_id
                    ).first()
                    if master_prop:
                        # 必須情報を既存データから補完
                        if 'building_name' not in property_data or not property_data['building_name']:
                            if master_prop.building:
                                property_data['building_name'] = master_prop.building.normalized_name
                        if 'area' not in property_data or not property_data['area']:
                            property_data['area'] = master_prop.area
                        if 'layout' not in property_data or not property_data['layout']:
                            property_data['layout'] = master_prop.layout
                        if 'floor_number' not in property_data or property_data.get('floor_number') is None:
                            property_data['floor_number'] = master_prop.floor_number
                finally:
                    temp_session.close()
        
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
    
    
    def validate_property_data(self, property_data: Dict[str, Any]) -> bool:
        """物件データの妥当性をチェック"""
        from .data_normalizer import validate_price, validate_area, validate_floor_number, validate_built_year
        
        url = property_data.get('url', '不明')
        building_name = property_data.get('building_name', '不明')
        
        # 検証エラーの詳細を収集
        validation_errors = []
        
        # 必須フィールドのチェック
        if not property_data.get('building_name'):
            validation_errors.append("建物名が未取得")
            self.log_warning('建物名がありません', url=url)
        
        if not property_data.get('price'):
            validation_errors.append("価格が未取得")
            self.log_warning('価格情報がありません', url=url, building_name=building_name)
        
        # site_property_idを必須項目として追加
        if not property_data.get('site_property_id'):
            validation_errors.append("サイト物件IDが未取得")
            self.logger.warning(f"サイト物件IDがありません: URL={url}, building_name={building_name}")
        
        # 部分的必須フィールドのチェック
        partial_required_fields = self.get_partial_required_fields()
        for field_name, config in partial_required_fields.items():
            field_value = property_data.get(field_name, '')
            empty_values = config.get('empty_values', ['-', '－', ''])
            
            if field_value in empty_values:
                # フィールドが取得できなかった場合の統計を更新
                self.update_stats(f'{field_name}_missing', 1)
                self.update_stats(f'properties_with_{field_name}_check', 1)
                
                # 空の値の場合は、property_dataから削除（NULLとして保存）
                if field_name in property_data:
                    del property_data[field_name]
                
                # 欠損率をチェック
                total_checked = self.get_stats(f'properties_with_{field_name}_check', 0)
                missing_count = self.get_stats(f'{field_name}_missing', 0)
                min_sample_size = config.get('min_sample_size', 10)
                
                if total_checked >= min_sample_size:  # 十分なサンプル数がある場合
                    missing_rate = missing_count / total_checked
                    max_missing_rate = config.get('max_missing_rate', 0.3)
                    
                    if missing_rate > max_missing_rate:
                        field_name_jp = {
                            'layout': '間取り',
                            'direction': '方角',
                            'floor_number': '階数'
                        }.get(field_name, field_name)
                        validation_errors.append(f"{field_name_jp}の欠損率が異常に高い: {missing_rate:.1%}")
                        self.logger.error(
                            f"{field_name_jp}の欠損率が異常に高い: {missing_rate:.1%} "
                            f"({missing_count}/{total_checked}件) - "
                            f"HTML構造が変更された可能性があります"
                        )
                    elif missing_rate > 0.1 and total_checked >= 20:  # 10%以上は警告
                        self.logger.warning(
                            f"{field_name}の欠損率が高めです: {missing_rate:.1%} "
                            f"({missing_count}/{total_checked}件)"
                        )
        
        # 住所は詳細ページから取得する場合があるため、一覧ページでは必須ではない
        # 詳細ページ取得後に再度チェックされる
        if not property_data.get('address') and property_data.get('detail_fetched', False):
            # 詳細ページを取得したのに住所がない場合のみエラー
            validation_errors.append("住所が未取得（詳細取得後）")
            self.logger.warning(f"詳細取得後も住所情報がありません: URL={url}, building_name={building_name}")
        
        # 価格の妥当性チェック（data_normalizerのvalidate_priceを使用）
        price = property_data.get('price', 0)
        if price and not validate_price(price):
            validation_errors.append(f"価格が範囲外: {price}万円（許容範囲: 100万円～100億円）")
            self.logger.warning(f"価格が異常です: {price}万円, URL={url}")
        
        # 面積の妥当性チェック（data_normalizerのvalidate_areaを使用）
        area = property_data.get('area', 0)
        if area and not validate_area(area):
            validation_errors.append(f"面積が範囲外: {area}㎡（許容範囲: 10㎡～500㎡）")
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
    
    def normalize_building_name(self, building_name: str) -> str:
        """
        建物名を正規化する
        共通モジュールの関数を使用
        """
        return normalize_building_name_common(building_name)
    
    def validate_building_name_from_detail(self, property_data: Dict[str, Any], detail_data: Dict[str, Any]) -> bool:
        """詳細ページから取得した建物名を検証
        
        Args:
            property_data: 一覧ページから取得した物件データ
            detail_data: 詳細ページから取得した物件データ
            
        Returns:
            bool: 検証が成功した場合True
        """
        list_building_name = property_data.get('building_name_from_list')
        detail_building_name = detail_data.get('building_name')
        
        # 検証モードに応じて処理を分岐
        if self.building_name_verification_mode == BuildingNameVerificationMode.MULTI_SOURCE:
            # MULTI_SOURCEモード: 詳細ページの複数箇所から取得した建物名を検証
            # 派生クラスでget_building_names_from_detailメソッドをオーバーライドして実装
            building_names_from_detail = self.get_building_names_from_detail(detail_data)
            
            is_verified, verified_name = self.verify_building_names_multi_source(
                building_names_from_detail, list_building_name
            )
            
            if is_verified and verified_name:
                detail_data['building_name'] = verified_name
                if list_building_name and list_building_name != verified_name:
                    self.logger.info(f"建物名を検証済みの名前で更新: {list_building_name} → {verified_name}")
                return True
            else:
                self.logger.warning(
                    f"建物名検証失敗（MULTI_SOURCE）: {property_data.get('url')} - "
                    f"一覧: {list_building_name}, 詳細候補: {building_names_from_detail}"
                )
                # エラーログを記録
                if hasattr(self, '_save_error_log'):
                    self._save_error_log({
                        'url': property_data.get('url', '不明'),
                        'reason': f'建物名検証失敗（複数箇所不一致）: 一覧「{list_building_name}」, 詳細候補「{building_names_from_detail}」',
                        'building_name': list_building_name,
                        'price': property_data.get('price', ''),
                        'timestamp': datetime.now().isoformat(),
                        'site_property_id': property_data.get('site_property_id', ''),
                        'source_site': self.source_site.value
                    })
                
                # 検証エラーを記録
                self._record_validation_error(
                    url=property_data.get('url', ''),
                    site_property_id=property_data.get('site_property_id', ''),
                    error_type='building_name_mismatch_multi_source',
                    error_details=f'一覧: {list_building_name}, 詳細候補: {building_names_from_detail}'
                )
                return False
                
        elif list_building_name and detail_building_name:
            # STRICTまたはPARTIALモード: 従来の検証処理
            is_verified, verified_name = self.verify_building_names_match(
                detail_building_name, 
                list_building_name,
                allow_partial_match=(
                    self.building_name_verification_mode == BuildingNameVerificationMode.PARTIAL 
                    or self.allow_partial_building_name_match
                )
            )
            
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
                
                # 検証エラーを記録
                self._record_validation_error(
                    url=property_data.get('url', ''),
                    site_property_id=property_data.get('site_property_id', ''),
                    error_type='building_name_mismatch',
                    error_details=f'一覧: {list_building_name}, 詳細: {detail_building_name}'
                )
                
                return False
            else:
                # 建物名が確認できた場合は、詳細ページの建物名を使用
                if verified_name:
                    detail_data['building_name'] = verified_name
                    if list_building_name != detail_building_name:
                        self.logger.info(f"建物名を詳細ページの名前で更新: {list_building_name} → {verified_name}")
                    else:
                        self.logger.info(f"建物名が一致: {verified_name}")
                return True
        
        # 建物名が取得できていない場合は検証をスキップ
        return True
    
    def get_building_names_from_detail(self, detail_data: Dict[str, Any]) -> List[str]:
        """詳細ページから複数の建物名を取得（MULTI_SOURCEモード用）
        
        派生クラスでオーバーライドして実装する。
        デフォルトでは、detail_dataのbuilding_nameを返す。
        
        Args:
            detail_data: 詳細ページから取得したデータ
            
        Returns:
            建物名のリスト
        """
        building_name = detail_data.get('building_name')
        if building_name:
            return [building_name]
        return []
    
    def verify_building_names_multi_source(self, building_names_from_detail: List[str], building_name_from_list: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """複数箇所から取得した建物名を検証（MULTI_SOURCEモード用）
        
        Args:
            building_names_from_detail: 詳細ページの複数箇所から取得した建物名のリスト
            building_name_from_list: 一覧ページから取得した建物名（省略可）
            
        Returns:
            (建物名が確認できたか, 確認された建物名またはNone)
        """
        if not building_names_from_detail:
            return False, None
            
        # 一覧ページの建物名がある場合、まず通常の検証を行う
        if building_name_from_list:
            for detail_name in building_names_from_detail:
                if detail_name:
                    is_verified, verified_name = self.verify_building_names_match(
                        detail_name, building_name_from_list, 
                        allow_partial_match=True, threshold=0.8
                    )
                    if is_verified:
                        self.logger.info(f"一覧ページの建物名と詳細ページの建物名が一致: {verified_name}")
                        return True, verified_name
        
        # 詳細ページの複数箇所から取得した建物名を検証
        if len(building_names_from_detail) >= 2:
            # 建物名の出現回数をカウント（正規化して比較）
            name_counts = {}
            original_names = {}  # 正規化前の名前を保持
            
            for name in building_names_from_detail:
                if name:
                    normalized_name = self.normalize_building_name(name)
                    if normalized_name:
                        # 小文字に変換して比較
                        normalized_lower = normalized_name.lower()
                        name_counts[normalized_lower] = name_counts.get(normalized_lower, 0) + 1
                        # 最初に見つかった元の表記を保存
                        if normalized_lower not in original_names:
                            original_names[normalized_lower] = name
            
            # 2回以上出現する建物名があれば、それを採用
            for normalized_name, count in name_counts.items():
                if count >= 2:
                    original_name = original_names[normalized_name]
                    self.logger.info(
                        f"詳細ページの複数箇所（{count}箇所）で一致する建物名を確認: {original_name}"
                    )
                    return True, original_name
            
            # 2回以上出現する建物名がない場合
            if building_names_from_detail:
                # 最初の候補を使用
                first_name = building_names_from_detail[0]
                self.logger.warning(
                    f"詳細ページの建物名が複数箇所で一致しないため、最初の候補を使用: {first_name}"
                )
                return True, first_name
        
        # 建物名が1つしかない場合
        elif len(building_names_from_detail) == 1:
            building_name = building_names_from_detail[0]
            self.logger.info(f"詳細ページから建物名を取得（1箇所のみ）: {building_name}")
            return True, building_name
        
        return False, None

    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str, 
                                   allow_partial_match: bool = False, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """一覧ページで取得した建物名と詳細ページで取得した建物名が一致するか確認
        
        Args:
            detail_building_name: 詳細ページから取得した建物名
            building_name_from_list: 一覧ページから取得した建物名
            allow_partial_match: 部分一致を許可するかどうか（デフォルト: False）
            threshold: 類似度の閾値（0.0-1.0）、部分一致の場合のみ使用
            
        Returns:
            (建物名が確認できたか, 確認された建物名またはNone)
        """
        if not building_name_from_list or not detail_building_name:
            return False, None
            
        # 正規化処理（共通メソッドを使用）
        normalized_list_name = self.normalize_building_name(building_name_from_list)
        normalized_detail_name = self.normalize_building_name(detail_building_name)
        
        # デバッグ: 正規化後の名前を表示（ローマ数字、単位、全角英字を含む場合、またはHOMES/部分一致の場合）
        debug_chars = 'ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVXivx㎡m²ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
        if (any(char in building_name_from_list + detail_building_name for char in debug_chars) or 
            allow_partial_match or self.source_site == SourceSite.HOMES):
            self.logger.debug(
                f"建物名正規化: 一覧「{building_name_from_list}」→「{normalized_list_name}」、"
                f"詳細「{detail_building_name}」→「{normalized_detail_name}」"
            )
        
        # 完全一致（正規化後）
        if normalized_list_name.lower() == normalized_detail_name.lower():
            self.logger.info(f"建物名が一致（完全一致）: {building_name_from_list}")
            return True, detail_building_name
        
        # 部分一致が許可されている場合のみ、部分一致をチェック
        if allow_partial_match:
            # SequenceMatcherを使用した類似度計算
            # 正規化された文字列同士の類似度を計算
            similarity = SequenceMatcher(None, normalized_list_name.lower(), normalized_detail_name.lower()).ratio()
            
            self.logger.debug(
                f"文字列類似度: {similarity:.1%} - "
                f"一覧「{normalized_list_name}」と詳細「{normalized_detail_name}」"
            )
            
            # 類似度が閾値以上なら一致と判定
            if similarity >= threshold:
                self.logger.info(
                    f"建物名が一致（類似度 {similarity:.0%}）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
                    
        self.logger.warning(
            f"建物名が一致しません: 一覧「{building_name_from_list}」、詳細「{detail_building_name}」"
        )
        return False, None
    
    def get_search_key_for_building(self, building_name: str) -> str:
        """
        建物検索用のキーを生成
        共通モジュールの関数を使用
        """
        return get_search_key_for_building_common(building_name)
    
    def safe_flush(self, session):
        """セッションのflushを安全に実行（エラー時は自動ロールバック）"""
            
        try:
            session.flush()
            return True
        except Exception as e:
            self.logger.warning(f"flush中にエラーが発生したため、ロールバックします: {type(e).__name__}: {e}")
            session.rollback()
            return False
    
    def _verify_building_attributes(self, building: Building, total_floors: int = None, 
                                 built_year: int = None, built_month: int = None,
                                 total_units: int = None) -> bool:
        """建物の属性（総階数、築年月、総戸数）が一致するか確認
        
        前提条件：この関数が呼び出される時点で、住所と建物名の一致は確認済み
        
        重要な仕様：
        - 比較可能な属性が少なくとも2つ必要
        - 比較可能な属性はすべて一致する必要がある
        - NULLの属性は比較から除外する
        - 総階数・総戸数が一致している場合は築年月の±1ヶ月の誤差を許容
        - 総階数・築年月が一致している場合は総戸数の±2戸の誤差を許容
        """
        # 比較可能な属性をカウント
        comparable_attributes = []
        
        # 総階数の比較
        if total_floors is not None and building.total_floors is not None:
            if building.total_floors != total_floors:
                self.logger.debug(
                    f"総階数が一致しない: 既存={building.total_floors}, 新規={total_floors}"
                )
                return False
            comparable_attributes.append('total_floors')
        
        # 築年月の比較（年と月の両方をチェック）
        built_year_month_mismatch = False
        built_month_diff = 0
        
        if built_year is not None and building.built_year is not None:
            if building.built_year != built_year:
                self.logger.debug(
                    f"築年が一致しない: 既存={building.built_year}, 新規={built_year}"
                )
                return False
            
            # 築月の比較（築年が一致している場合のみ）
            if built_month is not None and building.built_month is not None:
                built_month_diff = abs(building.built_month - built_month)
                if built_month_diff != 0:
                    self.logger.debug(
                        f"築月が異なる: 既存={building.built_year}年{building.built_month}月, "
                        f"新規={built_year}年{built_month}月 (差: {built_month_diff}ヶ月)"
                    )
                    # 築月の不一致を記録（後で他の条件により判定）
                    built_year_month_mismatch = True
                else:
                    comparable_attributes.append('built_year_month')  # 年月両方が完全一致
            else:
                comparable_attributes.append('built_year')  # 年のみ一致
        
        # 総戸数の比較
        total_units_diff = 0
        total_units_mismatch = False
        
        if total_units is not None and building.total_units is not None:
            total_units_diff = abs(building.total_units - total_units)
            if total_units_diff != 0:
                self.logger.debug(
                    f"総戸数が異なる: 既存={building.total_units}, 新規={total_units} (差: {total_units_diff}戸)"
                )
                total_units_mismatch = True
            else:
                comparable_attributes.append('total_units')
        
        # 比較可能な属性が2つ未満の場合は一致と判定（十分な情報がないため）
        if len(comparable_attributes) < 2:
            self.logger.debug(
                f"比較可能な属性が{len(comparable_attributes)}つのため、一致と判定"
                f" (属性: {', '.join(comparable_attributes) if comparable_attributes else 'なし'})"
            )
            return True
        
        # すべての比較可能な属性が完全一致している場合はOK
        if not built_year_month_mismatch and not total_units_mismatch:
            self.logger.debug(
                f"全属性が一致: {', '.join(comparable_attributes)}"
            )
            return True
        
        # 特別な許容条件をチェック
        # 条件1: 総階数・総戸数が一致している場合は築年月の±1ヶ月の誤差を許容
        if ('total_floors' in comparable_attributes and 
            'total_units' in comparable_attributes and
            built_year_month_mismatch and built_month_diff <= 1):
            self.logger.debug(
                f"総階数・総戸数一致により築年月の誤差±{built_month_diff}ヶ月を許容"
            )
            return True
        
        # 条件2: 総階数・築年月が一致している場合は総戸数の±2戸の誤差を許容
        if (('total_floors' in comparable_attributes or 'built_year' in comparable_attributes or 'built_year_month' in comparable_attributes) and
            total_units_mismatch and total_units_diff <= 2):
            
            # 総階数と築年月の両方、または築年月が一致している場合のみ許容
            structure_match = 'total_floors' in comparable_attributes
            time_match = 'built_year' in comparable_attributes or 'built_year_month' in comparable_attributes
            
            if structure_match or time_match:
                self.logger.debug(
                    f"総階数・築年月一致により総戸数の誤差±{total_units_diff}戸を許容"
                    f" (総階数:{structure_match}, 築年月:{time_match})"
                )
                return True
        
        # いずれの条件にも該当しない場合は不一致
        self.logger.debug(
            f"建物属性が不一致: "
            f"築年月誤差={built_month_diff if built_year_month_mismatch else 0}ヶ月, "
            f"総戸数誤差={total_units_diff if total_units_mismatch else 0}戸"
        )
        return False

    def _verify_building_attributes_strict(self, building: Building, total_floors: int = None, 
                                         built_year: int = None, built_month: int = None,
                                         total_units: int = None) -> bool:
        """建物の属性が厳密に一致するかチェック（誤差許容なし）
        
        Returns:
            bool: すべての比較可能な属性が厳密に一致する場合True
        """
        # 総階数の厳密チェック
        if total_floors is not None and building.total_floors is not None:
            if building.total_floors != total_floors:
                return False
        
        # 築年の厳密チェック
        if built_year is not None and building.built_year is not None:
            if building.built_year != built_year:
                return False
        
        # 築月の厳密チェック
        if built_month is not None and building.built_month is not None:
            if building.built_month != built_month:
                return False
        
        # 総戸数の厳密チェック
        if total_units is not None and building.total_units is not None:
            if building.total_units != total_units:
                return False
        
        return True
    
    def _calculate_name_match_score(self, search_key: str, canonical_name: str) -> tuple:
        """建物名の一致度スコアを計算
        
        Returns:
            tuple: (priority, score) - priorityが小さいほど優先度高、scoreが大きいほど一致度高
        """
        if canonical_name == search_key:
            return (1, 100)  # 完全一致：最高優先度
        
        # 前方一致チェック
        if canonical_name.startswith(search_key):
            ratio = len(search_key) / len(canonical_name)
            return (2, 80 + ratio * 15)  # 前方一致：高優先度
        
        if search_key.startswith(canonical_name):
            ratio = len(canonical_name) / len(search_key)
            return (2, 80 + ratio * 15)  # 逆前方一致：高優先度
        
        # 部分一致チェック
        if search_key in canonical_name:
            ratio = len(search_key) / len(canonical_name)
            return (3, 50 + ratio * 25)  # 部分一致：中優先度
        
        if canonical_name in search_key:
            ratio = len(canonical_name) / len(search_key)
            return (3, 50 + ratio * 25)  # 逆部分一致：中優先度
        
        # 一致しない場合
        return (4, 0)

    def _calculate_address_match_score(self, address1: str, address2: str) -> Tuple[int, str]:
        """
        正規化された住所の一致度を詳細に計算する
        
        Returns:
            Tuple[int, str]: (スコア, 一致タイプ)
            スコア: 100(完全一致), 90(番地まで一致), 80(丁目まで一致), 70(市区町村一致), 0(不一致)
        """
        if not address1 or not address2:
            return 0, "不一致"
        
        # 正規化された住所で比較
        addr1 = address1.strip()
        addr2 = address2.strip()
        
        # 完全一致（最高スコア）
        if addr1 == addr2:
            return 100, "完全一致"
        
        # AddressNormalizerを使って住所の構成要素に分解
        from ..utils.address_normalizer import AddressNormalizer
        normalizer = AddressNormalizer()
        
        # 各住所を構成要素に分解
        components1 = normalizer.extract_components(addr1)
        components2 = normalizer.extract_components(addr2)
        
        # 階層的な一致度判定
        # 都道府県が異なる場合は不一致
        if (components1['prefecture'] and components2['prefecture'] and 
            components1['prefecture'] != components2['prefecture']):
            return 0, "不一致"
        
        # 市区町村が異なる場合は不一致
        if (components1['city'] and components2['city'] and 
            components1['city'] != components2['city']):
            return 0, "不一致"
        
        # 区が異なる場合は不一致
        if (components1['ward'] and components2['ward'] and 
            components1['ward'] != components2['ward']):
            return 0, "不一致"
        
        # 町村が異なる場合は不一致
        if (components1['town'] and components2['town'] and 
            components1['town'] != components2['town']):
            return 0, "不一致"
        
        # 地域名（丁目より前の部分）が異なる場合は不一致
        if (components1['area'] and components2['area'] and 
            components1['area'] != components2['area']):
            return 0, "不一致"
        
        # 番地情報の詳細比較
        block1 = components1['block']
        block2 = components2['block']
        
        # 両方に番地情報がある場合
        if block1 and block2:
            if block1 == block2:
                return 100, "番地まで完全一致"
            
            # 番地の部分一致をチェック
            # 例: "1丁目2-3" vs "1丁目2" の場合
            import re
            
            # 丁目番号の抽出
            chome1 = re.search(r'(\d+)丁目', block1)
            chome2 = re.search(r'(\d+)丁目', block2)
            
            if chome1 and chome2:
                if chome1.group(1) == chome2.group(1):
                    # 丁目は一致、番地の詳細をチェック
                    # "2-3" 形式の番地を抽出
                    banchi1 = re.search(r'(\d+)(?:-(\d+))?', block1.replace(chome1.group(0), ''))
                    banchi2 = re.search(r'(\d+)(?:-(\d+))?', block2.replace(chome2.group(0), ''))
                    
                    if banchi1 and banchi2:
                        # 第一番地が一致
                        if banchi1.group(1) == banchi2.group(1):
                            # 号数もチェック
                            go1 = banchi1.group(2)
                            go2 = banchi2.group(2)
                            
                            if go1 and go2:
                                if go1 == go2:
                                    return 100, "号まで完全一致"
                                else:
                                    return 90, "番地一致（号が異なる）"
                            elif not go1 and not go2:
                                return 90, "番地まで一致"
                            else:
                                return 90, "番地まで一致（号の有無が異なる）"
                        else:
                            return 80, "丁目一致（番地が異なる）"
                    else:
                        return 80, "丁目まで一致"
                else:
                    return 70, "地域一致（丁目が異なる）"
            
            # 丁目がない場合の番地比較
            # 例: "2-3" vs "2" の場合
            banchi1_match = re.search(r'(\d+)(?:-(\d+))?', block1)
            banchi2_match = re.search(r'(\d+)(?:-(\d+))?', block2)
            
            if banchi1_match and banchi2_match:
                if banchi1_match.group(1) == banchi2_match.group(1):
                    go1 = banchi1_match.group(2)
                    go2 = banchi2_match.group(2)
                    
                    if go1 and go2:
                        if go1 == go2:
                            return 100, "番地・号完全一致"
                        else:
                            return 90, "番地一致（号が異なる）"
                    elif not go1 and not go2:
                        return 90, "番地一致"
                    else:
                        return 90, "番地一致（号の有無が異なる）"
                else:
                    return 80, "地域一致（番地が異なる）"
            
            # その他のパターンはブロック情報の部分一致として扱う
            if block1 in block2 or block2 in block1:
                return 85, "番地部分一致"
            else:
                return 70, "地域一致（番地が異なる）"
        
        # 片方にだけ番地情報がある場合
        elif block1 or block2:
            # より詳細な住所がある方を基準とする
            return 80, "地域まで一致（番地情報の詳細度が異なる）"
        
        # 番地情報が両方ともない場合、地域レベルまでの比較
        # 市区町村・町村・地域が一致していればOK
        match_level = []
        if components1['prefecture'] == components2['prefecture']:
            match_level.append('都道府県')
        if components1['city'] == components2['city']:
            match_level.append('市区町村')
        if components1['ward'] == components2['ward']:
            match_level.append('区')
        if components1['town'] == components2['town']:
            match_level.append('町村')
        if components1['area'] == components2['area']:
            match_level.append('地域')
        
        if match_level:
            highest_match = match_level[-1]  # 最も詳細な一致レベル
            return 70, f"{highest_match}まで一致"
        
        # 部分一致（包含関係）をチェック
        if addr1 in addr2 or addr2 in addr1:
            shorter_len = min(len(addr1), len(addr2))
            longer_len = max(len(addr1), len(addr2))
            inclusion_ratio = shorter_len / longer_len
            
            if inclusion_ratio >= 0.8:
                return 60, "高い部分一致"
            elif inclusion_ratio >= 0.6:
                return 50, "中程度の部分一致"
            else:
                return 40, "低い部分一致"
        
        return 0, "不一致"

    def _find_buildings_with_staged_matching(self, session, search_key: str, normalized_address: str, 
                                           total_floors: int = None, built_year: int = None, 
                                           built_month: int = None, total_units: int = None) -> Optional[Building]:
        """段階的マッチングで建物を検索
        
        1. 完全属性一致を優先
        2. 許容誤差一致をフォールバック
        3. 建物名一致度で優先順位付け
        """
        # 住所を正規化（表記ゆれを吸収）
        from ..utils.address_normalizer import AddressNormalizer
        normalizer = AddressNormalizer()
        
        # SQLで効率的に候補を絞り込み
        partial_match_query = session.query(Building).filter(
            Building.canonical_name.isnot(None),
            Building.address.isnot(None)
        )
        
        # 住所の部分一致条件を追加（より柔軟に）
        from sqlalchemy import or_
        partial_match_query = partial_match_query.filter(
            or_(
                Building.normalized_address == normalized_address,
                Building.normalized_address.like(f"{normalized_address}%"),
                Building.normalized_address.like(f"%{normalized_address}%"),  # 中間一致も追加
                text(f"'{normalized_address}' LIKE '%' || normalized_address || '%'")  # 逆方向も追加
            )
        )
        
        # 建物名の完全一致または部分一致条件を追加
        partial_match_query = partial_match_query.filter(
            or_(
                Building.canonical_name == search_key,  # 完全一致を優先
                Building.canonical_name.like(f"{search_key}%"),  # 前方一致
                Building.canonical_name.like(f"%{search_key}%"),  # 部分一致
                text(f"'{search_key}' LIKE '%' || canonical_name || '%'")  # 逆方向部分一致
            )
        )
        
        # 最大50件まで取得（より多くの候補を確認）
        candidate_buildings = partial_match_query.limit(50).all()
        
        if not candidate_buildings:
            return None
        
        # 住所の精密チェックと分類
        valid_candidates = []
        
        for building in candidate_buildings:
            # 住所の正規化チェック（Python レベルで精密チェック）
            building_normalized_addr = normalizer.normalize_for_comparison(building.address)
            
            # 詳細な住所一致度計算
            address_score, address_match_type = self._calculate_address_match_score(
                normalized_address, building_normalized_addr
            )
            
            # 住所が一致しない場合はスキップ（スコア40以下）
            if address_score < 40:
                continue
                
            # 建物名一致度と優先度を計算
            name_score, name_match_type = self._calculate_name_match_score(search_key, building.canonical_name)
            priority = 1 if building.canonical_name == search_key else 2  # 完全一致は優先度1
            
            # 属性一致チェック
            strict_match = self._verify_building_attributes_strict(building, total_floors, built_year, built_month, total_units)
            flexible_match = self._verify_building_attributes(building, total_floors, built_year, built_month, total_units)
                
            valid_candidates.append({
                'building': building,
                'name_priority': priority,
                'name_score': name_score,
                'address_score': address_score,
                'address_match_type': address_match_type,
                'strict_match': strict_match,
                'flexible_match': flexible_match
            })
        
        if not valid_candidates:
            return None
        
        # 優先順位でソート：
        # 1. 厳密一致を優先（strict_match=True）
        # 2. 住所の完全一致を優先（address_score）
        # 3. 建物名の優先度（priority）
        # 4. 建物名のスコア（score）
        valid_candidates.sort(key=lambda x: (
            not x['strict_match'],  # 厳密一致を優先（Falseが先）
            -x['address_score'],    # 住所スコア（高い方が優先）
            x['name_priority'],     # 優先度（数字が小さいほど優先）
            -x['name_score']        # スコア（大きいほど優先）
        ))
        
        best_candidate = valid_candidates[0]
        building = best_candidate['building']
        
        # ログ出力
        match_type = "厳密一致" if best_candidate['strict_match'] else "許容誤差一致"
        address_type = best_candidate['address_match_type']
        
        self.logger.info(
            f"段階的検索で建物を発見（{match_type}・住所{address_type}・スコア{best_candidate['address_score']}・優先度{best_candidate['name_priority']}）: "
            f"検索キー='{search_key}' → 既存='{building.canonical_name}' at {building.address}"
        )
        
        return building

    def find_existing_building_by_key(self, session, search_key: str, address: str = None, total_floors: int = None,
                                     built_year: int = None, built_month: int = None, total_units: int = None) -> Optional[Building]:
        """検索キーで既存の建物を探す（最適化された統一検索ロジック）"""
        # 住所が指定されていない場合は、建物名だけでの判断は危険なのでNoneを返す
        if not address:
            self.logger.debug(f"住所が指定されていないため、建物検索をスキップ: {search_key}")
            return None
        
        # 住所を正規化（表記ゆれを吸収）
        from ..utils.address_normalizer import AddressNormalizer
        normalizer = AddressNormalizer()
        normalized_address = normalizer.normalize_for_comparison(address)
        
        # === 1. 正式な建物名での完全一致（最優先） ===
        self.logger.debug(f"建物検索開始: search_key='{search_key}', normalized_address='{normalized_address}'")
        
        # まず、建物名（canonical_name）で候補を絞り込む
        candidate_buildings = session.query(Building).filter(
            Building.canonical_name == search_key
        ).all()
        
        self.logger.debug(f"建物名'{search_key}'で{len(candidate_buildings)}件の候補が見つかりました")
        
        # 候補の中から住所マッチングを行う
        for building in candidate_buildings:
            if not building.address:
                continue
                
            # 建物の住所を正規化
            building_normalized_addr = building.normalized_address
            if not building_normalized_addr:
                # normalized_addressがない場合は、その場で正規化
                building_normalized_addr = normalizer.normalize_for_comparison(building.address)
                # DBを更新（次回からは高速化）
                building.normalized_address = building_normalized_addr
                self.safe_flush(session)
            
            # 住所の完全一致をチェック
            if building_normalized_addr == normalized_address:
                # 完全一致でも建物属性を確認
                if self._verify_building_attributes(building, total_floors, built_year, built_month, total_units):
                    self.logger.info(f"既存建物を発見（名前と正規化住所が完全一致、属性も確認）: {building.normalized_name} at {building.address}")
                    return building
                else:
                    self.logger.debug(f"住所は完全一致するが、総階数または築年が一致しない: {building.normalized_name}")
                    # デバッグ情報：属性比較の詳細
                    self.logger.debug(f"属性詳細比較 - 既存: floors={building.total_floors}, year={building.built_year}, month={building.built_month}")
                    self.logger.debug(f"属性詳細比較 - 新規: floors={total_floors}, year={built_year}, month={built_month}")
        
        # 完全一致が見つからない場合、部分一致を試す
        for building in candidate_buildings:
            if not building.address:
                continue
                
            building_normalized_addr = building.normalized_address
            if not building_normalized_addr:
                building_normalized_addr = normalizer.normalize_for_comparison(building.address)
                building.normalized_address = building_normalized_addr
                self.safe_flush(session)
            
            # 部分一致をチェック
            if (building_normalized_addr.startswith(normalized_address) or 
                normalized_address.startswith(building_normalized_addr)):
                
                # 部分一致の場合も属性確認（住所は部分一致、建物名は完全一致）
                if self._verify_building_attributes(building, total_floors, built_year, built_month, total_units):
                    self.logger.info(f"既存建物を発見（建物名完全一致・住所部分一致・属性確認）: {building.normalized_name} at {building.address}")
                    return building
                else:
                    self.logger.debug(f"建物名完全一致・住所は部分一致するが、総階数または築年が一致しない: {building.normalized_name}")
        
        # === 2. BuildingListingNameテーブルでの検索（別名での完全一致） ===
        from sqlalchemy import or_
        from ..models import BuildingListingName
        from .data_normalizer import canonicalize_building_name
        
        # 検索語を正規化
        canonical_search = canonicalize_building_name(search_key)
        
        # BuildingListingNameから該当する建物を検索（複数候補の最適化）
        listing_matches = session.query(BuildingListingName).filter(
            or_(
                BuildingListingName.listing_name == search_key,
                BuildingListingName.canonical_name == canonical_search
            )
        ).all()
        
        if listing_matches:
            # 複数の候補から最適な建物を選択
            best_candidate = None
            best_score = -1
            
            for listing_match in listing_matches:
                # 建物を取得
                primary_building = session.query(Building).filter(
                    Building.id == listing_match.building_id
                ).first()
                
                if not primary_building or not primary_building.address:
                    continue
                
                # 住所の確認（完全一致・部分一致）
                building_normalized_addr = primary_building.normalized_address
                if not building_normalized_addr:
                    building_normalized_addr = normalizer.normalize_for_comparison(primary_building.address)
                    primary_building.normalized_address = building_normalized_addr
                    self.safe_flush(session)
                
                # 住所の一致度を計算
                address_score = 0
                if building_normalized_addr == normalized_address:
                    address_score = 100  # 完全一致
                elif building_normalized_addr.startswith(normalized_address) or normalized_address.startswith(building_normalized_addr):
                    address_score = 80   # 部分一致
                else:
                    continue  # 住所が一致しない場合はスキップ
                
                # 属性の一致度を計算
                attribute_score = 0
                if self._verify_building_attributes_strict(primary_building, total_floors, built_year, built_month, total_units):
                    attribute_score = 100  # 厳密一致
                elif self._verify_building_attributes(primary_building, total_floors, built_year, built_month, total_units):
                    attribute_score = 70   # 許容誤差一致
                else:
                    continue  # 属性が一致しない場合はスキップ
                
                # 建物名の一致度を計算
                name_score = 0
                if listing_match.listing_name == search_key:
                    name_score = 100  # 元の名前と完全一致
                elif listing_match.canonical_name == canonical_search:
                    name_score = 90   # 正規化名と完全一致
                else:
                    name_score = 50   # その他
                
                # 総合スコアを計算（住所を最重視、属性次重視、名前は参考程度）
                total_score = (address_score * 0.5) + (attribute_score * 0.4) + (name_score * 0.1)
                
                # より良い候補があれば更新
                if total_score > best_score:
                    best_score = total_score
                    best_candidate = {
                        'building': primary_building,
                        'address_score': address_score,
                        'attribute_score': attribute_score,
                        'name_score': name_score,
                        'total_score': total_score,
                        'listing_name': listing_match.listing_name
                    }
            
            # 最適な候補が見つかった場合
            if best_candidate:
                building = best_candidate['building']
                address_match_type = "完全一致" if best_candidate['address_score'] == 100 else "部分一致"
                attribute_match_type = "厳密一致" if best_candidate['attribute_score'] == 100 else "許容誤差一致"
                
                self.logger.info(
                    f"BuildingListingNameから最適な建物を選択（住所{address_match_type}・{attribute_match_type}・スコア{best_candidate['total_score']:.1f}）: "
                    f"'{search_key}' → '{building.normalized_name}' (建物ID: {building.id})"
                )
                return building
            else:
                self.logger.debug(f"BuildingListingNameで複数候補が見つかったが、住所または属性が一致する建物がない")
        
        # === 3. 段階的建物検索（部分一致・厳密一致 → 許容誤差、一致度優先） ===
        # 正式名称完全一致・別名完全一致で見つからない場合、段階的検索を実行
        # 1. 建物名部分一致（前方一致→部分一致）
        # 2. 厳密属性一致を優先
        # 3. 許容誤差一致をフォールバック
        
        if normalized_address:  # 住所がある場合のみ実行
            staged_result = self._find_buildings_with_staged_matching(
                session, search_key, normalized_address, total_floors, built_year, built_month, total_units
            )
            if staged_result:
                return staged_result
        
        self.logger.debug(f"一致する建物が見つかりません: {search_key} at {address} （正規化: {normalized_address}）")
        return None
    
    def get_or_create_building(self, building_name: str, address: str = None, external_property_id: str = None, 
                               built_year: int = None, built_month: int = None, total_floors: int = None, 
                               basement_floors: int = None, total_units: int = None, structure: str = None, 
                               land_rights: str = None, station_info: str = None) -> Tuple[Optional[Building], Optional[str]]:
        """
        建物を取得または作成
        
        常に新しいトランザクションスコープで実行
        """
        if not building_name:
            return None, None
        
        with self.transaction_scope() as session:
            return self._get_or_create_building_with_session(
                session, building_name, address, external_property_id,
                built_year, built_month, total_floors, basement_floors,
                total_units, structure, land_rights, station_info
            )
    
    def _get_or_create_building_with_session(self, session, building_name: str, address: str = None, 
                               external_property_id: str = None, built_year: int = None, built_month: int = None, 
                               total_floors: int = None, basement_floors: int = None, total_units: int = None, 
                               structure: str = None, land_rights: str = None, station_info: str = None) -> Tuple[Optional[Building], Optional[str]]:
        """建物を取得または作成（セッションを受け取るバージョン）"""
        # 元の建物名を保持
        original_building_name = building_name
        
        # 広告文が含まれている場合は、建物名部分のみを抽出
        extracted_name = extract_building_name_from_ad_text(building_name)
        if extracted_name and extracted_name != building_name:
            self.logger.debug(f"広告文から建物名を抽出: '{building_name}' → '{extracted_name}'")
            building_name = extracted_name
        elif not extracted_name:
            # 抽出に失敗した場合は元の名前をそのまま使用
            self.logger.debug(f"建物名抽出に失敗、元の名前を使用: '{building_name}'")
            building_name = original_building_name
        
        # 外部IDがある場合は先に検索
        if external_property_id:
            # ハンドラーを使用して既存の外部IDをチェック
            handler = self._ensure_external_id_handler(session)
            existing_external = handler.get_existing_external_id(
                self.source_site, external_property_id
            )
            
            if existing_external:
                # 既存の建物を使用
                building = session.query(Building).get(existing_external.building_id)
                if building:
                    print(f"[既存] 外部IDで建物を発見: {building.normalized_name} (ID: {building.id})")
                    # 建物名から部屋番号を抽出
                    _, extracted_room_number = self.normalizer.extract_room_number(building_name)
                    
                    # 建物情報を更新（より詳細な情報があれば）
                    updated = False
                    if address and not building.address:
                        building.address = address
                        # 正規化住所も更新
                        if hasattr(building, 'normalized_address'):
                            from ..utils.address_normalizer import AddressNormalizer
                            addr_normalizer = AddressNormalizer()
                            building.normalized_address = addr_normalizer.normalize_for_comparison(address)
                        updated = True
                    # 築年月の更新（既存の値がないか、異なる値の場合は更新）
                    if built_year and building.built_year != built_year:
                        old_built_year = building.built_year
                        building.built_year = built_year
                        updated = True
                        if old_built_year:
                            self.logger.info(f"築年月を更新: {old_built_year} → {built_year}, 建物ID: {building.id}")
                    if built_month and not building.built_month:
                        building.built_month = built_month
                        updated = True
                    if total_floors and not building.total_floors:
                        building.total_floors = total_floors
                        updated = True
                    if basement_floors and not building.basement_floors:
                        building.basement_floors = basement_floors
                        updated = True
                    if structure and not building.construction_type:
                        building.construction_type = structure
                        updated = True
                    if land_rights and not building.land_rights:
                        building.land_rights = land_rights
                        updated = True
                    if station_info and not building.station_info:
                        building.station_info = station_info
                        updated = True
                    if updated:
                        self.safe_flush(session)
                    
                    return building, extracted_room_number
                else:
                    # 外部IDは存在するが建物が見つからない（データ不整合）
                    orphaned_building_id = existing_external.building_id
                    print(f"[WARNING] 外部ID {external_property_id} に紐づく建物ID {orphaned_building_id} が存在しません")
                    # 孤立した外部IDレコードを削除
                    session.delete(existing_external)
                    self.safe_flush(session)
                    print(f"[INFO] 孤立した外部IDレコード（building_id={orphaned_building_id}）を削除しました")
                    # 重要: 孤立レコード削除後は新規建物作成として処理を続行
        
        # 建物名から部屋番号を抽出（内部処理用）
        clean_building_name, extracted_room_number = self.normalizer.extract_room_number(building_name)
        
        # 比較用の検索キーを生成（最小限の正規化）
        search_key = self.get_search_key_for_building(clean_building_name)
        
        # 既存の建物を検索（一元化された検索ロジック）
        building = self.find_existing_building_by_key(session, search_key, address, total_floors, built_year, built_month, total_units)
        
        if building:
            print(f"[INFO] 既存建物を発見: {building.normalized_name} (ID: {building.id})")
            
            # 建物情報を更新（より詳細な情報があれば）
            updated = False
            # 築年月の更新（既存の値がないか、異なる値の場合は更新）
            if built_year and building.built_year != built_year:
                old_built_year = building.built_year
                building.built_year = built_year
                updated = True
                if old_built_year:
                    self.logger.info(f"築年月を更新: {old_built_year} → {built_year}, 建物ID: {building.id}")
            if built_month and not building.built_month:
                building.built_month = built_month
                updated = True
            if total_floors and not building.total_floors:
                building.total_floors = total_floors
                updated = True
            if basement_floors and not building.basement_floors:
                building.basement_floors = basement_floors
                updated = True
            if structure and not building.construction_type:
                building.construction_type = structure
                updated = True
            if land_rights and not building.land_rights:
                building.land_rights = land_rights
                updated = True
            if station_info and not building.station_info:
                building.station_info = station_info
                updated = True
            
            if updated:
                self.safe_flush(session)
            
            # 外部IDを追加（既存の建物でも、外部IDが未登録の場合は追加）
            if external_property_id:
                # ハンドラーを使用して外部IDを追加
                handler = self._ensure_external_id_handler(session)
                success = handler.add_external_id(
                    building.id, self.source_site, external_property_id
                )
                if success:
                    print(f"[INFO] 既存建物に外部IDを関連付け: building_id={building.id}, external_id={external_property_id}")
            
            return building, extracted_room_number
        
        # 新規建物の場合、処理済みの建物名を使用
        normalized_name = clean_building_name
        
        # 新規建物を作成
        print(f"[INFO] 新規建物を作成: {normalized_name}")
        
        # 住所を正規化
        normalized_addr = None
        if address:
            from ..utils.address_normalizer import AddressNormalizer
            addr_normalizer = AddressNormalizer()
            normalized_addr = addr_normalizer.normalize_for_comparison(address)
        
        building = Building(
            normalized_name=normalized_name,  # 元の名前を使用
            canonical_name=search_key,        # 検索キーを保存
            address=address,
            normalized_address=normalized_addr,  # 正規化された住所を保存
            built_year=built_year,
            built_month=built_month,          # 最初の掲載情報から設定
            total_floors=total_floors,
            basement_floors=basement_floors,  # 地下階数も設定
            construction_type=structure,      # structureはconstruction_typeとして保存
            land_rights=land_rights,          # 土地権利も設定
            station_info=station_info         # 交通情報も設定
        )
        session.add(building)
        self.safe_flush(session)
        
        # デバッグ: 新規作成された建物のIDを確認
        self.logger.info(f"[DEBUG] 新規建物作成後のID: {building.id}, 名前: {building.normalized_name}")
        
        # 念のため、作成された建物が実際にデータベースに存在するか確認
        verify_building = session.query(Building).filter(Building.id == building.id).first()
        if not verify_building:
            self.logger.error(f"[CRITICAL] 新規作成した建物ID {building.id} がデータベースに見つかりません！")
            raise RuntimeError(f"新規作成した建物ID {building.id} がデータベースに見つかりません")
        else:
            self.logger.debug(f"[OK] 新規建物ID {building.id} の存在を確認")
        
        # 外部IDを追加（ある場合）
        if external_property_id:
            # external_id_handlerを遅延初期化
            if self.external_id_handler is None:
                self.external_id_handler = BuildingExternalIdHandler(session, self.logger)
            
            # ハンドラーを使用して外部IDを追加
            success = self.external_id_handler.add_external_id(
                building.id, self.source_site, external_property_id
            )
            if success:
                print(f"[INFO] 新規建物に外部IDを関連付け: building_id={building.id}, external_id={external_property_id}")
        
        return building, extracted_room_number
    
    def get_or_create_master_property(self, building: Building, room_number: str = None,
                                        floor_number: int = None, area: float = None,
                                        layout: str = None, direction: str = None,
                                        balcony_area: float = None, url: str = None,
                                        use_learning: bool = True) -> MasterProperty:
        """
        マスター物件を取得または作成（学習機能付き）
        
        常に新しいトランザクションスコープで実行
        """
        with self.transaction_scope() as session:
            return self._get_or_create_master_property_with_session(
                session, building, room_number, floor_number, area,
                layout, direction, balcony_area, url, use_learning
            )
    
    def _get_or_create_master_property_with_session(self, session, building: Building, room_number: str = None,
                                                    floor_number: int = None, area: float = None,
                                                    layout: str = None, direction: str = None,
                                                    balcony_area: float = None, url: str = None,
                                                    use_learning: bool = True) -> MasterProperty:
        """マスター物件を取得または作成（セッション指定版）"""
        # 同一物件の判定条件：建物、所在階、平米数、間取り、方角が一致
        # 部屋番号は両方に値がある場合のみ一致を要求（片方が未入力なら無視）
        
        # 階数の整合性チェック（物件の階数が建物の総階数を超えていないか）
        if floor_number is not None and building.total_floors is not None:
            if floor_number > building.total_floors:
                self.logger.warning(
                    f"物件の階数({floor_number}階)が建物の総階数({building.total_floors}階)を"
                    f"超えています。建物ID: {building.id}, 建物名: {building.normalized_name}"
                )
                # この場合、建物への紐付けを中止するべきだが、
                # 既存のロジックを大幅に変更する必要があるため、
                # まずは警告ログを出力するに留める
        
        # デバッグログ
        self.logger.info(f"Property search: building_id={building.id}, floor={floor_number}, "
                        f"area={area}, layout={layout}, direction={direction}, room_number={room_number}")
        
        # 既存のマスター物件を検索（絶対条件で）
        query = session.query(MasterProperty).filter(
            MasterProperty.building_id == building.id
        )
        
        # 階数は必須条件
        if floor_number is not None:
            query = query.filter(MasterProperty.floor_number == floor_number)
        else:
            query = query.filter(MasterProperty.floor_number.is_(None))
            
        # 面積は必須条件（0.5㎡の誤差を許容）
        if area is not None:
            query = query.filter(
                MasterProperty.area.between(area - 0.5, area + 0.5)
            )
        else:
            query = query.filter(MasterProperty.area.is_(None))
        
        # 間取りは必須条件
        if layout:
            normalized_layout = self.fuzzy_matcher.normalize_layout(layout)
            query = query.filter(MasterProperty.layout == normalized_layout)
        else:
            query = query.filter(MasterProperty.layout.is_(None))
        
        # 方角は必須条件（正規化して比較）
        if direction:
            normalized_direction = self.fuzzy_matcher.normalize_direction(direction)
            query = query.filter(MasterProperty.direction == normalized_direction)
        else:
            query = query.filter(MasterProperty.direction.is_(None))
        
        # ここまでの条件で候補を取得
        candidates = query.all()
        
        # 部屋番号による絞り込み（特殊なロジック）
        master_property = None
        
        # 完全一致する候補が見つからない場合、学習機能を使用
        if not candidates and use_learning:
            try:
                from ..utils.property_learning import PropertyLearningService
                learning_service = PropertyLearningService(session)
                
                # 学習結果を使った柔軟な検索
                flexible_candidates = learning_service.find_property_with_learning(
                    building_id=building.id,
                    floor_number=floor_number,
                    area=area,
                    layout=layout,
                    direction=direction,
                    room_number=room_number
                )
                
                if flexible_candidates:
                    self.logger.info(f"学習機能により{len(flexible_candidates)}件の候補物件を発見")
                    candidates = flexible_candidates
                    
                    # 学習により見つかった物件の場合、向きのバリエーションをログに記録
                    if direction:
                        variations = learning_service.get_direction_variations(building.id, floor_number)
                        if variations and len(variations) > 1:
                            self.logger.info(f"この階の方角バリエーション: {variations}")
            except ImportError:
                self.logger.debug("PropertyLearningServiceが利用できません")
            except Exception as e:
                self.logger.warning(f"学習機能の実行中にエラー: {e}")
        
        # 複数候補がある場合の処理と記録
        if len(candidates) > 1:
            self.logger.warning(
                f"⚠️ 複数の物件候補が見つかりました（{len(candidates)}件）: "
                f"building_id={building.id}, floor={floor_number}, area={area}, "
                f"layout={layout}, direction={direction}, room_number={room_number}"
            )
            
            # 候補の詳細をログに記録
            candidate_details = []
            for i, cand in enumerate(candidates):
                self.logger.info(
                    f"  候補{i+1}: ID={cand.id}, "
                    f"部屋番号={cand.room_number}, "
                    f"階={cand.floor_number}, "
                    f"面積={cand.area}㎡, "
                    f"間取り={cand.layout}, "
                    f"方角={cand.direction}"
                )
                candidate_details.append({
                    'id': cand.id,
                    'room_number': cand.room_number,
                    'floor_number': cand.floor_number,
                    'area': cand.area,
                    'layout': cand.layout,
                    'direction': cand.direction
                })
        
        if room_number:
            # 新規物件に部屋番号がある場合
            # 優先順位: 1. 部屋番号完全一致、2. 部屋番号なし、3. 最初の候補
            exact_match = None
            no_room_match = None
            
            for candidate in candidates:
                if candidate.room_number:
                    # 両方に部屋番号がある場合は一致を要求
                    if candidate.room_number == room_number:
                        exact_match = candidate
                        break
                else:
                    # 既存物件に部屋番号がない場合は候補として保持
                    if not no_room_match:
                        no_room_match = candidate
            
            # 優先順位に従って選択
            if exact_match:
                master_property = exact_match
                self.logger.info(f"部屋番号が完全一致: {room_number}")
            elif no_room_match:
                master_property = no_room_match
                self.logger.info(f"部屋番号なしの物件を選択（部屋番号を追加予定: {room_number}）")
            elif candidates:
                master_property = candidates[0]
                self.logger.warning(
                    f"部屋番号が一致する物件がないため、最初の候補を選択: "
                    f"ID={candidates[0].id}, 既存部屋番号={candidates[0].room_number}"
                )
        else:
            # 新規物件に部屋番号がない場合
            if candidates:
                # 優先順位: 部屋番号がない物件を優先
                no_room_candidates = [c for c in candidates if not c.room_number]
                
                if no_room_candidates:
                    master_property = no_room_candidates[0]
                    self.logger.info("部屋番号なし同士でマッチング")
                else:
                    # すべての候補に部屋番号がある場合は最初の候補を選択
                    master_property = candidates[0]
                    if len(candidates) > 1:
                        self.logger.warning(
                            f"複数候補から最初の物件を選択: "
                            f"ID={candidates[0].id}, 部屋番号={candidates[0].room_number}"
                        )
                    if master_property.room_number:
                        self.logger.info(f"新規物件に部屋番号なし、既存物件の部屋番号={master_property.room_number}を維持")
        
        # 複数候補から選択した場合、曖昧なマッチングとして記録
        if master_property and len(candidates) > 1:
            try:
                # 信頼度スコアを計算（部屋番号の一致度に基づく）
                confidence_score = 0.5  # デフォルト
                selection_reason = "複数候補から選択"
                
                if room_number and master_property.room_number == room_number:
                    confidence_score = 0.9
                    selection_reason = "部屋番号が完全一致"
                elif room_number and not master_property.room_number:
                    confidence_score = 0.7
                    selection_reason = "既存物件に部屋番号なし（追加予定）"
                elif not room_number and not master_property.room_number:
                    confidence_score = 0.6
                    selection_reason = "両方とも部屋番号なし"
                else:
                    confidence_score = 0.3
                    selection_reason = "部屋番号不一致のため最初の候補を選択"
                
                # AmbiguousPropertyMatchに記録（モデルが存在する場合）
                try:
                    from ..models_property_matching import AmbiguousPropertyMatch
                    
                    ambiguous_match = AmbiguousPropertyMatch(
                        source_site=str(self.source_site),
                        scraping_url=url,
                        scraping_data={
                            'floor_number': floor_number,
                            'area': area,
                            'layout': layout,
                            'direction': direction,
                            'room_number': room_number
                        },
                        selected_property_id=master_property.id,
                        selection_reason=selection_reason,
                        candidate_property_ids=[c.id for c in candidates],
                        candidate_details=candidate_details,
                        candidate_count=len(candidates),
                        building_id=building.id,
                        floor_number=floor_number,
                        area=area,
                        layout=layout,
                        direction=direction,
                        room_number=room_number,
                        confidence_score=confidence_score,
                        used_learning=use_learning and not candidates  # 学習機能を使った場合
                    )
                    session.add(ambiguous_match)
                    # 信頼度に応じてログレベルを変更
                    if confidence_score >= 0.7:
                        self.logger.info(
                            f"曖昧なマッチングを記録（高信頼度）: "
                            f"選択ID={master_property.id}, "
                            f"候補数={len(candidates)}, "
                            f"信頼度={confidence_score:.1%}, "
                            f"理由={selection_reason}"
                        )
                    else:
                        self.logger.warning(
                            f"⚠️ 曖昧なマッチングを記録（低信頼度）: "
                            f"選択ID={master_property.id}, "
                            f"候補数={len(candidates)}, "
                            f"信頼度={confidence_score:.1%}, "
                            f"理由={selection_reason}"
                        )
                except ImportError:
                    # モデルが存在しない場合はスキップ
                    pass
            except Exception as e:
                self.logger.debug(f"曖昧なマッチングの記録に失敗: {e}")
        
        if master_property:
            # 既存物件の情報を更新（より詳細な情報があれば）
            updated = False
            # 部屋番号の更新（既存が空の場合のみ）
            if room_number and not master_property.room_number:
                master_property.room_number = room_number
                updated = True
                self.logger.info(f"部屋番号を追加: {room_number}")
            if floor_number and not master_property.floor_number:
                master_property.floor_number = floor_number
                updated = True
            if area and not master_property.area:
                master_property.area = area
                updated = True
            if layout and not master_property.layout:
                master_property.layout = self.fuzzy_matcher.normalize_layout(layout)
                updated = True
            if direction and not master_property.direction:
                master_property.direction = self.fuzzy_matcher.normalize_direction(direction)
                updated = True
            if balcony_area and not master_property.balcony_area:
                master_property.balcony_area = balcony_area
                updated = True
            
            if updated:
                # デッドロック対策：リトライロジック
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        self.safe_flush(session)
                        break
                    except Exception as e:
                        if "deadlock detected" in str(e).lower() and attempt < max_retries - 1:
                            self.logger.warning(f"デッドロック検出、リトライ {attempt + 1}/{max_retries}")
                            session.rollback()
                            # 少し待機してからリトライ
                            import time
                            time.sleep(0.1 * (attempt + 1))
                            # 再度同じ更新を試みる（トランザクションは自動的に開始される）
                            master_property = session.query(MasterProperty).filter(
                                MasterProperty.id == master_property.id
                            ).first()
                            if master_property and balcony_area and not master_property.balcony_area:
                                master_property.balcony_area = balcony_area
                        else:
                            raise
            
            return master_property
        
        # 新規作成
        self.logger.info(f"[DEBUG] 新規MasterProperty作成: building_id={building.id if building else 'None'}, floor={floor_number}, room={room_number}")
        
        # buildingオブジェクトの検証
        if building and not session.query(Building).filter(Building.id == building.id).first():
            self.logger.error(f"[ERROR] 建物ID {building.id} がデータベースに存在しません！")
            # 建物を再取得または作成
            raise ValueError(f"建物ID {building.id} がデータベースに存在しません")
        
        master_property = MasterProperty(
            building_id=building.id,
            room_number=room_number,
            floor_number=floor_number,
            area=area,
            layout=self.fuzzy_matcher.normalize_layout(layout) if layout else None,
            direction=self.fuzzy_matcher.normalize_direction(direction) if direction else None,
            balcony_area=balcony_area
        )
        session.add(master_property)
        
        try:
            self.safe_flush(session)
        except Exception as e:
            # 重複エラーの場合はロールバックして再検索
            if "duplicate key value violates unique constraint" in str(e):
                self.logger.warning(f"Duplicate property detected, rolling back and retrying")
                session.rollback()
                
                # 再度検索（同じ条件で）
                return self._get_or_create_master_property_with_session(
                    session, building, room_number, floor_number, area, 
                    layout, direction, balcony_area, url, use_learning
                )
            else:
                # その他のエラーは再発生
                raise
        
        return master_property
    
    def create_or_update_listing(self, master_property: MasterProperty, url: str, title: str,
                               price: int, agency_name: str = None, site_property_id: str = None,
                               description: str = None, station_info: str = None,
                               management_fee: int = None, repair_fund: int = None,
                               published_at: datetime = None, first_published_at: datetime = None,
                               **kwargs) -> tuple[PropertyListing, str, dict]:
        """
        掲載情報を作成または更新
        
        常に新しいトランザクションスコープで実行
        """
        with self.transaction_scope() as session:
            return self._create_or_update_listing_with_session(
                session, master_property, url, title, price, agency_name,
                site_property_id, description, station_info, management_fee,
                repair_fund, published_at, first_published_at, **kwargs
            )
    
    def _create_or_update_listing_with_session(self, session, master_property: MasterProperty, url: str, title: str,
                               price: int, agency_name: str = None, site_property_id: str = None,
                               description: str = None, station_info: str = None,
                               management_fee: int = None, repair_fund: int = None,
                               published_at: datetime = None, first_published_at: datetime = None,
                               **kwargs) -> tuple[PropertyListing, str]:
        """掲載情報を作成または更新（セッションを受け取るバージョン）"""
        # 戻り値を初期化
        update_type = None
        update_details = None
        changed_fields = []
        # site_property_idがある場合は、それを使って既存の掲載を検索
        if site_property_id:
            listing = session.query(PropertyListing).filter(
                PropertyListing.source_site == self.source_site,
                PropertyListing.site_property_id == site_property_id
            ).first()
            
            # 既存掲載が見つかり、かつmaster_property_idが異なる場合の処理
            # これは通常、save_property_commonで既に同じmaster_propertyが渡されているはずなので、
            # 発生しないはずだが、念のためチェック
            if listing and listing.master_property_id != master_property.id:
                self.logger.warning(
                    f"掲載情報のmaster_property_idが異なります: "
                    f"既存={listing.master_property_id}, 新規={master_property.id}, "
                    f"site_property_id={site_property_id}"
                )
                # 既存の関係を優先（save_property_commonで処理済みのはず）
                # master_propertyを明示的に取得（lazy loadエラーを回避）
                master_property = session.query(MasterProperty).filter(
                    MasterProperty.id == listing.master_property_id
                ).first()
        else:
            # site_property_idがない場合は、URLとmaster_property_idで検索
            listing = session.query(PropertyListing).filter(
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
            existing_with_same_url = session.query(PropertyListing).filter(
                PropertyListing.url == url,
                PropertyListing.source_site == self.source_site
            ).first()
            
            if existing_with_same_url:
                # 同じURLで別の物件が存在する場合
                if existing_with_same_url.master_property_id != master_property.id:
                    # 別の物件の場合、古い方を非アクティブにする
                    self.logger.info(f"同じURLで別の物件が存在 (旧物件ID: {existing_with_same_url.master_property_id})")
                    existing_with_same_url.is_active = False
                    existing_with_same_url.delisted_at = get_utc_now()
                    self.safe_flush(session)
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
        
        # 既存のリスティングがある場合のupdate_typeは後で判定
        update_type = None
        
        if listing:
            # 更新タイプを判定
            price_changed = False
            other_changed = False
            old_price = listing.current_price  # 更新前の価格を保存（ログ用）
            # changed_fieldsは既にメソッドの先頭で初期化済み
            
            # 価格が変更されている場合は履歴を記録
            if listing.current_price != price:
                price_changed = True
                price_history = ListingPriceHistory(
                    property_listing_id=listing.id,
                    price=price,
                    recorded_at=get_utc_now()
                )
                session.add(price_history)
                
                # 現在価格を更新
                listing.current_price = price
                listing.price_updated_at = get_utc_now()
                
                # 価格履歴をデータベースに反映してから価格改定日を更新
                self.safe_flush(session)  # 重要: 価格履歴をDBに反映
                
                # 価格改定日を更新
                from ..utils.property_utils import update_latest_price_change
                update_latest_price_change(session, master_property.id)
            
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
            
            # 非アクティブだった掲載を再アクティブ化
            was_inactive = not listing.is_active
            listing.is_active = True
            listing.last_confirmed_at = get_utc_now()
            listing.detail_fetched_at = get_utc_now()  # 詳細取得時刻を更新
            
            # 掲載が再アクティブ化され、物件が販売終了になっていた場合は販売再開
            if was_inactive and master_property.sold_at:
                self.logger.info(f"掲載再開により販売終了物件を販売再開 - 物件ID: {master_property.id}, 掲載ID: {listing.id}")
                master_property.sold_at = None
                master_property.final_price = None
                master_property.final_price_updated_at = None
                self.safe_flush(session)
            
            # 更新タイプを判定
            update_details = None
            if price_changed:
                update_type = 'price_updated'
                # 価格変更の詳細を記録（旧価格と新価格）
                update_details = f"価格変更: {old_price}万円 → {price}万円"
                
                # 物件と建物の詳細情報を含むログメッセージ
                building_name = kwargs.get('listing_building_name', listing.listing_building_name or '')
                if master_property and master_property.building:
                    building_name = master_property.building.normalized_name or building_name
                
                detail_info = []
                if master_property:
                    if master_property.floor_number:
                        detail_info.append(f"{master_property.floor_number}階")
                    if master_property.area:
                        detail_info.append(f"{master_property.area}㎡")
                    if master_property.layout:
                        detail_info.append(f"{master_property.layout}")
                    if master_property.direction:
                        detail_info.append(f"{master_property.direction}向き")
                
                detail_str = ' / '.join(detail_info) if detail_info else ''
                
                # 建物名を含む自然なログメッセージ
                if building_name:
                    if detail_str:
                        self.logger.info(f"価格更新: {building_name} {detail_str} - {old_price}万円 → {price}万円 - {url}")
                    else:
                        self.logger.info(f"価格更新: {building_name} - {old_price}万円 → {price}万円 - {url}")
                else:
                    if detail_str:
                        self.logger.info(f"価格更新: {detail_str} - {old_price}万円 → {price}万円 - {url}")
                    else:
                        self.logger.info(f"価格更新: {old_price}万円 → {price}万円 - {url}")
            elif other_changed:
                update_type = 'other_updates'
                update_details = ', '.join(changed_fields)  # 変更内容を記録
                
                # 物件と建物の詳細情報を含むログメッセージ
                building_name = kwargs.get('listing_building_name', listing.listing_building_name or '')
                if master_property and master_property.building:
                    building_name = master_property.building.normalized_name or building_name
                
                detail_info = []
                if master_property:
                    if master_property.floor_number:
                        detail_info.append(f"{master_property.floor_number}階")
                    if master_property.area:
                        detail_info.append(f"{master_property.area}㎡")
                    if master_property.layout:
                        detail_info.append(f"{master_property.layout}")
                    if master_property.direction:
                        detail_info.append(f"{master_property.direction}向き")
                
                detail_str = ' / '.join(detail_info) if detail_info else ''
                
                # 建物名と物件詳細を含む自然なログメッセージ
                if building_name:
                    if detail_str:
                        self.logger.info(f"その他更新: {building_name} {detail_str} - 詳細: {update_details} - {url}")
                    else:
                        self.logger.info(f"その他更新: {building_name} - 詳細: {update_details} - {url}")
                else:
                    if detail_str:
                        self.logger.info(f"その他更新: {detail_str} - 詳細: {update_details} - {url}")
                    else:
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
                        elif key == 'listing_built_year' and old_value != value:
                            # 築年月の変更は重要
                            other_changed = True
                            if old_value is not None:
                                changed_fields.append(f'築年({old_value}年→{value}年)')
                            else:
                                changed_fields.append(f'築年(新規設定: {value}年)')
                            self.logger.info(f"築年月を更新: {old_value} → {value}, URL: {url}")
                        elif key == 'listing_built_month' and old_value != value:
                            other_changed = True
                            if old_value is not None:
                                changed_fields.append(f'築月({old_value}月→{value}月)')
                                self.logger.info(f"築月を更新: {old_value}月 → {value}月, URL: {url}")
                            else:
                                changed_fields.append(f'築月(新規設定: {value}月)')
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
                    # varchar(20)制限があるフィールドの値を切り詰める
                    if key in ['listing_layout', 'listing_direction'] and isinstance(value, str) and len(value) > 20:
                        self.logger.warning(f"{key}の値が20文字を超えているため切り詰めます: '{value[:20]}...'")
                        value = value[:20]
                    setattr(listing, key, value)
            
            # 更新タイプを再判定（kwargsでの変更も含める）
            if other_changed and update_type == 'refetched_unchanged':
                update_type = 'other_updates'
                update_details = ', '.join(changed_fields)
                self.logger.info(f"その他更新（追加フィールド）: {url} - 詳細: {update_details}")
        else:
            # 新規作成
            update_type = None  # update_type変数を初期化
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
                    management_fee=management_fee,
                    repair_fund=repair_fund,
                    is_active=True,
                    published_at=published_at,
                    first_published_at=first_published_at or published_at or get_utc_now(),
                    price_updated_at=first_published_at or published_at or get_utc_now(),
                    last_confirmed_at=get_utc_now(),
                    detail_fetched_at=get_utc_now(),  # 詳細取得時刻を設定
                    **kwargs
                )
                session.add(listing)
                self.safe_flush(session)
                
                # 最初の掲載日を更新
                update_earliest_listing_date(session, master_property.id)
                # 価格改定日を更新（新規なので価格履歴追加と同時）
                from ..utils.property_utils import update_latest_price_change
                update_latest_price_change(session, master_property.id)
            except Exception as e:
                # URL重複エラーまたはsite_property_id重複エラーの場合は、再度検索して既存レコードを使用
                if "property_listings_url_key" in str(e) or "property_listings_site_property_unique" in str(e):
                    session.rollback()
                    self.logger.debug(f"重複エラー検出。既存レコードを再検索... エラー: {str(e)}")
                    
                    # 再度検索（他のプロセスが同時に作成した可能性）
                    # site_property_idがある場合はそれで検索、なければURLで検索
                    if site_property_id:
                        listing = session.query(PropertyListing).filter(
                            PropertyListing.source_site == self.source_site,
                            PropertyListing.site_property_id == site_property_id
                        ).first()
                    else:
                        listing = session.query(PropertyListing).filter(
                            PropertyListing.url == url,
                            PropertyListing.source_site == self.source_site
                        ).first()
                    
                    if listing:
                        print(f"  → 既存レコード発見 (ID: {listing.id}, 物件ID: {listing.master_property_id})")
                        if listing.master_property_id != master_property.id:
                            # 別の物件の場合は、古い方を非アクティブにする
                            print(f"  → 別の物件のため、古い方を非アクティブ化")
                            listing.is_active = False
                            listing.delisted_at = get_utc_now()
                            self.safe_flush(session)
                            
                            # 非アクティブ化された物件の最初の掲載日を更新
                            if listing.master_property_id:
                                update_earliest_listing_date(session, listing.master_property_id)
                                # 価格改定日も更新（非アクティブ化により再計算が必要）
                                from ..utils.property_utils import update_latest_price_change
                                update_latest_price_change(session, listing.master_property_id)
                            
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
                                            management_fee=management_fee,
                                repair_fund=repair_fund,
                                is_active=True,
                                published_at=published_at,
                                first_published_at=first_published_at or published_at or datetime.now(),
                                price_updated_at=first_published_at or published_at or datetime.now(),
                                last_confirmed_at=datetime.now(),
                                detail_fetched_at=datetime.now(),
                                **kwargs
                            )
                            session.add(listing)
                            self.safe_flush(session)
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
                recorded_at=get_utc_now()  # datetime.now()ではなくget_utc_now()を使用（統一）
            )
            session.add(price_history)
            
            # 価格履歴をデータベースに反映してから価格改定日を更新
            self.safe_flush(session)  # 重要: 価格履歴をDBに反映
            
            # 価格改定日を更新（初回登録も価格設定として扱う）
            from ..utils.property_utils import update_latest_price_change
            update_latest_price_change(session, master_property.id)
            
            # 新規作成の場合、update_typeを'new'に設定（update_typeがまだ設定されていない場合）
            if update_type is None:
                update_type = 'new'
            
            # 新規掲載追加時、物件が販売終了になっていた場合は販売再開
            if master_property.sold_at:
                self.logger.info(f"販売終了物件に新規掲載が追加されたため販売再開 - 物件ID: {master_property.id}")
                master_property.sold_at = None
                master_property.final_price = None
                master_property.final_price_updated_at = None
                self.safe_flush(session)
            
            # 物件と建物の詳細情報を含むログメッセージ
            building_name = kwargs.get('listing_building_name', '')
            if master_property and master_property.building:
                building_name = master_property.building.normalized_name or building_name
            
            detail_info = []
            if master_property:
                if master_property.floor_number:
                    detail_info.append(f"{master_property.floor_number}階")
                if master_property.area:
                    detail_info.append(f"{master_property.area}㎡")
                if master_property.layout:
                    detail_info.append(f"{master_property.layout}")
                if master_property.direction:
                    detail_info.append(f"{master_property.direction}向き")
            
            detail_str = ' / '.join(detail_info) if detail_info else ''
            
            # 建物名と価格を含む自然なログメッセージ
            if building_name:
                if detail_str:
                    self.logger.info(f"新規登録: {building_name} {detail_str} - {price}万円 - {url}")
                else:
                    self.logger.info(f"新規登録: {building_name} - {price}万円 - {url}")
            else:
                if detail_str:
                    self.logger.info(f"新規登録: {detail_str} - {price}万円 - {url}")
                else:
                    self.logger.info(f"新規登録: {price}万円 - {url}")
        
        # 掲載情報の登録・更新後、BuildingListingNameテーブルを更新
        if listing and listing.listing_building_name:
            try:
                # セッションごとに新しいマネージャーインスタンスを作成
                from ..utils.building_listing_name_manager import BuildingListingNameManager
                listing_name_manager = BuildingListingNameManager(session)
                listing_name_manager.update_from_listing(listing)
            except Exception as e:
                self.logger.warning(f"BuildingListingNameの更新に失敗しました: {e}")
                self._handle_transaction_error(e, "BuildingListingName更新エラー")
        
        # 建物名と物件情報を多数決で更新
        self._update_by_majority_vote(session, master_property)
        
        # update_detailsが未設定の場合の処理
        if update_details is None:
            # other_changedがTrueでchanged_fieldsがある場合は、update_detailsを生成
            if update_type == 'other_updates' and changed_fields:
                update_details = ', '.join(changed_fields)
        
        # update_typeが設定されていない場合の処理
        if update_type is None:
            # elseブロック（新規作成）を通った場合、update_typeは未設定なので'new'を設定
            # 既存リスティングで変更がない場合は'refetched_unchanged'を設定すべきだが、
            # その場合はelseブロック（2953行目）で既に設定されているはず
            update_type = 'new'
            self.logger.debug(f"update_type未設定のため'new'を設定: {url}")
        
        # デバッグログ
        if update_type == 'other_updates' and not update_details:
            self.logger.warning(f"その他更新と判定されたが詳細が空です - URL: {url}")
        
        return listing, update_type, update_details
    
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
            with self.transaction_scope() as session:
                retry_record = session.query(Url404Retry).filter(
                    Url404Retry.url == url,
                    Url404Retry.source_site == self.source_site.value
                ).first()
                
                if retry_record:
                    # 再試行間隔を計算
                    retry_hours = self._calculate_retry_interval(retry_record.error_count)
                    hours_since_error = (datetime.now() - retry_record.last_error_at).total_seconds() / 3600
                    
                    if hours_since_error < retry_hours:
                        self.logger.warning(
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
            self._handle_transaction_error(e, "404エラーチェック")
            # エラーが発生した場合はスキップしない（処理を続行）
            return False
    
    def _should_skip_url_due_to_validation_error(self, url: str) -> bool:
        """検証エラー履歴によりスキップすべきURLか判定"""
        try:
            with self.transaction_scope() as session:
                from ..models import PropertyValidationError
                
                # PropertyValidationErrorテーブルから確認
                error_record = session.query(PropertyValidationError).filter(
                    PropertyValidationError.url == url,
                    PropertyValidationError.source_site == self.source_site.value
                ).first()
                
                if error_record:
                    # 再試行間隔を計算（404エラーと同じロジック）
                    retry_hours = self._calculate_retry_interval(error_record.error_count)
                    hours_since_error = (datetime.now() - error_record.last_error_at).total_seconds() / 3600
                    
                    if hours_since_error < retry_hours:
                        self.logger.warning(
                            f"検証エラー履歴によりスキップ: {url} "
                            f"(エラータイプ: {error_record.error_type}, "
                            f"エラー回数: {error_record.error_count}, "
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
            self.logger.debug(f"検証エラー履歴チェック中にエラー: {e}")
            self._handle_transaction_error(e, "検証エラーチェック")
            # エラーが発生した場合はスキップしない（処理を続行）
            return False
    
    def _should_skip_due_to_price_mismatch(self, site_property_id: str) -> bool:
        """価格不一致履歴によりスキップすべきか判定"""
        # 現在のテーブル構造では価格不一致のリトライ管理は未実装
        # 将来的に実装する場合はここに処理を追加
        return False
        
        # 以下は将来実装時のコード（コメントアウト）
        """
        try:
            with self.transaction_scope() as session:
                # price_mismatch_historyテーブルから確認
                result = session.execute(
                text('''
                    SELECT retry_count, attempted_at
                    FROM price_mismatch_history 
                    WHERE site_property_id = :site_id 
                    AND source_site = :site
                    AND is_resolved = false
                    ORDER BY attempted_at DESC
                    LIMIT 1
                '''),
                    {'site_id': site_property_id, 'site': self.source_site.value}
                ).first()
                
                if result:
                    retry_count, attempted_at = result
                    
                    # エラー回数に基づいて再試行間隔を計算（時間単位）
                    retry_hours = self._calculate_retry_interval(retry_count)
                    hours_since_error = (datetime.now() - attempted_at).total_seconds() / 3600
                    
                    if hours_since_error < retry_hours:
                        self.logger.warning(
                            f"価格不一致履歴によりスキップ: ID={site_property_id} "
                            f"(エラー回数: {retry_count}, "
                            f"最終エラーから: {hours_since_error:.1f}時間, "
                            f"再試行間隔: {retry_hours}時間)"
                        )
                        return True
                    else:
                        self.logger.debug(
                            f"価格不一致履歴ありだが再試行可能: ID={site_property_id} "
                            f"(最終エラーから{hours_since_error:.1f}時間経過)"
                        )
                return False
        except Exception as e:
            self.logger.debug(f"価格不一致履歴チェック中にエラー: {e}")
            self._handle_transaction_error(e, "価格不一致チェック")
            # エラーが発生した場合はスキップしない（処理を続行）
            return False
        """
    
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
            with self.transaction_scope() as session:
                # 既存のレコードを確認
                retry_record = session.query(Url404Retry).filter(
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
                    session.add(retry_record)
                    self.logger.info("404エラーを記録 (初回、次回再試行は2時間後以降)")
                
                # トランザクションは with 文を抜ける際に自動的にコミット
                
        except Exception as e:
            self.logger.error(f"404エラー記録中にエラー: {e}")
            # トランザクションはwith文を抜ける際に自動的にロールバック
    
    
    def _handle_validation_error(self, url: str, error_type: str, error_details: dict = None):
        """検証エラーのURLを記録"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、検証エラーを記録しません: {url}")
            return
            
        try:
            with self.transaction_scope() as session:
                from ..models import PropertyValidationError
                import json
                
                # 既存のレコードを確認
                error_record = session.query(PropertyValidationError).filter(
                    PropertyValidationError.url == url,
                    PropertyValidationError.source_site == self.source_site.value
                ).first()
                
                if error_record:
                    # エラー回数を更新
                    error_record.error_count += 1
                    error_record.last_error_at = datetime.now()
                    error_record.error_type = error_type
                    error_record.error_details = json.dumps(error_details or {}, ensure_ascii=False)
                    
                    # 再試行間隔を計算
                    retry_hours = self._calculate_retry_interval(error_record.error_count)
                    
                    self.logger.info(
                        f"検証エラー再発生 ({error_type}) - "
                        f"URL: {url}, 回数: {error_record.error_count}, "
                        f"次回再試行までの最小間隔: {retry_hours}時間"
                    )
                else:
                    # 新規レコードを作成
                    new_error = PropertyValidationError(
                        url=url,
                        source_site=self.source_site.value,
                        error_type=error_type,
                        error_details=json.dumps(error_details or {}, ensure_ascii=False),
                        error_count=1,
                        first_error_at=datetime.now(),
                        last_error_at=datetime.now()
                    )
                    session.add(new_error)
                    self.logger.info(f"検証エラーを記録 ({error_type}) - URL: {url} (初回、次回再試行は2時間後以降)")
                
                # トランザクションは with 文を抜ける際に自動的にコミット
                
        except Exception as e:
            self.logger.error(f"検証エラー記録中にエラー: {e}")
            # トランザクションはwith文を抜ける際に自動的にロールバック
    
    
    def _record_price_mismatch(self, site_property_id: str, url: str, list_price: int, detail_price: int):
        """価格不一致を記録"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、価格不一致を記録しません: {site_property_id}")
            return
            
        try:
            with self.transaction_scope() as session:
                # 既存のエラー記録を確認してエラー回数を取得
                result = session.execute(
                    text("""
                        SELECT retry_count 
                        FROM price_mismatch_history 
                        WHERE site_property_id = :site_id 
                        AND source_site = :site
                        AND is_resolved = false
                    """),
                    {'site_id': site_property_id, 'site': self.source_site.value}
                ).first()
                
                if result:
                    # 既存記録がある場合はエラー回数を増やす
                    retry_count = result[0] + 1
                else:
                    # 新規記録の場合
                    retry_count = 1
                
                # エラー回数に基づいて再試行間隔を計算（時間単位）
                retry_hours = self._calculate_retry_interval(retry_count)
                
                sql = text("""
                INSERT INTO price_mismatch_history 
                (source_site, site_property_id, property_url, list_price, detail_price, 
                 retry_after, retry_count)
                VALUES (:source_site, :site_property_id, :url, :list_price, :detail_price, 
                        NOW() + INTERVAL ':retry_hours hours', :retry_count)
                ON CONFLICT (source_site, site_property_id) 
                DO UPDATE SET 
                    list_price = :list_price,
                    detail_price = :detail_price,
                    attempted_at = NOW(),
                    retry_after = NOW() + INTERVAL ':retry_hours hours',
                    retry_count = :retry_count,
                    is_resolved = false
                """.replace(':retry_hours', str(retry_hours)))
                
                session.execute(sql, {
                    'source_site': self.source_site.value,
                    'site_property_id': site_property_id,
                    'url': url,
                    'list_price': list_price,
                    'detail_price': detail_price,
                    'retry_count': retry_count
                })
                # トランザクションは with 文を抜ける際に自動的にコミット
                
                self.logger.warning(
                    f"価格不一致を記録 - ID: {site_property_id}, "
                    f"一覧: {list_price}万円, 詳細: {detail_price}万円, "
                    f"エラー回数: {retry_count}, 再試行間隔: {retry_hours}時間"
                )
                
        except Exception as e:
            self.logger.error(f"価格不一致記録中のエラー: {e}")
            # トランザクションはwith文を抜ける際に自動的にロールバック

    def _record_validation_error(self, url: str, site_property_id: str, error_type: str, error_details: str = None):
        """検証エラーを記録し、再試行間隔を管理"""
        # エラー履歴無視モードの場合は記録しない
        if self.ignore_error_history:
            self.logger.info(f"エラー履歴無視モードのため、検証エラーを記録しません: {url}")
            return
            
        try:
            with self.transaction_scope() as session:
                from ..models import PropertyValidationError
                
                # 既存のエラー記録を確認
                error_record = session.query(PropertyValidationError).filter(
                    PropertyValidationError.url == url,
                    PropertyValidationError.source_site == self.source_site.value
                ).first()
                
                if error_record:
                    # 既存記録を更新
                    error_record.error_count += 1
                    error_record.last_error_at = datetime.now()
                    error_record.error_details = error_details
                    error_record.site_property_id = site_property_id or error_record.site_property_id
                    
                    self.logger.warning(
                        f"検証エラーを更新 - URL: {url}, タイプ: {error_type}, "
                        f"エラー回数: {error_record.error_count}"
                    )
                else:
                    # 新規記録を作成
                    error_record = PropertyValidationError(
                        url=url,
                        source_site=self.source_site.value,
                        site_property_id=site_property_id,
                        error_type=error_type,
                        error_details=error_details,
                        first_error_at=datetime.now(),
                        last_error_at=datetime.now(),
                        error_count=1
                    )
                    session.add(error_record)
                    
                    self.logger.warning(
                        f"検証エラーを新規記録 - URL: {url}, タイプ: {error_type}"
                    )
                
                # トランザクションは with 文を抜ける際に自動的にコミット
                
        except Exception as e:
            self.logger.error(f"検証エラー記録中のエラー: {e}")
            # トランザクションはwith文を抜ける際に自動的にロールバック
    
    
    
    def _is_paused(self) -> bool:
        """一時停止状態かどうかを確認（データベースベース）"""
        task_status = self._check_task_status_from_db()
        return task_status["is_paused"]
    
    def _is_cancelled(self) -> bool:
        """キャンセル状態かどうかを確認（データベースベース）"""
        # データベースベースのチェック
        if self.task_id:
            try:
                from ..models_scraping_task import ScrapingTask
                task = session.query(ScrapingTask).filter(
                    ScrapingTask.task_id == self.task_id
                ).first()
                
                # タスクが存在しない場合は即座に停止
                if not task:
                    self.logger.error(f"タスク {self.task_id} がデータベースに存在しません。スクレイピングを停止します。")
                    return True
                
                # タスクの状態をチェック
                if task.status == 'cancelled' or task.is_cancelled:
                    self.logger.warning(f"タスク {self.task_id} がキャンセルされました。スクレイピングを停止します。")
                    return True
                elif task.status in ['completed', 'error']:
                    self.logger.warning(f"タスク {self.task_id} の状態が '{task.status}' です。スクレイピングを停止します。")
                    return True
                elif task.status not in ['running', 'paused']:
                    # その他の未知の状態
                    self.logger.warning(f"タスク {self.task_id} の状態が不正です: '{task.status}'。スクレイピングを停止します。")
                    return True
                    
            except Exception as e:
                self.logger.debug(f"Failed to check task cancellation status: {e}")
        
        return False


    

    

    
    def _update_by_majority_vote(self, session: Session, master_property: MasterProperty):
        """多数決で情報を更新（エラーが発生しても処理は続行）"""
        if not master_property:
            return
            
        try:
            from ..utils.majority_vote_updater import MajorityVoteUpdater
            majority_updater = MajorityVoteUpdater(session)
            
            # 物件情報を多数決で更新
            try:
                majority_updater.update_master_property_by_majority(master_property)
                self.safe_flush(session)  # 変更を確定
            except Exception as e:
                self.logger.warning(f"物件情報の更新に失敗しました (property_id={master_property.id}): {e}")
                if self._handle_transaction_error(e, "多数決更新エラー"):
                    # セッションがリセットされたため、master_propertyを再取得
                    try:
                        master_property = session.query(MasterProperty).get(master_property.id)
                        if not master_property:
                            return
                    except Exception:
                        self.logger.error(f"マスター物件の再取得に失敗しました (property_id={master_property.id})")
                        return
            
            # 建物情報を多数決で更新
            if master_property.building_id:
                try:
                    # セッションがリセットされた可能性があるため、再度インポート
                    from ..utils.majority_vote_updater import MajorityVoteUpdater
                    majority_updater = MajorityVoteUpdater(session)
                    
                    # 建物情報を多数決で更新
                    building = session.query(Building).get(master_property.building_id)
                    if building:
                        # 建物名を含む全属性を多数決で更新
                        majority_updater.update_building_by_majority(building)
                        # 建物名の個別更新も実行（より最新の重み付けロジックを使用）
                        majority_updater.update_building_name_by_majority(master_property.building_id)
                    self.safe_flush(session)  # 変更を確定
                except Exception as e:
                    self.logger.warning(f"建物情報の更新に失敗しました (building_id={master_property.building_id}): {e}")
                    self._handle_transaction_error(e, "建物情報更新エラー")
                
                # 物件の表示用建物名を多数決で更新
                try:
                    # セッションがリセットされた可能性があるため、再度インポート
                    from ..utils.majority_vote_updater import MajorityVoteUpdater
                    majority_updater = MajorityVoteUpdater(session)
                    majority_updater.update_property_building_name_by_majority(master_property.id)
                    self.safe_flush(session)  # 変更を確定
                except Exception as e:
                    self.logger.warning(f"物件建物名の更新に失敗しました (property_id={master_property.id}): {e}")
                    self._handle_transaction_error(e, "物件建物名更新エラー")
        except Exception as e:
            self.logger.warning(f"多数決更新全体でエラー: {e}")
    
    def _log_validation_failure(self, property_data: Dict[str, Any]):
        """バリデーション失敗をログに記録"""
        url = property_data.get('url', '不明')
        failure_reason = ""
        
        if not property_data.get('price'):
            self._scraping_stats['price_missing'] += 1
            failure_reason = "価格情報なし"
        elif not property_data.get('building_name'):
            self._scraping_stats['building_info_missing'] += 1
            failure_reason = "建物名なし"
        elif not property_data.get('site_property_id'):
            self._scraping_stats['other_errors'] += 1
            failure_reason = "サイト物件IDなし"
        else:
            self._scraping_stats['other_errors'] += 1
            failure_reason = "その他のバリデーションエラー"
        
        print(f"  → 保存失敗: {failure_reason} (URL: {url})")
        
        if hasattr(self, '_save_error_log'):
            self._save_error_log({
                'url': url,
                'reason': failure_reason,
                'building_name': property_data.get('building_name', ''),
                'price': property_data.get('price', ''),
                'timestamp': datetime.now().isoformat()
            })
    
    def save_property_common(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """
        物件情報を保存する共通メソッド（新バージョン）
        
        トランザクション管理をコンテキストマネージャーで簡潔に実装
        注: existing_listingパラメータは後方互換性のため残しているが、使用しない
        """
        try:
            with self.transaction_scope() as session:
                # 詳細取得をスキップした場合の処理
                if not property_data.get('detail_fetched', False):
                    # 既存物件の確認と更新
                    if property_data.get('site_property_id'):
                        existing_listing = session.query(PropertyListing).filter(
                            PropertyListing.source_site == self.source_site,
                            PropertyListing.site_property_id == property_data['site_property_id']
                        ).first()
                        
                        if existing_listing:
                            # 最終確認日時を更新
                            existing_listing.last_scraped_at = datetime.now()
                            existing_listing.last_confirmed_at = datetime.now()
                            
                            # 非アクティブな掲載を再アクティブ化
                            if not existing_listing.is_active:
                                existing_listing.is_active = True
                                print(f"  → 掲載を再開 (ID: {existing_listing.id})")
                                
                                # 物件が販売終了になっていた場合は販売再開
                                if existing_listing.master_property_id:
                                    master_prop = session.query(MasterProperty).filter(
                                        MasterProperty.id == existing_listing.master_property_id
                                    ).first()
                                    if master_prop and master_prop.sold_at:
                                        master_prop.sold_at = None
                                        master_prop.final_price = None
                                        master_prop.final_price_updated_at = None
                                        print(f"  → 物件を販売再開 (物件ID: {master_prop.id})")
                            
                            print(f"  → 既存物件の最終確認日時を更新 (ID: {existing_listing.id})")
                            property_data['update_type'] = 'skipped'
                            property_data['property_saved'] = True
                            return True
                    
                    # 詳細取得していない新規物件は保存しない
                    property_data['property_saved'] = False
                    return False
                
                # データの妥当性チェック
                if not self.validate_property_data(property_data):
                    self._log_validation_failure(property_data)
                    property_data['property_saved'] = False
                    return False
                
                # 既存の掲載情報を確認
                existing_listing = None
                if property_data.get('site_property_id'):
                    existing_listing = session.query(PropertyListing).filter(
                        PropertyListing.source_site == self.source_site,
                        PropertyListing.site_property_id == property_data['site_property_id']
                    ).first()
                
                # 既存の掲載情報から物件・建物を取得、または新規作成
                if existing_listing and existing_listing.master_property_id:
                    # 既存の物件と建物を使用
                    master_property = session.query(MasterProperty).filter(
                        MasterProperty.id == existing_listing.master_property_id
                    ).first()
                    
                    if master_property:
                        building = master_property.building
                        extracted_room_number = master_property.room_number
                    else:
                        # master_propertyが見つからない場合は新規作成
                        # 現在のトランザクション内で建物を作成
                        building, extracted_room_number = self._get_or_create_building_with_session(
                            session,
                            building_name=property_data.get('building_name', ''),
                            address=property_data.get('address'),
                            external_property_id=property_data.get('external_property_id'),
                            built_year=property_data.get('built_year'),
                            built_month=property_data.get('built_month'),
                            total_floors=property_data.get('total_floors'),
                            structure=property_data.get('structure'),
                            land_rights=property_data.get('land_rights'),
                            station_info=property_data.get('station_info')
                        )
                        master_property = None
                else:
                    # 新規作成
                    # 現在のトランザクション内で建物を作成
                    building, extracted_room_number = self._get_or_create_building_with_session(
                        session,
                        building_name=property_data.get('building_name', ''),
                        address=property_data.get('address'),
                        external_property_id=property_data.get('external_property_id'),
                        built_year=property_data.get('built_year'),
                        built_month=property_data.get('built_month'),
                        total_floors=property_data.get('total_floors'),
                        structure=property_data.get('structure'),
                        land_rights=property_data.get('land_rights'),
                        station_info=property_data.get('station_info')
                    )
                    master_property = None
                
                if not building:
                    self.logger.warning(f"建物の作成に失敗: {property_data.get('building_name', '')}")
                    property_data['property_saved'] = False
                    return False
                
                # マスター物件を取得または作成
                if not master_property:
                    # 現在のトランザクション内でマスター物件を作成
                    master_property = self._get_or_create_master_property_with_session(
                        session,
                        building=building,
                        room_number=property_data.get('room_number', extracted_room_number),
                        floor_number=property_data.get('floor_number'),
                        area=property_data.get('area'),
                        layout=property_data.get('layout'),
                        direction=property_data.get('direction'),
                        balcony_area=property_data.get('balcony_area')
                    )
                
                if not master_property:
                    self.logger.warning("マスター物件の作成に失敗")
                    property_data['property_saved'] = False
                    return False
                
                # summary_remarksをMasterPropertyに保存
                if property_data.get('summary_remarks') and not master_property.summary_remarks:
                    master_property.summary_remarks = property_data['summary_remarks']
                
                # 掲載情報を作成または更新（create_or_update_listingは独自のトランザクションを使用）
                try:
                    listing_kwargs = {
                        'listing_building_name': property_data.get('building_name'),
                        'listing_floor_number': property_data.get('floor_number'),
                        'listing_area': property_data.get('area'),
                        'listing_layout': property_data.get('layout'),
                        'listing_direction': property_data.get('direction'),
                        'listing_total_floors': property_data.get('total_floors'),
                        'listing_balcony_area': property_data.get('balcony_area'),
                        'listing_built_year': property_data.get('built_year'),
                        'listing_built_month': property_data.get('built_month'),
                        'listing_address': property_data.get('address'),
                        'remarks': property_data.get('remarks'),
                        'agency_tel': property_data.get('agency_tel'),
                        'scraped_from_area': getattr(self, 'current_area_code', None)
                    }
                    
                    # Noneの値を除外
                    listing_kwargs = {k: v for k, v in listing_kwargs.items() if v is not None}
                    
                    result = self.create_or_update_listing(
                        master_property=master_property,
                        url=property_data['url'],
                        title=property_data.get('title', ''),
                        price=property_data['price'],
                        agency_name=property_data.get('agency_name'),
                        site_property_id=property_data.get('site_property_id'),
                        description=property_data.get('description'),
                        station_info=property_data.get('station_info'),
                        management_fee=property_data.get('management_fee'),
                        repair_fund=property_data.get('repair_fund'),
                        published_at=property_data.get('published_at'),
                        first_published_at=property_data.get('first_published_at'),
                        **listing_kwargs
                    )
                    
                    # 戻り値を展開
                    if len(result) == 2:
                        listing, update_type = result
                        update_details = None
                    else:
                        listing, update_type, update_details = result
                except Exception as e:
                    raise
                
                # 更新タイプを設定
                property_data['update_type'] = update_type
                property_data['update_details'] = update_details
                
                # サブクラス固有の処理
                if hasattr(self, '_post_listing_creation_hook'):
                    self._post_listing_creation_hook(session, listing, property_data)
                
                # 多数決で情報を更新
                self._update_by_majority_vote(session, master_property)
                
                # コミットはwith文を抜ける時に自動実行
                property_data['property_saved'] = True
                return True
                
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            import traceback
            self.logger.error(f"物件保存エラー: {e}")
            self.logger.error(f"詳細なトレースバック:\n{traceback.format_exc()}")
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
        """重大エラーアラートをデータベースに記録（重複を避けるため既存のアラートを更新）
        
        Args:
            field_name: エラーが発生したフィールド名
            error_count: エラー件数
            error_rate: エラー率
        """
        try:
            with self.transaction_scope() as session:
                from sqlalchemy import text
                from ..models import ScraperAlert
                
                # まず既存のアクティブアラートがあるか確認
                # field_nameはdetails JSON内に格納されているため、別の方法でチェック
                existing_alerts = session.query(ScraperAlert).filter(
                    ScraperAlert.source_site == self.source_site,
                    ScraperAlert.alert_type == 'critical_field_error',
                    ScraperAlert.is_active == True
                ).all()
                
                existing_alert = None
                for alert in existing_alerts:
                    if alert.details and alert.details.get('field_name') == field_name:
                        existing_alert = alert
                        break
                
                message = (
                    f"{self.source_site}のスクレイパーで重要フィールド'{field_name}'の"
                    f"エラー率が{error_rate:.1%}（{error_count}件）に達しました。"
                    f"HTML構造の変更を確認してください。"
                )
                
                details = {
                    'error_count': error_count,
                    'error_rate': error_rate,
                    'field_name': field_name,
                    'threshold': self._error_thresholds
                }
                
                if existing_alert:
                    # 既存のアラートを更新
                    existing_alert.message = message
                    existing_alert.details = details
                    existing_alert.updated_at = datetime.now()
                else:
                    # 新規アラートを作成
                    new_alert = ScraperAlert(
                        source_site=self.source_site,
                        alert_type='critical_field_error',
                        severity='high',
                        message=message,
                        details=details
                    )
                    session.add(new_alert)
                
                # トランザクションは with 文を抜ける際に自動的にコミット
                
        except Exception as e:
            self.logger.error(f"アラート記録エラー: {e}")
            # トランザクションはwith文を抜ける際に自動的にロールバック
    
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
        - building_name: 建物名
        
        Args:
            property_data: 物件データ
            
        Returns:
            bool: 必須フィールドがすべて存在する場合True
        """
        required_fields = ['url', 'site_property_id', 'price', 'building_name']
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
            'layout': '間取り',
            'built_year': '築年'
        }
        
        missing_fields = []
        missing_fields_jp = []
        required_fields = self.get_required_detail_fields()
        
        for field in required_fields:
            if field not in property_data or property_data.get(field) is None:
                missing_fields.append(field)
                missing_fields_jp.append(field_names_jp.get(field, field))
        
        # エラー情報を保存（process_property_with_detail_checkで使用）
        # missing_fields_jpが空の場合のチェックを追加
        if missing_fields_jp:
            reason_detail = f"必須フィールド（{', '.join(missing_fields_jp)}）が取得できませんでした"
        else:
            # すべてのフィールドが存在する場合（このメソッドが呼ばれるべきではないが念のため）
            reason_detail = "検証エラーが発生しました"
        
        self._last_detail_error = {
            'type': 'validation',
            'reason': f"{error_type}: {reason_detail}",
            'building_name': property_data.get('building_name', ''),
            'price': property_data.get('price', ''),
            'site_property_id': property_data.get('site_property_id', ''),
        }
        
        # ログにも出力（開発者向けは英語フィールド名も含める）
        if missing_fields:
            self.logger.error(f"{error_type}: {url} - 必須フィールドが取得できませんでした: {', '.join(missing_fields)} ({', '.join(missing_fields_jp)})")
        else:
            self.logger.error(f"{error_type}: {url} - 検証エラーが発生しました")
        
        return None
    
    def validate_address(self, address: str) -> bool:
        """住所が都道府県から始まる完全な形式であることを検証
        
        Args:
            address: 検証する住所文字列
            
        Returns:
            bool: 都道府県から始まる完全な住所の場合True
        """
        if not address:
            return False
        
        # 日本の都道府県のリスト
        prefectures = [
            '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
            '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
            '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
            '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
            '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
            '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
            '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
        ]
        
        # 住所が都道府県で始まるかチェック
        for prefecture in prefectures:
            if address.startswith(prefecture):
                # 都道府県だけでなく、それ以降の住所情報があることを確認
                if len(address) > len(prefecture):
                    return True
        
        return False

    def validate_detail_page_fields(self, property_data: Dict[str, Any], url: str = None) -> bool:
        """詳細ページで取得した物件データの必須フィールドを検証
        
        詳細ページでは以下のフィールドが必須：
        - site_property_id: サイト内物件ID（URLから抽出）
        - price: 価格
        - building_name: 建物名
        - address: 住所
        - area: 専有面積
        - layout: 間取り
        - built_year: 築年
        
        Args:
            property_data: 物件データ
            url: 物件URL（エラーログ用）
            
        Returns:
            bool: 必須フィールドがすべて存在する場合True
        """
        required_fields = self.get_required_detail_fields()
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
        
        # 築年の値の妥当性をチェック
        built_year = property_data.get('built_year')
        if built_year is not None:
            from .data_normalizer import validate_built_year
            if not validate_built_year(built_year):
                url = url or property_data.get('url', '不明')
                self.record_field_extraction_error('built_year', url)
                self.logger.error(f"築年が不正な値です: {built_year}年 (許容範囲: 1900年～現在年+5年) - URL: {url}")
                return False
        
        # 住所の検証（都道府県から始まる完全な住所かチェック）
        address = property_data.get('address')
        if address and not self.validate_address(address):
            url = url or property_data.get('url', '不明')
            self.record_field_extraction_error('address', url)
            self.logger.error(f"住所が都道府県から始まっていません: {address} - URL: {url}")
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
        """エラーログを保存"""
        # 現在の実装では外部のロギングハンドラー（admin/scraping.py）が
        # このメソッドをオーバーライドしてログを収集する
        pass
    
    def _save_warning_log(self, warning_info: Dict[str, Any]):
        """警告ログを保存"""
        # 現在の実装では外部のロギングハンドラー（admin/scraping.py）が
        # このメソッドをオーバーライドしてログを収集する
        pass

    def log_warning(self, message: str, **kwargs):
        """警告ログを記録する簡潔なインターフェース
        
        Args:
            message: 警告メッセージ
            **kwargs: 追加の情報（url, building_name, price等）
        
        使用例:
            self.log_warning("価格不一致を検出", url=url, 
                           building_name=building_name,
                           price=f"{list_price} → {detail_price}")
        """
        warning_info = {
            'reason': message,
            'timestamp': datetime.now().isoformat()
        }
        warning_info.update(kwargs)
        
        if hasattr(self, '_save_warning_log'):
            self._save_warning_log(warning_info)
    
    def log_error(self, message: str, **kwargs):
        """エラーログを記録する簡潔なインターフェース
        
        Args:
            message: エラーメッセージ
            **kwargs: 追加の情報（url, building_name, price等）
        
        使用例:
            self.log_error("物件処理エラー", url=url, 
                         building_name=building_name, 
                         error_detail=str(e))
        """
        error_info = {
            'reason': message,
            'timestamp': datetime.now().isoformat()
        }
        error_info.update(kwargs)
        
        if hasattr(self, '_save_error_log'):
            self._save_error_log(error_info)

    def _post_listing_creation_hook(self, session, listing: PropertyListing, property_data: Dict[str, Any]):
        """掲載情報作成後のフック（サブクラスでオーバーライド可能）"""
        pass

    def __del__(self):
        """
        デストラクタ
        
        HTTPセッションをクリーンアップ
        """
        # トランザクションは transaction_scope() で自動管理される
        
        if hasattr(self, 'http_session'):
            try:
                self.http_session.close()
            except Exception:
                pass

    def clean_address(self, address: str) -> str:
        """
        住所文字列をクリーニングする共通メソッド
        主にJavaScriptやmetaタグから取得した住所のクリーニング用
        
        Args:
            address: クリーニング前の住所文字列
            
        Returns:
            クリーニング済みの住所文字列
        """
        if not address:
            return address
            
        # 元の値を保存
        original_address = address
        
        # よくある不要なUIテキストのパターンを削除
        # (HTMLから取得した場合、Aタグは既に削除済みだが、
        #  JavaScriptやmetaタグから取得した場合に備えて)
        ui_patterns = [
            r'地図を見る',
            r'マップを見る',
            r'地図で見る',
            r'MAP',
            r'>>+',
            r'→+',
            r'詳細地図',
            r'周辺地図',
            r'地図表示',
            r'Googleマップ',
            r'地図',
        ]
        
        for pattern in ui_patterns:
            address = re.sub(pattern, '', address)
              
        # 不要な記号や空白文字を削除
        address = re.sub(r'\s+', '', address)  # 全角・半角スペースを削除
        address = re.sub(r'[(\(][^)\)]*[)\)]', '', address)  # 括弧内の補足情報を削除
        address = re.sub(r'[・\-―─→←↑↓》《〉〈]+$', '', address)  # 末尾の不要な記号を削除
        
        # 空白のみになった場合は元の値を返す
        if not address.strip():
            return original_address.strip()
            
        return address.strip()
    
    def validate_address(self, address: str) -> bool:
        """
        住所が有効かどうかを検証する
        
        Args:
            address: 検証する住所文字列
            
        Returns:
            有効な住所の場合True
        """
        if not address:
            return False
            
        # クリーニング後の住所で検証
        cleaned = self.clean_address(address)
        
        # 最小文字数チェック（都道府県名だけでも最低3文字）
        if len(cleaned) < 3:
            return False
            
        # 住所に含まれるべきパターン（都道府県、市区町村など）
        address_patterns = [
            r'[都道府県]',
            r'[市区町村]',
            r'[0-9０-９]+[丁目番地号\-－−]',
        ]
        
        # いずれかのパターンにマッチすれば有効な住所と判定
        for pattern in address_patterns:
            if re.search(pattern, cleaned):
                return True
                
        # 東京23区の特別パターン
        if re.search(r'東京都.+区', cleaned):
            return True
            
        return False
    
    def extract_address_from_element(self, element) -> str:
        """
        HTML要素から住所テキストを抽出する
        リンクなどのUI要素を除外して純粋な住所テキストのみを取得
        
        Args:
            element: BeautifulSoupの要素（通常はdd要素など）
            
        Returns:
            クリーニング済みの住所文字列
        """
        if not element:
            return ""
            
        # 要素のコピーを作成（元の要素を変更しないため）
        import copy
        element_copy = copy.copy(element)
        
        # シンプルにAタグ（リンク）を削除
        # これだけで「地図を見る」のようなリンクテキストが除外される
        for tag in element_copy.find_all('a'):
            tag.decompose()
        
        # その他の明らかなUI要素も削除（ボタン、画像、入力フィールド）
        for tag in element_copy.find_all(['button', 'img', 'input', 'svg', 'iframe']):
            tag.decompose()
        
        # テキストを取得
        address_text = element_copy.get_text(strip=True)
        
        # 念のため、残っている可能性のあるUIテキストをクリーニング
        # （JavaScriptで動的に追加される場合などに対応）
        return self.clean_address(address_text)

def extract_building_name_from_ad_text(ad_text: str) -> str:
    """
    広告テキストから建物名を抽出する独立関数
    純粋に広告文除去処理のみを実行し、判定は行わない
    """
    import re
    
    if not ad_text:
        return ad_text
    
    original_text = ad_text.strip()
    if not original_text:
        return ""
    
    # 統一された広告文除去処理
    if not original_text or not original_text.strip():
        return ""
        
    current_text = original_text.strip()
    
    # Step 1: 全文レベルでの階数・方角情報除去
    WING_NAMES = r'[A-Z東西南北本新旧]'
    
    # 棟名保持パターン（棟名を保持して階数のみ除去）
    BUILDING_WING_PATTERN = rf'({WING_NAMES}棟)\s*\d+階'
    current_text = re.sub(BUILDING_WING_PATTERN, r'\1', current_text)
    
    # 通常の階数・方角除去パターン
    floor_removal_patterns = [
        r'\s*\d+階\s*/\s*\d+階\s*',      # 7階/7階 パターン
        r'\s*\d+階\s*/\s*-+\s*',          # 4階/--- パターン
        r'\s*\(\d+F\)\s*',                # (4F) パターン
        r'\s*\d+階部分\s*',                 # 10階部分、1階部分 パターン
        r'\s*\d+階.*向き\s*',               # 19階南向き、3階南東向き パターン
        r'\s+\d+階\s+\d+LDK\s*',          # 1階 2LDK パターン
    ]
    
    for pattern in floor_removal_patterns:
        current_text = re.sub(pattern, ' ', current_text)
    
    # Step 2: 記号をすべてスペースに統一（・は保護）
    symbols_pattern = r'[☆★◆◇｜～〜【】■□▲△▼▽◎○●◯※＊\[\]「」『』（）()]'
    current_text = re.sub(symbols_pattern, ' ', current_text)
    
    # Step 3: 複数スペースを単一スペースに統一
    current_text = re.sub(r'\s+', ' ', current_text.strip())
    
    # Step 4: スペースで単語に分割してフィルタリング
    words = current_text.split()
    
    # 建物名キーワード（保護対象）
    building_keywords = [
        'マンション', 'タワー', 'ハウス', 'レジデンス', 'ヒルズ', 'パーク', '棟', 'コート', 
        'TOWER', 'RESIDENCE', 'HOUSE', 'PARK', 'COURT', 'HILL', 'HILLS', 'CITY',
        'ビル', 'ビルディング', 'プラザ', 'スクエア', 'ガーデン', 'アイランド',
        'PLAZA', 'SQUARE', 'GARDEN', 'ISLAND', 'SUITE', 'GRAND', 'BLUE', 'CLEARE',
        'FAMILLE', 'DUET', 'DUO', 'SCALA', 'DOEL', 'ALLES', 'CLEO', 'GALA',
        'STATION', 'VIEW', 'EAST', 'WEST', 'NORTH', 'SOUTH', 'CENTER',
        'ウエスト', 'イースト', 'ノース', 'サウス', 'セントラル', 'テラス', 'TERRACE',
        'ウエスト', 'ウェスト', 'エスト', 'Est', 'EAST', 'Terrazza',
        '駅前', '駅南', '駅北', '駅東', '駅西'
    ]
    
    # 削除対象のパターン（大幅拡充）
    removal_patterns = [
        r'^(?!.*(住宅|ハウス|マンション|ビル|アパート)).*駅$',  # 建物名キーワードを含まない駅名のみ
        r'徒歩\d+分$', r'JR.*線$', r'東京メトロ.*線$', r'\d+路線利用可$',
        r'リノベーション済?$', r'リフォーム済?$', r'新築未入居$', r'\d{4}年築$',
        r'\d+LDK$', r'WIC$', r'SIC$', r'TR$', r'ペット可$', r'内覧可$',
        r'^\d+階$', r'^\d+F$', r'\d+階部分$', r'\(\d+F\)$', r'\d+階/.*$',
        r'^\d+階.*向き.*$', r'.*\d+階$', r'^\d+th$', r'.*Floor$',
        r'^\d+階部分$',
        # 【】内の典型的な広告文
        r'^リノベーション済み$', r'^新築物件$', r'^仲介手数料無料$', 
        r'^弊社限定公開$', r'^新規物件$', r'^駅近$', r'^オススメ$',
        # 設備・状況情報の拡充（テスト結果に基づく）
        r'^角部屋$', r'^最上階$', r'^美品$', r'^内装リフォーム済$',
        r'^WIC付き$', r'^WIC付$', r'^SIC付$', r'^楽器可$', r'^事務所利用可$', r'^SOHO可$',
        # 築年・距離情報の強化
        r'^築\d+年$', r'^駅徒歩\d+分$', r'^JR.*線利用可$',
        # 路線情報の拡充  
        r'^東京メトロ.*線利用可$', r'^\d+路線利用可$',
        # 令和年号パターン
        r'^令和\d+年築$',
        # テスト結果に基づく改善：間取り情報の除去パターン追加
        r'^1R$', r'^1K$', r'^1DK$', r'^2DK$', r'^3DK$', r'^4DK$', r'^5DK$',
        # テスト結果に基づく改善：設備・施設情報の除去パターン追加
        r'^システムキッチン$', r'^オートロック$', r'^宅配ボックス$', r'^角住戸$',
        r'^システムキッチン付$', r'^オートロック付$', r'^宅配ボックス付$',
        r'^システムキッチン完備$', r'^宅配ボックス完備$',
        # テスト結果に基づく改善：シリーズ名の除去パターン追加
        r'^エクセルシリーズ$', r'^プレミアムシリーズ$', r'^グランドシリーズ$',
        # 追加の間取り・設備パターン
        r'^2LDK$', r'^3LDK$', r'^4LDK$', r'^5LDK$',
        r'^バルコニー付$', r'^専用庭付$', r'^ルーフバルコニー付$',
        r'^エレベーター付$', r'^駐車場付$', r'^駐輪場付$',
        # 追加の状況・品質パターン  
        r'^中古$', r'^新築$', r'^築浅$', r'^リフォーム中古$',
        r'^即入居可$', r'^空室$', r'^賃貸中$'
    ]
    
    # 建物名部分を保護（ザ、The、新等）
    protected_words = [
        'ザ', 'THE', 'The', 'new', 'NEW', '新', 'プライム', 'グランド', 
        'ロイヤル', 'クラッシィ', 'ブランズ', 'クレスト', 'プラウド',
        'セント', 'パレ', 'ドール', 'アルス', 'ベル', 'ヒル', 'サイド',
        'レクセル', 'シャトー', 'エスペランス', 'オープン', 'ファミール',
        'グラン', 'ミューゼ', 'コスタ', 'エクレール', 'Palais', 'Soleil',
        'ドゥ', 'トゥール', 'ドエル', 'サンクタス', 'ミューゼオ', 'ヴィンテージ', 
        'ペア', 'サンリーノ', '森のとなり',
        'ウエスト', 'ウェスト', 'イースト', 'ノース', 'サウス', 'セントラル',
        'テラス', 'エスト', 'Est', 'EAST', 'WEST', 'NORTH', 'SOUTH',
        'プラネ', '悠遊', 'ツイン', 'NORTH棟', 'EAST棟', 'WEST棟'
    ]
    
    filtered_words = []
    for word in words:
        if not word.strip():
            continue
            
        # 建物名キーワードを含む単語は保護
        if any(keyword in word for keyword in building_keywords):
            filtered_words.append(word)
            continue
        
        # 駅名を含む建物名パターンの保護
        if re.search(r'.+駅.*(住宅|ハウス|マンション|ビル|アパート)', word):
            filtered_words.append(word)
            continue
            
        # 保護対象の単語
        if word in protected_words:
            filtered_words.append(word)
            continue
            
        # 棟名保持パターンのチェック（単語レベル）
        wing_match = re.match(BUILDING_WING_PATTERN + '$', word)
        if wing_match:
            filtered_words.append(wing_match.group(1))
            continue
        
        # 削除パターンにマッチするかチェック
        should_remove = False
        for pattern in removal_patterns:
            if re.match(pattern, word):
                should_remove = True
                break
        
        if not should_remove:
            filtered_words.append(word)
    
    # 単語を再結合
    result = ' '.join(filtered_words).strip()
    return result