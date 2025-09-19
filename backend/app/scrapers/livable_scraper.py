"""
東急リバブルスクレイパー
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup, Tag
import traceback

from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import LivableParser
from ..models import PropertyListing
from .data_normalizer import DataNormalizer
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)


class LivableScraper(BaseScraper):
    """東急リバブルのスクレイパー"""
    
    BASE_URL = "https://www.livable.co.jp"
    
    # 定数の定義
    PRICE_MISMATCH_RETRY_DAYS = 7  # 価格不一致時の再試行日数
    PRICE_MISMATCH_THRESHOLD = 0.1  # 価格不一致の閾値（10%）
    DEFAULT_AGENCY_NAME = "東急リバブル"
    
    # デバッグ対象の物件ID
    DEBUG_PROPERTY_IDS = ['C13252J13', 'C13249B30']
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(SourceSite.LIVABLE, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = LivableParser(logger=self.logger)
        # 東急リバブルも一覧ページと詳細ページで建物名の表記が異なることがあるため、部分一致を許可
        self.allow_partial_building_name_match = True
        self.building_name_match_threshold = 0.6  # 東急リバブルは詳細ページの建物名が長い傾向があるため閾値を下げる  # 東急リバブルは詳細ページの建物名が長い傾向があるため閾値を下げる
    
    def get_optional_required_fields(self) -> List[str]:
        """Livableではlayoutは必須ではない（稀に取得できないため）
        
        Returns:
            List[str]: オプショナルな必須フィールドのリスト（空リスト）
        """
        return []  # layoutを必須から除外

    
    def get_partial_required_fields(self) -> Dict[str, Dict[str, Any]]:
        """Livableの部分的必須フィールドの設定
        
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
    
    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str, 
                                   allow_partial_match: bool = False, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """東急リバブル特有の建物名マッチングロジック
        
        東急リバブルでは詳細ページの建物名が一覧ページよりも詳細な場合が多い
        例：
        - 一覧「ＴＨＥ　ＲＯＰＰＯＮＧＩ　ＴＯＫＹＯ」 → 詳細「ＴＨＥ ＲＯＰＰＯＮＧＩ ＴＯＫＹＯ ＣＬＵＢ ＲＥＳＩＤＥＮＣＥ」
        - 一覧「三田ガーデンヒルズ」 → 詳細「三田ガーデンヒルズノースヒル」
        """
        # 基底クラスのメソッドを呼び出す
        is_verified, verified_name = super().verify_building_names_match(
            detail_building_name, building_name_from_list, allow_partial_match, threshold
        )
        
        # 基底クラスで一致しなかった場合、追加のチェックを行う
        if not is_verified and allow_partial_match:
            # 正規化
            normalized_list = self.normalize_building_name(building_name_from_list)
            normalized_detail = self.normalize_building_name(detail_building_name)
            
            # 一覧の建物名が詳細の建物名の先頭部分と一致するかチェック
            if normalized_detail.startswith(normalized_list):
                self.logger.info(
                    f"建物名が一致（前方一致）: 一覧「{building_name_from_list}」は詳細「{detail_building_name}」の先頭部分"
                )
                return True, detail_building_name
            
            # スペースを除去してもう一度チェック
            list_no_space = normalized_list.replace(' ', '').replace('　', '')
            detail_no_space = normalized_detail.replace(' ', '').replace('　', '')
            
            if detail_no_space.startswith(list_no_space):
                self.logger.info(
                    f"建物名が一致（前方一致・スペース除去後）: 一覧「{building_name_from_list}」は詳細「{detail_building_name}」の先頭部分"
                )
                return True, detail_building_name
        
        return is_verified, verified_name
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """東急リバブルのsite_property_idの妥当性を検証
        
        東急リバブルの物件IDは英数字で構成される（例：C13252J13）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # 東急リバブル固有の検証：英数字のみで構成されているか
        if not site_property_id.isalnum():
            self.logger.error(
                f"[LIVABLE] site_property_idは英数字で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜15文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[LIVABLE] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行
            
        # 'unknown'などの不正な値を拒否
        if site_property_id.lower() in ['unknown', 'detail', 'mansion']:
            self.logger.error(
                f"[LIVABLE] site_property_idが不正な値です: '{site_property_id}' URL={url}"
            )
            return False
            
        return True
    
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        # 共通の詳細チェック処理を使用
        result = self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property_common
        )
        
        return result
    
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """東急リバブルの検索URLを生成"""
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 東急リバブルのURL形式（修正版）
        base_url = f"{self.BASE_URL}/kounyu/mansion/tokyo/a{area_code}/"
        
        if page > 1:
            return f"{base_url}?page={page}"
        else:
            return base_url
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存（共通ロジックを使用）"""
        return self.save_property_common(property_data, existing_listing)
    
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        # パーサーで基本的な解析を実行
        detail_data = self.parser.parse_property_detail(soup)
        
        return detail_data