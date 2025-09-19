"""
基底HTMLパーサークラス

すべてのサイト固有パーサーの基底となるクラス
共通のパース機能とインターフェースを提供
"""
import re
import logging
from typing import Optional, List, Dict, Any, Tuple, Union
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup, Tag
from datetime import datetime

from ..components import HtmlParserComponent, DataValidatorComponent


class BaseHtmlParser:
    """
    HTMLパーサー基底クラス
    
    責務: サイト固有パーサーの共通インターフェースを提供
    - HTML操作はHtmlParserComponentに委譲
    - データ正規化はDataNormalizerの関数を使用
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
        from ..components.html_parser import HtmlParserComponent
        self.html_parser = HtmlParserComponent(logger=self.logger)
    
    # ========== HTML操作メソッド（HtmlParserComponentに委譲） ==========
    
    def extract_text(self, *args, **kwargs) -> Optional[str]:
        """HTML要素からテキストを抽出"""
        return self.html_parser.extract_text(*args, **kwargs)
    
    def safe_select_one(self, *args, **kwargs):
        """安全な単一要素のCSS選択"""
        return self.html_parser.safe_select_one(*args, **kwargs)
    
    def safe_select(self, *args, **kwargs) -> List:
        """安全なCSS選択"""
        return self.html_parser.safe_select(*args, **kwargs)
    
    def extract_table_data(self, *args, **kwargs) -> Dict[str, str]:
        """HTMLテーブルからデータを抽出"""
        return self.html_parser.extract_table_data(*args, **kwargs)
    
    def normalize_url(self, *args, **kwargs) -> Optional[str]:
        """URLを正規化"""
        return self.html_parser.normalize_url(*args, **kwargs)
    
    # ========== データ正規化メソッド（DataNormalizerを使用） ==========
    
    def parse_price(self, text: str) -> Optional[int]:
        """価格をパース（万円単位）"""
        from ..data_normalizer import extract_price
        return extract_price(text)
    
    def parse_area(self, text: str) -> Optional[float]:
        """面積をパース（㎡単位）"""
        from ..data_normalizer import extract_area
        return extract_area(text)
    
    def parse_floor(self, text: str) -> Optional[int]:
        """階数をパース"""
        from ..data_normalizer import extract_floor_number
        return extract_floor_number(text)
    
    def parse_built_date(self, text: str) -> Dict[str, Optional[int]]:
        """築年月を抽出（年と月を別々に返す）"""
        from ..data_normalizer import extract_built_year_month
        return extract_built_year_month(text)
    
    def normalize_layout(self, text: str) -> Optional[str]:
        """間取りを正規化"""
        from ..data_normalizer import normalize_layout
        return normalize_layout(text)
    
    def normalize_direction(self, text: str) -> Optional[str]:
        """方角を正規化"""
        from ..data_normalizer import normalize_direction
        return normalize_direction(text)
    
    def parse_station_info(self, text: str) -> Optional[str]:
        """駅情報をフォーマット"""
        from ..data_normalizer import format_station_info
        return format_station_info(text)
    
    def parse_total_floors(self, text: str) -> Optional[int]:
        """総階数をパース"""
        from ..data_normalizer import extract_total_floors
        total_floors, _ = extract_total_floors(text)
        return total_floors
    
    def parse_basement_floors(self, text: str) -> Optional[int]:
        """地下階数をパース"""
        from ..data_normalizer import extract_total_floors
        _, basement_floors = extract_total_floors(text)
        return basement_floors
    
    def parse_total_units(self, text: str) -> Optional[int]:
        """総戸数をパース"""
        from ..data_normalizer import extract_total_units
        return extract_total_units(text)
    
    def clean_address(self, text: str) -> Optional[str]:
        """住所からUI要素（地図を見る等）を削除"""
        if not text:
            return None

        from ...utils.address_normalizer import AddressNormalizer
        normalizer = AddressNormalizer()
        return normalizer.remove_ui_elements(text)

    def normalize_address(self, text: str) -> Optional[str]:
        """住所を正規化"""
        if not text:
            return None

        from ...utils.address_normalizer import AddressNormalizer
        normalizer = AddressNormalizer()
        return normalizer.normalize(text)