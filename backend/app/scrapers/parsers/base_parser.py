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

    
    # ========== フィールド抽出追跡フレームワーク ==========
    
    def track_field_extraction(
        self, 
        property_data: Dict[str, Any], 
        field_name: str, 
        value: Any,
        field_found: bool = True
    ):
        """
        フィールド抽出の追跡（HTML構造変更の早期検出用）
        
        このメソッドは、各フィールドの抽出状態を記録し、
        HTML構造の変更などでフィールド自体が見つからなくなった場合と、
        元々データがない場合を区別できるようにします。
        
        Args:
            property_data: データ格納先（パース結果を格納する辞書）
            field_name: フィールド名（例: 'management_fee', 'floor_number'）
            value: 抽出された値（Noneの場合は値が抽出できなかったことを示す）
            field_found: フィールド（HTML要素）が見つかったかどうか（デフォルト: True）
        
        使用例:
            # テーブルのth要素が見つかった場合
            if '管理費' in key:
                fee = extract_monthly_fee(value)
                self.track_field_extraction(property_data, 'management_fee', fee, field_found=True)
            
            # HTML要素自体が見つからなかった場合
            if not price_element:
                self.track_field_extraction(property_data, 'price', None, field_found=False)
        
        メタデータ構造:
            property_data['_field_extraction_meta'] = {
                'management_fee': {
                    'field_found': True,      # HTML要素が見つかったか
                    'value_extracted': False  # 有効な値が抽出できたか
                }
            }
        """
        # メタデータ領域を初期化
        if '_field_extraction_meta' not in property_data:
            property_data['_field_extraction_meta'] = {}
        
        # フィールドの抽出状態を記録
        property_data['_field_extraction_meta'][field_name] = {
            'field_found': field_found,           # HTML要素が見つかったか
            'value_extracted': value is not None  # 有効な値が抽出できたか
        }
        
        # 値が有効な場合のみproperty_dataに設定
        # None以外の値（0を含む）はすべて有効な値として扱う
        if value is not None:
            property_data[field_name] = value
    
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

    def parse_monthly_fee(self, text: str) -> Optional[int]:
        """月額費用をパース（円単位）"""
        from ..data_normalizer import extract_monthly_fee
        return extract_monthly_fee(text)
    
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
    
    def parse_date(self, text: str) -> Optional['datetime']:
        """日付文字列をdatetimeオブジェクトに変換"""
        from ..data_normalizer import parse_date
        return parse_date(text)
    
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
        result = normalizer.normalize(text)
        
        # 空文字列の場合もNoneを返す
        if not result:
            return None
        
        return result

    def normalize_building_name(self, building_name: str) -> str:
        """
        建物名を正規化（広告文除去）
        
        Args:
            building_name: 広告文を含む可能性のある建物名
            
        Returns:
            広告文を除去した建物名（除去後に空の場合は元の建物名）
        """
        from ...utils.building_name_normalizer import remove_ad_text_from_building_name
        
        cleaned_name = remove_ad_text_from_building_name(building_name)
        
        # 広告文除去後に空になった場合は、元の建物名をそのまま返す
        # （広告文のみの可能性があるが、データを失うよりは保持する）
        if not cleaned_name or not cleaned_name.strip():
            return building_name
        
        return cleaned_name
