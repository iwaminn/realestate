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


class BaseHtmlParser(ABC):
    """サイト固有HTMLパーサーの基底クラス"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # 共通コンポーネント
        self.html_parser = HtmlParserComponent(logger=self.logger)
        self.data_validator = DataValidatorComponent(logger=self.logger)
    
    # ===== 抽象メソッド（サブクラスで実装必須） =====
    
    @abstractmethod
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        物件一覧をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件情報のリスト
        """
        pass
    
    @abstractmethod
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        pass
    
    @abstractmethod
    def get_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        次ページのURLを取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            current_url: 現在のURL
            
        Returns:
            次ページのURL（なければNone）
        """
        pass
    
    # ===== 共通ヘルパーメソッド =====
    
    def extract_text(self, element: Optional[Union[Tag, str]]) -> str:
        """
        要素からテキストを抽出（コンポーネントに委譲）
        
        Args:
            element: HTML要素またはテキスト
            
        Returns:
            抽出されたテキスト
        """
        return self.html_parser.extract_text(element)
    
    def parse_price(self, text: str) -> Optional[int]:
        """
        価格をパース（コンポーネントに委譲）
        
        Args:
            text: 価格テキスト
            
        Returns:
            価格（万円単位）
        """
        return self.html_parser.parse_price(text)
    
    def parse_area(self, text: str) -> Optional[float]:
        """
        面積をパース
        
        Args:
            text: 面積テキスト
            
        Returns:
            面積（㎡）
        """
        number = self.html_parser.extract_number(text)
        return float(number) if number is not None else None
    
    def parse_floor(self, text: str) -> Optional[int]:
        """
        階数をパース
        
        Args:
            text: 階数テキスト
            
        Returns:
            階数
        """
        return self.html_parser.extract_integer(text)
    
    def normalize_layout(self, text: str) -> Optional[str]:
        """
        間取りを正規化（コンポーネントに委譲）
        
        Args:
            text: 間取りテキスト
            
        Returns:
            正規化された間取り
        """
        return self.data_validator.normalize_layout(text)
    
    def normalize_direction(self, text: str) -> Optional[str]:
        """
        方角を正規化（コンポーネントに委譲）
        
        Args:
            text: 方角テキスト
            
        Returns:
            正規化された方角
        """
        return self.data_validator.normalize_direction(text)
    
    def normalize_address(self, text: str) -> Optional[str]:
        """
        住所を正規化（コンポーネントに委譲）
        
        Args:
            text: 住所テキスト
            
        Returns:
            正規化された住所
        """
        return self.data_validator.normalize_address(text)
    
    def parse_built_date(self, text: str) -> Dict[str, Optional[int]]:
        """
        築年月をパース（コンポーネントに委譲）
        
        Args:
            text: 築年月テキスト
            
        Returns:
            {'built_year': 年, 'built_month': 月}
        """
        return self.html_parser.parse_built_date(text)
    
    def extract_table_data(self, table: Tag) -> Dict[str, str]:
        """
        テーブルデータを抽出（コンポーネントに委譲）
        
        Args:
            table: テーブル要素
            
        Returns:
            {キー: 値} の辞書
        """
        return self.html_parser.extract_table_data(table)
    
    def validate_property_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        物件データを検証（コンポーネントに委譲）
        
        Args:
            data: 物件データ
            
        Returns:
            (検証成功フラグ, エラーメッセージリスト)
        """
        return self.data_validator.validate_property_data(data)
    
    def safe_select(self, soup: BeautifulSoup, selector: str) -> List[Tag]:
        """
        セレクタで安全に要素を選択（コンポーネントに委譲）
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            マッチした要素のリスト
        """
        return self.html_parser.safe_select(soup, selector)
    
    def safe_select_one(self, soup: BeautifulSoup, selector: str) -> Optional[Tag]:
        """
        セレクタで安全に単一要素を選択（コンポーネントに委譲）
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            マッチした最初の要素
        """
        return self.html_parser.safe_select_one(soup, selector)
    
    def normalize_url(self, url: str, base_url: str) -> Optional[str]:
        """
        URLを正規化（コンポーネントに委譲）
        
        Args:
            url: URL（相対または絶対）
            base_url: ベースURL
            
        Returns:
            正規化されたURL
        """
        return self.html_parser.normalize_url(url, base_url)
    
    # ===== 共通パース処理 =====
    
    def parse_station_info(self, text: str) -> Optional[str]:
        """
        駅情報をパース
        
        Args:
            text: 駅情報テキスト
            
        Returns:
            パースされた駅情報
        """
        if not text:
            return None
        
        # 全角スペースを半角に、連続するスペースを1つに
        text = self.html_parser.clean_text(text)
        
        # 複数駅の場合は改行で区切る
        if '/' in text:
            stations = text.split('/')
            return '\n'.join(s.strip() for s in stations if s.strip())
        
        return text
    
    def parse_management_info(self, text: str) -> Optional[int]:
        """
        管理費・修繕積立金をパース
        
        Args:
            text: 費用テキスト
            
        Returns:
            費用（円単位）
        """
        if not text:
            return None
        
        # "円" を削除してから数値抽出
        text = text.replace('円', '')
        number = self.html_parser.extract_number(text)
        
        if number is not None:
            # 万円単位の場合は変換
            if '万' in text:
                return int(number * 10000)
            return int(number)
        
        return None