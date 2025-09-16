"""
ノムコム専用HTMLパーサー

ノムコム（nomu.com）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag
from datetime import datetime

from .base_parser import BaseHtmlParser


class NomuParser(BaseHtmlParser):
    """ノムコム専用パーサー"""
    
    # ノムコムのデフォルト設定
    DEFAULT_AGENCY_NAME = "野村不動産アーバンネット"
    BASE_URL = "https://www.nomu.com"
    
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
        
        # ノムコムの物件カードを検索
        property_cards = self.safe_select(soup, "div.item_resultsmall")
        
        if not property_cards:
            self.logger.debug("物件カードが見つかりません")
            return properties
        
        for card in property_cards:
            try:
                property_data = self._parse_property_card(card)
                if property_data:
                    properties.append(property_data)
            except Exception as e:
                self.logger.error(f"物件カード解析エラー: {e}")
                continue
        
        return properties
    
    def _parse_property_card(self, card: Tag) -> Optional[Dict[str, Any]]:
        """
        物件カードから情報を抽出
        
        Args:
            card: 物件カード要素
            
        Returns:
            物件データ
        """
        property_data = {}
        
        # タイトル/建物名とURL
        title_elem = card.find("div", class_="item_title")
        if title_elem:
            link = title_elem.find("a")
            if link:
                building_name = link.get_text(strip=True)
                property_data['title'] = building_name
                property_data['building_name'] = building_name
                
                href = link.get('href')
                if href:
                    property_data['url'] = self.normalize_url(href, self.BASE_URL)
                    # URLから物件IDを抽出
                    site_id_match = re.search(r'/mansion/id/([^/]+)/', href)
                    if site_id_match:
                        property_data['site_property_id'] = site_id_match.group(1)
        
        # テーブルから情報を抽出
        table = card.find("table")
        if table:
            self._extract_card_table_info(table, property_data)
        
        # 仲介業者名（ノムコムは野村不動産アーバンネット）
        property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        
        # 必須フィールドの検証
        if self._validate_card_data(property_data):
            return property_data
        else:
            return None
    
    def _extract_card_table_info(self, table: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードのテーブルから情報を抽出
        
        Args:
            table: テーブル要素
            property_data: データ格納先
        """
        # 価格を抽出 (item_3)
        price_cell = table.find("td", class_="item_td item_3")
        if price_cell:
            price_elem = price_cell.find("p", class_="item_price")
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = self.parse_price(price_text)
                if price:
                    property_data['price'] = price
        
        # 面積・間取り・方角を抽出 (item_4)
        detail_cell = table.find("td", class_="item_td item_4")
        if detail_cell:
            p_tags = detail_cell.find_all("p")
            
            # 1番目のp: 面積
            if len(p_tags) > 0:
                area_text = p_tags[0].get_text(strip=True)
                area = self.parse_area(area_text)
                if area:
                    property_data['area'] = area
            
            # 2番目のp: 間取り
            if len(p_tags) > 1:
                layout = self.normalize_layout(p_tags[1].get_text(strip=True))
                if layout:
                    property_data['layout'] = layout
            
            # 3番目のp: 方角
            if len(p_tags) > 2:
                direction = self.normalize_direction(p_tags[2].get_text(strip=True))
                if direction:
                    property_data['direction'] = direction
        
        # 階数・築年情報を抽出 (item_5)
        floor_cell = table.find("td", class_="item_td item_5")
        if floor_cell:
            p_tags = floor_cell.find_all("p")
            
            # 1番目のp: 築年月
            if len(p_tags) > 0:
                built_text = p_tags[0].get_text(strip=True)
                built_info = self.parse_built_date(built_text)
                if built_info['built_year']:
                    property_data['built_year'] = built_info['built_year']
                if built_info['built_month']:
                    property_data['built_month'] = built_info['built_month']
            
            # 2番目のp: 階数情報（例: "39階 / 48階建"）
            if len(p_tags) > 1:
                floor_text = p_tags[1].get_text(strip=True)
                # 所在階を抽出
                floor_match = re.search(r'(\d+)階', floor_text)
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))
                # 総階数を抽出
                total_match = re.search(r'(\d+)階建', floor_text)
                if total_match:
                    property_data['total_floors'] = int(total_match.group(1))
        
        # 住所と駅情報を抽出 (item_2)
        location_cell = table.find("td", class_="item_td item_2")
        if location_cell:
            p_tags = location_cell.find_all("p")
            
            # 1番目のp: 住所
            if len(p_tags) > 0:
                address_text = p_tags[0].get_text(strip=True)
                address = self.normalize_address(address_text)
                if address:
                    property_data['address'] = address
            
            # 2番目以降のp: 駅情報
            station_parts = []
            for i in range(1, len(p_tags)):
                station_text = p_tags[i].get_text(strip=True)
                if station_text:
                    station_parts.append(station_text)
            
            if station_parts:
                station_info = ' / '.join(station_parts)
                property_data['station_info'] = station_info
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        
        # 建物名を取得
        self._extract_building_name(soup, property_data)
        
        # 価格を取得
        self._extract_detail_price(soup, property_data)
        
        # 住所と駅情報を取得
        self._extract_address_and_station(soup, property_data)
        
        # 物件詳細情報を取得（mansionテーブル）
        self._extract_mansion_table_info(soup, property_data)
        
        # 管理費と修繕積立金を取得
        self._extract_fees(soup, property_data)
        
        # 面積と間取りを優先的に取得（現在のページ構造対応）
        self._extract_area_and_layout_current_format(soup, property_data)
        
        # その他の詳細情報を取得
        self._extract_additional_details(soup, property_data)
        
        return property_data

    def _extract_building_name(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """建物名を抽出"""
        # まずclass="item_title"を探す
        h1_elem = soup.find("h1", {"class": "item_title"})
        if not h1_elem:
            # classがないh1タグも試す
            h1_elem = soup.find("h1")
        
        if h1_elem:
            # h1要素のコピーを作成（元のDOMを変更しないため）
            h1_copy = h1_elem.__copy__()
            
            # item_newクラスの要素を探して除外
            item_new_elem = h1_copy.find(class_='item_new')
            if item_new_elem:
                item_new_elem.extract()  # 価格情報を削除
            
            # 残ったテキストが建物名
            building_name = h1_copy.get_text(strip=True)
            if building_name:
                detail_data['building_name'] = building_name
    
    def _extract_detail_price(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """詳細ページから価格を取得"""
        # item_newクラスから価格を取得
        price_elem = soup.find(class_='item_new')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price = self.parse_price(price_text)
            if price:
                detail_data['price'] = price
    
    def _extract_address_and_station(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """住所と駅情報を取得"""
        # objectAddressクラスのテーブルから取得
        address_table = soup.find("table", class_="objectAddress")
        if address_table:
            # 住所行を探す
            rows = address_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    header = th.get_text(strip=True)
                    value = td.get_text(' ', strip=True)
                    
                    if "所在地" in header or "住所" in header:
                        detail_data['address'] = self.normalize_address(value)
                    elif "交通" in header or "最寄" in header:
                        detail_data['station_info'] = value
    
    def _extract_mansion_table_info(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """mansionテーブルから物件情報を取得"""
        mansion_table = soup.find("table", class_="mansion")
        if not mansion_table:
            return
        
        rows = mansion_table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            i = 0
            while i < len(cells) - 1:
                header = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                
                # 階数情報
                if "階数" in header or "所在階" in header:
                    floor_match = re.search(r'(\d+)階', value)
                    if floor_match:
                        detail_data['floor_number'] = int(floor_match.group(1))
                    # 総階数
                    total_match = re.search(r'(\d+)階建', value)
                    if total_match:
                        detail_data['total_floors'] = int(total_match.group(1))
                
                # 築年月
                elif "築年月" in header:
                    built_info = self.parse_built_date(value)
                    if built_info['built_year']:
                        detail_data['built_year'] = built_info['built_year']
                    if built_info['built_month']:
                        detail_data['built_month'] = built_info['built_month']
                
                # 専有面積
                elif "専有面積" in header or "面積" in header:
                    area = self.parse_area(value)
                    if area:
                        detail_data['area'] = area
                
                # 間取り
                elif "間取り" in header:
                    layout = self.normalize_layout(value)
                    if layout:
                        detail_data['layout'] = layout
                
                # バルコニー面積
                elif "バルコニー" in header:
                    balcony_area = self.parse_area(value)
                    if balcony_area:
                        detail_data['balcony_area'] = balcony_area
                
                # 方角
                elif "向き" in header or "方角" in header or "方位" in header:
                    direction = self.normalize_direction(value)
                    if direction:
                        detail_data['direction'] = direction
                
                i += 2
    
    def _extract_fees(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """管理費と修繕積立金を取得"""
        # mansionテーブルから取得
        mansion_table = soup.find("table", class_="mansion")
        if mansion_table:
            rows = mansion_table.find_all("tr")
            for row in rows:
                cells = row.find_all(["th", "td"])
                i = 0
                while i < len(cells) - 1:
                    header = cells[i].get_text(strip=True)
                    value = cells[i + 1].get_text(strip=True)
                    
                    # 管理費
                    if "管理費" in header:
                        mgmt_fee = self.parse_monthly_fee(value)
                        if mgmt_fee:
                            detail_data['management_fee'] = mgmt_fee
                    
                    # 修繕積立金
                    elif "修繕" in header:
                        repair_fee = self.parse_monthly_fee(value)
                        if repair_fee:
                            detail_data['repair_fund'] = repair_fee
                    
                    i += 2
    
    def _extract_area_and_layout_current_format(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """現在のページ構造から面積と間取りを取得（優先処理）"""
        # すでに取得済みの場合はスキップ
        if 'area' in detail_data and 'layout' in detail_data:
            return
        
        # メインの物件情報セクションを探す
        info_section = soup.find("div", class_="object_detail_info")
        if info_section:
            # dl要素から情報を取得
            dl_elements = info_section.find_all("dl")
            for dl in dl_elements:
                dt = dl.find("dt")
                dd = dl.find("dd")
                if dt and dd:
                    label = dt.get_text(strip=True)
                    value = dd.get_text(strip=True)
                    
                    if "専有面積" in label and 'area' not in detail_data:
                        area = self.parse_area(value)
                        if area:
                            detail_data['area'] = area
                    
                    elif "間取り" in label and 'layout' not in detail_data:
                        layout = self.normalize_layout(value)
                        if layout:
                            detail_data['layout'] = layout
    
    def _extract_additional_details(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """その他の詳細情報を取得"""
        # 備考欄の取得
        remarks_elem = soup.find("div", class_="remarks")
        if remarks_elem:
            remarks_text = remarks_elem.get_text(' ', strip=True)
            if remarks_text:
                detail_data['remarks'] = remarks_text[:500]  # 最大500文字
        
        # 不動産会社情報（ノムコムは固定）
        detail_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        detail_data['agency_tel'] = '0120-953-552'  # ノムコムのフリーダイヤル
    
    def _process_detail_table_data(self, table_data: Dict[str, str], property_data: Dict[str, Any]) -> None:
        """
        詳細テーブルデータを処理
        
        Args:
            table_data: テーブルから抽出したデータ
            property_data: データ格納先
        """
        for key, value in table_data.items():
            if not value:
                continue
            
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
            
            # 建物階数（総階数を先に判定）
            elif '階建' in key or '総階数' in key:
                total_floors = self.parse_floor(value)
                if total_floors:
                    property_data['total_floors'] = total_floors
            
            # 所在階
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
        title = self.safe_select_one(soup, "h1.objectName, h1.bukken_name")
        if title:
            building_name = self.extract_text(title)
            if building_name:
                property_data['building_name'] = building_name
    
    def _extract_property_images(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件画像URLを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        images = []
        
        # メイン画像
        main_img = self.safe_select_one(soup, "img.mainPhoto, img.main_image")
        if main_img and main_img.get('src'):
            img_url = self.normalize_url(main_img['src'], self.BASE_URL)
            if img_url:
                images.append(img_url)
        
        # サムネイル画像
        thumb_imgs = self.safe_select(soup, "div.thumbnails img, div.sub_images img")
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
        remarks_elem = self.safe_select_one(soup, "div.remarks, div.comment, div.pr_comment")
        if remarks_elem:
            remarks = self.extract_text(remarks_elem)
            if remarks:
                property_data['remarks'] = remarks
                # 最初の100文字を要約として使用
                property_data['summary_remarks'] = remarks[:100] + ('...' if len(remarks) > 100 else '')
    
    def _extract_agency_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        不動産会社情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # ノムコムは固定
        property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        
        # 電話番号を探す
        tel_elem = self.safe_select_one(soup, "span.tel, div.contact_tel")
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