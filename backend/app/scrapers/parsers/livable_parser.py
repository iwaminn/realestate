"""
東急リバブル専用HTMLパーサー

東急リバブル（www.livable.co.jp）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin

from .base_parser import BaseHtmlParser
from ..data_normalizer import extract_monthly_fee


class LivableParser(BaseHtmlParser):
    """東急リバブル専用パーサー"""
    
    # 東急リバブルのデフォルト設定
    DEFAULT_AGENCY_NAME = "東急リバブル"
    BASE_URL = "https://www.livable.co.jp"
    
    # デバッグ用の物件ID
    DEBUG_PROPERTY_IDS = []
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        super().__init__(logger)
        self.logger = logger or logging.getLogger(__name__)


    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        物件一覧をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件情報のリスト
        """
        properties = []
        
        # 物件リストアイテムを取得
        property_items = self._find_property_items(soup)
        
        for i, item in enumerate(property_items):
            property_data = self._parse_property_item(item, i)
            if property_data:
                properties.append(property_data)
        
        # デバッグ: 物件IDの重複チェック
        self._check_duplicate_property_ids(properties)
        
        return properties
    
    def _find_property_items(self, soup: BeautifulSoup) -> List[Tag]:
        """
        物件リストアイテムを検索
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件アイテムのリスト
        """
        property_items = soup.select('.o-product-list__item')
        
        if not property_items:
            # 別のセレクタを試す
            property_items = soup.select('.o-map-search__property-item')
        
        return property_items
    
    def _parse_property_item(self, item: Tag, index: int) -> Optional[Dict[str, Any]]:
        """
        物件アイテムをパース
        
        Args:
            item: 物件アイテム要素
            index: インデックス番号
            
        Returns:
            物件データ
        """
        property_data = {}
        
        # 物件詳細へのリンク
        link = self._extract_property_link(item)
        if link:
            href = link.get('href', '')
            property_data['url'] = urljoin(self.BASE_URL, href)
            
            # site_property_idを抽出
            site_property_id = self._extract_property_id(href)
            if not site_property_id:
                self.logger.error(f"site_property_id取得失敗: {property_data['url']}")
                return None
                
            property_data['site_property_id'] = site_property_id
            
            # デバッグ: 特定物件のリンク情報
            if site_property_id in self.DEBUG_PROPERTY_IDS:
                self.logger.info(f"DEBUG: 一覧ページItem#{index} - ID: {site_property_id}, URL: {property_data['url']}")
        
        # 価格を取得
        self._extract_list_price(item, property_data)
        
        # 建物名を取得（一覧ページから）
        building_name = self._extract_building_name_from_item(item)
        if building_name:
            property_data['building_name_from_list'] = building_name
            property_data['building_name'] = building_name  # 必須フィールドとして設定
        
        # 基本情報を抽出
        self._extract_basic_info_from_item(item, property_data)
        
        # 必須フィールドの検証
        if self._validate_list_data(property_data):
            return property_data
        else:
            return None
    
    def _extract_property_link(self, item: Tag) -> Optional[Tag]:
        """
        物件詳細へのリンクを抽出
        
        Args:
            item: 物件アイテム要素
            
        Returns:
            リンク要素
        """
        # 複数のセレクタを試す
        selectors = [
            'a.c-article-item_link',
            'a.o-product-list__link',
            'a.property-link',
            'a[href*="/detail/"]',
            'a[href*="/chuko/"]'
        ]
        
        for selector in selectors:
            link = item.select_one(selector)
            if link:
                return link
        
        # 最後の手段として、最初のリンクを取得
        link = item.find('a')
        return link
    
    def _extract_property_id(self, href: str) -> Optional[str]:
        """
        URLから物件IDを抽出
        
        Args:
            href: URL
            
        Returns:
            物件ID
        """
        if not href:
            return None
        
        # パターン1: /mansion/XXXXXXXX/
        match = re.search(r'/mansion/([A-Z0-9]+)/?', href)
        if match:
            return match.group(1)
        
        # パターン2: /grantact/detail/XXXXXXXX
        match = re.search(r'/grantact/detail/([A-Z0-9]+)', href)
        if match:
            return match.group(1)
        
        # パターン3: その他のパターン（数字のみ）
        patterns = [
            r'/detail/(\d+)',
            r'/chuko/(\d+)',
            r'/bukken/(\d+)',
            r'id=(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, href)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_list_price(self, item: Tag, property_data: Dict[str, Any]) -> None:
        """
        一覧ページから価格を抽出
        
        Args:
            item: 物件アイテム要素
            property_data: データ格納先
        """
        # 価格要素を検索（元のスクレイパーと同じセレクタ）
        price_elem = item.select_one('.o-product-list__info-body--price')
        if price_elem:
            # span要素に分かれている可能性があるため、共通メソッドを使用
            price_text = self.build_price_text_from_spans(price_elem)
            price = self.parse_price(price_text)
            if price:
                property_data['price'] = price
                return
        
        # 代替セレクタ
        price_selectors = [
            'dl.c-article-item_info_data dd',  # dtが"価格"の場合
            'span.o-product-list__price',
            'span.price',
            'div.price-value'
        ]
        
        # dl要素から検索
        info_items = item.select('dl.c-article-item_info_data')
        for dl in info_items:
            dt = dl.find('dt')
            if dt and '価格' in self.extract_text(dt):
                dd = dl.find('dd')
                if dd:
                    price_text = self.extract_text(dd)
                    price = self.parse_price(price_text)
                    if price:
                        property_data['price'] = price
                        return
        
        # 通常のセレクタで検索
        for selector in price_selectors:
            price_elem = item.select_one(selector)
            if price_elem:
                price_text = self.extract_text(price_elem)
                price = self.parse_price(price_text)
                if price:
                    property_data['price'] = price
                    return
    
    def _extract_building_name_from_item(self, item: Tag) -> Optional[str]:
        """
        物件アイテムから建物名を抽出
        
        Args:
            item: 物件アイテム要素
            
        Returns:
            建物名
        """
        building_name = None
        
        # 方法1: タイトル要素から抽出
        title_selectors = [
            'h3.c-article-item_info_title span.c-article-item_info_title_text',
            'h3 span.c-article-item_info_title_text',
            'h3.o-product-list__title',
            '.property-title'
        ]
        
        for selector in title_selectors:
            title_elem = item.select_one(selector)
            if title_elem:
                building_name = self.extract_text(title_elem)
                if building_name:
                    return building_name
        
        # 方法2: リンクのテキストから抽出
        link = self._extract_property_link(item)
        if link:
            link_text = link.get_text(' ', strip=True)
            # パターン: 数字/数字の後、物件タイプの前
            match = re.search(r'\d+/\d+<?>?\s*(.*?)(?:\s*（間取り）)??\s*(?:中古マンション|新築マンション)', link_text)
            if match:
                building_name = match.group(1).strip()
        
        # 方法3: 画像のalt属性から取得
        if not building_name:
            img = item.select_one('img[alt]')
            if img:
                alt = img.get('alt', '').strip()
                # alt属性から建物名を抽出（「(外観)」「（間取り）」などを除去）
                if alt and '外観' not in alt and '間取り' not in alt:
                    building_name = alt
                elif alt:
                    # （外観）、（間取り）などのカッコ付きテキストを除去
                    building_name = re.sub(r'[（(][^）)]*[）)]', '', alt).strip()
        
        return building_name
    
    def _extract_basic_info_from_item(self, item: Tag, property_data: Dict[str, Any]) -> None:
        """
        物件アイテムから基本情報を抽出

        Args:
            item: 物件アイテム要素
            property_data: データ格納内
        """
        # まず、m-contact-property__infoクラスのdl要素から情報を抽出（新しい構造）
        info_items = item.select('dl.m-contact-property__info')
        for dl in info_items:
            dt = dl.find('dt')
            dd = dl.find('dd')

            if not dd:
                continue

            value = self.extract_text(dd)

            if not dt:
                continue

            key = self.extract_text(dt)

            # 間取り
            if '間取り' in key:
                layout = self.normalize_layout(value)
                if layout:
                    property_data['layout'] = layout

            # 専有面積
            elif '専有面積' in key:
                area = self.parse_area(value)
                if area:
                    property_data['area'] = area

            # 築年月
            elif '築年月' in key:
                built_info = self.parse_built_date(value)
                if built_info['built_year']:
                    property_data['built_year'] = built_info['built_year']
                if built_info['built_month']:
                    property_data['built_month'] = built_info['built_month']

            # 所在階数
            elif '所在階' in key or '階数' in key:
                # 例: "4階／地上9階" から 4 を抽出
                import re
                floor_match = re.match(r'(\d+)階', value)
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))

            # 向き
            elif '向き' in key:
                direction = self.normalize_direction(value)
                if direction:
                    property_data['direction'] = direction

            # 所在地
            elif '所在地' in key:
                address = self.normalize_address(value)
                if address:
                    property_data['address'] = address

        # 既存のc-article-item_info_dataからも情報を抽出（旧構造のフォールバック）
        if not property_data.get('layout') or not property_data.get('area'):
            info_items = item.select('dl.c-article-item_info_data')
        for dl in info_items:
            dt = dl.find('dt')
            dd = dl.find('dd')
            
            if not dd:
                continue
            
            value = self.extract_text(dd)
            
            # dtがない場合（間取りの場合がある）
            if not dt:
                # c-article-item_info_data--type クラスがある場合は間取り
                if 'c-article-item_info_data--type' in dl.get('class', []):
                    layout = self.normalize_layout(value)
                    if layout:
                        property_data['layout'] = layout
                continue
            
            key = self.extract_text(dt)
            
            # 専有面積
            if '専有面積' in key or '面積' in key:
                area = self.parse_area(value)
                if area:
                    property_data['area'] = area
            
            # 階数
            elif '階数' in key or '階' in key:
                floor = self.parse_floor(value)
                if floor:
                    property_data['floor_number'] = floor
            
            # 向き
            elif '向き' in key or '方角' in key:
                direction = self.normalize_direction(value)
                if direction:
                    property_data['direction'] = direction
            
            # 所在地
            elif '所在地' in key or '住所' in key:
                address = self.normalize_address(value)
                if address:
                    property_data['address'] = address
            
            # 築年月
            elif '築年月' in key:
                built_info = self.parse_built_date(value)
                if built_info['built_year']:
                    property_data['built_year'] = built_info['built_year']
                if built_info['built_month']:
                    property_data['built_month'] = built_info['built_month']
        
        # フォールバック: 通常のセレクタ
        if 'layout' not in property_data:
            # パターン1: o-product-list__layoutクラス
            layout_elem = item.select_one('.o-product-list__layout, .layout')
            if layout_elem:
                layout = self.normalize_layout(self.extract_text(layout_elem))
                if layout:
                    property_data['layout'] = layout
            
            # パターン2: spanタグで「間取」を検索し、次のp要素を取得
            if 'layout' not in property_data:
                for elem in item.find_all('span'):
                    if '間取' in self.extract_text(elem):
                        # 次の要素を探す
                        next_elem = elem.find_next_sibling('p')
                        if next_elem:
                            layout = self.normalize_layout(self.extract_text(next_elem))
                            if layout:
                                property_data['layout'] = layout
                                break
                        # 親要素内で探す
                        parent = elem.parent
                        if parent:
                            p_elem = parent.find('p')
                            if p_elem:
                                layout = self.normalize_layout(self.extract_text(p_elem))
                                if layout:
                                    property_data['layout'] = layout
                                    break
            
            # パターン3: translate クラスを持つ要素で間取りパターンに一致するもの
            if 'layout' not in property_data:
                translate_elems = item.select('.translate')
                for elem in translate_elems:
                    text = self.extract_text(elem)
                    # 間取りパターンに一致するか確認（1LDK, 2DK, 3LDK等）
                    if re.match(r'^\d+[A-Z]+', text):
                        layout = self.normalize_layout(text)
                        if layout:
                            property_data['layout'] = layout
                            break
        
        if 'area' not in property_data:
            area_elem = item.select_one('.o-product-list__area, .area')
            if area_elem:
                area_text = self.extract_text(area_elem)
                area = self.parse_area(area_text)
                if area:
                    property_data['area'] = area
        
        if 'floor_number' not in property_data:
            floor_elem = item.select_one('.o-product-list__floor, .floor')
            if floor_elem:
                floor_text = self.extract_text(floor_elem)
                floor = self.parse_floor(floor_text)
                if floor:
                    property_data['floor_number'] = floor
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース（東急リバブル専用の詳細実装）
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        detail_info = {}
        
        # URLからGrantact物件かどうかを判定
        # ページの内容からURLを推測（通常はスクレイパーからURLが渡される）
        is_grantact = False
        
        # Grantact物件の判定（テーブルクラスや特定の要素で判定）
        grantact_tables = soup.find_all('table', class_=['grantact-table', 'property-table'])
        if grantact_tables:
            is_grantact = True
        
        # URLからも判定（metaタグやcanonical URLから）
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical and canonical.get('href'):
            if '/grantact/' in canonical['href']:
                is_grantact = True
        
        if is_grantact:
            # Grantact物件の詳細解析
            return self._parse_grantact_detail(soup, property_data, detail_info)
        else:
            # 通常物件の詳細解析
            return self._parse_normal_detail(soup, property_data, detail_info)

    def _parse_normal_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any], 
                           detail_info: Dict[str, Any]) -> Dict[str, Any]:
        """通常パターンの詳細ページを解析"""
        # タイトル・建物名を取得
        self._extract_title_and_building_name(soup, property_data)
        
        # 住所を取得
        self._extract_address(soup, property_data)
        
        # 価格を取得
        if not self._extract_detail_price(soup, property_data):
            self.logger.warning("価格の取得に失敗しました")
        
        # 物件詳細情報を抽出
        self._extract_property_details(soup, property_data, detail_info)
        

        
        # 建物名が取得できなかった場合の警告
        if not property_data.get('building_name'):
            self.logger.warning("建物名を取得できませんでした")
        
        # 詳細情報を保存
        property_data['detail_info'] = detail_info
        
        # detail_infoの重要な情報をproperty_dataにコピー
        self._copy_detail_info_to_property_data(detail_info, property_data)
        
        return property_data
    
    def _parse_grantact_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any], 
                              detail_info: Dict[str, Any]) -> Dict[str, Any]:
        """grantactパターンの詳細ページを解析"""
        try:
            # 価格エリアから専有面積と間取りを取得
            price_area = soup.find('section', class_='price_area')
            if price_area:
                # flex infoブロックから情報を取得
                info_div = price_area.find('div', class_='info')
                if info_div:
                    for item_div in info_div.find_all('div'):
                        span = item_div.find('span')
                        p = item_div.find('p')
                        if span and p:
                            label = span.get_text(strip=True)
                            value = p.get_text(strip=True)
                            
                            if '専有面積' in label:
                                area = self.parse_area(value)
                                if area:
                                    property_data['area'] = area
                                    self.logger.info(f"[Livable] Grantact専有面積を取得: {area}㎡")
                            elif '間取' in label:
                                layout = self.normalize_layout(value)
                                if layout:
                                    property_data['layout'] = layout
                                    self.logger.info(f"[Livable] Grantact間取りを取得: {layout}")
                            elif '販売価格' in label or '価格' in label:
                                price = self.parse_price(value)
                                if price:
                                    property_data['price'] = price
                                    self.logger.info(f"[Livable] Grantact価格を取得: {price}万円")
            
            # テーブルから追加情報を取得
            tables = soup.find_all('table')
            for table in tables:
                for row in table.find_all('tr'):
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        self._extract_grantact_info(label, value, property_data, detail_info)
            
            # タイトルから建物名を取得
            self._extract_grantact_building_name(soup, property_data)
            
            # JavaScript変数から住所を取得
            self._extract_grantact_address(soup, property_data)
            
            # 必須フィールドの確認とフォールバック
            self._validate_grantact_required_fields(soup, property_data)
            
            # 不動産会社情報
            property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
            
            # 詳細情報を保存
            property_data['detail_info'] = detail_info
            
            # detail_infoの重要な情報をproperty_dataにコピー
            self._copy_detail_info_to_property_data(detail_info, property_data)
            
            return property_data
            
        except Exception as e:
            self.logger.error(f"grantact詳細ページ解析エラー: {str(e)}")
            return property_data
    
    def _extract_grantact_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """grantactページから情報を抽出"""
        # 生データを保存
        detail_info[label] = value
        
        # 価格
        if '価格' in label:
            price = self.parse_price(value)
            if price:
                property_data['price'] = price
        
        # 間取り
        elif '間取り' in label or '間取' in label:
            layout = self.normalize_layout(value)
            if layout:
                property_data['layout'] = layout
        
        # 専有面積
        elif '専有面積' in label:
            area = self.parse_area(value)
            if area:
                property_data['area'] = area
        
        # バルコニー面積
        elif 'バルコニー' in label:
            balcony = self.parse_area(value)
            if balcony:
                property_data['balcony_area'] = balcony
        
        # 階数
        elif '所在階' in label:
            floor = self.parse_floor(value)
            if floor:
                property_data['floor_number'] = floor
        
        # 向き
        elif '向き' in label or '方位' in label:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in label:
            built_info = self.parse_built_date(value)
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
            if built_info['built_month']:
                property_data['built_month'] = built_info['built_month']
        
        # 管理費
        elif '管理費' in label:
            fee = extract_monthly_fee(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in label:
            fund = extract_monthly_fee(value)
            if fund:
                property_data['repair_fund'] = fund
    
    def _extract_grantact_building_name(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページから建物名を抽出（複数箇所から取得して検証）"""
        building_names = []
        
        # 1. タイトルタグから取得
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # 【GRANTACT】の後の建物名を取得
            if '【GRANTACT】' in title_text:
                match = re.search(r'【GRANTACT】([^｜|\|]+)', title_text)
                if match:
                    building_name = match.group(1).strip()
                    if building_name:
                        building_names.append(('title', building_name))
                        self.logger.info(f"[Livable] タイトルから建物名を取得: {building_name}")
            else:
                # 通常のタイトルパターン
                match = re.search(r'^([^｜|\|\\(]+)', title_text)
                if match:
                    building_name = match.group(1).strip()
                    if building_name:
                        building_names.append(('title', building_name))
                        self.logger.info(f"[Livable] タイトルから建物名を取得: {building_name}")
        
        # 2. h1タグから取得
        h1_tag = soup.find('h1')
        if h1_tag:
            h1_text = h1_tag.get_text(strip=True)
            # 【GRANTACT】が含まれる場合はその後の部分を取得
            if '【GRANTACT】' in h1_text:
                match = re.search(r'【GRANTACT】([^｜|\|]+)', h1_text)
                if match:
                    building_name = match.group(1).strip()
                    if building_name:
                        building_names.append(('h1', building_name))
                        self.logger.info(f"[Livable] h1から建物名を取得: {building_name}")
            else:
                # 通常のパターン
                building_name = h1_text.strip()
                if building_name and not building_name.startswith('東急リバブル'):
                    building_names.append(('h1', building_name))
                    self.logger.info(f"[Livable] h1から建物名を取得: {building_name}")
        
        # 3. og:titleメタタグから取得（補助的な情報源）
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            content = og_title['content']
            if '【GRANTACT】' in content:
                match = re.search(r'【GRANTACT】([^｜|\|]+)', content)
                if match:
                    building_name = match.group(1).strip()
                    if building_name:
                        building_names.append(('og:title', building_name))
                        self.logger.info(f"[Livable] og:titleから建物名を取得: {building_name}")
        
        # 建物名のクロスバリデーション
        if len(building_names) >= 2:
            # 複数箇所から取得できた場合、一致確認
            primary_name = building_names[0][1]
            secondary_name = building_names[1][1]
            
            # 正規化して比較
            # 簡易的な正規化（全角半角統一、スペース削除）
            import unicodedata
            def simple_normalize(text):
                # 全角を半角に変換
                text = unicodedata.normalize('NFKC', text)
                # 大文字小文字を統一
                text = text.upper()
                # スペースを削除
                text = text.replace(' ', '').replace('　', '')
                return text
            
            normalized_primary = simple_normalize(primary_name)
            normalized_secondary = simple_normalize(secondary_name)
            
            if normalized_primary == normalized_secondary:
                self.logger.info(f"[Livable] 建物名が一致（{building_names[0][0]}と{building_names[1][0]}）: {primary_name}")
                property_data['building_name'] = primary_name
                property_data['_building_name_validated'] = True
            else:
                # 部分一致をチェック（片方が他方を含む場合）
                if normalized_primary in normalized_secondary or normalized_secondary in normalized_primary:
                    # より長い方を採用
                    longer_name = primary_name if len(primary_name) >= len(secondary_name) else secondary_name
                    self.logger.info(f"[Livable] 建物名が部分一致、より詳細な名前を採用: {longer_name}")
                    property_data['building_name'] = longer_name
                    property_data['_building_name_validated'] = True
                else:
                    self.logger.warning(
                        f"[Livable] 建物名が不一致: {building_names[0][0]}='{primary_name}' vs "
                        f"{building_names[1][0]}='{secondary_name}'"
                    )
                    # 最初に見つかった建物名を採用
                    property_data['building_name'] = primary_name
                    property_data['_building_name_validated'] = False
        elif len(building_names) == 1:
            # 1箇所からしか取得できなかった場合
            property_data['building_name'] = building_names[0][1]
            property_data['_building_name_validated'] = False
            self.logger.warning(f"[Livable] 建物名を1箇所からのみ取得: {building_names[0][0]}='{building_names[0][1]}'")
        else:
            self.logger.error("[Livable] 建物名を取得できませんでした")
    
    def _extract_grantact_address(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページから住所を抽出"""
        # JavaScriptから住所を取得
        script_texts = soup.find_all('script', string=lambda text: text and 'address' in text if text else False)
        for script in script_texts:
            script_content = script.string
            # "address":"東京都港区白金２丁目1-8" のパターンを探す
            address_match = re.search(r'"address"\s*:\s*"([^"]+)"', script_content)
            if address_match:
                address = address_match.group(1)
                normalized = self.normalize_address(address)
                if normalized:
                    property_data['address'] = normalized
                    return
    
    def _validate_grantact_required_fields(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページの必須フィールドを検証"""
        # 価格が取得できていない場合
        if not property_data.get('price'):
            # 方法1: 販売価格のspan/pペアから取得
            for div in soup.select('div'):
                span = div.find('span')
                if span and '販売価格' in span.get_text(strip=True):
                    price_p = span.find_next_sibling('p')
                    if price_p:
                        price = self.parse_price(price_p.get_text(strip=True))
                        if price:
                            property_data['price'] = price
                            break
            
            # 方法2: テーブルのth=価格から取得
            if not property_data.get('price'):
                for th in soup.select('th'):
                    if '価格' == th.get_text(strip=True):
                        td = th.find_next_sibling('td')
                        if td:
                            price = self.parse_price(td.get_text(strip=True))
                            if price:
                                property_data['price'] = price
                                break
        
        # 建物名が取得できていない場合
        if not property_data.get('building_name'):
            # h1タグなどから再試行
            h1 = soup.find('h1')
            if h1:
                building_name = h1.get_text(strip=True)
                if building_name:
                    property_data['building_name'] = building_name

    def _extract_title_and_building_name(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """タイトルと建物名を抽出"""
        # まずはタイトルタグから取得を試みる
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # "南青ハイツ(C48257022)｜マンション購入｜東急リバブル" のような形式から建物名を抽出
            title_match = re.search(r'^(.+?)(?:\(|｜)', title_text)
            if title_match:
                property_data['title'] = title_match.group(1).strip()
                # 建物名がまだない場合は、タイトルから取得した名前を使用
                if 'building_name' not in property_data:
                    property_data['building_name'] = property_data['title']
            else:
                property_data['title'] = title_text
        else:
            # フォールバック：ヘッドライン要素から取得
            title_elem = soup.select_one('.o-detail-header__headline, h1, h2')
            if title_elem:
                property_data['title'] = title_elem.get_text(strip=True)
    
    def _extract_address(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """住所を抽出"""
        address_from_html = None
        
        # HTMLのテーブルから住所を取得（最も完全な情報が期待できる）
        dl_elements = soup.select('dl.m-status-table')
        for dl in dl_elements:
            dt_elements = dl.select('dt.m-status-table__headline')
            dd_elements = dl.select('dd.m-status-table__body')
            
            for dt, dd in zip(dt_elements, dd_elements):
                dt_text = dt.get_text(strip=True)
                if '所在地' in dt_text or '住所' in dt_text:
                    # HTMLから直接テキストを抽出
                    address_text = dd.get_text(strip=True)
                    
                    # 住所をクリーニング
                    if address_text and address_text != '-':
                        # UI要素を除去（基底クラスのメソッドを使用）
                        address_text = self.clean_address(address_text)
                        
                        if address_text:
                            address_from_html = address_text
                            break
            if address_from_html:
                break
        
        # JavaScriptから住所を取得（フォールバック用）
        if not address_from_html:
            script_texts = soup.find_all('script', string=lambda text: text and 'address' in text if text else False)
            for script in script_texts:
                script_content = script.string
                # "address":"東京都港区白金２丁目1-8" のパターンを探す
                address_match = re.search(r'"address"\s*:\s*"([^"]+)"', script_content)
                if address_match:
                    address_from_html = address_match.group(1)
                    break
        
        if address_from_html:
            # normalize_addressで最終的なクリーニング
            normalized = self.normalize_address(address_from_html)
            if normalized:
                property_data['address'] = normalized
    
    def _extract_detail_price(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> bool:
        """詳細ページから価格を抽出"""
        # 優先1: o-detail-header__priceセレクタ
        price_elem = soup.select_one('.o-detail-header__price')
        if price_elem:
            # span.numから価格を構築
            price_text = self.build_price_text_from_spans(price_elem)
            price = self.parse_price(price_text)
            if price:
                property_data['price'] = price
                return True
        
        # 優先2: m-status-tableから価格を探す
        dl_elements = soup.select('dl.m-status-table')
        for dl in dl_elements:
            dt = dl.select_one('dt.m-status-table__headline')
            dd = dl.select_one('dd.m-status-table__body')
            if dt and dd:
                dt_text = dt.get_text(strip=True)
                if '価格' in dt_text:
                    price_text = dd.get_text(strip=True)
                    price = self.parse_price(price_text)
                    if price:
                        property_data['price'] = price
                        return True
        
        # 優先3: その他のパターン
        price_selectors = [
            '.price-value',
            'span.price',
            'p.price',
            '.property-price'
        ]
        
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = self.extract_text(price_elem)
                price = self.parse_price(price_text)
                if price:
                    property_data['price'] = price
                    return True
        
        return False
    
    def _extract_property_details(self, soup: BeautifulSoup, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """物件詳細情報を抽出"""
        # m-status-tableクラスの全てのdl要素を処理
        dl_elements = soup.select('dl.m-status-table')
        
        for dl in dl_elements:
            dt_elements = dl.select('dt.m-status-table__headline')
            dd_elements = dl.select('dd.m-status-table__body')
            
            # dtとddをペアで処理
            for dt, dd in zip(dt_elements, dd_elements):
                key = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                if not value or value == '-':
                    continue
                
                # detail_infoに生データを保存
                detail_info[key] = value
                
                # 各フィールドを処理
                self._process_detail_item(key, value, property_data)
    
    def _copy_detail_info_to_property_data(self, detail_info: Dict[str, Any], property_data: Dict[str, Any]):
        """detail_infoの重要な情報をproperty_dataにコピー"""
        # 間取りの特殊処理
        if 'layout' not in property_data and '間取り' in detail_info:
            layout = self.normalize_layout(detail_info['間取り'])
            if layout:
                property_data['layout'] = layout
        
        # 階数の特殊処理
        if 'floor_number' not in property_data and '所在階' in detail_info:
            floor = self.parse_floor(detail_info['所在階'])
            if floor:
                property_data['floor_number'] = floor
        
        # 総階数の特殊処理
        if 'total_floors' not in property_data:
            if '建物階数' in detail_info:
                total = self.parse_floor(detail_info['建物階数'])
                if total:
                    property_data['total_floors'] = total
            elif '階建' in detail_info:
                total = self.parse_floor(detail_info['階建'])
                if total:
                    property_data['total_floors'] = total
    
    def build_price_text_from_spans(self, elem: Tag) -> str:
        """span要素から価格テキストを構築"""
        # span.numから価格を構築
        num_spans = elem.select('span.num')
        if num_spans:
            # すべてのspanのテキストを結合
            price_text = ''.join(span.get_text(strip=True) for span in num_spans)
            if price_text:
                # 「億」が含まれていない場合は「万円」を追加
                if '億' not in price_text and '万' not in price_text:
                    price_text += '万円'
                return price_text
        
        # フォールバック: 通常のテキスト抽出
        return elem.get_text(strip=True)
    
    def _process_detail_table_data(self, table_data: Dict[str, str], property_data: Dict[str, Any]) -> None:
        """
        詳細テーブルデータを処理
        
        Args:
            table_data: テーブルから抽出したデータ
            property_data: データ格納先
        """
        for key, value in table_data.items():
            self._process_detail_item(key, value, property_data)
    
    def _process_detail_item(self, key: str, value: str, property_data: Dict[str, Any]) -> None:
        """
        詳細アイテムを処理
        
        Args:
            key: キー
            value: 値
            property_data: データ格納先
        """
        if not value:
            return
        
        # 価格
        if '価格' in key:
            price = self.parse_price(value)
            if price:
                property_data['price'] = price
        
        # 間取り
        elif '間取' in key:
            layout = self.normalize_layout(value)
            if layout:
                property_data['layout'] = layout
        
        # 専有面積
        elif '専有面積' in key:
            area = self.parse_area(value)
            if area:
                property_data['area'] = area
        
        # バルコニー面積
        elif 'バルコニー' in key:
            balcony_area = self.parse_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 階数関連の処理をまとめて処理
        elif any(x in key for x in ['所在階', '階数', '階建']):
            # 「所在階/階建」「所在階数」「所在階」「建物階数」「総階数」「階建」を統一処理
            
            # 所在階（floor_number）の抽出
            if '所在階' in key:
                floor = self.parse_floor(value)
                if floor:
                    property_data['floor_number'] = floor
            
            # 総階数（total_floors）と地下階数（basement_floors）の抽出
            # 「所在階/階建」「所在階数」パターンから総階数を抽出
            if '/' in value or '地上' in value or '階建' in key or '階数' in key or '地下' in value:
                total_floors = self.parse_total_floors(value)
                if total_floors:
                    property_data['total_floors'] = total_floors
                
                # 地下階数の抽出
                basement_floors = self.parse_basement_floors(value)
                if basement_floors:
                    property_data['basement_floors'] = basement_floors
        
        # 総戸数
        elif '総戸数' in key or '総区画数' in key:
            units = self.parse_total_units(value)
            if units:
                property_data['total_units'] = units
        
        # 方角
        elif '向き' in key or '方位' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in key:
            built_info = self.parse_built_date(value)
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
            if built_info['built_month']:
                property_data['built_month'] = built_info['built_month']
        
        # 所在地
        elif '所在地' in key:
            # normalize_addressがUI要素（「地図を見る」など）を自動的に削除
            address = self.normalize_address(value)
            if address:
                property_data['address'] = address
        
        # 交通
        elif '交通' in key or '最寄' in key:
            station = self.parse_station_info(value)
            if station:
                property_data['station_info'] = station
        
        # 管理費
        elif '管理費' in key:
            # "/月" を除去
            value = value.replace('/月', '').strip()
            fee = extract_monthly_fee(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in key:
            # "/月" を除去
            value = value.replace('/月', '').strip()
            fund = extract_monthly_fee(value)
            if fund:
                property_data['repair_fund'] = fund
        
        # 部屋番号
        elif '部屋番号' in key or '号室' in key:
            room = self.extract_text(value)
            if room and room != '-':
                property_data['room_number'] = room
    
    def _extract_building_name_from_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細ページから建物名を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # タイトルから建物名を取得
        title_selectors = [
            "h1.p-property-overview_title span.p-property-overview_title_name",
            "span.p-property-overview_title_name",
            "h1.property-title",
            "h1.bukken-title",
            "h1"
        ]
        
        for selector in title_selectors:
            title = self.safe_select_one(soup, selector)
            if title:
                building_name = self.extract_text(title)
                if building_name:
                    # タイトルフィールドにも設定（表示用）
                    property_data['title'] = building_name
                    property_data['building_name'] = building_name
                    return
    

    
    def get_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        次ページのURLを取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            current_url: 現在のURL
            
        Returns:
            次ページのURL（なければNone）
        """
        # ページネーションを探す
        next_link = self.safe_select_one(soup, "a.next, a[rel='next'], li.next a")
        
        if next_link and next_link.get('href'):
            next_url = self.normalize_url(next_link['href'], self.BASE_URL)
            if next_url and next_url != current_url:
                return next_url
        
        return None
    
    def _validate_list_data(self, data: Dict[str, Any]) -> bool:
        """
        一覧ページデータの妥当性を検証
        
        Args:
            data: 物件データ
            
        Returns:
            妥当性フラグ
        """
        # 必須フィールド
        required = ['site_property_id', 'price', 'url']
        for field in required:
            if field not in data or not data[field]:
                self.logger.debug(f"必須フィールド '{field}' が欠落")
                return False
        
        # 価格の妥当性
        if data.get('price'):
            price = data['price']
            if price < 100 or price > 500000:  # 100万円〜50億円
                self.logger.debug(f"価格が範囲外: {price}万円")
                return False
        
        return True
    
    def _check_duplicate_property_ids(self, properties: List[Dict[str, Any]]) -> None:
        """
        物件IDの重複をチェック
        
        Args:
            properties: 物件リスト
        """
        seen_ids = {}
        for prop in properties:
            prop_id = prop.get('site_property_id')
            if prop_id:
                if prop_id in seen_ids:
                    self.logger.warning(f"重複物件ID検出: {prop_id}")
                seen_ids[prop_id] = True