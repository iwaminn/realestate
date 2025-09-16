"""
三井のリハウス専用HTMLパーサー

三井のリハウス（www.rehouse.co.jp）のHTML構造に特化したパーサー
"""
import re
import json
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

from .base_parser import BaseHtmlParser


class RehouseParser(BaseHtmlParser):
    """三井のリハウス専用パーサー"""
    
    # 三井のリハウスのデフォルト設定
    DEFAULT_AGENCY_NAME = "三井のリハウス"
    BASE_URL = "https://www.rehouse.co.jp"
    
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
        
        # 物件カードを検索
        property_items = self._find_property_items(soup)
        
        if not property_items:
            self.logger.warning("No property items found on the page")
            return properties
        
        for item in property_items:
            try:
                property_data = self._parse_property_item(item)
                if property_data:
                    properties.append(property_data)
            except Exception as e:
                self.logger.error(f"物件アイテム解析エラー - {type(e).__name__}: {str(e)}")
                continue
        
        return properties

    def _find_property_items(self, soup: BeautifulSoup) -> List[Tag]:
        """物件カードを検索"""
        # 三井のリハウスの物件カード構造
        property_items = soup.select('div.property-index-card')
        
        if not property_items:
            # 他のセレクタも試す
            selectors = [
                'div[class*="property-card"]',
                'div[class*="property-item"]',
                'article[class*="property"]',
                'li[class*="property"]'
            ]
            
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    property_items = items
                    self.logger.info(f"Found {len(items)} properties using selector: {selector}")
                    break
        else:
            self.logger.info(f"Found {len(property_items)} properties using selector: div.property-index-card")
        
        return property_items
    
    def _parse_property_item(self, item: Tag) -> Optional[Dict[str, Any]]:
        """物件アイテムをパース"""
        # _parse_property_cardメソッドを呼び出す
        return self._parse_property_card(item)
    
    def _parse_property_card(self, card: Tag) -> Optional[Dict[str, Any]]:
        """
        物件カードから情報を抽出
        
        Args:
            card: 物件カード要素
            
        Returns:
            物件データ
        """
        property_data = {}
        
        # 詳細ページへのリンク
        link_elem = card.find('a', href=re.compile(r'/bkdetail/'))
        if not link_elem:
            link_elem = card.find('a', href=re.compile(r'/detail/'))
        
        if not link_elem:
            return None
        
        detail_url = link_elem.get('href')
        if not detail_url.startswith('http'):
            detail_url = self.normalize_url(detail_url, self.BASE_URL)
        
        property_data['url'] = detail_url
        
        # 物件コードを抽出
        code_match = re.search(r'/bkdetail/([^/]+)/', detail_url)
        if not code_match:
            self.logger.error(f"[REHOUSE] URLから物件IDを抽出できませんでした: {detail_url}")
            return None
            
        site_property_id = code_match.group(1)
        property_data['site_property_id'] = site_property_id
        
        # property-index-card-inner内の情報を取得
        inner = card.find(class_='property-index-card-inner')
        if not inner:
            return None
        
        # 全テキストを取得して価格を抽出
        full_text = inner.get_text(' ', strip=True)
        price = self.parse_price(full_text)
        if price:
            property_data['price'] = price
        
        # 建物名を取得（h2タグから）
        title_elem = inner.find('h2')
        if not title_elem:
            # description-section内のh2も試す
            desc_section = inner.find(class_='description-section')
            if desc_section:
                title_elem = desc_section.find('h2')
        
        if title_elem:
            building_name = title_elem.get_text(strip=True)
            property_data['building_name'] = building_name
        
        # description-section内の詳細情報
        desc_section = inner.find(class_='description-section')
        if desc_section:
            self._extract_description_info(desc_section, property_data)
        
        # 仲介業者名
        property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        
        # 必須フィールドの検証
        if self._validate_card_data(property_data):
            return property_data
        else:
            return None

    def _extract_description_info(self, desc_section: Tag, property_data: Dict[str, Any]):
        """description-sectionから情報を抽出"""
        desc_text = desc_section.get_text(' ', strip=True)
        
        # 住所を抽出（都道府県、区、市町村から始まるパターンに対応）
        # 都道府県が含まれている完全な住所、または区・市から始まる住所を探す
        address_patterns = [
            r'((?:東京都|北海道|(?:京都|大阪)府|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)県)[^\s]+)',
            r'([^\s]*[市区町村][^\s/]+)'  # 市区町村から始まる住所
        ]
        
        for pattern in address_patterns:
            addr_match = re.search(pattern, desc_text)
            if addr_match:
                address = addr_match.group(1)
                # そのまま設定（基底クラスの検証に任せる）
                property_data['address'] = address
                break
        
        # 駅情報を抽出（「駅」が含まれる行）
        lines = desc_text.split('\n')
        for line in lines:
            if '駅' in line and '徒歩' in line:
                property_data['station_info'] = line.strip()
                break
        
        # 階数・間取り・面積などの情報
        # 「3LDK」「65.5m²」などのパターンを探す
        layout_match = re.search(r'([1-9][LDKS]+|ワンルーム)', desc_text)
        if layout_match:
            property_data['layout'] = self.normalize_layout(layout_match.group(1))
        
        area_match = re.search(r'(\d+\.?\d*)m[²2]', desc_text)
        if area_match:
            property_data['area'] = float(area_match.group(1))
        
        # 階数情報（「5階」などのパターン）
        floor_match = re.search(r'(\d+)階', desc_text)
        if floor_match:
            property_data['floor_number'] = int(floor_match.group(1))
    
    def _extract_card_info(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードから詳細情報を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        # dl要素から情報を抽出
        info_items = card.select("dl.property-info dt, dl.property-info dd")
        
        i = 0
        while i < len(info_items) - 1:
            if info_items[i].name == 'dt':
                key = self.extract_text(info_items[i])
                value = self.extract_text(info_items[i + 1]) if info_items[i + 1].name == 'dd' else None
                
                if key and value:
                    self._process_info_item(key, value, property_data)
                
                i += 2
            else:
                i += 1
        
        # テーブルから情報を抽出
        table = card.find("table", class_="property-details")
        if table:
            table_data = self.extract_table_data(table)
            for key, value in table_data.items():
                self._process_info_item(key, value, property_data)
    
    def _process_info_item(self, key: str, value: str, property_data: Dict[str, Any]) -> None:
        """
        情報アイテムを処理
        
        Args:
            key: キー
            value: 値
            property_data: データ格納先
        """
        if not value:
            return
        
        # 間取り
        if '間取' in key:
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
        
        # 築年月
        elif '築年月' in key:
            built_info = self.parse_built_date(value)
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
            if built_info['built_month']:
                property_data['built_month'] = built_info['built_month']
        
        # 住所・所在地
        elif '所在地' in key or '住所' in key:
            address = self.normalize_address(value)
            if address:
                property_data['address'] = address
        
        # 最寄駅
        elif '交通' in key or '最寄' in key or '駅' in key:
            station = self.parse_station_info(value)
            if station:
                property_data['station_info'] = station
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        
        # 価格を抽出（複数の方法を試行）
        self._extract_price(soup, property_data)
        
        # テーブルから情報を抽出
        self._extract_table_info(soup, property_data)
        
        # dl要素から情報を抽出
        self._extract_dl_info(soup, property_data)
        
        # 建物名を取得
        self._extract_building_name_from_detail(soup, property_data)
        
        # 物件画像
        self._extract_property_images(soup, property_data)
        
        # 物件備考
        self._extract_remarks(soup, property_data)
        
        # 不動産会社情報
        self._extract_agency_info(soup, property_data)
        
        # 日付情報
        self._extract_date_info(soup, property_data)
        
        return property_data

    def _extract_price(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> bool:
        """価格を抽出（複数の方法を試行）"""
        # 最も信頼できるJSON-LD構造化データから価格を取得
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # Product型のスキーマを探す
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    offers = data.get('offers', {})
                    if isinstance(offers, dict) and 'price' in offers:
                        # 円単位の価格を万円単位に変換
                        price_yen = int(offers['price'])
                        property_data['price'] = price_yen // 10000
                        return True
            except:
                pass
        
        # JSON-LDで見つからない場合は、テーブル内から価格を探す
        table_cells = soup.select('td.table-data.content')
        for cell in table_cells:
            cell_text = cell.get_text(strip=True)
            if '万円' in cell_text:
                price = self.parse_price(cell_text)
                if price and price > 100:  # 最低価格100万円
                    property_data['price'] = price
                    return True
        
        # それでも見つからない場合は、他の要素から探す
        for elem in soup.find_all(string=re.compile(r'[\d,]+\s*万円')):
            # 除外キーワードを含む場合はスキップ（管理費、修繕積立金など）
            exclude_keywords = ['管理費', '修繕', '積立', '敷金', '礼金', '仲介']
            if any(keyword in str(elem.parent.get_text()) for keyword in exclude_keywords):
                continue
            
            price = self.parse_price(str(elem))
            if price and price > 100:
                property_data['price'] = price
                return True
        
        return False
    
    def _extract_table_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """テーブルから情報を抽出"""
        tables = soup.select('table')
        for table in tables:
            rows = table.select('tr')
            for row in rows:
                cells = row.select('th, td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    self._process_table_field(label, value, property_data)
    
    def _process_table_field(self, label: str, value: str, property_data: Dict[str, Any]):
        """テーブルの1フィールドを処理"""
        # 階数情報
        if '階数' in label and '階建' in value:
            # 例: "36階 / 地上37階 地下1階建"
            floor_match = re.search(r'^(\d+)階', value)
            if floor_match:
                property_data['floor_number'] = int(floor_match.group(1))
            
            total_floors_match = re.search(r'地上(\d+)階', value)
            if total_floors_match:
                property_data['total_floors'] = int(total_floors_match.group(1))
        
        elif '所在階' in label:
            floor_match = re.search(r'(\d+)階', value)
            if floor_match:
                property_data['floor_number'] = int(floor_match.group(1))
        
        # 建物構造で総階数を抽出
        elif '構造' in label or '建物' in label:
            total_floors_match = re.search(r'地上(\d+)階', value)
            if total_floors_match and 'total_floors' not in property_data:
                property_data['total_floors'] = int(total_floors_match.group(1))
        
        # 専有面積
        elif '専有面積' in label or ('面積' in label and 'バルコニー' not in label):
            area = self.parse_area(value)
            if area:
                property_data['area'] = area
        
        # 間取り
        elif '間取り' in label:
            layout = self.normalize_layout(value)
            if layout:
                property_data['layout'] = layout
        
        # バルコニー面積
        elif 'バルコニー' in label and '面積' in label:
            balcony_area = self.parse_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 向き/主要採光面
        elif '向き' in label or '採光' in label or ('バルコニー' in label and '面積' not in label):
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
            management_fee = self.parse_management_info(value)
            if management_fee:
                property_data['management_fee'] = management_fee
        
        # 修繕積立金
        elif '修繕積立金' in label or '修繕積立費' in label:
            repair_fund = self.parse_management_info(value)
            if repair_fund:
                property_data['repair_fund'] = repair_fund
        
        # 総戸数
        elif '総戸数' in label or '総区画数' in label:
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                property_data['total_units'] = int(units_match.group(1))
        
        # 所在地/住所
        elif '所在地' in label or '住所' in label:
            # GoogleMapsなどの不要な文字を削除
            address = re.sub(r'GoogleMaps.*$', '', value).strip()
            address = self.normalize_address(address)
            if address:
                property_data['address'] = address
        
        # 交通/最寄り駅
        elif '交通' in label or '駅' in label:
            station_info = self.parse_station_info(value)
            if station_info:
                property_data['station_info'] = station_info
        
        # 取引態様
        elif '取引態様' in label:
            property_data['transaction_type'] = value
        
        # 現況
        elif '現況' in label:
            property_data['current_status'] = value
        
        # 引渡時期
        elif '引渡' in label:
            property_data['delivery_date'] = value
    
    def _extract_date_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """日付情報を抽出"""
        # 更新日や登録日などの情報を取得
        date_elements = soup.select('.update-date, .registration-date')
        for elem in date_elements:
            text = elem.get_text(strip=True)
            if '更新日' in text:
                property_data['last_updated'] = text
            elif '登録日' in text:
                property_data['registered_date'] = text
    
    def _extract_dl_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        dl要素から情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        dl_elements = self.safe_select(soup, "dl.detail-list")
        
        for dl in dl_elements:
            dt_elements = dl.find_all('dt')
            dd_elements = dl.find_all('dd')
            
            for dt, dd in zip(dt_elements, dd_elements):
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
                    self._process_detail_item(key, value, property_data)
    
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
            fee = self.parse_management_info(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in key:
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
            "h1.property-name",
            "h1.detail-title",
            "div.property-header h1",
            "h1"
        ]
        
        for selector in title_selectors:
            title = self.safe_select_one(soup, selector)
            if title:
                building_name = self.extract_text(title)
                if building_name:
                    # 部屋番号部分を除去
                    building_name = re.sub(r'\s*\d+号室.*$', '', building_name)
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
        main_img = self.safe_select_one(soup, "img.main-image, img#mainPhoto")
        if main_img and main_img.get('src'):
            img_url = self.normalize_url(main_img['src'], self.BASE_URL)
            if img_url:
                images.append(img_url)
        
        # サムネイル画像
        thumb_imgs = self.safe_select(soup, "div.thumbs img, ul.photo-list img")
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
            "div.property-comment",
            "div.agent-comment",
            "div.remarks",
            "section.comment"
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
        # 店舗情報を探す
        store_elem = self.safe_select_one(soup, "div.store-info, div.shop-info")
        if store_elem:
            store_text = store_elem.get_text(' ', strip=True)
            
            # 店舗名を抽出
            if '三井' in store_text or 'リハウス' in store_text:
                property_data['agency_name'] = '三井のリハウス'
            
            # 電話番号を抽出
            tel_match = re.search(r'(?:TEL|電話)[:：\s]*([0-9\-]+)', store_text)
            if tel_match:
                property_data['agency_tel'] = tel_match.group(1)
        else:
            # デフォルト値
            property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
            
            # 電話番号を個別に探す
            tel_elem = self.safe_select_one(soup, "span.tel, div.phone")
            if tel_elem:
                tel = self.extract_text(tel_elem)
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
        next_link = self.safe_select_one(soup, "a.next-page, a[rel='next'], li.next a")
        
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