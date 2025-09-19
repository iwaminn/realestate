"""
HTMLパーサーコンポーネント

HTML解析に関する共通処理を担当
- テキスト抽出
- テーブルデータ抽出
- CSS選択
- URL正規化
"""
import re
import logging
from typing import Optional, List, Dict, Any, Union
from bs4 import BeautifulSoup, Tag
from datetime import datetime


class HtmlParserComponent:
    """
    HTML解析コンポーネント
    
    責務: HTMLの解析と要素からの基本的なテキスト抽出
    - BeautifulSoupを使ったHTML解析
    - HTML要素からのテキスト抽出
    - CSS選択と要素の安全な取得
    - URLの正規化
    
    データの意味解釈や正規化はDataNormalizerに委譲
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def parse_html(self, html_content: str, parser: str = 'html.parser') -> Optional[BeautifulSoup]:
        """
        HTML文字列をBeautifulSoupオブジェクトに変換
        
        Args:
            html_content: HTML文字列
            parser: パーサーの種類
            
        Returns:
            BeautifulSoupオブジェクト
        """
        if not html_content:
            return None
            
        try:
            return BeautifulSoup(html_content, parser)
        except Exception as e:
            self.logger.error(f"HTML解析エラー: {e}")
            return None
    
    def extract_text(self, element: Union[Tag, BeautifulSoup, str, None]) -> Optional[str]:
        """
        HTML要素からテキストを抽出
        
        Args:
            element: BeautifulSoupの要素、文字列、またはNone
            
        Returns:
            抽出されたテキスト（前後の空白を除去）
        """
        if element is None:
            return None
            
        if isinstance(element, str):
            return self.clean_text(element)
            
        try:
            text = element.get_text(strip=True)
            return self.clean_text(text) if text else None
        except Exception as e:
            self.logger.warning(f"テキスト抽出エラー: {e}")
            return None
    
    def clean_text(self, text: str) -> Optional[str]:
        """
        テキストをクリーニング
        
        Args:
            text: クリーニング対象のテキスト
            
        Returns:
            クリーニングされたテキスト
        """
        if not text:
            return None
        
        # 改行・タブ・連続する空白を単一の空白に置換
        text = re.sub(r'\s+', ' ', text)
        
        # 前後の空白を削除
        text = text.strip()
        
        # 空文字列の場合はNoneを返す
        return text if text else None

    def extract_table_data(self, table: Tag) -> Dict[str, str]:
        """
        HTMLテーブルからデータを抽出
        
        Args:
            table: tableタグ要素
            
        Returns:
            キーと値のペアの辞書
        """
        data = {}
        
        if not table:
            return data
        
        # trタグを取得
        rows = table.find_all('tr')
        
        for row in rows:
            # th/tdの組み合わせを処理
            th = row.find('th')
            td = row.find('td')
            
            if th and td:
                key = self.extract_text(th)
                value = self.extract_text(td)
                
                if key and value:
                    data[key] = value
            
            # dt/ddの組み合わせも処理（一部のサイトで使用）
            dt = row.find('dt')
            dd = row.find('dd')
            
            if dt and dd:
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                
                if key and value:
                    data[key] = value
        
        return data
    
    def safe_select(self, soup: BeautifulSoup, selector: str) -> List[Tag]:
        """
        安全なCSS選択（エラーハンドリング付き）
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            マッチした要素のリスト
        """
        if not soup or not selector:
            return []
            
        try:
            return soup.select(selector)
        except Exception as e:
            self.logger.warning(f"CSS選択エラー ({selector}): {e}")
            return []
    
    def safe_select_one(self, soup: BeautifulSoup, selector: str) -> Optional[Tag]:
        """
        安全な単一要素のCSS選択
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            最初にマッチした要素またはNone
        """
        elements = self.safe_select(soup, selector)
        return elements[0] if elements else None
    
    def normalize_url(self, url: str, base_url: str = '') -> Optional[str]:
        """
        URLを正規化（相対URLを絶対URLに変換）
        
        Args:
            url: 正規化するURL
            base_url: ベースURL
            
        Returns:
            正規化されたURL
        """
        if not url:
            return None
        
        # 既に絶対URLの場合はそのまま返す
        if url.startswith('http://') or url.startswith('https://'):
            return url
        
        # base_urlが指定されていない場合は相対URLをそのまま返す
        if not base_url:
            return url
        
        # urllib.parseを使用してURLを結合
        from urllib.parse import urljoin
        
        try:
            return urljoin(base_url, url)
        except Exception as e:
            self.logger.warning(f"URL正規化エラー: {e}")
            return None