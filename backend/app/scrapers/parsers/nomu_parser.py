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
                
                # 所在階を抽出（基底クラスのメソッドを使用）
                floor_number = self.parse_floor(floor_text)
                if floor_number:
                    property_data['floor_number'] = floor_number
                
                # 総階数を抽出
                # "48階建"のような部分から総階数を抽出
                if '階建' in floor_text:
                    # スラッシュの後の部分を取得
                    parts = floor_text.split('/')
                    if len(parts) > 1:
                        total_text = parts[1].strip()
                    else:
                        total_text = floor_text
                    
                    # 総階数を基底クラスのメソッドで取得
                    total_floors = self.parse_total_floors(total_text)
                    if total_floors:
                        property_data['total_floors'] = total_floors
                
                # 地下階の処理（基底クラスのメソッドを使用）
                basement = self.parse_basement_floors(floor_text)
                if basement:
                    property_data['basement_floors'] = basement
        
        # 住所を抽出 (item_2) - 駅情報は詳細ページで取得するため一覧では不要
        location_cell = table.find("td", class_="item_td item_2")
        if location_cell:
            p_tags = location_cell.find_all("p")
            
            # 1番目のp: 住所のみ取得
            if len(p_tags) > 0:
                address_text = p_tags[0].get_text(strip=True)
                address = self.normalize_address(address_text)
                if address:
                    property_data['address'] = address

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
            # まず、propertyDetails要素を取得（物件属性情報はここに含まれる）
            property_details = soup.find(id="propertyDetails")
            if not property_details:
                # propertyDetails要素がない場合は、メインコンテンツ全体を使用
                self.logger.info("[NomuParser] propertyDetails要素が見つからないため、メインコンテンツ全体を使用")
                property_details = soup.find(id="main") or soup
            
            # 新しいHTML構造（item_table）の処理
            # 複数のitem_tableがある場合、それぞれを処理
            item_tables = soup.find_all("table", class_="item_table")
            if item_tables:
                self.logger.debug(f"[NomuParser] {len(item_tables)}個のitem_tableを検出")
                for table in item_tables:
                    self._process_item_table(table, property_data)
            
            # item_status形式の要素も処理（階数情報などが含まれる）
            # item_tableの後に処理することで、より正確な値で上書きする
            self._extract_item_status_info(soup, property_data)
            
            # item_tableが存在する場合はここでreturn
            if item_tables:
                
                # 建物名と価格を取得（ページ全体のヘッダーから - propertyDetails外の可能性がある）
                self._extract_building_name(soup, property_data)
                self._extract_detail_price(soup, property_data)
                
                # デフォルトの不動産会社名
                if 'agency_name' not in property_data:
                    property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
                
                return property_data
            
            # 従来のHTML構造の処理（tableBoxを使用）
            # ノムコムの詳細ページの主要セクションを特定（propertyDetails内で検索）
            
            # 1. 価格・建物名などの基本情報セクション
            # propertyDetails内またはページ全体から探す（建物名はヘッダーにある場合もある）
            property_info_section = property_details.find("div", class_="propertyInfo")
            if not property_info_section:
                # フォールバック: propertyDetails全体を使用
                property_info_section = property_details
            
            # 2. 詳細情報テーブル（#propertyDetails .tableBox table）
            # 管理費、修繕積立金、間取り、面積などが含まれる
            main_detail_table = None
            # tableBox内のテーブルを探す（より具体的なセレクタ）
            table_box = property_details.find("div", class_="tableBox")
            if table_box:
                main_detail_table = table_box.find("table")
            
            if not main_detail_table:
                # 新しいHTML構造（item_table）では別の場所で処理されるため、デバッグログに変更
                self.logger.debug("[NomuParser] tableBoxテーブルが見つかりません - 新しいHTML構造の可能性があります")
            
            # 3. 住所・交通情報テーブル
            # objectAddressクラスまたは所在地を含むテーブル
            address_table = property_details.find("table", class_="objectAddress")
            if not address_table:
                # tableBox内のcol4テーブルを使用（既に取得済みのmain_detail_tableを使用）
                # 通常、1つのcol4テーブルに全情報が含まれている
                address_table = main_detail_table

            
            # 4. マンション全体の情報（総階数、総戸数など）
            # mansionクラスのテーブルまたは建物階数を含むテーブル
            mansion_info_table = property_details.find("table", class_="mansion")
            if not mansion_info_table:
                for table in property_details.find_all("table"):
                    if table.find("th", string=re.compile("建物階数|総戸数")):
                        mansion_info_table = table
                        break
            
            # 各セクションから情報を抽出（範囲を限定して渡す）
            
            # 建物名を取得（ページ全体のヘッダーから - propertyDetails外の可能性がある）
            self._extract_building_name(soup, property_data)
            
            # 価格を取得（ページ全体から価格要素を探す）
            self._extract_detail_price(soup, property_data)
            
            # 住所と駅情報を取得（住所テーブルから）
            if address_table:
                self._extract_address_and_station(address_table, property_data)
            
            # マンション詳細テーブルから情報を取得（総階数、総戸数など）
            if mansion_info_table:
                self._extract_mansion_table_info(mansion_info_table, property_data)
            
            # 管理費・修繕積立金を取得（詳細テーブルから）
            if main_detail_table:
                self._extract_fees(main_detail_table, property_data)
            
            # 詳細テーブルデータを統合的に処理（面積、間取り、バルコニー面積など）
            if main_detail_table:
                self._process_detail_table_data(main_detail_table, property_data)
            
            # リスト形式の情報を抽出（propertyDetails内から）
            if property_details:
                self._extract_list_format_info(property_details, property_data)
            
            # デフォルトの不動産会社名
            if 'agency_name' not in property_data:
                property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
            
            return property_data
            
        except Exception as e:
            self.logger.error(f"[NomuParser] 詳細ページ解析エラー: {e}", exc_info=True)
            return None


    def _extract_item_status_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        item_status形式の要素から情報を抽出
        新しいHTML構造で使用される形式
        
        Args:
            soup: ページ全体のBeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # item_status形式の要素を取得
        status_items = soup.find_all('li', class_='item_status')
        
        for item in status_items:
            title_elem = item.find('span', class_='item_status_title')
            content_elem = item.find('span', class_='item_status_content')
            
            if not title_elem or not content_elem:
                continue
            
            title = self.extract_text(title_elem)
            content = self.extract_text(content_elem)
            
            if not title or not content:
                continue
            
            # 各項目を処理
            if '所在階' in title:
                # 「22階 / 42階建」のような形式から階数を抽出
                floor = self.parse_floor(content)
                if floor:
                    # デバッグログ
                    if 'floor_number' in property_data:
                        self.logger.debug(f"[NomuParser] floor_numberを更新: {property_data['floor_number']}階 → {floor}階")
                    property_data['floor_number'] = floor
                
                # 総階数も抽出
                if '階建' in content:
                    total_floors = self.parse_total_floors(content)
                    if total_floors:
                        if 'total_floors' in property_data:
                            self.logger.debug(f"[NomuParser] total_floorsを更新: {property_data['total_floors']}階 → {total_floors}階")
                        property_data['total_floors'] = total_floors
            
            elif '間取' in title and 'layout' not in property_data:
                layout = self.normalize_layout(content)
                if layout:
                    property_data['layout'] = layout
            
            elif '専有面積' in title and 'area' not in property_data:
                area = self.parse_area(content)
                if area:
                    property_data['area'] = area
            
            elif '所在地' in title and 'address' not in property_data:
                # リンクがある場合は特別な処理
                link = content_elem.find('a')
                if link:
                    # リンクテキスト（東京都港区など）を取得
                    address_parts = []
                    link_text = link.get_text(strip=True)
                    if link_text:
                        address_parts.append(link_text)
                    # リンクを削除して残りのテキストを取得
                    link.extract()
                    remaining_text = content_elem.get_text(strip=True)
                    if remaining_text:
                        address_parts.append(remaining_text)
                    if address_parts:
                        full_address = ''.join(address_parts)
                        property_data['address'] = self.normalize_address(full_address)
                else:
                    address = self.normalize_address(content)
                    if address:
                        property_data['address'] = address
            
            elif '交通' in title and 'station_info' not in property_data:
                property_data['station_info'] = content
            
            elif '築年月' in title and 'built_year' not in property_data:
                built_info = self.parse_built_date(content)
                if built_info['built_year']:
                    property_data['built_year'] = built_info['built_year']
                if built_info['built_month'] and 'built_month' not in property_data:
                    property_data['built_month'] = built_info['built_month']
            
            elif 'バルコニー' in title and 'balcony_area' not in property_data:
                balcony_area = self.parse_area(content)
                if balcony_area:
                    property_data['balcony_area'] = balcony_area
            
            elif '向き' in title and 'direction' not in property_data:
                direction = self.normalize_direction(content)
                if direction:
                    property_data['direction'] = direction
            
            elif '管理費' in title and 'management_fee' not in property_data:
                fee = self.parse_price(content)
                if fee:
                    property_data['management_fee'] = fee
            
            elif '修繕積立' in title and 'repair_fund' not in property_data:
                fund = self.parse_price(content)
                if fund:
                    property_data['repair_fund'] = fund
            
            elif '総戸数' in title and 'total_units' not in property_data:
                units = self.parse_total_units(content)
                if units:
                    property_data['total_units'] = units

    def _extract_building_name(self, element: BeautifulSoup, detail_data: Dict[str, Any]):
        """建物名を抽出"""
        # .propertyMain h1から建物名を取得（明確なセレクタのみ使用）
        h1_elem = element.select_one(".propertyMain h1")
        
        if not h1_elem:
            # フォールバックとして明確なクラス指定のh1.item_titleを探す
            h1_elem = element.find("h1", {"class": "item_title"})
        
        if h1_elem:
            # h1要素のコピーを作成（元のDOMを変更しないため）
            h1_copy = h1_elem.__copy__()
            
            # item_newクラスの要素を探して除外（価格情報などを除外）
            item_new_elem = h1_copy.find(class_='item_new')
            if item_new_elem:
                item_new_elem.extract()
            
            # 残ったテキストが建物名
            building_name = h1_copy.get_text(strip=True)
            if building_name:
                detail_data['building_name'] = building_name
                detail_data['title'] = building_name  # タイトルも設定
        else:
            # 建物名が取得できない場合はエラーログを出力
            self.logger.error("[NomuParser] 建物名を取得できませんでした - HTML構造が変更された可能性があります")  # タイトルも設定  # タイトルも設定
    
    def _extract_detail_price(self, element: BeautifulSoup, detail_data: Dict[str, Any]):
        """詳細ページから価格を取得"""
        price_text = None
        
        # まず.detailInfo .priceTxtから価格を取得
        price_elem = element.select_one('.detailInfo .priceTxt')
        
        if price_elem:
            # .detailInfo .priceTxtが見つかった場合、そのテキストを使用
            price_text = price_elem.get_text(strip=True)
        else:
            # 見つからない場合は#propertyDetails内を探す
            property_details = element.find(id="propertyDetails")
            if property_details:
                # propertyDetails内で「価格」というthタグを探す
                price_th = None
                for th in property_details.find_all('th'):
                    th_text = th.get_text(strip=True)
                    if th_text and th_text.startswith('価格'):
                        price_th = th
                        break
                
                if price_th:
                    # 「価格」thタグの次のtd要素を探す
                    td = price_th.find_next_sibling('td')
                    if td:
                        # td内のp要素のテキストを取得
                        p_elem = td.find('p')
                        if p_elem:
                            price_text = p_elem.get_text(strip=True)
                        else:
                            # p要素がない場合はtdのテキストを直接取得
                            price_text = td.get_text(strip=True)
        
        # 価格をパース
        if price_text:
            price = self.parse_price(price_text)
            if price:
                detail_data['price'] = price
                self.logger.debug(f"価格取得成功: {price}万円 (raw: {price_text})")
        else:
            # 価格が取得できない場合はデバッグログを出力（一覧ページから既に取得済みの可能性）
            self.logger.debug("[NomuParser] 詳細ページから価格を取得できませんでした - 一覧ページの価格を使用")
    
    def _extract_address_and_station(self, element: BeautifulSoup, detail_data: Dict[str, Any]):
        """住所と駅情報を取得"""
        # elementがテーブルの場合はそのまま使用
        if element.name == 'table':
            address_table = element
        else:
            # objectAddressクラスのテーブルから取得
            address_table = element.find("table", class_="objectAddress")
            if not address_table:
                address_table = element.find("table")
        
        if address_table:
            # 住所行を探す
            rows = address_table.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    header = th.get_text(strip=True)
                    
                    if "所在地" in header or "住所" in header:
                        # Nomuの場合、住所がリンクと通常テキストに分かれている
                        # 例: <a>東京都港区</a> 高輪2丁目
                        address_parts = []
                        
                        # リンク部分を取得（都道府県＋市区町村）
                        link = td.find('a')
                        if link:
                            # リンクのテキストを取得（東京都港区など）
                            prefecture_city = link.get_text(strip=True)
                            if prefecture_city:
                                address_parts.append(prefecture_city)
                            # リンクを削除して残りのテキストを取得
                            link.extract()
                        
                        # 残りのテキスト（町名・番地など）を取得
                        remaining_text = td.get_text(strip=True)
                        if remaining_text:
                            # 「周辺地図を見る」などの不要なテキストを除去
                            remaining_text = remaining_text.replace('周辺地図を見る', '').strip()
                            if remaining_text:
                                address_parts.append(remaining_text)
                        
                        # 住所を結合
                        if address_parts:
                            full_address = ''.join(address_parts)
                            detail_data['address'] = self.normalize_address(full_address)
                    
                    elif "交通" in header or "最寄" in header:
                        value = td.get_text(' ', strip=True)
                        detail_data['station_info'] = value
    
    def _extract_mansion_table_info(self, element: BeautifulSoup, detail_data: Dict[str, Any]):
        """mansionテーブルから建物全体の情報を取得（個別物件情報は扱わない）"""
        # elementがテーブルの場合はそのまま使用、それ以外の場合は内部のテーブルを探す
        if element.name == 'table':
            mansion_table = element
        else:
            mansion_table = element.find("table", class_="mansion")
            if not mansion_table:
                # mansion以外のテーブルでも処理を試みる
                mansion_table = element.find("table")
        
        if not mansion_table:
            return
        
        rows = mansion_table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            i = 0
            while i < len(cells) - 1:
                header = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)
                
                # 建物全体の総階数情報のみ（個別の所在階は扱わない）
                if "建物階数" in header or "地上" in header:
                    # 総階数（地下階も含む）
                    total_match = re.search(r'地下(\d+)階・?地上(\d+)階', value)
                    if total_match:
                        # 地下X階・地上Y階の形式
                        if 'basement_floors' not in detail_data:
                            detail_data['basement_floors'] = int(total_match.group(1))
                        if 'total_floors' not in detail_data:
                            detail_data['total_floors'] = int(total_match.group(2))
                    else:
                        # 地下階がない場合
                        total_match = re.search(r'(\d+)階建', value)
                        if total_match and 'total_floors' not in detail_data:
                            detail_data['total_floors'] = int(total_match.group(1))
                        # または基底クラスのメソッドを使用
                        if 'basement_floors' not in detail_data:
                            basement = self.parse_basement_floors(value)
                            if basement:
                                detail_data['basement_floors'] = basement
                
                # 築年月（建物全体の情報）
                elif "築年月" in header and 'built_year' not in detail_data:
                    built_info = self.parse_built_date(value)
                    if built_info['built_year']:
                        detail_data['built_year'] = built_info['built_year']
                    if built_info['built_month'] and 'built_month' not in detail_data:
                        detail_data['built_month'] = built_info['built_month']
                
                # 総戸数（建物全体の情報）
                elif "総戸数" in header and 'total_units' not in detail_data:
                    units = self.parse_total_units(value)
                    if units:
                        detail_data['total_units'] = units
                
                i += 2

    
    def _extract_fees(self, element: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        管理費と修繕積立金を抽出
        
        Args:
            element: 検索対象のBeautifulSoup要素（特定セクション）
            property_data: データ格納先
        """
        # 渡された要素内の<tr>タグを探索（全体検索ではなくセクション内のみ）
        for tr in element.find_all('tr'):
            # 管理費と修繕積立金が同じ行にあるパターンに対応
            ths = tr.find_all('th')
            tds = tr.find_all('td')
            
            for i, th in enumerate(ths):
                th_text = self.extract_text(th)
                if not th_text:  # Noneチェックを追加
                    continue
                
                # 管理費
                if '管理費' in th_text and 'management_fee' not in property_data:
                    # 同じ行に2つのth/tdがある場合
                    if len(ths) == 2 and len(tds) == 2:
                        # 最初のthが管理費の場合、最初のtdを取得
                        if i == 0:
                            fee = self.parse_monthly_fee(self.extract_text(tds[0]))
                            if fee:
                                property_data['management_fee'] = fee
                        # 2番目のthが管理費の場合、2番目のtdを取得
                        elif i == 1:
                            fee = self.parse_monthly_fee(self.extract_text(tds[1]))
                            if fee:
                                property_data['management_fee'] = fee
                    else:
                        # 通常のパターン
                        td = th.find_next_sibling('td')
                        if td:
                            fee = self.parse_monthly_fee(self.extract_text(td))
                            if fee:
                                property_data['management_fee'] = fee
                
                # 修繕積立金
                elif '修繕積立金' in th_text and 'repair_fund' not in property_data:
                    # 同じ行に2つのth/tdがある場合
                    if len(ths) == 2 and len(tds) == 2:
                        # 最初のthが修繕積立金の場合、最初のtdを取得
                        if i == 0:
                            fee = self.parse_monthly_fee(self.extract_text(tds[0]))
                            if fee:
                                property_data['repair_fund'] = fee
                        # 2番目のthが修繕積立金の場合、2番目のtdを取得
                        elif i == 1:
                            fee = self.parse_monthly_fee(self.extract_text(tds[1]))
                            if fee:
                                property_data['repair_fund'] = fee
                    else:
                        # 通常のパターン
                        td = th.find_next_sibling('td')
                        if td:
                            fee = self.parse_monthly_fee(self.extract_text(td))
                            if fee:
                                property_data['repair_fund'] = fee
    
    def _extract_area_and_layout_current_format(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        面積と間取りを現在のフォーマットから抽出（既存値がない場合のみ）
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 専有面積（既に値がある場合はスキップ）
        if 'area' not in property_data:
            for th in soup.find_all('th'):
                if '専有面積' in self.extract_text(th):
                    td = th.find_next_sibling('td')
                    if td:
                        area = self.parse_area(self.extract_text(td))
                        if area:
                            property_data['area'] = area
                    break
        
        # 間取り（既に値がある場合はスキップ）
        if 'layout' not in property_data:
            for th in soup.find_all('th'):
                if '間取り' in self.extract_text(th):
                    td = th.find_next_sibling('td')
                    if td:
                        layout = self.normalize_layout(self.extract_text(td))
                        if layout:
                            property_data['layout'] = layout
                    break
    


    
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
    
    def _extract_list_format_info(self, element: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        リスト形式（dl/dt/dd）の情報を抽出
        
        Args:
            element: 検索対象のBeautifulSoup要素（特定セクション）
            property_data: データ格納先
        """
        # 渡された要素内のdl要素を探す（全体検索ではなくセクション内のみ）
        for dl in element.find_all('dl', class_=re.compile('detail|info|property')):
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
                    # parse_total_floorsメソッドを使用
                    total = self.parse_total_floors(value)
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
        
        # div class="heading"パターンの情報も抽出（ノムコムの新しいHTML構造対応）
        heading_divs = element.find_all('div', class_='heading')
        for heading in heading_divs:
            if not heading:
                continue
                
            label = self.extract_text(heading)
            if not label:
                continue
                
            # headingの親要素からpタグを探す
            parent = heading.parent
            if not parent:
                continue
                
            p_tag = parent.find('p')
            if not p_tag:
                continue
                
            value = self.extract_text(p_tag)
            if not value:
                continue
            
            # 総戸数を処理
            if '総戸数' in label and 'total_units' not in property_data:
                units = self.parse_total_units(value)
                if units:
                    property_data['total_units'] = units
        
        # 不動産会社情報はデフォルト値を設定しない（ページから取得）
    
    def _process_detail_table_data(self, element: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細ページのテーブルデータを処理
        
        Args:
            element: BeautifulSoupオブジェクト（テーブル要素またはコンテナ要素）
            property_data: データ格納先
        """
        # elementが直接tableの場合
        if element.name == 'table':
            # テーブルのクラスに応じて処理を分岐
            classes = element.get('class', [])
            if 'item_table' in classes:
                # 新しいHTML構造のテーブル
                self._process_item_table(element, property_data)
            else:
                # tableBox内のテーブル（従来の構造）
                self._process_property_detail_table(element, property_data)
        else:
            # elementがコンテナの場合、テーブルの種類を判定
            
            # 1. tableBox内のテーブルを探す（従来の構造）
            table_box = element.find("div", class_="tableBox")
            if table_box:
                tables = table_box.find_all("table")
                for table in tables:
                    self._process_property_detail_table(table, property_data)
                return
            
            # 2. item_tableクラスのテーブルを探す（新しい構造）
            item_tables = element.find_all("table", class_="item_table")
            if item_tables:
                for table in item_tables:
                    self._process_item_table(table, property_data)
                return
    
    def _process_property_detail_table(self, table: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件詳細テーブル（.tableBox内のテーブル）を処理
        
        Args:
            table: テーブル要素
            property_data: データ格納先
        """
        for row in table.find_all('tr'):
            # 各行には複数のth/tdペアが存在する可能性がある
            ths = row.find_all('th')
            tds = row.find_all('td')
            
            # th/tdペアを処理
            for th, td in zip(ths, tds):
                if not th or not td:
                    continue
                
                # thのテキストを取得（最初の20文字で判定）
                key_text = th.get_text(strip=True)
                key = key_text[:20] if len(key_text) > 20 else key_text
                value = td.get_text(strip=True)
                
                if not value:
                    continue
                
                # 価格はextract_detail_priceメソッドで処理するため、ここでは扱わない
                if '価格' in key:
                    continue
                
                # 間取り
                if '間取' in key and 'layout' not in property_data:
                    layout = self.normalize_layout(value)
                    if layout:
                        property_data['layout'] = layout
                
                # 専有面積
                elif '専有面積' in key and 'area' not in property_data:
                    area = self.parse_area(value)
                    if area:
                        property_data['area'] = area
                
                # バルコニー面積
                elif 'バルコニー' in key and 'balcony_area' not in property_data:
                    balcony_area = self.parse_area(value)
                    if balcony_area:
                        property_data['balcony_area'] = balcony_area
                
                # 構造（総階数）
                # 注：構造フィールドからの総階数抽出は無効化
                # 「RC造20階」のような表記は構造部分の階数であり、建物全体の総階数ではない可能性があるため
                # elif '構造' in key and 'total_floors' not in property_data:
                #     # RC造14階地下2階建て のような形式
                #     total_floors = self.parse_total_floors(value)
                #     if total_floors:
                #         property_data['total_floors'] = total_floors
                # 地下階も構造フィールドからは取得しない
                # if 'basement_floors' not in property_data:
                #     basement = self.parse_basement_floors(value)
                #     if basement:
                #         property_data['basement_floors'] = basement
                
                # 所在階
                elif '所在階' in key and 'floor_number' not in property_data:
                    floor = self.parse_floor(value)
                    if floor:
                        property_data['floor_number'] = floor
                
                # 向き（方角）
                elif '向き' in key and 'direction' not in property_data:
                    direction = self.normalize_direction(value)
                    if direction:
                        property_data['direction'] = direction
                
                # 築年月
                elif '築年月' in key and 'built_year' not in property_data:
                    built_info = self.parse_built_date(value)
                    if built_info['built_year']:
                        property_data['built_year'] = built_info['built_year']
                    if built_info['built_month'] and 'built_month' not in property_data:
                        property_data['built_month'] = built_info['built_month']
                
                # 所在地
                elif '所在地' in key and 'address' not in property_data:
                    address = self.normalize_address(value)
                    if address:
                        property_data['address'] = address
                
                # 交通
                elif '交通' in key and 'station_info' not in property_data:
                    station = self.parse_station_info(value)
                    if station:
                        property_data['station_info'] = station
                
                # 管理費
                elif '管理費' in key and 'management_fee' not in property_data:
                    from ..data_normalizer import extract_monthly_fee
                    fee = extract_monthly_fee(value)
                    if fee:
                        property_data['management_fee'] = fee
                
                # 修繕積立金
                elif '修繕積立' in key and 'repair_fund' not in property_data:
                    from ..data_normalizer import extract_monthly_fee
                    fund = extract_monthly_fee(value)
                    if fund:
                        property_data['repair_fund'] = fund
                
                # 総戸数
                elif '総戸数' in key and 'total_units' not in property_data:
                    units = self.parse_total_units(value)
                    if units:
                        property_data['total_units'] = units

    def _process_item_table(self, table: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        新しいHTML構造のitem_tableクラスのテーブルを処理
        
        Args:
            table: テーブル要素（class="item_table"）
            property_data: データ格納先
        """
        # item_tableは通常の2カラムテーブル（th/td）構造
        for row in table.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            
            if not th or not td:
                continue
                
            key = self.extract_text(th)
            value = self.extract_text(td)
            
            if not key or not value:
                continue
            
            # 各項目を処理
            if '価格' in key and 'price' not in property_data:
                price = self.parse_price(value)
                if price:
                    property_data['price'] = price
            
            elif '間取' in key and 'layout' not in property_data:
                layout = self.normalize_layout(value)
                if layout:
                    property_data['layout'] = layout
            
            elif '専有面積' in key and 'area' not in property_data:
                area = self.parse_area(value)
                if area:
                    property_data['area'] = area
            
            elif 'バルコニー' in key and 'balcony_area' not in property_data:
                balcony_area = self.parse_area(value)
                if balcony_area:
                    property_data['balcony_area'] = balcony_area
            
            elif ('位置' in key or '所在階' in key) and 'floor_number' not in property_data:
                # 「22階 / 47階建」のような形式から所在階を抽出
                floor = self.parse_floor(value)
                if floor:
                    property_data['floor_number'] = floor
                # 総階数も抽出
                if '階建' in value and 'total_floors' not in property_data:
                    total_floors = self.parse_total_floors(value)
                    if total_floors:
                        property_data['total_floors'] = total_floors
            
            elif '構造' in key:
                # 構造情報は保存するが、総階数は抽出しない（誤った値の可能性があるため）
                if 'structure' not in property_data:
                    property_data['structure'] = value
            
            elif '向き' in key and 'direction' not in property_data:
                direction = self.normalize_direction(value)
                if direction:
                    property_data['direction'] = direction
            
            elif '築年月' in key and 'built_year' not in property_data:
                built_info = self.parse_built_date(value)
                if built_info['built_year']:
                    property_data['built_year'] = built_info['built_year']
                if built_info['built_month'] and 'built_month' not in property_data:
                    property_data['built_month'] = built_info['built_month']
            
            elif '所在地' in key and 'address' not in property_data:
                address = self.normalize_address(value)
                if address:
                    property_data['address'] = address
            
            elif '交通' in key and 'station_info' not in property_data:
                station = self.parse_station_info(value)
                if station:
                    property_data['station_info'] = station
            
            elif '管理費' in key and 'management_fee' not in property_data:
                from ..data_normalizer import extract_monthly_fee
                fee = extract_monthly_fee(value)
                if fee:
                    property_data['management_fee'] = fee
            
            elif '修繕積立' in key and 'repair_fund' not in property_data:
                from ..data_normalizer import extract_monthly_fee
                fund = extract_monthly_fee(value)
                if fund:
                    property_data['repair_fund'] = fund
            
            elif '総戸数' in key and 'total_units' not in property_data:
                units = self.parse_total_units(value)
                if units:
                    property_data['total_units'] = units
            
            elif '建物階数' in key and 'total_floors' not in property_data:
                # 「47階建」のような形式から総階数を抽出
                total_floors = self.parse_total_floors(value)
                if total_floors:
                    property_data['total_floors'] = total_floors
                # 地下階もチェック
                if 'basement_floors' not in property_data:
                    basement = self.parse_basement_floors(value)
                    if basement:
                        property_data['basement_floors'] = basement
    
        
            # その他のフィールドも同様に処理...

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