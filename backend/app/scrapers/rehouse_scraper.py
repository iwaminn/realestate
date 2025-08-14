"""
三井のリハウススクレイパー実装

URLパターン:
- 一覧: https://www.rehouse.co.jp/buy/mansion/prefecture/{都道府県}/city/{市区町村}/
- 詳細: https://www.rehouse.co.jp/buy/mansion/bkdetail/{物件コード}/
"""

import re
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
import logging

from bs4 import BeautifulSoup, Tag
import requests

from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)

logger = logging.getLogger(__name__)


class RehouseScraper(BaseScraper):
    """三井のリハウス用スクレイパー"""
    
    SOURCE_SITE = SourceSite.REHOUSE
    BASE_URL = "https://www.rehouse.co.jp"
    
    # 定数の定義
    MIN_PROPERTY_PRICE = 1000  # 物件価格の最小値（万円）
    
    # 価格を含まないキーワード（これらが含まれる価格情報は無視）
    PRICE_EXCLUDE_KEYWORDS = ['管理費', '修繕', '賃料', '駐車場']
    
    # 備考から除外するキーワード
    REMARKS_EXCLUDE_KEYWORDS = ['利用規約', 'Copyright', '個人情報', 'お問い合わせ']
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties, ignore_error_history)
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
        })
    
    def get_list_url(self, prefecture: str = "13", city: str = "13103", page: int = 1) -> str:
        """一覧ページのURLを生成"""
        base_url = f"{self.BASE_URL}/buy/mansion/prefecture/{prefecture}/city/{city}/"
        
        # ページングパラメータ
        if page > 1:
            return f"{base_url}?page={page}"
        return base_url
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """三井のリハウスのsite_property_idの妥当性を検証
        
        三井のリハウスの物件IDは英数字で構成される（例：F02AGA18）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # 三井のリハウス固有の検証：英数字のみで構成されているか
        if not site_property_id.replace('-', '').replace('_', '').isalnum():
            self.logger.error(
                f"[REHOUSE] site_property_idは英数字（ハイフン・アンダースコア可）で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜12文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[REHOUSE] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行
            
        return True
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """検索URLを生成（共通インターフェース用）"""
        from .area_config import get_area_code
        area_code = get_area_code(area)
        return self.get_list_url("13", area_code, page)
    
    def parse_property_list(self, soup_or_html) -> List[Dict]:
        """一覧ページから物件情報を抽出"""
        # BeautifulSoupオブジェクトまたはHTML文字列を受け取る
        if isinstance(soup_or_html, str):
            soup = BeautifulSoup(soup_or_html, 'html.parser')
        else:
            soup = soup_or_html
        properties = []
        
        # 物件カードを検索
        property_items = self._find_property_items(soup)
        
        if not property_items:
            logger.warning("No property items found on the page")
            return properties
        
        for item in property_items:
            try:
                property_data = self._parse_property_item(item)
                if property_data:
                    # 一覧ページでの必須フィールドを検証（基底クラスの共通メソッドを使用）
                    if self.validate_list_page_fields(property_data):
                        properties.append(property_data)
            except Exception as e:
                logger.error(f"物件アイテム解析エラー - {type(e).__name__}: {str(e)}")
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
                    logger.info(f"Found {len(items)} properties using selector: {selector}")
                    break
        else:
            logger.info(f"Found {len(property_items)} properties using selector: div.property-index-card")
        
        return property_items
    
    def _parse_property_item(self, item: Tag) -> Optional[Dict]:
        """個別の物件要素から情報を抽出"""
        property_data = {}
        
        # 詳細ページへのリンク
        link_elem = item.select_one('a[href*="/bkdetail/"]')
        if not link_elem:
            link_elem = item.select_one('a[href*="/detail/"]')
        
        if not link_elem:
            return None
        
        detail_url = link_elem.get('href')
        if not detail_url.startswith('http'):
            detail_url = urljoin(self.BASE_URL, detail_url)
        
        property_data['url'] = detail_url
        property_data['source_site'] = self.SOURCE_SITE
        
        # 物件コードを抽出
        code_match = re.search(r'/bkdetail/([^/]+)/', detail_url)
        if not code_match:
            self.logger.error(f"[REHOUSE] URLから物件IDを抽出できませんでした: {detail_url}")
            return None
            
        site_property_id = code_match.group(1)
        
        # site_property_idの妥当性を検証
        if not self.validate_site_property_id(site_property_id, detail_url):
            self.logger.error(f"[REHOUSE] 不正なsite_property_idを検出しました: '{site_property_id}'")
            return None
            
        property_data['site_property_id'] = site_property_id
        self.logger.info(f"[REHOUSE] Extracted site_property_id: {site_property_id} from {detail_url}")
        
        # property-index-card-inner内の情報を取得
        inner = item.select_one('.property-index-card-inner')
        if not inner:
            return None
        
        # 全テキストを取得
        full_text = inner.get_text(' ', strip=True)
        
        # 価格
        price = extract_price(full_text)
        if price:
            property_data['price'] = price
        
        # 建物名を取得（一覧ページから）
        # h2タグに建物名があることが判明
        title_elem = item.select_one('.property-index-card-inner h2, .description-section h2')
        if title_elem:
            building_name = title_elem.get_text(strip=True)
            property_data['building_name_from_list'] = building_name
            property_data['building_name'] = building_name  # 必須フィールドとして設定
        
        # description-section内の詳細情報
        desc_section = inner.select_one('.description-section')
        if desc_section:
            self._extract_description_info(desc_section, property_data)
        
        return property_data
    
    def _extract_description_info(self, desc_section: Tag, property_data: Dict[str, Any]):
        """description-sectionから情報を抽出"""
        desc_text = desc_section.get_text(' ', strip=True)
        
        # 住所を抽出
        if '港区' in desc_text:
            addr_match = re.search(r'(港区[^\s/]+)', desc_text)
            if addr_match:
                property_data['address'] = '東京都' + addr_match.group(1)
        
        # 駅情報
        station_match = re.search(r'([^\s]+線\s*[^\s]+駅\s*徒歩\d+分)', desc_text)
        if station_match:
            property_data['station_info'] = station_match.group(1)
        
        # 間取り、面積、築年、階数の情報を抽出
        info_pattern = r'([1-9][LDKS]+|ワンルーム)\s*/\s*(\d+(?:\.\d+)?)㎡\s*/\s*(\d{4})年(\d{2})月築\s*/\s*(\d+)階'
        info_match = re.search(info_pattern, desc_text)
        if info_match:
            # 間取りを正規化してから設定
            layout = normalize_layout(info_match.group(1))
            if layout:
                property_data['layout'] = layout
            else:
                # 正規化に失敗した場合は元の値を20文字に制限
                property_data['layout'] = info_match.group(1)[:20]
            property_data['area'] = float(info_match.group(2))
            property_data['built_year'] = int(info_match.group(3))
            property_data['floor_number'] = int(info_match.group(5))
        else:
            # 個別に抽出
            layout = normalize_layout(desc_text)
            if layout:
                property_data['layout'] = layout
            
            area = extract_area(desc_text)
            if area:
                property_data['area'] = area
            
            built_year = extract_built_year(desc_text)
            if built_year:
                property_data['built_year'] = built_year
            
            floor_number = extract_floor_number(desc_text)
            if floor_number is not None:
                property_data['floor_number'] = floor_number
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（共通インターフェース用）"""
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property
        )
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析（共通インターフェース用）"""
        return self.get_property_detail(url)
    
    def get_property_detail(self, url: str) -> Optional[Dict]:
        """詳細ページから物件情報を取得"""
        try:
            soup = self.fetch_page(url)
            if not soup:
                return None
            
            # site_property_idをURLから抽出
            code_match = re.search(r'/bkdetail/([^/]+)/', url)
            if not code_match:
                self.logger.error(f"[REHOUSE] 詳細ページでURLから物件IDを抽出できませんでした: {url}")
                return None
                
            site_property_id = code_match.group(1)
            
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, url):
                self.logger.error(f"[REHOUSE] 詳細ページで不正なsite_property_idを検出しました: '{site_property_id}'")
                return None
                
            property_data = {
                'url': url, 
                'source_site': self.SOURCE_SITE, 
                'site_property_id': site_property_id,
                '_page_text': soup.get_text()  # 建物名一致確認用
            }
            
            # 物件名
            h1_elem = soup.find('h1')
            if h1_elem:
                property_data['building_name'] = h1_elem.get_text(strip=True)
            
            # 価格を抽出（複数の方法を試行）
            if not self._extract_price(soup, property_data):
                logger.warning(f"Price not found for {url}")
            
            # テーブルから情報を抽出
            self._extract_table_info(soup, property_data)
            
            # dlリスト構造から情報を取得
            self._extract_dl_info(soup, property_data)
            
            # 不動産会社情報
            self._extract_agency_info(soup, property_data)
            
            # 日付情報を抽出
            self._extract_date_info(soup, property_data)
            
            
            
            # 詳細ページでの必須フィールドを検証
            if not self.validate_detail_page_fields(property_data, url):
                return self.log_validation_error_and_return_none(property_data, url)
            
            return property_data
            
        except Exception as e:
            # TaskCancelledExceptionの場合は再スロー
            from ..utils.exceptions import TaskCancelledException
            if isinstance(e, TaskCancelledException):
                raise
            self.log_detailed_error("詳細ページ解析エラー", url, e)
            return None
    
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
            if '万円' in cell_text and not any(keyword in cell_text for keyword in self.PRICE_EXCLUDE_KEYWORDS):
                price = extract_price(cell_text)
                if price and price > self.MIN_PROPERTY_PRICE:
                    property_data['price'] = price
                    return True
        
        # それでも見つからない場合は、備考（remarks）以外から探す
        for elem in soup.find_all(text=re.compile(r'[\d,]+\s*万円')):
            parent = elem.parent
            # 親要素がremarksクラスを持つ場合はスキップ
            if parent and parent.get('class') and 'remarks' in parent.get('class'):
                continue
            
            # 除外キーワードを含む場合はスキップ
            if any(keyword in str(elem) for keyword in self.PRICE_EXCLUDE_KEYWORDS):
                continue
            
            price = extract_price(elem)
            if price and price > self.MIN_PROPERTY_PRICE:
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
        # 所在階/総階数
        if '階数' in label and '階建' in label:
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
        
        # 建物構造
        elif '構造' in label or '建物' in label:
            total_floors, basement_floors = extract_total_floors(value)
            if total_floors is not None and 'total_floors' not in property_data:
                property_data['total_floors'] = total_floors
            if basement_floors is not None and basement_floors > 0:
                property_data['basement_floors'] = basement_floors
        
        # 専有面積
        elif '専有面積' in label or '面積' in label:
            area = extract_area(value)
            if area:
                property_data['area'] = area
        
        # 間取り
        elif '間取り' in label:
            layout = normalize_layout(value)
            if layout:
                property_data['layout'] = layout
        
        # バルコニー面積
        elif 'バルコニー' in label and '面積' in label:
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 向き/主要採光面
        elif '向き' in label or '採光' in label or 'バルコニー' in label:
            direction = normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                property_data['built_year'] = built_year
                # 月情報も取得
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    property_data['built_month'] = int(month_match.group(1))
        
        # 管理費
        elif '管理費' in label:
            management_fee = extract_monthly_fee(value)
            if management_fee:
                property_data['management_fee'] = management_fee
        
        # 修繕積立金
        elif '修繕積立金' in label or '修繕積立費' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                property_data['repair_fund'] = repair_fund
        
        # 総戸数
        elif '総戸数' in label or '総区画数' in label:
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                property_data['total_units'] = int(units_match.group(1))
                self.logger.info(f"[REHOUSE] 総戸数: {property_data['total_units']}戸")
        
        # 所在地/住所
        elif '所在地' in label or '住所' in label:
            # GoogleMapsなどの不要な文字を削除
            address = re.sub(r'GoogleMaps.*$', '', value).strip()
            property_data['address'] = address
        
        # 交通/最寄り駅
        elif '交通' in label or '駅' in label:
            property_data['station_info'] = self._format_station_info(value)
        
        # 取引態様
        elif '取引態様' in label:
            property_data['transaction_type'] = value
        
        # 現況
        elif '現況' in label:
            property_data['current_status'] = value
        
        # 引渡時期
        elif '引渡' in label:
            property_data['delivery_date'] = value
    
    def _format_station_info(self, station_info: str) -> str:
        """駅情報をフォーマット"""
        # 「分」の後で分割して、各路線情報を改行で区切る
        stations = re.split(r'分(?=[^分])', station_info)
        formatted_stations = []
        for i, station in enumerate(stations):
            station = station.strip()
            if station:
                # 最後の要素以外は「分」を追加
                if i < len(stations) - 1:
                    station += '分'
                formatted_stations.append(station)
        return '\n'.join(formatted_stations)
    
    def _extract_dl_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """dlリスト構造から情報を取得"""
        dl_elements = soup.select('dl')
        for dl in dl_elements:
            dt_elements = dl.select('dt')
            dd_elements = dl.select('dd')
            
            for i, dt in enumerate(dt_elements):
                if i < len(dd_elements):
                    label = dt.get_text(strip=True)
                    value = dd_elements[i].get_text(strip=True)
                    
                    # 所在階の補完
                    if '所在階' in label and 'floor_number' not in property_data:
                        floor_match = re.search(r'(\d+)階', value)
                        if floor_match:
                            property_data['floor_number'] = int(floor_match.group(1))
    
    def _extract_agency_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """不動産会社情報を抽出"""
        agency_selectors = [
            '.agency-name', '.company-name', '.shop-name',
            '[class*="agency"]', '[class*="company"]', '[class*="shop"]'
        ]
        
        for selector in agency_selectors:
            agency_elem = soup.select_one(selector)
            if agency_elem:
                property_data['agency_name'] = agency_elem.get_text(strip=True)
                break
        
        # 電話番号
        tel_patterns = [
            r'0\d{1,4}-\d{1,4}-\d{4}',
            r'0\d{9,10}'
        ]
        
        page_text = soup.get_text()
        for pattern in tel_patterns:
            tel_match = re.search(pattern, page_text)
            if tel_match:
                property_data['agency_tel'] = tel_match.group()
                break
    
    def _extract_date_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """日付情報を抽出"""
        page_text = soup.get_text()
        
        # 情報公開日（初めて公開された日）
        first_publish_patterns = [
            r'情報公開日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'初回登録日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'初回掲載日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?'
        ]
        
        for pattern in first_publish_patterns:
            date_match = re.search(pattern, page_text)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                property_data['first_published_at'] = datetime(year, month, day)
                print(f"売出確認日: {property_data['first_published_at'].strftime('%Y-%m-%d')}")
                break
        
        # 情報提供日（最新の更新日）
        update_patterns = [
            r'情報提供日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'更新日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'最終更新日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'登録日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'掲載日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?',
            r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?\s*(?:公開|登録|掲載)'
        ]
        
        for pattern in update_patterns:
            date_match = re.search(pattern, page_text)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                property_data['published_at'] = datetime(year, month, day)
                # first_published_atがない場合は、published_atを使用
                if 'first_published_at' not in property_data:
                    property_data['first_published_at'] = property_data['published_at']
                print(f"情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                break
    
    
    
    def scrape_area(self, area: str = "minato", max_pages: int = 5):
        """エリアの物件をスクレイピング（東京都港区に対応）"""
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 共通ロジックを使用（価格変更ベースのスマートスクレイピングを含む）
        return self.common_scrape_area_logic(area, max_pages)
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報をデータベースに保存"""
        # 共通の保存処理を使用
        return self.save_property_common(property_data, existing_listing)
    
    def _post_listing_creation_hook(self, listing: PropertyListing, property_data: Dict[str, Any]):
        """掲載情報作成後のフック（三井のリハウス特有の処理）"""
        # 追加フィールドの設定
        self._set_additional_fields(listing, property_data)
        
        # 詳細情報を保存
        if property_data.get('detail_fetched', False):
            listing.detail_info = self._build_detail_info(property_data)
            listing.detail_fetched_at = datetime.now()
        
        # 多数決による物件情報更新
        # listingからmaster_propertyへの参照を取得
        if listing.master_property:
            self.update_master_property_by_majority(listing.master_property)
    
    
    def _set_additional_fields(self, listing: PropertyListing, property_data: Dict[str, Any]):
        """追加フィールドを設定"""
        if property_data.get('agency_tel'):
            listing.agency_tel = property_data['agency_tel']
        if property_data.get('remarks'):
            listing.remarks = property_data['remarks']
        if property_data.get('summary_remarks'):
            listing.summary_remarks = property_data['summary_remarks']
    
    def _build_detail_info(self, property_data: Dict[str, Any]) -> Dict[str, Any]:
        """詳細情報を構築"""
        return {
            'transaction_type': property_data.get('transaction_type'),
            'current_status': property_data.get('current_status'),
            'delivery_date': property_data.get('delivery_date'),
            'built_month': property_data.get('built_month')
        }