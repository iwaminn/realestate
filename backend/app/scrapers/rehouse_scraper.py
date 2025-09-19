"""
三井のリハウススクレイパー実装

URLパターン:
- 一覧: https://www.rehouse.co.jp/buy/mansion/prefecture/{都道府県}/city/{市区町村}/
- 詳細: https://www.rehouse.co.jp/buy/mansion/bkdetail/{物件コード}/
"""

import re
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
import logging

from bs4 import BeautifulSoup, Tag
import requests

from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import RehouseParser
from ..models import PropertyListing
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)

logger = logging.getLogger(__name__)


class RehouseScraper(BaseScraper):
    """三井のリハウス用スクレイパー"""
    
    SOURCE_SITE = SourceSite.REHOUSE
    BASE_URL = "https://www.rehouse.co.jp"
    
    # 定数の定義
    MIN_PROPERTY_PRICE = 1000  # 物件価格の最小値（万円）
    
    # 価格を含まないキーワード（これらが含まれる価格情報は無視）
    PRICE_EXCLUDE_KEYWORDS = ['管理費', '修繕', '賃料', '駐車場']
    
    # 備考から除外するキーワード
    REMARKS_EXCLUDE_KEYWORDS = ['利用規約', 'Copyright', '個人情報', 'お問い合わせ']
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = RehouseParser(logger=self.logger)
        # http_sessionは削除済み（基底クラスのhttp_clientを使用）
        self.http_client.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
        })
    
    def get_list_url(self, prefecture: str = "13", city: str = "13103", page: int = 1) -> str:
        """一覧ページのURLを生成"""
        base_url = f"{self.BASE_URL}/buy/mansion/prefecture/{prefecture}/city/{city}/"
        
        # ページングパラメータ
        if page > 1:
            return f"{base_url}?page={page}"
        return base_url
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """三井のリハウスのsite_property_idの妥当性を検証
        
        三井のリハウスの物件IDは英数字で構成される（例：F02AGA18）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # 三井のリハウス固有の検証：英数字のみで構成されているか
        if not site_property_id.replace('-', '').replace('_', '').isalnum():
            self.logger.error(
                f"[REHOUSE] site_property_idは英数字（ハイフン・アンダースコア可）で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜12文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[REHOUSE] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行
            
        return True
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """検索URLを生成（共通インターフェース用）"""
        from .area_config import get_area_code
        area_code = get_area_code(area)
        return self.get_list_url("13", area_code, page)
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def _find_property_items(self, soup: BeautifulSoup) -> List[Tag]:
        """物件カードを検索 - パーサーに委譲"""
        return self.parser._find_property_items(soup)
    
    def _parse_property_item(self, item: Tag) -> Optional[Dict]:
        """個別の物件要素から情報を抽出 - パーサーに委譲"""
        property_data = self.parser._parse_property_card(item)
        
        if property_data:
            # site_property_idの妥当性を検証
            if 'site_property_id' in property_data:
                if not self.validate_site_property_id(property_data['site_property_id'], property_data.get('url', '')):
                    self.logger.error(f"[REHOUSE] 不正なsite_property_idを検出しました: '{property_data['site_property_id']}'")
                    return None
        
        return property_data
    

    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（共通インターフェース用）"""
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property
        )
    
    def extract_property_id(self, url: str) -> Optional[str]:
        """URLから物件IDを抽出"""
        import re
        # REHOUSEのURLパターンから物件IDを抽出
        # 例: https://www.rehouse.co.jp/buy/mansion/bkdetail/FK7ARA05/
        match = re.search(r'/([A-Z0-9]+)/$', url)
        if match:
            return match.group(1)
        return None

    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        # パーサーで解析を実行
        detail_data = self.parser.parse_property_detail(soup)
        
        # スクレイパー固有の処理
        if detail_data:
            detail_data["url"] = url
            detail_data["_page_text"] = soup.get_text()  # 建物名一致確認用
            
            # site_property_idの抽出と検証
            if "site_property_id" not in detail_data and url:
                site_id = self.extract_property_id(url)
                if site_id and self.validate_site_property_id(site_id, url):
                    detail_data["site_property_id"] = site_id
        
        return detail_data
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報をデータベースに保存"""
        # 共通の保存処理を使用
        return self.save_property_common(property_data, existing_listing)
    
    def _post_listing_creation_hook(self, session, listing: PropertyListing, property_data: Dict[str, Any]):
        """掲載情報作成後のフック（三井のリハウス特有の処理）"""
        # 追加フィールドの設定
        self._set_additional_fields(listing, property_data)
        
        # 詳細情報を保存
        if property_data.get('detail_fetched', False):
            listing.detail_info = self._build_detail_info(property_data)
            listing.detail_fetched_at = datetime.now()
        
        # 多数決による物件情報更新（建物情報も含む）
        # listingからmaster_propertyへの参照を取得
        if listing.master_property:
            self._update_by_majority_vote(session, listing.master_property)
    
    
    def _set_additional_fields(self, listing: PropertyListing, property_data: Dict[str, Any]):
        """追加フィールドを設定"""
        if property_data.get('agency_tel'):
            listing.agency_tel = property_data['agency_tel']
        if property_data.get('remarks'):
            listing.remarks = property_data['remarks']
        if property_data.get('summary_remarks'):
            listing.summary_remarks = property_data['summary_remarks']
    
    def _build_detail_info(self, property_data: Dict[str, Any]) -> Dict[str, Any]:
        """詳細情報を構築"""
        return {
            'transaction_type': property_data.get('transaction_type'),
            'current_status': property_data.get('current_status'),
            'delivery_date': property_data.get('delivery_date'),
            'built_month': property_data.get('built_month')
        }