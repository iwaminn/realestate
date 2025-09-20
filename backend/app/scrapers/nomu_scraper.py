"""
ノムコムスクレイパー
野村不動産アーバンネット（nomu.com）からの物件情報取得
"""

import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import NomuParser
from ..models import PropertyListing
from .area_config import get_area_code


class NomuScraper(BaseScraper):
    """ノムコムのスクレイパー"""

    BASE_URL = "https://www.nomu.com"

    # 定数の定義
    DEFAULT_AGENCY_NAME = "野村不動産アーバンネット"
    MAX_ADDRESS_LENGTH = 50  # 住所として妥当な最大文字数

    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(SourceSite.NOMU, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = NomuParser(logger=self.logger)
        
        # カスタムバリデーターを登録
        self.register_custom_validators()
    
    def register_custom_validators(self):
        """ノムコム用のカスタムバリデーターを登録"""
        super().register_custom_validators()
        
        # 必須フィールドのバリデーターを登録
        # 面積: 完全一致を要求
        self.add_required_field_validator('area', exact_match=True)
        
        # 間取りは除外（サイト側でデータ不整合があるため）
        # self.add_required_field_validator('layout', exact_match=True)
        
        # 階数: 完全一致を要求
        self.add_required_field_validator('floor_number', exact_match=True)

    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """ノムコムのsite_property_idの妥当性を検証

        ノムコムの物件IDは英数字で構成される（例：A12345678）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False

        # ノムコム固有の検証：英数字のみで構成されているか
        if not site_property_id.replace('-', '').replace('_', '').isalnum():
            self.logger.error(
                f"[NOMU] site_property_idは英数字（ハイフン・アンダースコア可）で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False

        # 通常は6〜15文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[NOMU] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行

        return True

    def get_search_url(self, area_code: str, page: int = 1) -> str:
        """検索URLを生成"""
        # エリアコード変換（minato -> 13103）
        actual_area_code = get_area_code(area_code)
        base_url = f"{self.BASE_URL}/mansion/area_tokyo/{actual_area_code}/"
        if page > 1:
            return f"{base_url}?pager_page={page}"
        return base_url

    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def parse_property_card(self, card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件カードから情報を抽出 - パーサーに委譲"""
        property_data = self.parser._parse_property_card(card)

        if property_data:
            # 仲介業者名（ノムコムは野村不動産アーバンネット）
            property_data['agency_name'] = self.DEFAULT_AGENCY_NAME

            # site_property_idの検証
            if 'site_property_id' in property_data:
                if not self.validate_site_property_id(property_data['site_property_id'], property_data.get('url', '')):
                    self.logger.error(f"[NOMU] 不正なsite_property_idを検出しました: '{property_data['site_property_id']}'")
                    return None

        return property_data

    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（共通インターフェース用）"""
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self._parse_property_detail_from_url,
            save_property_func=self.save_property
        )

    def _parse_property_detail_from_url(self, url: str, list_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        URLから詳細ページを取得して解析
        
        Args:
            url: 詳細ページのURL
            list_data: 一覧ページで取得したデータ（クロスバリデーション用）
        
        Returns:
            詳細データまたはNone
        """
        detail_data = self.parse_property_detail(url)
        if detail_data:
            detail_data['url'] = url
            
            # クロスバリデーションは基底クラスで実施されるため、ここでは不要
            # （基底クラスのvalidate_detail_against_listメソッドとカスタムバリデーターで実行）
            
        return detail_data
    


    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存"""
        return self.save_property_common(property_data, existing_listing)

    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """
        物件詳細ページを解析 - パーサーに委譲

        Args:
            url: 詳細ページのURL

        Returns:
            物件詳細情報の辞書、失敗時はNone
        """
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
                # URLから物件IDを抽出（例："/nm/d22750022/"から"22750022"）
                match = re.search(r'/nm/d(\d+)/', url)
                if match:
                    site_id = match.group(1)
                    if self.validate_site_property_id(site_id, url):
                        detail_data["site_property_id"] = site_id

        return detail_data