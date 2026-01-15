"""
LIFULL HOME'Sスクレイパー（リファクタリング版）
homes.co.jpから中古マンション情報を取得
"""

import random
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup
from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import HomesParser
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from .data_normalizer import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors,
    validate_area  # 共通のvalidate_area関数を使用（1000㎡まで対応）
)


class HomesScraper(BaseScraper):
    """LIFULL HOME'Sのスクレイパー"""

    BASE_URL = "https://www.homes.co.jp"
    SOURCE_SITE = SourceSite.HOMES

    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = HomesParser(logger=self.logger)
        # HOMESは一覧ページと詳細ページで建物名の表記が異なることがあるため、部分一致を許可
        self.allow_partial_building_name_match = True
        # MULTI_SOURCEモードを使用（詳細ページの複数箇所から建物名を取得して検証）
        from ..scrapers.base_scraper import BuildingNameVerificationMode
        self.building_name_verification_mode = BuildingNameVerificationMode.MULTI_SOURCE
        self._setup_headers()

        # Playwrightクライアント（AWS WAF対策のためJavaScript実行が必要）
        self._playwright_client = None
        self._request_count = 0  # リクエストカウンター（セッション再起動用）
        self._session_restart_threshold = 50  # この回数ごとにブラウザを再起動

        # カスタムバリデーターを登録
        self.register_custom_validators()

    def register_custom_validators(self):
        """HOMES用のカスタムバリデーターを登録"""
        super().register_custom_validators()

        # 必須フィールドのバリデーターを登録
        # 専有面積: 完全一致を要求
        self.add_required_field_validator('area', exact_match=True)

        # 間取り: 完全一致を要求
        self.add_required_field_validator('layout', exact_match=True)

        # 注: HOMESの一覧ページには所在階情報がないため、バリデーション対象外

    def get_optional_required_fields(self) -> List[str]:
        """HOMESではlayoutは必須ではない（稀に取得できないため）
        
        Returns:
            List[str]: オプショナルな必須フィールドのリスト（空リスト）
        """
        return []  # layoutを必須から除外

    
    def get_partial_required_fields(self) -> Dict[str, Dict[str, Any]]:
        """HOMESの部分的必須フィールドの設定
        
        layoutはほとんどの場合取得できるが、一部の物件で取得できない。
        30%以上の欠損率の場合にエラーとする。
        
        Returns:
            Dict[str, Dict[str, Any]]: 部分的必須フィールドの設定
        """
        return {
            'layout': {
                'max_missing_rate': 0.3,  # 30%までの欠損を許容
                'min_sample_size': 10,     # 10件以上のサンプルで評価
                'empty_values': ['-', '－', '']  # 空とみなす値
            }
        }
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """LIFULL HOME'Sのsite_property_idの妥当性を検証
        
        LIFULL HOME'Sの物件IDは以下の形式：
        - 数字のみ（例：1234567890）
        - b-で始まる英数字（例：b-35005010002458）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # LIFULL HOME'S固有の検証
        # パターン1: 数字のみ
        if site_property_id.isdigit():
            # 通常は7〜12桁程度
            if len(site_property_id) < 7 or len(site_property_id) > 15:
                self.logger.warning(
                    f"[HOMES] site_property_idの桁数が異常です（通常7-15桁）: '{site_property_id}' "
                    f"(桁数: {len(site_property_id)}) URL={url}"
                )
            return True
            
        # パターン2: b-で始まる英数字
        if site_property_id.startswith('b-'):
            remaining = site_property_id[2:]
            if remaining and remaining.replace('-', '').isalnum():
                return True
            else:
                self.logger.error(
                    f"[HOMES] b-形式のsite_property_idが不正です: '{site_property_id}' URL={url}"
                )
                return False
                
        # どちらのパターンにも合致しない
        self.logger.error(
            f"[HOMES] site_property_idの形式が不正です（数字のみ、またはb-で始まる英数字である必要があります）: '{site_property_id}' URL={url}"
        )
        return False
    
    def _setup_headers(self):
        """HTTPヘッダーの設定（フォールバック用）"""
        self.http_client.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })

    def _get_playwright_client(self):
        """Playwrightクライアントを取得（遅延初期化）"""
        if self._playwright_client is None:
            from ..utils.playwright_client import PlaywrightClient
            self._playwright_client = PlaywrightClient(headless=True, timeout=30000)
            self._playwright_client.start()
            self.logger.info("[HOMES] Playwrightクライアントを初期化しました")
        return self._playwright_client

    def cleanup(self):
        """リソースのクリーンアップ"""
        if self._playwright_client is not None:
            self._playwright_client.stop()
            self._playwright_client = None
            self.logger.info("[HOMES] Playwrightクライアントを停止しました")
        super().cleanup() if hasattr(super(), 'cleanup') else None

    def _restart_browser_session(self):
        """ブラウザセッションを再起動（AWS WAF対策）"""
        if self._playwright_client is not None:
            self.logger.info("[HOMES] ブラウザセッションを再起動します（WAF対策）")
            self._playwright_client.stop()
            self._playwright_client = None
            # 再起動前に少し待機
            time.sleep(random.uniform(3, 5))

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得してBeautifulSoupオブジェクトを返す（Playwright使用）"""
        try:
            # ランダムな遅延を追加（3〜6秒、人間らしいアクセスパターン）
            delay = random.uniform(3, 6)
            time.sleep(delay)

            # 一定回数ごとにブラウザセッションを再起動（WAF対策）
            self._request_count += 1
            if self._request_count >= self._session_restart_threshold:
                self._restart_browser_session()
                self._request_count = 0

            # Playwrightを使用してJavaScriptを実行
            client = self._get_playwright_client()

            # 一覧ページと詳細ページで待機するセレクタを変える
            if '/list/' in url:
                wait_selector = '.mod-mergeBuilding, .prg-building'
            else:
                wait_selector = 'h1, .property-detail'

            html = client.fetch_page(url, wait_selector=wait_selector, wait_time=1)

            if not html:
                self.logger.error(f"[HOMES] ページ取得失敗: {url}")
                return None

            # HTMLサイズの確認
            if len(html) < 1000:
                self.logger.warning(f"[HOMES] レスポンスが小さすぎます ({len(html)} bytes): {url}")

            # JavaScript無効ページかどうかを確認
            if 'JavaScript is disabled' in html:
                self.logger.error(f"[HOMES] JavaScript実行に失敗しました: {url}")
                return None

            return BeautifulSoup(html, 'html.parser')

        except Exception as e:
            self.logger.error(f"[HOMES] ページ取得エラー: {url}, {type(e).__name__}: {e}")
            return None
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """HOME'Sの検索URLを生成"""
        from .area_config import get_area_code, get_homes_city_code
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        # ページ1の場合はページパラメータを付けない（HOMESの仕様）
        if page == 1:
            return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/"
        else:
            return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/?page={page}"

    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def is_last_page(self, soup: BeautifulSoup) -> bool:
        """現在のページが最終ページかどうかを判定（パーサーに委譲）"""
        return self.parser.is_last_page(soup)
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        from ..utils.exceptions import PropertyTypeNotSupportedError
        
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        try:
            # パーサーで詳細な解析を実行
            detail_data = self.parser.parse_property_detail(soup)
            
            # スクレイパー固有の処理
            if detail_data:
                detail_data["url"] = url
                detail_data["_page_text"] = soup.get_text()  # 建物名一致確認用
                
                # site_property_idの抽出と検証
                if "site_property_id" not in detail_data and url:
                    import re
                    site_id_match = re.search(r'/mansion/b-(\\d+)/', url)
                    if site_id_match:
                        detail_data["site_property_id"] = site_id_match.group(1)
            
            return detail_data
            
        except PropertyTypeNotSupportedError as e:
            # マンション以外の物件タイプ（タウンハウス、一戸建てなど）は静かにスキップ
            self.logger.info(f"対象外の物件タイプのためスキップ: {url} - {e}")
            return None
    
    def _extract_site_property_id(self, href: str, property_data: Dict[str, Any]) -> bool:
        """URLから物件IDを抽出
        
        Returns:
            bool: 抽出に成功した場合True
        """
        id_match = (re.search(r'/mansion/([0-9]+)/', href) or 
                   re.search(r'/mansion/b-([^/]+)/', href) or 
                   re.search(r'/detail-([0-9]+)/', href))
        if id_match:
            site_property_id = id_match.group(1)
            
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, href):
                self.logger.error(f"[HOMES] 不正なsite_property_idを検出しました: '{site_property_id}'")
                return False
                
            property_data['site_property_id'] = site_property_id
            self.logger.info(f"[HOMES] Extracted site_property_id: {site_property_id}")
            return True
        else:
            self.logger.error(f"[HOMES] サイト物件IDを抽出できません: URL={href}")
            return False
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存"""
        self.process_property_data(property_data, existing_listing)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        url = property_data.get('url', '')
        if '/mansion/b-' in url and not re.search(r'/\d{3,4}[A-Z]?/$', url):
            self.logger.info(f"[HOMES] Processing building URL (will redirect to property): {url}")
        
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property_common
        )
    
    
