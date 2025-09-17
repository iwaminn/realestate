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
            property_data: データ格納先
        """
        # dl要素から情報を抽出
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
            layout_elem = item.select_one('.o-product-list__layout, .layout')
            if layout_elem:
                layout = self.normalize_layout(self.extract_text(layout_elem))
                if layout:
                    property_data['layout'] = layout
        
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
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        
        # 物件情報テーブルを探す
        detail_tables = self.safe_select(soup, "table.bukken-table, table.property-detail")
        
        for table in detail_tables:
            table_data = self.extract_table_data(table)
            self._process_detail_table_data(table_data, property_data)
        
        # dl要素から情報を抽出
        data_lists = self.safe_select(soup, "div.p-property-data-list dl, dl")
        for dl in data_lists:
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                self._process_detail_item(key, value, property_data)
        
        # 建物名を取得
        self._extract_building_name_from_detail(soup, property_data)
        
        # 物件画像
        self._extract_property_images(soup, property_data)
        
        # 物件備考
        self._extract_remarks(soup, property_data)
        
        # 不動産会社情報
        self._extract_agency_info(soup, property_data)
        
        return property_data
    
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
        
        # 所在階/階建 - 特殊パターン処理
        elif '所在階/階建' in key:
            # "8階/15階建" のような形式を処理
            match = re.search(r'(\d+)階/(\d+)階建', value)
            if match:
                property_data['floor_number'] = int(match.group(1))
                property_data['total_floors'] = int(match.group(2))
        
        # 所在階
        elif '所在階' in key:
            floor = self.parse_floor(value)
            if floor:
                property_data['floor_number'] = floor
        
        # 建物階数
        elif '階数' in key or '総階数' in key or '階建' in key:
            total_floors = self.parse_floor(value)
            if total_floors:
                property_data['total_floors'] = total_floors
        
        # 総戸数
        elif '総戸数' in key or '総区画数' in key:
            # 「200戸以上」「1,095戸」などから数値を抽出
            # カンマ、スペース、改行を除去
            cleaned_value = value.replace(',', '').replace('，', '').replace(' ', '').replace('\n', '').replace('\t', '')
            
            # 「戸」を含む数値を抽出
            units_match = re.search(r'(\d+)戸', cleaned_value)
            if units_match:
                property_data['total_units'] = int(units_match.group(1))
            else:
                # 「戸」がない場合も試す（数値のみ）
                units_match = re.search(r'(\d+)', cleaned_value)
                if units_match:
                    property_data['total_units'] = int(units_match.group(1))
        
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
            fee = self.parse_management_info(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in key:
            # "/月" を除去
            value = value.replace('/月', '').strip()
            fund = self.parse_management_info(value)
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
    
    def _extract_property_images(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件画像URLを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        images = []
        
        # メイン画像
        main_img = self.safe_select_one(soup, "img.main-photo, img.property-main-image")
        if main_img and main_img.get('src'):
            img_url = self.normalize_url(main_img['src'], self.BASE_URL)
            if img_url:
                images.append(img_url)
        
        # サムネイル画像
        thumb_imgs = self.safe_select(soup, "div.photo-gallery img, div.thumbnails img")
        for img in thumb_imgs[:10]:  # 最大10枚
            if img.get('src'):
                img_url = self.normalize_url(img['src'], self.BASE_URL)
                if img_url and img_url not in images:
                    images.append(img_url)
        
        if images:
            property_data['image_urls'] = images
    
    def _extract_remarks(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件備考を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        remarks_selectors = [
            "div.p-property-pr p",
            "div.p-property-pr",
            "div.remarks",
            "div.pr-comment",
            "div.comment"
        ]
        
        for selector in remarks_selectors:
            remarks_elem = self.safe_select_one(soup, selector)
            if remarks_elem:
                remarks = self.extract_text(remarks_elem)
                if remarks:
                    property_data['remarks'] = remarks
                    # 最初の100文字を要約として使用
                    property_data['summary_remarks'] = remarks[:100] + ('...' if len(remarks) > 100 else '')
                    return
    
    def _extract_agency_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        不動産会社情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 会社情報を探す
        company_elem = self.safe_select_one(soup, "div.p-property-company")
        if company_elem:
            company_text = company_elem.get_text(' ', strip=True)
            
            # 会社名を抽出
            if 'リバブル' in company_text:
                # 東急リバブルの場合もページから取得した情報をそのまま使用
                pass
            else:
                # 最初の行を会社名として使用
                lines = [line.strip() for line in company_text.split('\n') if line.strip()]
                if lines:
                    property_data['agency_name'] = lines[0]
            
            # 電話番号を抽出
            tel_match = re.search(r'TEL[:：\s]*([0-9\-]+)', company_text)
            if tel_match:
                property_data['agency_tel'] = tel_match.group(1)
        else:
            # デフォルト値を設定しない（空のままにする）
            # 電話番号を探す
            tel_elem = self.safe_select_one(soup, "span.tel, div.contact-tel")
            if tel_elem:
                tel = self.extract_text(tel_elem)
                # 数字とハイフンのみ抽出
                tel_match = re.search(r'[\d\-]+', tel)
                if tel_match:
                    property_data['agency_tel'] = tel_match.group()
    
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