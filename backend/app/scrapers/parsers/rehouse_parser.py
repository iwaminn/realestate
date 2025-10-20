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
from ..data_normalizer import extract_monthly_fee


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
        
        # 仲介業者名はデフォルト値を設定しない（詳細ページで取得）
        
        # 必須フィールドの検証
        if self._validate_card_data(property_data):
            return property_data
        else:
            return None

    def _extract_description_info(self, desc_section: Tag, property_data: Dict[str, Any]):
        """description-sectionから情報を抽出（一覧ページ用）"""
        desc_text = desc_section.get_text(' ', strip=True)

        # 住所のみ抽出（詳細ページでも取得するが、一覧での識別用）
        # 都道府県が含まれている完全な住所、または区・市から始まる住所を探す
        address_patterns = [
            r'((?:東京都|北海道|(?:京都|大阪)府|[^\s]{2,3}県)[^\s]+)',  # 都道府県を含む
            r'([^\s]*[市区町村][^\s/]+)'  # 市区町村から始まる
        ]

        for pattern in address_patterns:
            addr_match = re.search(pattern, desc_text)
            if addr_match:
                # 基底クラスのnormalize_addressメソッドを使用（GoogleMaps等の不要な文字列も除去）
                address = self.normalize_address(addr_match.group(1))
                if address:
                    property_data['address'] = address
                    break

        # 間取りを抽出（例: "3LDK"）（フィールド抽出追跡を使用）
        layout_match = re.search(r'\b([1-9]\d*(?:K|DK|LDK|SDK|R|SLDK))\b', desc_text)
        if layout_match:
            layout = self.normalize_layout(layout_match.group(1))
            self.track_field_extraction(property_data, 'layout', layout, field_found=True)
        else:
            self.track_field_extraction(property_data, 'layout', None, field_found=False)

        # 専有面積を抽出（例: "85.07㎡"）（フィールド抽出追跡を使用）
        area_match = re.search(r'([\d.]+)(?:㎡|m2)', desc_text)
        if area_match:
            area = self.parse_area(area_match.group(0))
            self.track_field_extraction(property_data, 'area', area, field_found=True)
        else:
            self.track_field_extraction(property_data, 'area', None, field_found=False)

        # 所在階を抽出（例: "7階"）（フィールド抽出追跡を使用）
        floor_match = re.search(r'(\d+)階', desc_text)
        if floor_match:
            floor_number = self.parse_floor(floor_match.group(0))
            self.track_field_extraction(property_data, 'floor_number', floor_number, field_found=True)
        else:
            self.track_field_extraction(property_data, 'floor_number', None, field_found=False)
    
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
        （_process_table_fieldと統合してシンプル化）
        
        Args:
            key: キー
            value: 値
            property_data: データ格納先
        """
        # 共通の処理は_process_table_fieldに委譲
        self._process_table_field(key, value, property_data)
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件詳細情報
        """
        property_data = {}
        
        # デバッグ: HTMLの一部を確認
        if self.logger:
            # テーブル要素の確認
            tables = soup.select('table')
            self.logger.info(f"[REHOUSE-DEBUG] 発見したテーブル数: {len(tables)}")
            
            # 専有面積を含む要素を探す
            area_elements = soup.find_all(string=re.compile(r'専有面積|面積'))
            self.logger.info(f"[REHOUSE-DEBUG] 面積関連要素数: {len(area_elements)}")
            if area_elements:
                for elem in area_elements[:3]:  # 最初の3つだけログ出力
                    parent_text = elem.parent.get_text(strip=True) if elem.parent else ''
                    self.logger.info(f"[REHOUSE-DEBUG] 面積要素: {parent_text[:100]}")
        
        # 価格を抽出（複数の方法を試行）
        self._extract_price(soup, property_data)
        
        # テーブルから情報を抽出
        self._extract_table_info(soup, property_data)
        
        # dl要素から情報を抽出
        self._extract_dl_info(soup, property_data)
        
        # 建物名を取得
        self._extract_building_name_from_detail(soup, property_data)
        
        # 日付情報
        self._extract_date_info(soup, property_data)
        
        # リハウスは自社サイトなので仲介業者名は固定
        property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        
        # デバッグ: 最終的なデータを確認
        if self.logger:
            self.logger.info(f"[REHOUSE-DEBUG] 最終データキー: {list(property_data.keys())}")
            if 'area' in property_data:
                self.logger.info(f"[REHOUSE-DEBUG] 面積取得成功: {property_data['area']}㎡")
            else:
                self.logger.warning(f"[REHOUSE-DEBUG] 面積が取得できませんでした")
        
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
                        price = price_yen // 10000
                        # フィールド抽出追跡を使用
                        self.track_field_extraction(property_data, 'price', price, field_found=True)
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
                    # フィールド抽出追跡を使用
                    self.track_field_extraction(property_data, 'price', price, field_found=True)
                    return True
        
        # それでも見つからない場合は、他の要素から探す
        for elem in soup.find_all(string=re.compile(r'[\d,]+\s*万円')):
            # 除外キーワードを含む場合はスキップ（管理費、修繕積立金など）
            exclude_keywords = ['管理費', '修繕', '積立', '敷金', '礼金', '仲介']
            if any(keyword in str(elem.parent.get_text()) for keyword in exclude_keywords):
                continue
            
            price = self.parse_price(str(elem))
            if price and price > 100:
                # フィールド抽出追跡を使用
                self.track_field_extraction(property_data, 'price', price, field_found=True)
                return True
        
        # 価格が見つからなかった場合
        self.track_field_extraction(property_data, 'price', None, field_found=False)
        return False
    
    def _extract_table_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """テーブルから情報を抽出"""
        tables = soup.select('table')
        if self.logger:
            self.logger.info(f"[REHOUSE-TABLE] テーブル数: {len(tables)}")
        
        for i, table in enumerate(tables):
            # リハウス特有のテーブル構造に対応
            # まず基底クラスのメソッドを試す
            table_data = self.extract_table_data(table)
            
            # 基底クラスで取得できない場合は、リハウス特有の構造を処理
            if not table_data:
                table_data = self._extract_rehouse_table_data(table)
            
            # デバッグログ
            if self.logger and table_data:
                self.logger.info(f"[REHOUSE-TABLE-{i}] テーブルデータ取得: {list(table_data.items())[:3]}")
                # 面積関連のデータがあるかチェック
                for label, value in table_data.items():
                    if '面積' in label:
                        self.logger.info(f"[REHOUSE-TABLE-{i}] 面積関連: label='{label}', value='{value}'")
            
            for label, value in table_data.items():
                self._process_table_field(label, value, property_data)
    
    def _extract_rehouse_table_data(self, table: Tag) -> Dict[str, str]:
        """リハウス特有のテーブル構造からデータを抽出"""
        data = {}
        
        # リハウスのテーブルは th と td が同じ tr にない場合がある
        # または class="table-label" と class="table-data" のパターン
        rows = table.select('tr')
        
        for row in rows:
            # パターン1: class属性で識別
            label_elem = row.find(class_=re.compile('table-label|label'))
            data_elem = row.find(class_=re.compile('table-data|content|data'))
            
            if label_elem and data_elem:
                key = self.extract_text(label_elem)
                value = self.extract_text(data_elem)
                if key and value:
                    data[key] = value
                    if self.logger and '面積' in key:
                        self.logger.info(f"[REHOUSE-CUSTOM] 面積データ発見: {key}={value}")
                continue
            
            # パターン2: th/td のペア（同じ行）
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                key = self.extract_text(cells[0])
                value = self.extract_text(cells[1])
                if key and value:
                    data[key] = value
                    if self.logger and '面積' in key:
                        self.logger.info(f"[REHOUSE-CELLS] 面積データ発見: {key}={value}")
        
        # パターン3: tbody内で連続するtr要素（ラベルと値が別の行）
        tbody = table.find('tbody')
        if tbody and not data:
            all_rows = tbody.find_all('tr')
            for i in range(len(all_rows) - 1):
                current_row = all_rows[i]
                next_row = all_rows[i + 1]
                
                # 現在の行がラベル、次の行が値の可能性
                label_cell = current_row.find(['th', 'td'])
                value_cell = next_row.find(['th', 'td'])
                
                if label_cell and value_cell:
                    key = self.extract_text(label_cell)
                    value = self.extract_text(value_cell)
                    
                    # キーが日本語を含み、値が数値や単位を含む場合
                    if key and value and re.search(r'[ぁ-ん]+|[ァ-ヴー]+|[一-龠]+', key):
                        if re.search(r'\d|㎡|円|階|年', value):
                            data[key] = value
                            if self.logger and '面積' in key:
                                self.logger.info(f"[REHOUSE-ROWS] 面積データ発見: {key}={value}")
        
        return data
    
    def _process_table_field(self, label: str, value: str, property_data: Dict[str, Any]):
        """テーブルの1フィールドを処理"""
        if not value:
            return
            
        # 階数情報
        if '階数' in label and '階建' in value:
            # 所在階の抽出（基底クラスのメソッド使用）（フィールド抽出追跡を使用）
            floor = self.parse_floor(value)
            self.track_field_extraction(property_data, 'floor_number', floor, field_found=True)
            
            # 総階数の抽出（基底クラスのメソッド使用）（フィールド抽出追跡を使用）
            total_floors = self.parse_total_floors(value)
            self.track_field_extraction(property_data, 'total_floors', total_floors, field_found=True)
            
            # 地下階の抽出（基底クラスのメソッド使用）
            basement = self.parse_basement_floors(value)
            if basement:
                property_data['basement_floors'] = basement
        
        elif '所在階' in label:
            # フィールド抽出追跡を使用
            floor = self.parse_floor(value)
            self.track_field_extraction(property_data, 'floor_number', floor, field_found=True)
        
        # 建物構造で総階数を抽出
        elif '構造' in label or '建物' in label:
            total_floors = self.parse_total_floors(value)
            if total_floors and 'total_floors' not in property_data:
                # フィールド抽出追跡を使用
                self.track_field_extraction(property_data, 'total_floors', total_floors, field_found=True)
        
        # 専有面積（基底クラスのparse_area使用）（フィールド抽出追跡を使用）
        elif '専有面積' in label or ('面積' in label and 'バルコニー' not in label):
            area = self.parse_area(value)
            self.track_field_extraction(property_data, 'area', area, field_found=True)
            if area and self.logger:
                self.logger.debug(f"[REHOUSE] 面積設定: {area}㎡ (label={label}, value={value})")
            elif self.logger:
                self.logger.warning(f"[REHOUSE] 面積パース失敗: label={label}, value={value}")
        
        # 間取り（基底クラスのnormalize_layout使用）（フィールド抽出追跡を使用）
        elif '間取り' in label:
            layout = self.normalize_layout(value)
            self.track_field_extraction(property_data, 'layout', layout, field_found=True)
        
        # バルコニー面積（基底クラスのparse_area使用）
        elif 'バルコニー' in label and '面積' in label:
            balcony_area = self.parse_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 向き/主要採光面（基底クラスのnormalize_direction使用）
        elif '向き' in label or '採光' in label or ('バルコニー' in label and '面積' not in label):
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月（基底クラスのparse_built_date使用）（フィールド抽出追跡を使用）
        elif '築年月' in label:
            built_info = self.parse_built_date(value)
            built_year = built_info.get('built_year')
            self.track_field_extraction(property_data, 'built_year', built_year, field_found=True)
            if built_info.get('built_month'):
                property_data['built_month'] = built_info['built_month']
        
        # 管理費（フィールド抽出追跡を使用）
        elif '管理費' in label:
            management_fee = extract_monthly_fee(value)
            self.track_field_extraction(property_data, 'management_fee', management_fee, field_found=True)
        
        # 修繕積立金（フィールド抽出追跡を使用）
        elif '修繕積立金' in label or '修繕積立費' in label:
            repair_fund = extract_monthly_fee(value)
            self.track_field_extraction(property_data, 'repair_fund', repair_fund, field_found=True)
        
        # 総戸数（基底クラスのparse_total_units使用）（フィールド抽出追跡を使用）
        elif '総戸数' in label or '総区画数' in label:
            units = self.parse_total_units(value)
            self.track_field_extraction(property_data, 'total_units', units, field_found=True)
        
        # 所在地/住所（基底クラスのnormalize_address使用）（フィールド抽出追跡を使用）
        elif '所在地' in label or '住所' in label:
            address = self.normalize_address(value)
            self.track_field_extraction(property_data, 'address', address, field_found=True)
        
        # 交通/最寄り駅（基底クラスのparse_station_info使用）（フィールド抽出追跡を使用）
        elif '交通' in label or '駅' in label:
            station_info = self.parse_station_info(value)
            self.track_field_extraction(property_data, 'station_info', station_info, field_found=True)
        
        # 取引態様
        elif '取引態様' in label:
            property_data['transaction_type'] = value
        
        # 現況
        elif '現況' in label:
            property_data['current_status'] = value
        
        # 引渡時期
        elif '引渡' in label:
            property_data['delivery_date'] = value
        
        # 敷地の権利形態（フィールド抽出追跡を使用）
        elif '敷地' in label and '権利' in label:
            land_rights = self.extract_text(value)
            # '-' は値なしとして扱う
            if land_rights == '-':
                land_rights = None
            self.track_field_extraction(property_data, 'land_rights', land_rights, field_found=True)
    
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
        # _process_table_fieldに委譲して共通化
        self._process_table_field(key, value, property_data)
        
        # 詳細ページ固有の追加処理
        if '部屋番号' in key or '号室' in key:
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
            "h1",  # 現在のリハウスは単純なh1タグを使用
            "h1.property-name",
            "h1.detail-title",
            "div.property-header h1"
        ]
        
        for selector in title_selectors:
            title = self.safe_select_one(soup, selector)
            if title:
                building_name = self.extract_text(title)
                if building_name:
                    # タイトルフィールドにも設定（表示用）
                    property_data['title'] = building_name
                    
                    # デバッグログ
                    if self.logger:
                        self.logger.debug(f"リハウス: タイトル取得成功 - selector={selector}, title={building_name}")
                    
                    # 建物名を正規化（広告文除去）
                    building_name = self.normalize_building_name(building_name)
                    # フィールド抽出追跡を使用
                    self.track_field_extraction(property_data, 'building_name', building_name, field_found=True)
                    return
        
        # タイトルが取得できなかった場合
        if self.logger:
            self.logger.warning("リハウス: タイトルが取得できませんでした")
        # フィールド抽出追跡を使用
        self.track_field_extraction(property_data, 'building_name', None, field_found=False)
    
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