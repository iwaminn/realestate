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
from ..data_normalizer import extract_monthly_fee


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
        
        # 仲介業者名はデフォルト値を設定しない（詳細ページで取得）
        
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
                price_text = self._build_price_text(price_elem)
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
                # 総階数を抽出（地下階も含む）
                basement_match = re.search(r'地下(\d+)階・?地上(\d+)階', floor_text)
                if basement_match:
                    # 地下X階・地上Y階の形式
                    property_data['basement_floors'] = int(basement_match.group(1))
                    property_data['total_floors'] = int(basement_match.group(2))
                else:
                    # 通常の階数表記
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

    def _build_price_text(self, price_elem: Tag) -> str:
        """
        価格要素から価格文字列を構築
        
        ノムコムの価格表示は複数のspan要素に分かれているため、
        それらを結合して価格文字列を作成
        
        Args:
            price_elem: 価格要素
            
        Returns:
            価格文字列
        """
        # span要素から価格を組み立てる
        spans = price_elem.find_all("span")
        price_parts = []
        
        for span in spans:
            span_text = span.get_text(strip=True)
            if span_text:
                class_list = span.get("class", [])
                class_str = " ".join(class_list) if isinstance(class_list, list) else str(class_list)
                
                # numクラスまたは数字を含む場合
                if "num" in class_str or re.search(r'\d', span_text):
                    price_parts.append(span_text)
                # unitクラスまたは単位を含む場合
                elif "unit" in class_str or "yen" in class_str or span_text in ["億", "万円", "万"]:
                    price_parts.append(span_text)
        
        if price_parts:
            price_text = "".join(price_parts)
        else:
            # span要素から組み立てられない場合は全体テキストを使用
            price_text = price_elem.get_text(strip=True)
        
        # 億で終わる場合は円を追加
        if price_text and price_text.endswith("億"):
            price_text += "円"
        # 万で終わる場合は円を追加
        elif price_text and price_text.endswith("万"):
            price_text += "円"
        
        return price_text
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        詳細ページを解析
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報の辞書、失敗時はNone
        """
        if not soup:
            return None
            
        property_data = {}
        
        try:
            # ノムコムの詳細ページの主要セクションを特定
            # 1. メインコンテンツエリア
            main_content = soup.find("div", {"id": "main"}) or soup.find("div", class_="main-content") or soup
            
            # 2. 物件概要セクション（価格・建物名など）
            property_header = main_content.find("div", class_=re.compile("property[-_]?header|summary")) or \
                            main_content.find("section", class_="summary") or \
                            main_content
            
            # 3. マンション詳細テーブル（mansion_table）
            mansion_table_section = main_content.find("div", class_=re.compile("mansion[-_]?table")) or \
                                   main_content.find("table", class_="mansion_table") or \
                                   main_content.find("div", {"id": "mansion_detail"})
            
            # 4. 物件詳細テーブル（detail_table、spec_table など）
            detail_table_section = main_content.find("div", class_=re.compile("detail[-_]?table|spec[-_]?table")) or \
                                 main_content.find("table", class_=re.compile("detail|spec")) or \
                                 main_content.find("div", {"id": re.compile("detail|spec")})
            
            # 5. 基本情報セクション（住所、駅情報など）
            basic_info_section = main_content.find("div", class_=re.compile("basic[-_]?info|location")) or \
                               main_content.find("section", class_="location") or \
                               property_header
            
            # 6. 費用情報セクション（管理費、修繕積立金など）
            cost_section = main_content.find("div", class_=re.compile("cost|fee|expense")) or \
                          detail_table_section or \
                          main_content
            
            # 各セクションから情報を抽出（範囲を限定して渡す）
            
            # 建物名を取得（ヘッダーセクションから）
            if property_header:
                self._extract_building_name(property_header, property_data)
            
            # 価格を取得（ヘッダーセクションから）
            if property_header:
                self._extract_detail_price(property_header, property_data)
            
            # 住所と駅情報を取得（基本情報セクションから）
            if basic_info_section:
                self._extract_address_and_station(basic_info_section, property_data)
            
            # マンション詳細テーブルから情報を取得
            if mansion_table_section:
                self._extract_mansion_table_info(mansion_table_section, property_data)
            
            # 管理費・修繕積立金を取得（費用セクションから）
            if cost_section:
                self._extract_fees(cost_section, property_data)
            
            # 面積と間取りを取得（詳細セクションから）
            if detail_table_section:
                self._extract_area_and_layout_current_format(detail_table_section, property_data)
                # 追加の詳細情報を取得（バルコニー面積など）
                self._extract_additional_details(detail_table_section, property_data)
                # 詳細テーブルデータを処理
                self._process_detail_table_data(detail_table_section, property_data)
            
            # 築年月の代替抽出（メインコンテンツ全体から、他で取得できなかった場合）
            if 'built_year' not in property_data and main_content:
                self._extract_built_year_from_various_sources(main_content, property_data)
            
            # リスト形式の情報を抽出（メインコンテンツから、追加のフォールバック）
            if main_content:
                self._extract_list_format_info(main_content, property_data)
            
            # デフォルトの不動産会社名
            if 'agency_name' not in property_data:
                property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
            
            return property_data
            
        except Exception as e:
            self.logger.error(f"[NomuParser] 詳細ページ解析エラー: {e}", exc_info=True)
            return None

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
                detail_data['title'] = building_name  # タイトルも設定
    
    def _extract_detail_price(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """詳細ページから価格を取得"""
        # p.item_priceから価格を取得（正しいセレクタ）
        price_elem = soup.select_one('p.item_price')
        if price_elem:
            # span要素を組み合わせて価格テキストを構築
            price_text = self._build_price_text(price_elem)
            price = self.parse_price(price_text)
            if price:
                detail_data['price'] = price
                self.logger.debug(f"価格取得成功: {price}万円 (raw: {price_text})")
    
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
                    # 総階数（地下階も含む）
                    total_match = re.search(r'地下(\d+)階・?地上(\d+)階', value)
                    if total_match:
                        # 地下X階・地上Y階の形式
                        detail_data['basement_floors'] = int(total_match.group(1))
                        detail_data['total_floors'] = int(total_match.group(2))
                    else:
                        # 地下階がない場合
                        total_match = re.search(r'(\d+)階建', value)
                        if total_match:
                            detail_data['total_floors'] = int(total_match.group(1))
                        # または基底クラスのメソッドを使用
                        basement = self.parse_basement_floors(value)
                        if basement:
                            detail_data['basement_floors'] = basement
                
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
    
    def _extract_fees(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        管理費と修繕積立金を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        for th in soup.find_all('th'):
            th_text = self.extract_text(th)
            
            # 管理費
            if th_text and '管理費' in th_text and 'management_fee' not in property_data:
                td = th.find_next_sibling('td')
                if td:
                    # parse_priceメソッドで月額費用も抽出可能
                    fee = self.parse_price(self.extract_text(td))
                    if fee:
                        property_data['management_fee'] = fee
            
            # 修繕積立金
            elif th_text and '修繕積立金' in th_text and 'repair_reserve_fund' not in property_data:
                td = th.find_next_sibling('td')
                if td:
                    # parse_priceメソッドで月額費用も抽出可能
                    fee = self.parse_price(self.extract_text(td))
                    if fee:
                        property_data['repair_reserve_fund'] = fee
    
    def _extract_area_and_layout_current_format(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        面積と間取りを現在のフォーマットから抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 専有面積
        for th in soup.find_all('th'):
            if '専有面積' in self.extract_text(th):
                td = th.find_next_sibling('td')
                if td:
                    area = self.parse_area(self.extract_text(td))
                    if area:
                        property_data['area'] = area
                break
        
        # 間取り
        for th in soup.find_all('th'):
            if '間取り' in self.extract_text(th):
                td = th.find_next_sibling('td')
                if td:
                    layout = self.normalize_layout(self.extract_text(td))
                    if layout:
                        property_data['layout'] = layout
                break
    
    def _extract_additional_details(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """その他の詳細情報を取得"""
        # 備考欄の取得
        remarks_elem = soup.find("div", class_="remarks")
        if remarks_elem:
            remarks_text = remarks_elem.get_text(' ', strip=True)
            if remarks_text:
                detail_data['remarks'] = remarks_text[:500]  # 最大500文字

    
    def _extract_built_year_from_various_sources(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        様々なソースから築年を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # パターン1: 「築年月」を含むテキスト
        for elem in soup.find_all(text=re.compile(r'築年月')):
            parent = elem.parent
            if parent and parent.name == 'th':
                td = parent.find_next_sibling('td')
                if td:
                    # 基底クラスのparse_built_dateメソッドを使用
                    built_info = self.parse_built_date(self.extract_text(td))
                    if built_info['built_year']:
                        property_data['built_year'] = built_info['built_year']
                        if built_info['built_month']:
                            property_data['built_month'] = built_info['built_month']
                        return
        
        # パターン2: 「築」を含むテキストを広く探索
        for elem in soup.find_all(text=re.compile(r'\d{4}年.*築')):
            # 基底クラスのparse_built_dateメソッドを使用
            built_info = self.parse_built_date(str(elem))
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
                return
    
    def _extract_list_format_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        リスト形式（dl/dt/dd）の情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # dl要素を探す
        for dl in soup.find_all('dl', class_=re.compile('detail|info|property')):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            
            for dt, dd in zip(dts, dds):
                if not dt or not dd:
                    continue
                    
                label = self.extract_text(dt)
                value = self.extract_text(dd)
                
                if not label or not value:
                    continue
                
                # 各項目を処理
                if '間取り' in label and 'layout' not in property_data:
                    layout = self.normalize_layout(value)
                    if layout:
                        property_data['layout'] = layout
                
                elif '専有面積' in label and 'area' not in property_data:
                    area = self.parse_area(value)
                    if area:
                        property_data['area'] = area
                
                elif 'バルコニー' in label and 'balcony_area' not in property_data:
                    # parse_areaメソッドを使用
                    balcony = self.parse_area(value)
                    if balcony:
                        property_data['balcony_area'] = balcony
                
                elif '階' in label and '階建' not in label:
                    if 'floor_number' not in property_data:
                        floor = self.parse_floor(value)
                        if floor:
                            property_data['floor_number'] = floor
                
                elif ('階建' in label or '総階数' in label) and 'total_floors' not in property_data:
                    # parse_floorメソッドを使用
                    total = self.parse_floor(value)
                    if total:
                        property_data['total_floors'] = total
                
                elif '築年' in label and 'built_year' not in property_data:
                    # parse_built_dateメソッドを使用
                    built_info = self.parse_built_date(value)
                    if built_info['built_year']:
                        property_data['built_year'] = built_info['built_year']
                
                elif '構造' in label and 'structure' not in property_data:
                    # 構造はそのまま保存
                    structure = value.strip()
                    if structure:
                        property_data['structure'] = structure
                
                elif '向き' in label and 'direction' not in property_data:
                    direction = self.normalize_direction(value)
                    if direction:
                        property_data['direction'] = direction
                
                elif '管理費' in label and 'management_fee' not in property_data:
                    fee = self.parse_price(value)
                    if fee:
                        property_data['management_fee'] = fee
                
                elif '修繕' in label and 'repair_reserve_fee' not in property_data:
                    fee = self.parse_price(value)
                    if fee:
                        property_data['repair_reserve_fee'] = fee
                
                elif '総戸数' in label and 'total_units' not in property_data:
                    units = self.parse_total_units(value)
                    if units:
                        property_data['total_units'] = units
        
        # 不動産会社情報はデフォルト値を設定しない（ページから取得）
    
    def _process_detail_table_data(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細ページのテーブルデータを処理
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # テーブルからデータを抽出（最初のテーブルを探す）
        table = soup.find("table")
        if table:
            table_data = self.extract_table_data(table)
        else:
            table_data = None
        
        if not table_data:
            return
            
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
            elif '階建' in key or '総階数' in key or '建物階数' in key:
                # 地下階があるかチェック
                basement_match = re.search(r'地下(\d+)階・?地上(\d+)階', value)
                if basement_match:
                    # 地下X階・地上Y階の形式
                    property_data['basement_floors'] = int(basement_match.group(1))
                    property_data['total_floors'] = int(basement_match.group(2))
                else:
                    # 地下階がない場合
                    total_floors = self.parse_floor(value)
                    if total_floors:
                        property_data['total_floors'] = total_floors
                    # 地下階を別途チェック
                    basement = self.parse_basement_floors(value)
                    if basement:
                        property_data['basement_floors'] = basement
            
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
                from ..data_normalizer import extract_monthly_fee
                fee = extract_monthly_fee(value)
                if fee:
                    property_data['management_fee'] = fee
            
            # 修繕積立金
            elif '修繕積立' in key:
                from ..data_normalizer import extract_monthly_fee
                fund = extract_monthly_fee(value)
                if fund:
                    property_data['repair_fund'] = fund
            
            # 部屋番号
            elif '部屋番号' in key or '号室' in key:
                room = value.strip()
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