"""
LIFULL HOME'Sスクレイパー（リファクタリング版）
homes.co.jpから中古マンション情報を取得
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup
from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)


class HomesScraper(BaseScraper):
    """LIFULL HOME'Sのスクレイパー"""
    
    BASE_URL = "https://www.homes.co.jp"
    SOURCE_SITE = SourceSite.HOMES
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties)
        self._setup_headers()
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """LIFULL HOME'Sのsite_property_idの妥当性を検証
        
        LIFULL HOME'Sの物件IDは以下の形式：
        - 数字のみ（例：1234567890）
        - b-で始まる英数字（例：b-35005010002458）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # LIFULL HOME'S固有の検証
        # パターン1: 数字のみ
        if site_property_id.isdigit():
            # 通常は7〜12桁程度
            if len(site_property_id) < 7 or len(site_property_id) > 15:
                self.logger.warning(
                    f"[HOMES] site_property_idの桁数が異常です（通常7-15桁）: '{site_property_id}' "
                    f"(桁数: {len(site_property_id)}) URL={url}"
                )
            return True
            
        # パターン2: b-で始まる英数字
        if site_property_id.startswith('b-'):
            remaining = site_property_id[2:]
            if remaining and remaining.replace('-', '').isalnum():
                return True
            else:
                self.logger.error(
                    f"[HOMES] b-形式のsite_property_idが不正です: '{site_property_id}' URL={url}"
                )
                return False
                
        # どちらのパターンにも合致しない
        self.logger.error(
            f"[HOMES] site_property_idの形式が不正です（数字のみ、またはb-で始まる英数字である必要があります）: '{site_property_id}' URL={url}"
        )
        return False
    
    def _setup_headers(self):
        """HTTPヘッダーの設定"""
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得してBeautifulSoupオブジェクトを返す"""
        try:
            time.sleep(3)  # より長い遅延を設定
            
            # リファラーを設定
            if '/list/' in url:
                self.http_session.headers['Referer'] = 'https://www.homes.co.jp/'
            else:
                self.http_session.headers['Referer'] = 'https://www.homes.co.jp/mansion/chuko/tokyo/list/'
            
            response = self.http_session.get(url, timeout=30, allow_redirects=True)
            
            # 405エラーの特別処理
            if response.status_code == 405:
                self.logger.error(f"405 Method Not Allowed for {url}")
                self.logger.info("Trying with modified headers...")
                self.http_session.headers['Sec-Fetch-Site'] = 'same-origin'
                self.http_session.headers['Sec-Fetch-Mode'] = 'cors'
                time.sleep(5)
                response = self.http_session.get(url, timeout=30)
            
            response.raise_for_status()
            
            if len(response.content) < 1000:
                self.logger.warning(f"Response seems too small ({len(response.content)} bytes) for {url}")
            
            return BeautifulSoup(response.content, 'html.parser')
            
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {type(e).__name__}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"Response headers: {dict(e.response.headers)}")
            return None
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """HOME'Sの検索URLを生成"""
        from .area_config import get_area_code, get_homes_city_code
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/?page={page}"
    
    def _extract_price(self, soup: BeautifulSoup, page_text: str) -> Optional[int]:
        """価格情報を抽出"""
        # セレクタのリスト
        price_selectors = [
            'b.text-brand', 'b[class*="text-brand"]', '.priceLabel', '.price',
            '[class*="price"]', 'span[class*="price"]', 'div[class*="price"]',
            'p[class*="price"]', '.bukkenPrice', '.detailPrice', '[class*="amount"]'
        ]
        
        # セレクタで価格を探す
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem and '万円' in elem.get_text():
                price = extract_price(elem.get_text(strip=True))
                if price:
                    self.logger.info(f"[HOMES] Price found with selector: {selector} - {price}万円")
                    return price
        
        # b要素とstrong要素を確認
        for tag in ['b', 'strong']:
            for elem in soup.select(tag):
                if '万円' in elem.get_text():
                    price = extract_price(elem.get_text(strip=True))
                    if price:
                        self.logger.info(f"[HOMES] Price found in {tag} tag: {price}万円")
                        return price
        
        # ページ全体から価格を探す
        self.logger.warning("[HOMES] Price not found with selectors, searching in full text...")
        price_matches = re.findall(r'[\d,]+(?:億[\d,]*)?万円', page_text)
        
        for price_text in price_matches[:5]:
            price = extract_price(price_text)
            if price and price >= 100:  # 100万円以上なら妥当な価格
                self.logger.info(f"[HOMES] Selected price from text: {price}万円")
                return price
        
        self.logger.error("[HOMES] No price pattern found")
        return None
    
    def _extract_building_name_and_room(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        """建物名と部屋番号を抽出"""
        building_name = None
        room_number = None
        
        # パンくずリストから建物名を取得（最優先）
        breadcrumb = soup.select_one('.breadList, .breadcrumb, nav[aria-label="breadcrumb"], .topicPath')
        if breadcrumb:
            breadcrumb_items = breadcrumb.select('li, .breadList__item, .breadcrumb-item')
            if len(breadcrumb_items) >= 2:
                building_item = breadcrumb_items[-2]
                building_text = building_item.get_text(strip=True)
                match = re.search(r'(.+?)の中古マンション', building_text)
                if match:
                    building_name = match.group(1)
                else:
                    building_name = building_text.replace('中古マンション', '').strip()
                self.logger.info(f"[HOMES] Building name from breadcrumb: {building_name}")
        
        # h1タグから情報を取得
        if not building_name:
            h1_elem = soup.select_one('h1.font-bold, h1[class*="text-2xl"], h1')
            if h1_elem:
                h1_text = h1_elem.get_text(strip=True)
                if '中古マンション' in h1_text:
                    h1_text = h1_text.replace('中古マンション', '').strip()
                parts = h1_text.split('/')
                if parts:
                    building_name = parts[0].strip()
        
        # titleタグまたはog:titleから情報を取得
        if not building_name:
            title_elem = soup.select_one('title')
            og_title = soup.select_one('meta[property="og:title"]')
            title_text = (title_elem.get_text(strip=True) if title_elem else 
                         og_title.get('content', '') if og_title else '')
            
            if title_text:
                title_text = title_text.replace('【ホームズ】', '').strip()
                property_name_part = (title_text.split('｜')[0].strip() if '｜' in title_text else 
                                    title_text.split('|')[0].strip() if '|' in title_text else 
                                    title_text.split('、')[0].strip())
                
                # 部屋番号を抽出
                room_match = re.search(r'\s+(\d{3,4}[A-Z]*)\s*($|｜|\|)', property_name_part)
                if room_match:
                    room_number = room_match.group(1)
                    building_name = property_name_part.replace(room_number, '').strip()
                else:
                    parts = property_name_part.split()
                    if len(parts) >= 2 and re.match(r'^\d{3,4}[A-Z]*$', parts[-1]):
                        room_number = parts[-1]
                        building_name = ' '.join(parts[:-1])
                    else:
                        building_name = property_name_part
        
        # 最終的なクリーンアップ
        if building_name:
            building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
        
        return building_name, room_number
    
    def _extract_property_details_from_dl(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """データリスト（dl/dt/dd）から情報を抽出"""
        details = {}
        
        # dl要素を処理
        for dl in soup.select('.detailInfo dl, .mod-detailInfo dl, [class*="detail"] dl'):
            dt = dl.select_one('dt')
            dd = dl.select_one('dd')
            
            if not dt or not dd:
                continue
            
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            self._process_detail_field(label, value, details)
        
        # dl要素の別パターン
        for dl in soup.select('dl'):
            dt_elements = dl.select('dt')
            dd_elements = dl.select('dd')
            for i, dt in enumerate(dt_elements):
                if i < len(dd_elements):
                    label = dt.get_text(strip=True)
                    value = dd_elements[i].get_text(strip=True)
                    self._process_detail_field(label, value, details)
        
        return details
    
    def _extract_property_details_from_table(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """テーブルから情報を抽出"""
        details = {}
        
        for table in soup.select('table'):
            for row in table.select('tr'):
                cells = row.select('th, td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    self._process_detail_field(label, value, details)
        
        return details
    
    def _process_detail_field(self, label: str, value: str, details: Dict[str, Any]):
        """フィールドを処理してdetailsに格納"""
        # デバッグ: 面積関連のフィールドをログに記録
        if '面積' in label:
            self.logger.debug(f"[HOMES] 面積フィールド検出 - label: '{label}', value: '{value}'")
        
        if '所在地' in label or '住所' in label:
            details['address'] = value
        elif '間取り' in label:
            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
            if layout_match:
                details['layout'] = layout_match.group(1)
            else:
                layout = normalize_layout(value.split('/')[0].strip())
                if layout:
                    details['layout'] = layout
        elif '専有面積' in label:
            area = extract_area(value)
            if area:
                details['area'] = area
        elif '面積' in label and 'バルコニー' not in label and '建築' not in label and '敷地' not in label and '専有' not in label:
            # 専有面積が取得できていない場合のみ、他の面積情報を使用
            if 'area' not in details:
                area = extract_area(value)
                if area:
                    details['area'] = area
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                details['built_year'] = built_year
                details['age'] = datetime.now().year - built_year
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    details['built_month'] = int(month_match.group(1))
        elif '所在階' in label and '階数' in label:
            floor_match = re.search(r'(\d+)階\s*/\s*(\d+)階建', value)
            if floor_match:
                details['floor_number'] = int(floor_match.group(1))
                details['total_floors'] = int(floor_match.group(2))
                _, basement_floors = extract_total_floors(value)
                if basement_floors is not None and basement_floors > 0:
                    details['basement_floors'] = basement_floors
        elif '階' in label and '建' not in label:
            details['floor'] = value
            floor_match = re.search(r'(\d+)階/(\d+)階建', value)
            if floor_match:
                details['floor_number'] = extract_floor_number(floor_match.group(1))
                details['total_floors'] = normalize_integer(floor_match.group(2))
                _, basement_floors = extract_total_floors(value)
                if basement_floors is not None and basement_floors > 0:
                    details['basement_floors'] = basement_floors
            else:
                floor_match = re.search(r'(\d+)階', value)
                if floor_match:
                    details['floor_number'] = int(floor_match.group(1))
        elif '交通' in label or '最寄' in label or '駅' in label:
            station_info = value.replace('、', '\n')
            station_info = re.sub(
                r'(?=東京メトロ|都営|ＪＲ|京王|小田急|東急|京急|京成|新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス)',
                '\n',
                station_info
            ).strip()
            details['station_info'] = station_info
        elif '向き' in label or '方角' in label or 'バルコニー' in label or '採光' in label:
            direction = normalize_direction(value)
            if direction:
                details['direction'] = direction
        elif '管理費' in label:
            # "管理費等"も含めて処理する
            management_fee = extract_monthly_fee(value)
            if management_fee:
                details['management_fee'] = management_fee
        elif '修繕積立金' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                details['repair_fund'] = repair_fund
        elif '部屋番号' in label or '号室' in label:
            details['room_number'] = value
        elif '権利' in label and ('土地' in label or '敷地' in label):
            details['land_rights'] = value
        elif '駐車' in label:
            details['parking_info'] = value
        elif '主要採光面' in label:
            direction = normalize_direction(value)
            if direction:
                details['direction'] = direction
        elif 'バルコニー面積' in label or ('バルコニー' in label and '面積' in value):
            area = extract_area(value)
            if area:
                details['balcony_area'] = area
        elif '備考' in label:
            details['remarks'] = value
        elif '情報公開日' in label:
            published_date = self._extract_date(value)
            if published_date:
                details['first_published_at'] = published_date
        elif '情報提供日' in label or '情報更新日' in label or '登録日' in label:
            published_date = self._extract_date(value)
            if published_date:
                details['published_at'] = published_date
    
    def _extract_date(self, text: str) -> Optional[datetime]:
        """日付を抽出"""
        date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', text)
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            return datetime(year, month, day)
        return None
    
    def _extract_date_from_page(self, soup: BeautifulSoup, page_text: str) -> Optional[datetime]:
        """ページ全体から情報公開日を取得"""
        # class属性から探す
        date_elements = soup.select('[class*="date"], [class*="update"], [class*="公開"], [class*="info"]')
        for elem in date_elements:
            text = elem.get_text(strip=True)
            if '情報公開日' in text or '掲載日' in text or '登録日' in text:
                date = self._extract_date(text)
                if date:
                    return date
        
        # ページ全体から探す
        date_pattern = re.search(r'情報公開日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', page_text)
        if date_pattern:
            return self._extract_date(date_pattern.group(0))
        
        return None
    
    def _extract_agency_info(self, soup: BeautifulSoup, page_text: str) -> Tuple[Optional[str], Optional[str]]:
        """不動産会社情報を取得"""
        agency_name = None
        agency_tel = None
        
        # 会社情報セクションから探す
        company_sections = soup.select('.companyInfo, .company-info, [class*="company"]')
        for section in company_sections:
            for table in section.select('table'):
                for row in table.select('tr'):
                    cells = row.select('th, td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        if '会社名' in label or '社名' in label:
                            agency_name = value
                        elif 'TEL' in label or '電話' in label:
                            tel_match = re.search(r'[\d\-\(\)]+', value)
                            if tel_match:
                                agency_tel = tel_match.group(0).replace('(', '').replace(')', '-')
        
        # ページ全体から探す
        if not agency_name:
            company_pattern = re.search(r'(?:会社名|取扱会社|情報提供元)[：:]\s*([^\n]+)', page_text)
            if company_pattern:
                company_name = company_pattern.group(1).strip().split('　')[0].split(' ')[0]
                if len(company_name) > 2 and ('株式会社' in company_name or '有限会社' in company_name):
                    agency_name = company_name
        
        # 問合せ先から探す
        if not agency_name:
            inquiry_pattern = re.search(r'問合せ先[：:]\s*([^\n]+)', page_text)
            if inquiry_pattern:
                company_text = inquiry_pattern.group(1).strip()
                company_match = re.search(r'((?:株式会社|有限会社)?[^\s　]+(?:株式会社|有限会社)?)', company_text)
                if company_match:
                    agency_name = re.sub(r'(会社情報|ポイント|〜).*$', '', company_match.group(1)).strip()
        
        # 電話番号を探す
        if not agency_tel:
            tel_pattern = re.search(r'(?:TEL|電話|問合せ)[：:]\s*([\d\-\(\)]+)', page_text)
            if tel_pattern:
                agency_tel = tel_pattern.group(1).replace('(', '').replace(')', '-')
        
        return agency_name, agency_tel
    
    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """画像URLを抽出"""
        image_urls = []
        
        # メイン画像
        main_image = soup.select_one('.mainPhoto img, .photo img, [class*="main-image"] img')
        if main_image and main_image.get('src'):
            image_urls.append(urljoin(self.BASE_URL, main_image.get('src')))
        
        # サブ画像
        sub_images = soup.select('.subPhoto img, .thumbs img, [class*="sub-image"] img, .gallery img')
        for img in sub_images[:9]:  # 最大10枚（メイン1枚 + サブ9枚）
            if img.get('src'):
                image_urls.append(urljoin(self.BASE_URL, img.get('src')))
        
        return image_urls
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            self.logger.info(f"[HOMES] parse_property_detail called for URL: {url}")
            
            # 建物ページURLの検出
            is_building_page = '/mansion/b-' in url and not re.search(r'/\d{3,4}[A-Z]?/$', url)
            if is_building_page:
                self.logger.info(f"[HOMES] Building URL detected, will be redirected to property: {url}")
            
            time.sleep(self.delay)
            
            soup = self.fetch_page(url)
            if not soup:
                return None
            
            property_data = {'url': url}
            page_text = soup.get_text()
            
            # URLから物件IDを抽出
            if not self._extract_site_property_id(url, property_data):
                self.logger.error(f"[HOMES] 詳細ページでsite_property_idを取得できませんでした: {url}")
                return None
            
            # 建物名と部屋番号
            building_name, room_number = self._extract_building_name_and_room(soup)
            if building_name:
                property_data['building_name'] = building_name
                property_data['title'] = building_name
            else:
                property_data['title'] = '物件名不明'
            
            if room_number:
                property_data['room_number'] = room_number
            
            # 価格
            price = self._extract_price(soup, page_text)
            if price:
                property_data['price'] = price
            
            # 詳細情報（dl要素）
            dl_details = self._extract_property_details_from_dl(soup)
            property_data.update(dl_details)
            
            # 詳細情報（テーブル）
            table_details = self._extract_property_details_from_table(soup)
            property_data.update(table_details)
            
            # 建物ページの場合、面積情報の妥当性を確認
            if is_building_page and 'area' in property_data:
                area_value = property_data.get('area')
                # 専有面積として妥当な範囲（10-300㎡）であれば保持
                if area_value and 10 <= area_value <= 300:
                    self.logger.info(f"[HOMES] 建物ページですが専有面積として妥当な値のため保持: {area_value}㎡")
                else:
                    self.logger.info(f"[HOMES] 建物ページで異常な面積値のため削除: {area_value}㎡")
                    del property_data['area']
            
            # 情報公開日
            if 'published_at' not in property_data:
                published_at = self._extract_date_from_page(soup, page_text)
                if published_at:
                    property_data['published_at'] = published_at
                    if 'first_published_at' not in property_data:
                        property_data['first_published_at'] = published_at
            
            # 不動産会社情報
            agency_name, agency_tel = self._extract_agency_info(soup, page_text)
            if agency_name:
                property_data['agency_name'] = agency_name
            if agency_tel:
                property_data['agency_tel'] = agency_tel
            
            # 画像URL
            image_urls = self._extract_images(soup)
            if image_urls:
                property_data['image_urls'] = image_urls
                property_data['image_url'] = image_urls[0]  # 後方互換性
            
            # 物件説明
            description_elem = soup.select_one('.comment, .pr-comment, [class*="description"]')
            if description_elem:
                property_data['description'] = description_elem.get_text(strip=True)
            
            # デフォルト値設定
            property_data.setdefault('building_type', 'マンション')
            property_data.setdefault('address', '東京都港区')
            
            # 必須フィールドのチェック
            if not property_data.get('building_name'):
                self.record_field_extraction_error('building_name', url)
                self.logger.error(f"[HOMES] Building name not found for {url}")
                return None
            
            # 詳細ページでの必須フィールドを検証
            if not self.validate_detail_page_fields(property_data, url):
                return self.log_validation_error_and_return_none(property_data, url)
            
            return property_data
            
        except (TaskPausedException, TaskCancelledException):
            raise
        except Exception as e:
            self.log_detailed_error("詳細ページ解析エラー", url, e)
            return None
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと最小限の情報のみを抽出"""
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
                    full_url = urljoin(self.BASE_URL, href)
                    property_data = {
                        'url': full_url,
                        'has_update_mark': False
                    }
                    if self._extract_site_property_id(href, property_data):
                        # 一覧ページでの必須フィールドを検証（基底クラスの共通メソッドを使用）
                        if self.validate_list_page_fields(property_data):
                            properties.append(property_data)
                    else:
                        self.logger.error(f"[HOMES] 物件をスキップします（site_property_id取得失敗）: {full_url}")
            else:
                # 各物件行を処理
                for row in price_rows:
                    property_data = self._parse_property_row(row)
                    if property_data:
                        properties.append(property_data)
                        
                        # リアルタイムで統計を更新
                        if hasattr(self, '_scraping_stats'):
                            self._scraping_stats['properties_found'] = len(properties)
                        
                        # 処理上限チェック
                        if self.max_properties and len(properties) >= self.max_properties:
                            self.logger.info(f"[HOMES] Reached max properties limit ({self.max_properties})")
                            return properties
        
        return properties
    
    def _parse_property_row(self, row) -> Optional[Dict[str, Any]]:
        """物件行をパース"""
        property_link = row.select_one('a[href*="/mansion/b-"]')
        if not property_link:
            return None
        
        href = property_link.get('href', '')
        if '/mansion/b-' not in href:
            return None
        
        full_url = urljoin(self.BASE_URL, href)
        property_data = {
            'url': full_url,
            'has_update_mark': False
        }
        
        # 価格情報を取得
        tds = row.select('td')
        if len(tds) > 2:
            price_text = tds[2].get_text(strip=True)
            price = extract_price(price_text)
            if price:
                property_data['price'] = price
                self.logger.info(f"[HOMES] Found price: {price}万円 for {href}")
        
        # 物件IDを抽出
        if not self._extract_site_property_id(href, property_data):
            self.logger.error(f"[HOMES] 物件行をスキップします（site_property_id取得失敗）: {href}")
            return None
        
        return property_data
    
    def _extract_site_property_id(self, href: str, property_data: Dict[str, Any]) -> bool:
        """URLから物件IDを抽出
        
        Returns:
            bool: 抽出に成功した場合True
        """
        id_match = (re.search(r'/mansion/([0-9]+)/', href) or 
                   re.search(r'/mansion/b-([^/]+)/', href) or 
                   re.search(r'/detail-([0-9]+)/', href))
        if id_match:
            site_property_id = id_match.group(1)
            
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, href):
                self.logger.error(f"[HOMES] 不正なsite_property_idを検出しました: '{site_property_id}'")
                return False
                
            property_data['site_property_id'] = site_property_id
            self.logger.info(f"[HOMES] Extracted site_property_id: {site_property_id}")
            return True
        else:
            self.logger.error(f"[HOMES] サイト物件IDを抽出できません: URL={href}")
            return False
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        self.logger.info(f"[HOMES] Starting scrape for area: {area}")
        
        # エリアコードの確認
        from .area_config import get_area_code, get_homes_city_code
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        self.logger.info(f"[HOMES] Area conversion: {area} -> {area_code} -> {city_code}")
        
        # 共通ロジックを使用
        return self.common_scrape_area_logic(area, max_pages)
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存"""
        self.process_property_data(property_data, existing_listing)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        url = property_data.get('url', '')
        if '/mansion/b-' in url and not re.search(r'/\d{3,4}[A-Z]?/$', url):
            self.logger.info(f"[HOMES] Processing building URL (will redirect to property): {url}")
        
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self._save_property_after_detail
        )
    
    def _save_property_after_detail(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """詳細データ取得後の保存処理"""
        return self.save_property_common(property_data, existing_listing)
    
    def fetch_and_update_detail(self, listing) -> bool:
        """詳細ページを取得して情報を更新"""
        try:
            detail_data = self.parse_property_detail(listing.url)
            if not detail_data:
                return False
            
            # マスター物件の情報を更新
            if detail_data.get('floor_number') and not listing.master_property.floor_number:
                listing.master_property.floor_number = detail_data['floor_number']
                print(f"    階数を更新: {detail_data['floor_number']}階")
            
            if detail_data.get('area') and not listing.master_property.area:
                listing.master_property.area = detail_data['area']
                print(f"    面積を更新: {detail_data['area']}㎡")
            
            if detail_data.get('layout') and not listing.master_property.layout:
                listing.master_property.layout = detail_data['layout']
                print(f"    間取りを更新: {detail_data['layout']}")
            
            if detail_data.get('direction') and not listing.master_property.direction:
                listing.master_property.direction = detail_data['direction']
                print(f"    方角を更新: {detail_data['direction']}")
            
            if detail_data.get('room_number') and not listing.master_property.room_number:
                listing.master_property.room_number = detail_data['room_number']
                print(f"    部屋番号を更新: {detail_data['room_number']}")
            
            if detail_data.get('balcony_area') and not listing.master_property.balcony_area:
                listing.master_property.balcony_area = detail_data['balcony_area']
                print(f"    バルコニー面積を更新: {detail_data['balcony_area']}㎡")
            
            # 掲載情報を更新
            if detail_data.get('description'):
                listing.description = detail_data['description']
            
            if detail_data.get('station_info'):
                listing.station_info = detail_data['station_info']
            
            if detail_data.get('management_fee'):
                listing.management_fee = detail_data['management_fee']
                print(f"    管理費を更新: {detail_data['management_fee']}円")
            
            if detail_data.get('repair_fund'):
                listing.repair_fund = detail_data['repair_fund']
                print(f"    修繕積立金を更新: {detail_data['repair_fund']}円")
            
            if detail_data.get('agency_name'):
                listing.agency_name = detail_data['agency_name']
                print(f"    不動産会社を更新: {detail_data['agency_name']}")
            
            if detail_data.get('agency_tel'):
                listing.agency_tel = detail_data['agency_tel']
                print(f"    不動産会社電話番号を更新: {detail_data['agency_tel']}")
            
            if detail_data.get('remarks'):
                listing.remarks = detail_data['remarks']
                print(f"    備考を更新")
            
            # 画像を追加
            if detail_data.get('image_urls'):
                self.add_property_images(listing, detail_data['image_urls'])
            elif detail_data.get('image_url'):
                self.add_property_images(listing, [detail_data['image_url']])
            
            # 建物情報を更新
            building = listing.master_property.building
            if detail_data.get('total_floors') and not building.total_floors:
                building.total_floors = detail_data['total_floors']
                print(f"    総階数を更新: {detail_data['total_floors']}階")
            
            if detail_data.get('basement_floors') is not None and not building.basement_floors:
                building.basement_floors = detail_data['basement_floors']
                if detail_data['basement_floors'] > 0:
                    print(f"    地下階数を更新: {detail_data['basement_floors']}階")
            
            if detail_data.get('structure') and not building.structure:
                building.structure = detail_data['structure']
                print(f"    構造を更新: {detail_data['structure']}")
            
            if detail_data.get('land_rights') and not building.land_rights:
                building.land_rights = detail_data['land_rights']
                print(f"    権利形態を更新: {detail_data['land_rights']}")
            
            if detail_data.get('parking_info') and not building.parking_info:
                building.parking_info = detail_data['parking_info']
                print(f"    駐車場情報を更新: {detail_data['parking_info']}")
            
            if detail_data.get('built_year') and not building.built_year:
                building.built_year = detail_data['built_year']
                print(f"    築年を更新: {detail_data['built_year']}年")
            
            # 詳細情報を保存
            detail_info = {}
            for key in ['age', 'floor', 'total_floors']:
                if key in detail_data:
                    detail_info[key] = detail_data[key]
            
            listing.detail_info = detail_info
            listing.detail_fetched_at = datetime.now()
            listing.has_update_mark = False
            
            self.session.commit()
            return True
            
        except (TaskPausedException, TaskCancelledException):
            raise
        except Exception as e:
            print(f"    詳細ページ取得エラー - {type(e).__name__}: {str(e)}")
            self.log_detailed_error("詳細ページ取得エラー", property_data.get('url', '不明'), e,
                                  {'building_name': property_data.get('building_name', ''),
                                   'price': property_data.get('price', '')})
            return False