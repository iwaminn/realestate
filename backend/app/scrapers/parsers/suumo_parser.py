"""
SUUMO専用HTMLパーサー

SUUMO（suumo.jp）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

from .base_parser import BaseHtmlParser
from ..data_normalizer import extract_monthly_fee


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
        物件一覧をパース - URL、価格、建物名、面積、階数を取得
        
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
            
            # 建物名、所在階、専有面積を取得（property_unit-info内から）
            property_info = unit.select_one('.property_unit-info')
            if property_info:
                dl_elements = property_info.select('dl')
                for dl in dl_elements:
                    dt_elements = dl.select('dt')
                    dd_elements = dl.select('dd')
                    
                    for dt, dd in zip(dt_elements, dd_elements):
                        dt_text = dt.get_text(strip=True)
                        dd_text = dd.get_text(strip=True)
                        
                        if '物件名' in dt_text:
                            if dd_text:
                                property_data['building_name'] = dd_text
                        elif '専有面積' in dt_text:
                            # 専有面積を取得（基底クラスのメソッドを使用）（フィールド抽出追跡を使用）
                            area = self.parse_area(dd_text)
                            self.track_field_extraction(property_data, 'area', area, field_found=True)
                        elif '間取り' in dt_text:
                            # 間取りを取得（基底クラスのメソッドを使用）（フィールド抽出追跡を使用）
                            layout = self.normalize_layout(dd_text)
                            self.track_field_extraction(property_data, 'layout', layout, field_found=True)
                        elif '築年月' in dt_text:
                            # 築年月を取得（基底クラスのメソッドで年月を分離）
                            built_info = self.parse_built_date(dd_text)
                            if built_info['built_year']:
                                property_data['built_year'] = built_info['built_year']
                            if built_info['built_month']:
                                property_data['built_month'] = built_info['built_month']
            
            # 物件情報テーブルからも情報を取得（cassette-contentから）
            # 注: SUUMOの一覧ページには所在階情報はない
            content_section = unit.select_one('.cassette-content')
            if content_section:
                table = content_section.select_one('table')
                if table:
                    for row in table.select('tr'):
                        cells = row.select('td')
                        if len(cells) >= 2:
                            # 面積情報を探す（バックアップとして）
                            for cell in cells:
                                cell_text = cell.get_text(strip=True)
                                if 'm²' in cell_text or '㎡' in cell_text:
                                    if 'area' not in property_data:
                                        area = self.parse_area(cell_text)
                                        self.track_field_extraction(property_data, 'area', area, field_found=True)
            
            # URLとsite_property_idがある場合のみ追加
            if property_data.get('url') and property_data.get('site_property_id'):
                properties.append(property_data)
        
        return properties

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
        
        # 間取り（フィールド抽出追跡を使用）
        elif '間取' in key and 'layout' not in property_data:
            layout = self.normalize_layout(value)
            self.track_field_extraction(property_data, 'layout', layout, field_found=True)
        
        # 面積（フィールド抽出追跡を使用）
        elif '専有面積' in key or '面積' in key:
            area = self.parse_area(value)
            self.track_field_extraction(property_data, 'area', area, field_found=True)

        # 階数（フィールド抽出追跡を使用）
        elif '所在階' in key or '階' in key:
            floor = self.parse_floor(value)
            self.track_field_extraction(property_data, 'floor_number', floor, field_found=True)
        
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
                    # タイトルフィールドには元のテキストを設定（表示用）
                    property_data['title'] = building_name
                    
                    # 建物名を正規化（広告文除去）
                    building_name = self.normalize_building_name(building_name)
                    
                    # フィールド抽出追跡を使用
                    self.track_field_extraction(property_data, 'building_name', building_name, field_found=True)
                    return
    
    def _extract_basic_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        基本情報を抽出

        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 「物件詳細情報」という見出しを探す
        property_detail_table = None
        
        # h3タグから「物件詳細情報」を探す
        for h3 in soup.find_all('h3'):
            h3_text = self.extract_text(h3)
            if h3_text and '物件詳細情報' in h3_text:
                # 見出しの次に出現するテーブルを探す
                property_detail_table = h3.find_next('table')
                if property_detail_table:
                    # クラス名を確認して物件詳細テーブルであることを確認
                    # NavigableStringなどの場合を考慮
                    if hasattr(property_detail_table, 'get'):
                        table_classes = property_detail_table.get('class', [])
                        if table_classes and 'bgWhite' in table_classes:
                            # 正しいテーブルを発見
                            break
                        else:
                            property_detail_table = None
                    else:
                        property_detail_table = None
                break
        
        # 物件詳細情報のテーブルが見つかった場合のみ処理
        if property_detail_table:
            self._process_table(property_detail_table, property_data)
        else:
            # 物件詳細情報テーブルが見つからない場合はログ出力
            self.logger.warning("[SUUMO] 物件詳細情報テーブルが見つかりませんでした")
    
    def _process_table(self, table, property_data: Dict[str, Any]) -> None:
        """
        テーブルを処理して情報を抽出
        
        Args:
            table: BeautifulSoupのtable要素
            property_data: データ格納先
        """
        rows = table.find_all("tr")
        for row in rows:
            # 1行に複数のth/tdペアがある場合に対応
            ths = row.find_all("th")
            tds = row.find_all("td")
            
            # th/tdをペアで処理
            for th, td in zip(ths, tds):
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

    def _extract_table_key(self, th) -> str:
        """
        テーブルのthからキーを抽出
        
        Args:
            th: th要素
            
        Returns:
            抽出されたキー
        """
        # div.flがあればそのテキストを取得
        key_div = th.find('div', class_='fl')
        if key_div:
            return self.extract_text(key_div)
        
        # なければth全体から取得（ヒントを除去）
        return self.extract_text(th).replace('ヒント', '').strip()
    
    def _extract_detail_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 「物件詳細情報」のh3見出しを探す
        h3_detail = None
        for h3 in soup.find_all('h3'):
            h3_text = self.extract_text(h3)
            if h3_text and '物件詳細情報' in h3_text:
                h3_detail = h3
                break
        
        if h3_detail:
            # h3の次のテーブルを探す
            current = h3_detail
            for _ in range(10):  # 最大10要素まで探索
                current = current.find_next()
                if not current:
                    break
                
                if current.name == 'table':
                    # 物件詳細情報のテーブルを発見
                    rows = current.find_all('tr')
                    for row in rows:
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            # thのテキストを取得（ヒントを除去）
                            key = self.extract_text(th).replace('ヒント', '').strip()
                            value = self.extract_text(td)
                            
                            if key and value:
                                self._process_detail_item(key, value, property_data)
                    break
        
        # 管理費・修繕積立金を抽出（h2:物件概要 > h3:【マンション】> table）
        if not property_data.get('management_fee') or not property_data.get('repair_fund'):
            # h2:物件概要を探す（内部構造が複雑なのでget_text()で判定）
            for h2 in soup.find_all('h2'):
                if '物件概要' in self.extract_text(h2):
                    # h2の下のh3:【マンション】を探す
                    building_h3 = h2.find_next('h3', string=lambda text: text and '【マンション】' in text)
                    if building_h3:
                        table = building_h3.find_next('table')
                        if table:
                            for th, td in zip(table.find_all('th'), table.find_all('td')):
                                key = self._extract_table_key(th)
                                if '管理費' in key or '修繕積立' in key:
                                    self._process_detail_item(key, self.extract_text(td), property_data)
                    break
        
        # 従来のdl要素からの抽出も維持（フォールバック）
        dl_elements = self.safe_select(soup, "dl.data-body")
        for dl in dl_elements:
            dt_elements = dl.find_all("dt")
            dd_elements = dl.find_all("dd")
            
            for dt, dd in zip(dt_elements, dd_elements):
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
                    self._process_detail_item(key, value, property_data)
        
        # 方角が取得できていない場合、JavaScriptデータから抽出（フォールバック）
        if not property_data.get('direction'):
            self._extract_direction_from_javascript(soup, property_data)
    
    def _extract_direction_from_javascript(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        JavaScriptデータから方角を抽出（フォールバック処理）
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        
        # script要素からJavaScriptデータを探す
        for script in soup.find_all('script'):
            if script.string and 'muki' in script.string:
                # muki : "東" のパターンを探す
                match = re.search(r'muki\s*:\s*"([^"]*)"', script.string)
                if match:
                    direction_raw = match.group(1)
                    if direction_raw:
                        # 方角を正規化（基底クラスのnormalize_directionメソッドを使用）
                        direction = self.normalize_direction(direction_raw)
                        if direction:
                            property_data['direction'] = direction
                            self.logger.info(f"Direction not found in HTML, extracted from JavaScript: {direction}")
                break

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
        
        # 価格（フィールド抽出追跡を使用）
        if ('価格' in key or '販売価格' in key) and 'price' not in property_data:
            price = self.parse_price(value)
            self.track_field_extraction(property_data, 'price', price, field_found=True)

        # 間取り（フィールド抽出追跡を使用）
        elif '間取' in key and 'layout' not in property_data:
            layout = self.normalize_layout(value)
            self.track_field_extraction(property_data, 'layout', layout, field_found=True)

        # 専有面積（フィールド抽出追跡を使用）
        elif '専有面積' in key and 'area' not in property_data:
            area = self.parse_area(value)
            self.track_field_extraction(property_data, 'area', area, field_found=True)
            
            # 専有面積のセル内にバルコニー面積が含まれる場合の処理
            if 'バルコニー面積' in value and 'balcony_area' not in property_data:
                # バルコニー面積：XX.XXm2 のパターンを探す
                balcony_match = re.search(r'バルコニー面積[：:]\s*([0-9.]+)', value)
                if balcony_match:
                    try:
                        balcony_area = float(balcony_match.group(1))
                        property_data['balcony_area'] = balcony_area
                        self.logger.info(f"Extracted balcony area from 専有面積 cell: {balcony_area}㎡")
                    except ValueError:
                        pass
        
        # バルコニー面積
        elif 'バルコニー' in key:
            balcony_area = self.parse_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 階数（所在階/階建）（フィールド抽出追跡を使用）
        elif '所在階' in key:
            # 所在階の抽出
            floor = self.parse_floor(value)
            self.track_field_extraction(property_data, 'floor_number', floor, field_found=True)

            # 総階数の抽出（"10階建"の部分から）
            total_floors = self.parse_total_floors(value)
            self.track_field_extraction(property_data, 'total_floors', total_floors, field_found=True)

            # 地下階数の抽出
            basement_floors = self.parse_basement_floors(value)
            if basement_floors:
                property_data['basement_floors'] = basement_floors
        
        # 総階数（フィールド抽出追跡を使用）
        elif '階建' in key or '総階数' in key:
            total_floors = self.parse_total_floors(value)
            self.track_field_extraction(property_data, 'total_floors', total_floors, field_found=True)
            
            # 地下階数の抽出
            basement_floors = self.parse_basement_floors(value)
            if basement_floors:
                property_data['basement_floors'] = basement_floors
        
        # 総戸数（フィールド抽出追跡を使用）
        elif '総戸数' in key or '総区画数' in key:
            units = self.parse_total_units(value)
            # 数値が取れない場合も再試行
            if units is None:
                units_match = re.search(r'(\d+)', value)
                if units_match:
                    units = int(units_match.group(1))
            self.track_field_extraction(property_data, 'total_units', units, field_found=True)
        
        # 方角
        elif '向き' in key or '主要採光面' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月（フィールド抽出追跡を使用）
        elif '築年月' in key or '竣工時期' in key:
            # 基底クラスのメソッドで年月を分離して保存
            built_info = self.parse_built_date(value)
            built_year = built_info.get('built_year')
            self.track_field_extraction(property_data, 'built_year', built_year, field_found=True)
            
            # 築月も設定
            if built_info.get('built_month'):
                property_data['built_month'] = built_info['built_month']
        
        # 所在地・住所（フィールド抽出追跡を使用）
        elif '所在地' in key or '住所' in key:
            address = self.normalize_address(value)
            self.track_field_extraction(property_data, 'address', address, field_found=True)
        
        # 交通（フィールド抽出追跡を使用）
        elif '交通' in key:
            station = self.parse_station_info(value)
            self.track_field_extraction(property_data, 'station_info', station, field_found=True)
        
        # 管理費（フィールド抽出追跡を使用）
        elif '管理費' in key:
            fee = extract_monthly_fee(value)
            self.track_field_extraction(property_data, 'management_fee', fee, field_found=True)
        
        # 修繕積立金（フィールド抽出追跡を使用）
        elif '修繕積立' in key:
            fund = extract_monthly_fee(value)
            self.track_field_extraction(property_data, 'repair_fund', fund, field_found=True)
        
        # 部屋番号
        elif '部屋番号' in key:
            room = self.extract_text(value)
            if room and room != '-':
                property_data['room_number'] = room

        # その他面積（バルコニー面積が含まれる場合がある）
        elif 'その他面積' in key and 'balcony_area' not in property_data:
            # バルコニー面積：XX.XXm2 のパターンを探す
            if 'バルコニー面積' in value:
                balcony_match = re.search(r'バルコニー面積[：:]\s*([0-9.]+)', value)
                if balcony_match:
                    try:
                        balcony_area = float(balcony_match.group(1))
                        property_data['balcony_area'] = balcony_area
                        self.logger.info(f"Extracted balcony area from その他面積 cell: {balcony_area}㎡")
                    except ValueError:
                        pass
    
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
    
    def is_last_page(self, soup: BeautifulSoup) -> bool:
        """
        現在のページが最終ページかどうかを判定
        
        Returns:
            最終ページの場合True
        """
        try:
            # 「次へ」リンクの有無で判定
            next_link = soup.select_one('.pagination a[rel="next"], .pagination-parts a:contains("次へ")')
            if next_link is None:
                return True
            
            # ページ番号から判定
            pagination = soup.select_one('.pagination, .pagination-parts')
            if pagination:
                current = pagination.select_one('.active, .current, strong')
                if current:
                    page_links = pagination.select('a')
                    if page_links:
                        last_page_text = page_links[-1].get_text(strip=True)
                        if last_page_text == '次へ' and len(page_links) > 1:
                            last_page_text = page_links[-2].get_text(strip=True)
                        
                        try:
                            current_page = int(current.get_text(strip=True))
                            last_page = int(last_page_text)
                            return current_page >= last_page
                        except (ValueError, AttributeError):
                            pass
            
            return False
            
        except Exception as e:
            self.logger.warning(f"[SUUMO] ページ終端判定でエラー: {e}")
            return False

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