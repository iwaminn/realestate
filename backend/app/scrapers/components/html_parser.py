"""
HTMLパーサーコンポーネント

HTML解析に関する共通処理を担当
- テキスト抽出
- 数値抽出
- 日付パース
- テーブルデータ抽出
"""
import re
import logging
from typing import Optional, List, Dict, Any, Union
from bs4 import BeautifulSoup, Tag
from datetime import datetime
import unicodedata


class HtmlParserComponent:
    """HTML解析を担当するコンポーネント"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def parse_html(self, content: str, parser: str = 'html.parser') -> Optional[BeautifulSoup]:
        """
        HTML文字列をBeautifulSoupオブジェクトに変換
        
        Args:
            content: HTML文字列
            parser: パーサーの種類（デフォルト: html.parser）
            
        Returns:
            BeautifulSoupオブジェクト
        """
        if not content:
            return None
        
        try:
            soup = BeautifulSoup(content, parser)
            return soup
        except Exception as e:
            self.logger.error(f"HTML解析エラー: {e}")
            return None

    def extract_text(self, element: Optional[Union[Tag, str]]) -> str:
        """
        要素からテキストを安全に抽出
        
        Args:
            element: BeautifulSoup要素またはテキスト
            
        Returns:
            抽出・整形されたテキスト（空文字列を返す）
        """
        if element is None:
            return ""
        
        if isinstance(element, str):
            text = element
        else:
            text = element.get_text(strip=True)
        
        return self.clean_text(text)
    
    def clean_text(self, text: str) -> str:
        """
        テキストをクリーンアップ
        
        Args:
            text: 生のテキスト
            
        Returns:
            クリーンアップされたテキスト
        """
        if not text:
            return ""
        
        # 全角スペースを半角に変換
        text = text.replace('　', ' ')
        
        # 連続するスペースを1つに
        text = re.sub(r'\s+', ' ', text)
        
        # 前後の空白を削除
        text = text.strip()
        
        return text
    
    def extract_number(self, text: str) -> Optional[float]:
        """
        テキストから数値を抽出
        
        Args:
            text: 数値を含むテキスト
            
        Returns:
            抽出された数値（float）
        """
        if not text:
            return None
        
        # 全角数字を半角に変換
        text = unicodedata.normalize('NFKC', text)
        
        # カンマを除去
        text = text.replace(',', '')
        
        # 数値パターンを抽出
        pattern = r'[-+]?\d*\.?\d+'
        match = re.search(pattern, text)
        
        if match:
            try:
                return float(match.group())
            except ValueError:
                self.logger.warning(f"数値変換失敗: {match.group()}")
                return None
        
        return None
    
    def extract_integer(self, text: str) -> Optional[int]:
        """
        テキストから整数を抽出
        
        Args:
            text: 整数を含むテキスト
            
        Returns:
            抽出された整数
        """
        number = self.extract_number(text)
        if number is not None:
            return int(number)
        return None
    
    def parse_price(self, text: str) -> Optional[int]:
        """
        価格テキストをパース（万円単位）
        
        Args:
            text: 価格テキスト（例: "3,500万円"）
            
        Returns:
            価格（万円単位の整数）
        """
        if not text:
            return None
        
        # 全角数字を半角に変換
        text = unicodedata.normalize('NFKC', text)
        
        # 億円の処理
        if '億' in text:
            # 例: "1億5000万円" -> 15000
            pattern = r'(\d+)億\s*(\d+)?万?'
            match = re.search(pattern, text)
            if match:
                oku = int(match.group(1))
                man = int(match.group(2)) if match.group(2) else 0
                return oku * 10000 + man
        
        # 万円の処理
        if '万' in text:
            # 例: "3,500万円" -> 3500
            pattern = r'([\d,]+)万'
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    return int(price_str)
                except ValueError:
                    pass
        
        # 数値のみの場合（万円単位と仮定）
        number = self.extract_integer(text)
        if number and number > 100:  # 100万円以上なら妥当な価格
            return number
        
        return None
    
    def parse_date(self, text: str, base_year: Optional[int] = None) -> Optional[datetime]:
        """
        日付テキストをパース
        
        Args:
            text: 日付テキスト
            base_year: 基準年（年が省略されている場合用）
            
        Returns:
            datetime オブジェクト
        """
        if not text:
            return None
        
        # 全角数字を半角に変換
        text = unicodedata.normalize('NFKC', text)
        
        patterns = [
            # 2024年1月15日
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', '%Y-%m-%d'),
            # 2024/01/15
            (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d'),
            # 2024-01-15
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
            # 1月15日（年なし）
            (r'(\d{1,2})月(\d{1,2})日', '%m-%d'),
        ]
        
        for pattern, format_str in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    if '%Y' not in format_str:
                        # 年が含まれない場合
                        year = base_year or datetime.now().year
                        date_str = f"{year}-{match.group(1)}-{match.group(2)}"
                        return datetime.strptime(date_str, '%Y-%m-%d')
                    else:
                        date_str = '-'.join(match.groups())
                        return datetime.strptime(date_str, format_str.replace('/', '-'))
                except ValueError:
                    continue
        
        return None
    
    def extract_table_data(self, table: Tag) -> Dict[str, str]:
        """
        テーブルからキー・バリューデータを抽出
        
        Args:
            table: テーブル要素
            
        Returns:
            {キー: 値} の辞書
        """
        data = {}
        
        if not table:
            return data
        
        # th-td形式
        for row in table.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                key = self.extract_text(th)
                value = self.extract_text(td)
                if key:
                    data[key] = value
        
        # dt-dd形式（dl要素）
        if table.name == 'dl':
            dts = table.find_all('dt')
            dds = table.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key:
                    data[key] = value
        
        return data
    
    def safe_select(self, soup: Optional[BeautifulSoup], selector: str) -> List[Tag]:
        """
        セレクタで安全に要素を取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            マッチした要素のリスト
        """
        if not soup:
            return []
        
        try:
            return soup.select(selector)
        except Exception as e:
            self.logger.warning(f"セレクタエラー: {selector} - {e}")
            return []
    
    def safe_select_one(self, soup: Optional[BeautifulSoup], selector: str) -> Optional[Tag]:
        """
        セレクタで安全に単一要素を取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            selector: CSSセレクタ
            
        Returns:
            マッチした最初の要素
        """
        elements = self.safe_select(soup, selector)
        return elements[0] if elements else None
    
    def normalize_url(self, url: Optional[str], base_url: str) -> Optional[str]:
        """
        URLを正規化（相対URLを絶対URLに変換）
        
        Args:
            url: URL（相対または絶対）
            base_url: ベースURL
            
        Returns:
            正規化されたURL
        """
        if not url:
            return None
        
        url = url.strip()
        
        if url.startswith('http://') or url.startswith('https://'):
            return url
        
        if url.startswith('//'):
            return 'https:' + url
        
        if url.startswith('/'):
            # ベースURLからドメインを取得
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        
        # 相対パスの場合
        from urllib.parse import urljoin
        return urljoin(base_url, url)
    
    def parse_built_date(self, text: str) -> Dict[str, Optional[int]]:
        """
        築年月をパース
        
        Args:
            text: 築年月テキスト（例: "平成25年3月"）
            
        Returns:
            {'built_year': 年, 'built_month': 月} の辞書
        """
        result = {'built_year': None, 'built_month': None}
        
        if not text:
            return result
        
        # 全角数字を半角に変換
        text = unicodedata.normalize('NFKC', text)
        
        # 西暦の年月を抽出
        year_match = re.search(r'(\d{4})年', text)
        month_match = re.search(r'(\d{1,2})月', text)
        
        if year_match:
            result['built_year'] = int(year_match.group(1))
        if month_match:
            result['built_month'] = int(month_match.group(1))
        
        # 和暦対応
        if not result['built_year']:
            if '令和' in text:
                match = re.search(r'令和(\d+)年', text)
                if match:
                    result['built_year'] = 2018 + int(match.group(1))
            elif '平成' in text:
                match = re.search(r'平成(\d+)年', text)
                if match:
                    result['built_year'] = 1988 + int(match.group(1))
            elif '昭和' in text:
                match = re.search(r'昭和(\d+)年', text)
                if match:
                    result['built_year'] = 1925 + int(match.group(1))
        
        return result