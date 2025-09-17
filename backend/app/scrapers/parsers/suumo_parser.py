"""
SUUMO専用HTMLパーサー

SUUMO（suumo.jp）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

from .base_parser import BaseHtmlParser


class SuumoParser(BaseHtmlParser):
    """SUUMO専用パーサー"""
    
    # SUUMOのデフォルト設定
    DEFAULT_AGENCY_NAME = None  # SUUMOは不動産会社ではないため、デフォルト値は設定しない
    BASE_URL = "https://suumo.jp"
    
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
        物件一覧をパース - URLと最小限の情報のみを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件情報のリスト
        """
        properties = []
        
        # SUUMOの物件リストセレクタ（新旧両方のフォーマットに対応）
        property_units = soup.select('.property_unit')
        
        # 新形式のセレクタも試す
        if not property_units:
            property_units = soup.select('.cassette')
        
        for unit in property_units:
            property_data = {}
            
            # 物件詳細へのリンク（タイトルリンクを取得）
            title_link = unit.select_one('.property_unit-title a')
            if title_link:
                # タイトルテキストを取得
                title_text = self.extract_text(title_link)
                if title_text:
                    property_data['title'] = title_text
                    
                url = title_link.get('href')
                if url:
                    from urllib.parse import urljoin
                    property_data['url'] = urljoin(self.BASE_URL, url)
                    # URLからIDを抽出
                    import re
                    # 新しいURLパターン /nc_XXXXX/ に対応
                    id_match = re.search(r'/nc_(\d+)/', property_data['url'])
                    if not id_match:
                        # 旧パターンも試す
                        id_match = re.search(r'/chuko/mansiondetail_(\d+)/', property_data['url'])
                    if id_match:
                        property_data['site_property_id'] = id_match.group(1)
            
            # 価格を取得（一覧ページから）
            price_elem = unit.select_one('.dottable-value')
            if price_elem:
                price_text = self.extract_text(price_elem)
                property_data['price'] = self.parse_price(price_text)
            
            # 建物名を取得（一覧ページから）
            # SUUMOでは物件名はproperty_unit-info内のdlタグに含まれる
            property_info = unit.select_one('.property_unit-info')
            if property_info:
                dl_elements = property_info.select('dl')
                for dl in dl_elements:
                    dt_elements = dl.select('dt')
                    dd_elements = dl.select('dd')
                    
                    for dt, dd in zip(dt_elements, dd_elements):
                        if '物件名' in dt.get_text():
                            building_name = dd.get_text(strip=True)
                            if building_name:
                                property_data['building_name'] = building_name
                            break
            
            # URLとsite_property_idがある場合のみ追加
            if property_data.get('url') and property_data.get('site_property_id'):
                properties.append(property_data)
        
        return properties
    
    def _parse_property_card(self, card: Tag) -> List[Dict[str, Any]]:
        """
        物件カードから情報を抽出
        
        Args:
            card: 物件カード要素
            
        Returns:
            物件データのリスト
        """
        properties = []
        property_data = {}
        
        # 物件詳細へのリンク（タイトルリンクを取得）
        title_link = card.select_one('.property_unit-title a')
        if not title_link:
            # 代替セレクタ
            title_link = card.select_one('h2.property_unit-title a') or \
                        card.select_one('a.js-cassette_link_href') or \
                        card.select_one('h2 a')
        
        if title_link:
            href = title_link.get('href')
            if href:
                property_data['url'] = self.normalize_url(href, self.BASE_URL)
                # URLからIDを抽出
                id_match = re.search(r'/(\d+)/?(?:\?|$)', property_data['url'])
                if id_match:
                    property_data['site_property_id'] = id_match.group(1)
                
                # 建物名を取得
                property_data['building_name'] = self.extract_text(title_link)
        
        # 価格情報
        price_elem = card.select_one('.dottable-value') or \
                     card.select_one('.price') or \
                     card.select_one('span.ui-text--bold')
        if price_elem:
            price = self.parse_price(self.extract_text(price_elem))
            if price:
                property_data['price'] = price
        
        # 間取り・面積・階数などの詳細情報
        detail_items = card.select('.dottable-line')
        for item in detail_items:
            text = self.extract_text(item)
            if '間取り' in text or 'LDK' in text or 'DK' in text:
                layout = self.normalize_layout(text)
                if layout:
                    property_data['layout'] = layout
            elif '専有面積' in text or '㎡' in text:
                area = self.parse_area(text)
                if area:
                    property_data['area'] = area
            elif '階' in text:
                floor = self.parse_floor(text)
                if floor:
                    property_data['floor_number'] = floor
        
        # URLがある場合のみ追加
        if property_data.get('url'):
            properties.append(property_data)
        
        return properties
    
    def _extract_building_name(self, card: Tag) -> Optional[str]:
        """
        建物名を抽出
        
        Args:
            card: カード要素
            
        Returns:
            建物名
        """
        # 建物名の候補セレクタ
        selectors = [
            "h2.cassette_heading a",
            "h2.property-name",
            "div.cassette_title",
            "a.js-cassette_link_href"
        ]
        
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                building_name = self.extract_text(elem)
                if building_name:
                    return building_name
        
        return None
    
    def _extract_common_info(self, card: Tag) -> Dict[str, Any]:
        """
        物件カード共通情報を抽出
        
        Args:
            card: カード要素
            
        Returns:
            共通情報
        """
        common_info = {}
        
        # 住所
        address_elem = card.select_one("li.cassette-list-item--address, div.address")
        if address_elem:
            common_info['address'] = self.normalize_address(self.extract_text(address_elem))
        
        # 交通情報
        access_elem = card.select_one("li.cassette-list-item--access, div.access")
        if access_elem:
            common_info['station_info'] = self.parse_station_info(self.extract_text(access_elem))
        
        # 築年月
        built_elem = card.select_one("li.cassette-list-item--built, span.built")
        if built_elem:
            built_info = self.parse_built_date(self.extract_text(built_elem))
            if built_info['built_year']:
                common_info['built_year'] = built_info['built_year']
            if built_info['built_month']:
                common_info['built_month'] = built_info['built_month']
        
        # 総階数
        floors_elem = card.select_one("li.cassette-list-item--floors, span.floors")
        if floors_elem:
            total_floors = self.parse_floor(self.extract_text(floors_elem))
            if total_floors:
                common_info['total_floors'] = total_floors
        
        return common_info
    
    def _extract_room_info(self, room_elem: Tag, property_data: Dict[str, Any]) -> None:
        """
        部屋固有の情報を抽出
        
        Args:
            room_elem: 部屋要素
            property_data: データ格納先
        """
        # URL
        link = room_elem.select_one("a") or room_elem.find("a", href=True)
        if link and link.get('href'):
            property_data['url'] = self.normalize_url(link['href'], self.BASE_URL)
            # URLからIDを抽出
            site_id_match = re.search(r'/(\d+)/', link['href'])
            if site_id_match:
                property_data['site_property_id'] = site_id_match.group(1)
        
        # 価格
        price_elem = room_elem.select_one("span.cassetteitem_price--sale, td.price")
        if price_elem:
            price = self.parse_price(self.extract_text(price_elem))
            if price:
                property_data['price'] = price
        
        # 間取り
        layout_elem = room_elem.select_one("span.cassetteitem_madori, td.layout")
        if layout_elem:
            layout = self.normalize_layout(self.extract_text(layout_elem))
            if layout:
                property_data['layout'] = layout
        
        # 面積
        area_elem = room_elem.select_one("span.cassetteitem_menseki, td.area")
        if area_elem:
            area = self.parse_area(self.extract_text(area_elem))
            if area:
                property_data['area'] = area
        
        # 階数
        floor_elem = room_elem.select_one("td:contains('階'), span.floor")
        if floor_elem:
            floor_text = self.extract_text(floor_elem)
            floor = self.parse_floor(floor_text)
            if floor:
                property_data['floor_number'] = floor
        
        # 方角
        direction_elem = room_elem.select_one("td:contains('向き'), span.direction")
        if direction_elem:
            direction = self.normalize_direction(self.extract_text(direction_elem))
            if direction:
                property_data['direction'] = direction
        
        # 不動産会社名
        agency_elem = room_elem.select_one("span.cassetteitem_agency, div.agency")
        if agency_elem:
            property_data['agency_name'] = self.extract_text(agency_elem)
        # 不動産会社が取得できない場合は空のままにする
    
    def _extract_single_property_info(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        単一物件の情報を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        # URL
        link = card.select_one("a[href]")
        if link and link.get('href'):
            property_data['url'] = self.normalize_url(link['href'], self.BASE_URL)
            # URLからIDを抽出
            site_id_match = re.search(r'/(\d+)/', link['href'])
            if site_id_match:
                property_data['site_property_id'] = site_id_match.group(1)
        
        # 価格、間取り、面積などの情報を取得
        info_table = card.select_one("table.cassette-item-table")
        if info_table:
            table_data = self.extract_table_data(info_table)
            for key, value in table_data.items():
                self._process_table_item(key, value, property_data)
        
        # 不動産会社名（デフォルト）
        if 'agency_name' not in property_data:
            property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
    
    def _process_table_item(self, key: str, value: str, property_data: Dict[str, Any]) -> None:
        """
        テーブルアイテムを処理
        
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
        
        # 面積
        elif '専有面積' in key or '面積' in key:
            area = self.parse_area(value)
            if area:
                property_data['area'] = area
        
        # 階数
        elif '所在階' in key or '階' in key:
            floor = self.parse_floor(value)
            if floor:
                property_data['floor_number'] = floor
        
        # 方角
        elif '向き' in key or '方角' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        
        # 物件名
        self._extract_property_name(soup, property_data)
        
        # 基本情報テーブル
        self._extract_basic_info(soup, property_data)
        
        # 詳細情報テーブル
        self._extract_detail_info(soup, property_data)
        
        # 物件画像
        self._extract_property_images(soup, property_data)
        
        # 物件備考
        self._extract_remarks(soup, property_data)
        
        # 不動産会社情報
        self._extract_agency_info(soup, property_data)
        
        return property_data
    
    def _extract_property_name(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件名を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        title_selectors = [
            "h1.section_h1--inner",
            "h1.property-title",
            "div.section_h1 h1",
            "h1"
        ]
        
        for selector in title_selectors:
            title = self.safe_select_one(soup, selector)
            if title:
                building_name = self.extract_text(title)
                if building_name:
                    # タイトルフィールドにも設定（表示用）
                    property_data['title'] = building_name
                    
                    # 部屋番号部分を除去してbuilding_nameに設定
                    building_name = re.sub(r'\s*\d+号室.*$', '', building_name)
                    building_name = re.sub(r'\s*\d+階.*$', '', building_name)
                    property_data['building_name'] = building_name
                    return
    
    def _extract_basic_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        基本情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 基本情報テーブル（複数のクラス名パターンに対応）
        info_tables = soup.select("table.data_table, table.bgc-wht, table.bgWhite")
        
        # それでも見つからない場合は、すべてのテーブルから探す
        if not info_tables:
            # bgWhiteクラスを含むテーブルをすべて取得
            all_tables = soup.find_all("table", class_=lambda x: x and "bgWhite" in " ".join(x) if isinstance(x, list) else False)
            info_tables = all_tables if all_tables else []
        
        # 各テーブルを処理
        for info_table in info_tables:
            rows = info_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    # キーからリンクなどの子要素を除外して、テキストのみを取得
                    # まずdiv.flがあればそのテキストを取得、なければthの直接テキストを取得
                    key_div = th.find('div', class_='fl')
                    if key_div:
                        # div.fl内のテキストを取得
                        key = self.extract_text(key_div)
                    else:
                        # thの直接のテキストノードのみを取得（子要素のテキストは除外）
                        key_parts = []
                        for content in th.contents:
                            if isinstance(content, str):
                                key_parts.append(content.strip())
                        key = ''.join(key_parts).strip()
                        
                        # それでも取得できない場合は全体のテキストから「ヒント」を除去
                        if not key:
                            key = self.extract_text(th)
                            # 「ヒント」という文字列を除去
                            key = key.replace('ヒント', '').strip()
                    
                    # 値は通常通り全体のテキストを取得
                    value = self.extract_text(td)
                    
                    # キーが空でない場合のみ処理
                    if key:
                        self._process_detail_item(key, value, property_data)
    
    def _extract_detail_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 詳細情報のdl要素
        dl_elements = self.safe_select(soup, "dl.data-body")
        for dl in dl_elements:
            dt_elements = dl.find_all("dt")
            dd_elements = dl.find_all("dd")
            
            for dt, dd in zip(dt_elements, dd_elements):
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
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
        if '価格' in key or '販売価格' in key:
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
        
        # 階数（所在階/階建）
        elif '所在階' in key:
            # "5階/10階建"のような形式を処理
            match = re.search(r'(\d+)階/(\d+)階建', value)
            if match:
                property_data['floor_number'] = int(match.group(1))
                property_data['total_floors'] = int(match.group(2))
            else:
                floor = self.parse_floor(value)
                if floor:
                    property_data['floor_number'] = floor
        
        # 総階数
        elif '階建' in key or '総階数' in key:
            total_floors = self.parse_floor(value)
            if total_floors:
                property_data['total_floors'] = total_floors
        
        # 総戸数
        elif '総戸数' in key or '総区画数' in key:
            # 「1,095戸」「250戸」などから数値を抽出（カンマも考慮）
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
        elif '向き' in key or '主要採光面' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in key or '竣工時期' in key:
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
        elif '交通' in key:
            station = self.parse_station_info(value)
            if station:
                property_data['station_info'] = station
        
        # 管理費
        elif '管理費' in key:
            fee = self.parse_management_info(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in key:
            fund = self.parse_management_info(value)
            if fund:
                property_data['repair_fund'] = fund
        
        # 部屋番号
        elif '部屋番号' in key:
            room = self.extract_text(value)
            if room and room != '-':
                property_data['room_number'] = room
    
    def _extract_property_images(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件画像URLを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        images = []
        
        # メイン画像
        main_img = self.safe_select_one(soup, "img.slide_photo, img#mainImage")
        if main_img and main_img.get('src'):
            img_url = self.normalize_url(main_img['src'], self.BASE_URL)
            if img_url:
                images.append(img_url)
        
        # サムネイル画像
        thumb_imgs = self.safe_select(soup, "ul.thumb_list img, div.thumbnail img")
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
            "div.section-comment",
            "div.property-pr",
            "section.comment",
            "div.pr_comment"
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
        # 会社情報セクション
        company_section = self.safe_select_one(soup, "div.company-data, section.company")
        if company_section:
            # 会社名
            company_name_elem = company_section.find("h3") or company_section.find("p", class_="company-name")
            if company_name_elem:
                property_data['agency_name'] = self.extract_text(company_name_elem)
            
            # 電話番号
            tel_elem = company_section.find("span", class_="tel") or company_section.find("p", class_="phone")
            if tel_elem:
                tel_text = self.extract_text(tel_elem)
                tel_match = re.search(r'[\d\-]+', tel_text)
                if tel_match:
                    property_data['agency_tel'] = tel_match.group()
        
        # 不動産会社が取得できない場合は空のままにする（SUUMOは不動産会社ではない）
        # if 'agency_name' not in property_data:
        #     property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
    
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
        next_link = self.safe_select_one(soup, "p.pagination-parts a[title='次へ'], a.next")
        
        if next_link and next_link.get('href'):
            next_url = self.normalize_url(next_link['href'], self.BASE_URL)
            if next_url and next_url != current_url:
                return next_url
        
        return None
    
    def _validate_card_data(self, data: Dict[str, Any]) -> bool:
        """
        カードデータの妥当性を検証
        
        Args:
            data: 物件データ
            
        Returns:
            妥当性フラグ
        """
        # 必須フィールド
        required = ['building_name', 'price', 'url']
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