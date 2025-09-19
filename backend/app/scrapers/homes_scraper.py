"""
LIFULL HOME'Sスクレイパー（リファクタリング版）
homes.co.jpから中古マンション情報を取得
"""

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
        """HTTPヘッダーの設定"""
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
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得してBeautifulSoupオブジェクトを返す"""
        try:
            time.sleep(3)  # より長い遅延を設定
            
            # リファラーを設定
            if '/list/' in url:
                self.http_client.session.headers['Referer'] = 'https://www.homes.co.jp/'
            else:
                self.http_client.session.headers['Referer'] = 'https://www.homes.co.jp/mansion/chuko/tokyo/list/'
            
            response = self.http_client.session.get(url, timeout=30, allow_redirects=True)
            
            # 405エラーの特別処理
            if response.status_code == 405:
                self.logger.error(f"405 Method Not Allowed for {url}")
                self.logger.info("Trying with modified headers...")
                self.http_client.session.headers['Sec-Fetch-Site'] = 'same-origin'
                self.http_client.session.headers['Sec-Fetch-Mode'] = 'cors'
                time.sleep(5)
                response = self.http_client.session.get(url, timeout=30)
            
            response.raise_for_status()
            
            if len(response.content) < 1000:
                self.logger.warning(f"Response seems too small ({len(response.content)} bytes) for {url}")
            
            return BeautifulSoup(response.content, 'html.parser')
            
        except Exception as e:
            # 404エラーの場合も警告として記録（URL構造が変わった可能性もある）
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                self.logger.warning(f"[HOMES] ページが見つかりません（404）: {url} - 最終ページを超えたか、URL構造が変更された可能性があります")
            else:
                self.logger.error(f"Failed to fetch {url}: {type(e).__name__}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.debug(f"Response headers: {dict(e.response.headers)}")
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
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
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
    
    
