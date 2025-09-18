"""
LIFULL HOME'S専用HTMLパーサー

LIFULL HOME'S（www.homes.co.jp）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

from .base_parser import BaseHtmlParser


class HomesParser(BaseHtmlParser):
    """LIFULL HOME'S専用パーサー"""
    
    # LIFULL HOME'Sのデフォルト設定
    DEFAULT_AGENCY_NAME = None  # LIFULL HOME'Sは不動産会社ではないため、デフォルト値は設定しない
    BASE_URL = "https://www.homes.co.jp"
    
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
        
        self.logger.info("[HOMES] Parsing property list page")
        
        # 建物ブロックを探す
        building_blocks = soup.select('.mod-mergeBuilding--sale')
        self.logger.info(f"[HOMES] Found {len(building_blocks)} building blocks")
        
        for block in building_blocks:
            building_link = block.select_one('h3 a, .heading a')
            if not building_link:
                continue
            
            # 複数物件に対応
            price_rows = block.select('tr.raSpecRow')
            
            if not price_rows:
                # raSpecRowがない場合も建物URLを物件URLとして扱う
                href = building_link.get('href', '')
                if '/mansion/b-' in href:
                    from urllib.parse import urljoin
                    full_url = urljoin(self.BASE_URL, href)
                    property_data = {
                        'url': full_url
                    }
                    # URLからIDを抽出
                    import re
                    id_match = re.search(r'/b-(\d+)', href)
                    if id_match:
                        property_data['site_property_id'] = id_match.group(1)
                        # 価格を必須フィールドとして追加（ダミー値）
                        property_data['price'] = 0  # 詳細ページで取得
                        properties.append(property_data)
                    else:
                        self.logger.error(f"[HOMES] 物件をスキップします（site_property_id取得失敗）: {full_url}")
            else:
                # 各物件行を処理
                for row in price_rows:
                    property_data = self._parse_property_row(row)
                    if property_data:
                        properties.append(property_data)
        
        return properties

    
    def _parse_property_row(self, row: Tag) -> Optional[Dict[str, Any]]:
        """物件行から情報を抽出"""
        property_data = {}
        
        # td要素を取得
        tds = row.find_all('td')
        if len(tds) < 5:
            return None
        
        # 物件詳細へのリンク（最初のtdにある）
        link_elem = tds[0].find('a')
        if link_elem:
            href = link_elem.get('href', '')
            if href:
                from urllib.parse import urljoin
                property_data['url'] = urljoin(self.BASE_URL, href)
                # URLからIDを抽出
                import re
                # 新しいURLパターン /mansion/b-XXXXX/
                id_match = re.search(r'/mansion/b-(\d+)', href)
                if not id_match:
                    # 旧パターン /mansion/XXXXX/
                    id_match = re.search(r'/mansion/(\d+)', href)
                if id_match:
                    property_data['site_property_id'] = id_match.group(1)
        
        # 価格（3番目のtd）
        if len(tds) > 2:
            price_text = self.extract_text(tds[2])
            price = self.parse_price(price_text)
            if price:
                property_data['price'] = price
        
        # 間取り（4番目のtd）
        if len(tds) > 3:
            layout_text = self.extract_text(tds[3])
            layout = self.normalize_layout(layout_text)
            if layout:
                property_data['layout'] = layout
        
        # 面積（5番目のtd）
        if len(tds) > 4:
            area_text = self.extract_text(tds[4])
            area = self.parse_area(area_text)
            if area:
                property_data['area'] = area
        
        # 階数（2番目のtdに含まれている可能性があるが、詳細ページで取得する）
        # ここでは一覧ページの必須フィールドのみ
        
        # 必須フィールドのチェック（URLとsite_property_idのみ必須）
        if property_data.get('url') and property_data.get('site_property_id'):
            return property_data
        
        return None
    
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
        title_elem = card.find("h2", class_="object-name") or card.find("a", class_="property-name")
        if title_elem:
            if title_elem.name == 'a':
                property_data['building_name'] = self.extract_text(title_elem)
                href = title_elem.get('href')
            else:
                link = title_elem.find('a')
                if link:
                    property_data['building_name'] = self.extract_text(link)
                    href = link.get('href')
                else:
                    property_data['building_name'] = self.extract_text(title_elem)
                    # h2の親要素からリンクを探す
                    parent_link = card.find('a', href=re.compile(r'/chintai/'))
                    href = parent_link.get('href') if parent_link else None
            
            if href:
                property_data['url'] = self.normalize_url(href, self.BASE_URL)
                # URLからIDを抽出（例: /chintai/123456/）
                site_id_match = re.search(r'/chintai/(\d+)', href)
                if site_id_match:
                    property_data['site_property_id'] = site_id_match.group(1)
        
        # 価格
        price_elem = card.find("span", class_="price") or card.find("span", class_="priceLabel")
        if price_elem:
            price = self.parse_price(self.extract_text(price_elem))
            if price:
                property_data['price'] = price
        
        # 詳細情報を抽出
        self._extract_card_details(card, property_data)
        
        # 仲介業者名を取得
        self._extract_agency_from_card(card, property_data)
        
        # 必須フィールドの検証
        if self._validate_card_data(property_data):
            return property_data
        else:
            return None
    
    def _extract_card_details(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードから詳細情報を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        # 詳細テーブルを探す
        detail_table = card.find("table", class_="object-data")
        if detail_table:
            table_data = self.extract_table_data(detail_table)
            for key, value in table_data.items():
                self._process_detail_item(key, value, property_data)
        
        # dl要素から情報を抽出
        dl_elements = card.select("dl.detail-info")
        for dl in dl_elements:
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
                    self._process_detail_item(key, value, property_data)
    
    def _extract_agency_from_card(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードから不動産会社名を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        agency_elem = card.find("div", class_="company-name") or card.find("span", class_="agency")
        if agency_elem:
            property_data['agency_name'] = self.extract_text(agency_elem)
        else:
            pass  # 不動産会社が取得できない場合は空のままにする
    
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
        detail_tables = self.safe_select(soup, "table.rentTbl, table.bukkenSpec, table.w-full, table.table-fixed, div.mod-buildingDetailSpec table, section.propertyDetail table")

        for table in detail_tables:
            rows = table.find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    key = self.extract_text(th)
                    value = self.extract_text(td)
                    if key and value:
                        self._process_detail_item(key, value, property_data)

        # dl/dt/ddパターンも処理（バルコニー面積などが含まれる場合がある）
        dl_elements = self.safe_select(soup, "dl")
        for dl in dl_elements:
            dt = dl.find("dt")
            dd = dl.find("dd")
            if dt and dd:
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
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
        
        # 価格（賃料）
        if '価格' in key or '賃料' in key:
            price = self.parse_price(value)
            if price:
                property_data['price'] = price
        
        # 間取り
        elif '間取' in key:
            # 正規表現で間取りを抽出（例: "3LDK / 85.5㎡" -> "3LDK"）
            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
            if layout_match:
                property_data['layout'] = layout_match.group(1)
            else:
                # フォールバック: normalize_layoutを使用
                from ..data_normalizer import normalize_layout
                layout = normalize_layout(value.split('/')[0].strip())
                if layout:
                    property_data['layout'] = layout
        
        # 専有面積
        elif '専有面積' in key or ('面積' in key and 'バルコニー' not in key and '建築' not in key and '敷地' not in key):
            from ..data_normalizer import extract_area, validate_area
            area = extract_area(value)
            if area and validate_area(area):
                property_data['area'] = area
        
        # バルコニー面積
        elif 'バルコニー' in key:
            from ..data_normalizer import extract_area
            balcony_area = extract_area(value)
            # バルコニー面積は0㎡以上、100㎡以下であれば有効
            if balcony_area is not None and 0 <= balcony_area <= 100:
                property_data['balcony_area'] = balcony_area
        
        # 階数情報
        elif '階' in key:
            # "10階 / 14階建 (地下1階)" のような形式を処理（スペースあり）
            match = re.search(r'(\d+)階\s*/\s*(\d+)階建', value)
            if match:
                property_data['floor_number'] = int(match.group(1))
                property_data['total_floors'] = int(match.group(2))
            else:
                # "3階/10階建"のような形式を処理（スペースなし）
                match = re.search(r'(\d+)階/(\d+)階建', value)
                if match:
                    property_data['floor_number'] = int(match.group(1))
                    property_data['total_floors'] = int(match.group(2))
                else:
                    # 所在階のみ
                    if '所在階' in key:
                        floor = self.parse_floor(value)
                        if floor:
                            property_data['floor_number'] = floor
                    # 総階数のみ
                    elif '階建' in value:
                        # "14階建 (地下1階)" のような形式から総階数を取得
                        total_match = re.search(r'(\d+)階建', value)
                        if total_match:
                            property_data['total_floors'] = int(total_match.group(1))
                        else:
                            total_floors = self.parse_floor(value)
                            if total_floors:
                                property_data['total_floors'] = total_floors
        
        # 方角（主要採光面も含む）
        elif '向き' in key or '方位' in key or '方角' in key or '採光' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in key or '竣工' in key:
            built_info = self.parse_built_date(value)
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
            if built_info['built_month']:
                property_data['built_month'] = built_info['built_month']
        
        # 所在地
        elif '所在地' in key or '住所' in key:
            address = self.normalize_address(value)
            if address:
                property_data['address'] = address
        
        # 交通
        elif '交通' in key or '最寄' in key or '駅' in key:
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
        
        # 総戸数
        elif '総戸数' in key or '総区画数' in key:
            # 「250戸」などから数値を抽出
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                property_data['total_units'] = int(units_match.group(1))

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
        building_name = None
        room_number = None
        
        # 複数の方法で建物名を取得（優先順位順）
        
        # 方法1: h1タグから取得（複数パターン対応）
        h1_elem = soup.find('h1', class_=lambda x: x and 'Header__logo' not in str(x))
        if h1_elem:
            # パターン1: bukkenNameクラス
            bukken_name_elem = h1_elem.select_one('.bukkenName')
            if bukken_name_elem:
                building_name = self.extract_text(bukken_name_elem)
                # bukkenRoomクラスから部屋番号も取得
                bukken_room_elem = h1_elem.select_one('.bukkenRoom')
                if bukken_room_elem:
                    room_text = self.extract_text(bukken_room_elem)
                    match = re.search(r'/(\d{3,4}[A-Z]?)(?:\s|$)', room_text)
                    if match:
                        room_number = match.group(1)
            
            # パターン2: break-wordsクラス
            elif h1_elem.select_one('.break-words'):
                break_words_elem = h1_elem.select_one('.break-words')
                text = self.extract_text(break_words_elem)
                # 階数部分を除去
                if '階' in text:
                    parts = text.rsplit(' ', 1)
                    if len(parts) > 1 and '階' in parts[-1]:
                        building_name = parts[0]
                    else:
                        building_name = text
                else:
                    building_name = text
            
            # パターン3: 通常のh1タグ
            elif not building_name:
                h1_text = self.extract_text(h1_elem)
                if h1_text:
                    building_name = h1_text
        
        # 方法2: パンくずリストから取得
        if not building_name:
            # breadcrumb-listタグを探す
            breadcrumb_tag = soup.find('breadcrumb-list')
            if breadcrumb_tag:
                breadcrumb_list = breadcrumb_tag.select('ol > li')
            else:
                # その他のパンくずパターン
                breadcrumb_tag = soup.select_one('p.mod-breadcrumbs, [class*="breadcrumb"]')
                if breadcrumb_tag:
                    breadcrumb_list = breadcrumb_tag.select('li')
                else:
                    breadcrumb_list = soup.select('ol.hide-scrollbar > li')
            
            if breadcrumb_list and len(breadcrumb_list) > 0:
                # 最後のli要素を取得
                last_li = breadcrumb_list[-1]
                last_elem = last_li.select_one('a')
                if last_elem:
                    last_text = self.extract_text(last_elem)
                else:
                    last_text = self.extract_text(last_li)
                
                # 建物名として妥当かチェック
                if last_text and len(last_text) > 2 and '一覧' not in last_text and 'エリア' not in last_text:
                    building_name = re.sub(r'^(中古マンション|マンション)', '', last_text).strip()
                    # 階数情報を除去
                    building_name = re.sub(r'\s+\d+階(?:/\d+[A-Z]?)?$', '', building_name)
        
        # 方法3: 物件概要テーブルから取得
        if not building_name:
            detail_tables = soup.select('table.detailTable, table.mod-detailTable, table[class*="detail"], table.rentTbl, table.bukkenSpec')
            for table in detail_tables:
                rows = table.select('tr')
                for row in rows:
                    th = row.select_one('th')
                    td = row.select_one('td')
                    if th and td:
                        header = self.extract_text(th)
                        if '物件名' in header or 'マンション名' in header or '建物名' in header:
                            building_name = self.extract_text(td)
                            building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
                            break
                if building_name:
                    break
        
        # 方法4: その他のセレクタ
        if not building_name:
            other_selectors = [
                "h1.heading",
                "h1.bukkenName", 
                "div.mod-buildingTitle h1",
                "h2.buildingName",
                ".propertyName"
            ]
            
            for selector in other_selectors:
                elem = self.safe_select_one(soup, selector)
                if elem:
                    building_name = self.extract_text(elem)
                    if building_name:
                        break
        
        # 結果を保存
        if building_name:
            # タイトルフィールドにも設定（表示用）
            property_data['title'] = building_name
            
            # 部屋番号部分を除去してbuilding_nameに設定
            cleaned_name = re.sub(r'\s*\d+号室.*$', '', building_name)
            cleaned_name = re.sub(r'\s*\d+階.*$', '', cleaned_name)
            property_data['building_name'] = cleaned_name
            
            # 部屋番号も保存
            if room_number:
                property_data['room_number'] = room_number
            
            # 建物名候補リストも作成（MULTI_SOURCEモード用）
            property_data['_building_names_candidates'] = [cleaned_name]
    
    def _extract_property_images(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        物件画像URLを抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        images = []
        
        # メイン画像
        main_img = self.safe_select_one(soup, "img#mainImage, img.mainPhoto")
        if main_img and main_img.get('src'):
            img_url = self.normalize_url(main_img['src'], self.BASE_URL)
            if img_url:
                images.append(img_url)
        
        # サムネイル画像
        thumb_imgs = self.safe_select(soup, "div.thumbnail img, ul.imageList img")
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
            "div.prComment",
            "div.bukkenPr",
            "div.comment",
            "section.remarks"
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
        company_elem = self.safe_select_one(soup, "div.companyInfo, div.realtor")
        if company_elem:
            company_text = company_elem.get_text(' ', strip=True)
            
            # 会社名を抽出
            company_name_elem = company_elem.find("h3") or company_elem.find("div", class_="companyName")
            if company_name_elem:
                property_data['agency_name'] = self.extract_text(company_name_elem)
            
            # 電話番号を抽出
            tel_match = re.search(r'(?:TEL|電話)[:：\s]*([0-9\-]+)', company_text)
            if tel_match:
                property_data['agency_tel'] = tel_match.group(1)
        
        # デフォルト値
        if 'agency_name' not in property_data:
            pass  # 不動産会社が取得できない場合は空のままにする
    
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
        next_link = self.safe_select_one(soup, "a.next, li.next a, a[rel='next']")
        
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