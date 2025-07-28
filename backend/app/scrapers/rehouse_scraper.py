"""
三井のリハウススクレイパー実装

URLパターン:
- 一覧: https://www.rehouse.co.jp/buy/mansion/prefecture/{都道府県}/city/{市区町村}/
- 詳細: https://www.rehouse.co.jp/buy/mansion/bkdetail/{物件コード}/
"""

import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
import logging

from bs4 import BeautifulSoup
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
    
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties)
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
        })
    
    def get_list_url(self, prefecture: str = "13", city: str = "13103", page: int = 1) -> str:
        """一覧ページのURLを生成"""
        # 三井のリハウスのURLパターン
        base_url = f"{self.BASE_URL}/buy/mansion/prefecture/{prefecture}/city/{city}/"
        
        # ページングパラメータ
        # 三井のリハウスは ?page= パラメータを使用
        if page > 1:
            return f"{base_url}?page={page}"
        return base_url
    
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
        
        # 三井のリハウスの物件カード構造
        # div.property-index-card が物件カードのコンテナ
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
        
        if not property_items:
            logger.warning("No property items found on the page")
            return properties
        
        for item in property_items:
            try:
                property_data = self._parse_property_item(item)
                if property_data:
                    properties.append(property_data)
            except Exception as e:
                logger.error(f"Error parsing property item: {e}")
                continue
        
        return properties
    
    def _parse_property_item(self, item) -> Optional[Dict]:
        """個別の物件要素から情報を抽出"""
        property_data = {}
        
        # 詳細ページへのリンク（「詳細を見る」リンク）
        link_elem = item.select_one('a[href*="/bkdetail/"]')
        if not link_elem:
            # 他のパターンも試す
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
        if code_match:
            property_data['property_code'] = code_match.group(1)
        
        
        # property-index-card-inner内の情報を取得
        inner = item.select_one('.property-index-card-inner')
        if not inner:
            return None
        
        # 全テキストを取得
        full_text = inner.get_text(' ', strip=True)
        
        # 価格
        # データ正規化フレームワークを使用して価格を抽出
        price = extract_price(full_text)
        if price:
            property_data['price'] = price
        
        # description-section内の詳細情報
        desc_section = inner.select_one('.description-section')
        if desc_section:
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
            # 例: "2LDK / 54.09㎡ / 1979年04月築 / 3階"
            info_pattern = r'([1-9][LDKS]+|ワンルーム)\s*/\s*(\d+(?:\.\d+)?)㎡\s*/\s*(\d{4})年(\d{2})月築\s*/\s*(\d+)階'
            info_match = re.search(info_pattern, desc_text)
            if info_match:
                property_data['layout'] = info_match.group(1)
                property_data['area'] = float(info_match.group(2))
                property_data['built_year'] = int(info_match.group(3))
                property_data['floor_number'] = int(info_match.group(5))
            else:
                # 個別に抽出
                # 間取り
                # データ正規化フレームワークを使用して間取りを正規化
                layout = normalize_layout(desc_text)
                if layout:
                    property_data['layout'] = layout
                
                # 面積
                # データ正規化フレームワークを使用して面積を抽出
                area = extract_area(desc_text)
                if area:
                    property_data['area'] = area
                
                # 築年
                # データ正規化フレームワークを使用して築年を抽出
                built_year = extract_built_year(desc_text)
                if built_year:
                    property_data['built_year'] = built_year
                
                # 所在階
                # データ正規化フレームワークを使用して階数を抽出
                floor_number = extract_floor_number(desc_text)
                if floor_number is not None:
                    property_data['floor_number'] = floor_number
        
        return property_data
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（共通インターフェース用）"""
        # 共通の詳細チェック処理を使用
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
            property_data = {'url': url, 'source_site': self.SOURCE_SITE}
            
            # 物件名
            h1_elem = soup.find('h1')
            if h1_elem:
                property_data['building_name'] = h1_elem.get_text(strip=True)
            
            # 価格
            price_elem = soup.find(text=re.compile(r'\d+万円'))
            if price_elem:
                # データ正規化フレームワークを使用して価格を抽出
                price = extract_price(price_elem)
                if price:
                    property_data['price'] = price
            
            # 物件概要テーブルから情報を抽出
            tables = soup.select('table')
            for table in tables:
                rows = table.select('tr')
                for row in rows:
                    cells = row.select('th, td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        # 所在階/総階数
                        if '階数' in label and '階建' in label:  # 「階数 / 階建」フィールド
                            # 例: "36階 / 地上37階 地下1階建"
                            # 所在階
                            floor_match = re.search(r'^(\d+)階', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                            # 総階数
                            total_floors_match = re.search(r'地上(\d+)階', value)
                            if total_floors_match:
                                property_data['total_floors'] = int(total_floors_match.group(1))
                        elif '所在階' in label:
                            floor_match = re.search(r'(\d+)階', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                        
                        # 建物構造（「階数 / 階建」で処理した場合はスキップ）
                        elif '構造' in label or '建物' in label:
                            # データ正規化フレームワークを使用して総階数と地下階数を抽出
                            total_floors, basement_floors = extract_total_floors(value)
                            if total_floors is not None and 'total_floors' not in property_data:
                                property_data['total_floors'] = total_floors
                            if basement_floors is not None and basement_floors > 0:
                                property_data['basement_floors'] = basement_floors
                        
                        # 専有面積
                        elif '専有面積' in label or '面積' in label:
                            # データ正規化フレームワークを使用して面積を抽出
                            area = extract_area(value)
                            if area:
                                property_data['area'] = area
                        
                        # 間取り
                        elif '間取り' in label:
                            # データ正規化フレームワークを使用して間取りを正規化
                            layout = normalize_layout(value)
                            if layout:
                                property_data['layout'] = layout
                        
                        # バルコニー面積
                        elif 'バルコニー' in label and '面積' in label:
                            # データ正規化フレームワークを使用して面積を抽出
                            balcony_area = extract_area(value)
                            if balcony_area:
                                property_data['balcony_area'] = balcony_area
                        
                        # 向き/主要採光面
                        elif '向き' in label or '採光' in label or 'バルコニー' in label:
                            # データ正規化フレームワークを使用して方角を正規化
                            direction = normalize_direction(value)
                            if direction:
                                property_data['direction'] = direction
                        
                        # 築年月
                        elif '築年月' in label:
                            # データ正規化フレームワークを使用して築年を抽出
                            built_year = extract_built_year(value)
                            if built_year:
                                property_data['built_year'] = built_year
                                # 月情報も取得
                                month_match = re.search(r'(\d{1,2})月', value)
                                if month_match:
                                    property_data['built_month'] = int(month_match.group(1))
                        
                        # 管理費
                        elif '管理費' in label:
                            # データ正規化フレームワークを使用して月額費用を抽出
                            management_fee = extract_monthly_fee(value)
                            if management_fee:
                                property_data['management_fee'] = management_fee
                        
                        # 修繕積立金
                        elif '修繕積立金' in label or '修繕積立費' in label:
                            # データ正規化フレームワークを使用して月額費用を抽出
                            repair_fund = extract_monthly_fee(value)
                            if repair_fund:
                                property_data['repair_reserve_fund'] = repair_fund
                        
                        # 所在地/住所
                        elif '所在地' in label or '住所' in label:
                            # GoogleMapsなどの不要な文字を削除
                            address = re.sub(r'GoogleMaps.*$', '', value).strip()
                            property_data['address'] = address
                        
                        # 交通/最寄り駅
                        elif '交通' in label or '駅' in label:
                            # 駅ごとに改行を入れて視認性を向上
                            # 「駅徒歩」の後で分割
                            station_info = value
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
                            property_data['station_info'] = '\n'.join(formatted_stations)
                        
                        # 取引態様
                        elif '取引態様' in label:
                            property_data['transaction_type'] = value
                        
                        # 現況
                        elif '現況' in label:
                            property_data['current_status'] = value
                        
                        # 引渡時期
                        elif '引渡' in label:
                            property_data['delivery_date'] = value
            
            # dlリスト構造からも情報を取得
            dl_elements = soup.select('dl')
            for dl in dl_elements:
                dt_elements = dl.select('dt')
                dd_elements = dl.select('dd')
                
                for i, dt in enumerate(dt_elements):
                    if i < len(dd_elements):
                        label = dt.get_text(strip=True)
                        value = dd_elements[i].get_text(strip=True)
                        
                        # 上記と同様のパターンマッチング
                        if '所在階' in label and 'floor_number' not in property_data:
                            floor_match = re.search(r'(\d+)階', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
            
            # 不動産会社情報
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
            
            # 物件の特徴/備考
            remarks_selectors = [
                '.remarks', '.feature', '.comment', '.description',
                '[class*="remark"]', '[class*="feature"]', '[class*="comment"]'
            ]
            
            remarks_texts = []
            for selector in remarks_selectors:
                remarks_elem = soup.select_one(selector)
                if remarks_elem:
                    text = remarks_elem.get_text(strip=True)
                    if text and len(text) > 10:  # 短すぎるテキストは除外
                        remarks_texts.append(text)
            
            if remarks_texts:
                property_data['remarks'] = '\n'.join(remarks_texts)
                # 要約も生成（簡易的に最初の200文字を使用）
                property_data['summary_remarks'] = property_data['remarks'][:200]
            
            # 画像URL
            image_urls = []
            img_selectors = [
                'img[src*="property"]', 'img[src*="bukken"]',
                '.property-image img', '.photo img'
            ]
            
            for selector in img_selectors:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = img.get('src')
                    if src:
                        if not src.startswith('http'):
                            src = urljoin(self.BASE_URL, src)
                        if src not in image_urls:
                            image_urls.append(src)
            
            if image_urls:
                property_data['image_urls'] = image_urls[:10]  # 最大10枚
            
            return property_data
            
        except Exception as e:
            # TaskCancelledExceptionの場合は再スロー
            from ..utils.exceptions import TaskCancelledException
            if isinstance(e, TaskCancelledException):
                raise
            logger.error(f"Error fetching property detail from {url}: {e}")
            return None
    
    def scrape_area(self, area: str = "minato", max_pages: int = 5):
        """エリアの物件をスクレイピング（東京都港区に対応）"""
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 三井のリハウスは東京都のみ対応
        prefecture = "13"  # 東京都
        city = area_code  # 区コード
        
        # 共通ロジックを使用（価格変更ベースのスマートスクレイピングを含む）
        return self.common_scrape_area_logic(area, max_pages)
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報をデータベースに保存"""
        try:
            # 必須フィールドの確認
            if not property_data.get('building_name') or not property_data.get('price'):
                print(f"    → 必須情報不足（建物名: {property_data.get('building_name')}, 価格: {property_data.get('price')}）")
                return False
            
            print(f"    → 価格: {property_data['price']}万円, 面積: {property_data.get('area', '不明')}㎡, 階数: {property_data.get('floor_number', '不明')}階")
            
            # 建物を取得または作成
            building, extracted_room_number = self.get_or_create_building(
                property_data['building_name'],
                property_data.get('address', ''),
                built_year=property_data.get('built_year'),
                total_floors=property_data.get('total_floors')
            )
            
            if not building:
                print(f"    → 建物情報作成失敗")
                return False
            
            # 部屋番号の決定（抽出された部屋番号を優先）
            room_number = property_data.get('room_number', '')
            if extracted_room_number and not room_number:
                room_number = extracted_room_number
                print(f"    → 建物名から部屋番号を抽出: {room_number}")
            
            # マスター物件を取得または作成
            master_property = self.get_or_create_master_property(
                building=building,
                room_number=room_number,
                floor_number=property_data.get('floor_number'),
                area=property_data.get('area'),
                layout=property_data.get('layout'),
                direction=property_data.get('direction'),
                url=property_data.get('url')
            )
            
            # バルコニー面積を設定
            if property_data.get('balcony_area'):
                master_property.balcony_area = property_data['balcony_area']
            
            # 掲載情報を作成または更新
            listing, update_type = self.create_or_update_listing(
                master_property=master_property,
                url=property_data['url'],
                title=property_data.get('building_name', ''),
                price=property_data['price'],
                agency_name=property_data.get('agency_name'),
                site_property_id=property_data.get('property_code', ''),
                description=property_data.get('description'),
                station_info=property_data.get('station_info'),
                management_fee=property_data.get('management_fee'),
                repair_fund=property_data.get('repair_reserve_fund'),
                published_at=property_data.get('published_at'),
                first_published_at=property_data.get('first_published_at'),
                # 掲載サイトごとの物件属性
                listing_floor_number=property_data.get('floor_number'),
                listing_area=property_data.get('area'),
                listing_layout=property_data.get('layout'),
                listing_direction=property_data.get('direction'),
                listing_total_floors=property_data.get('total_floors'),
                listing_balcony_area=property_data.get('balcony_area'),
                listing_address=property_data.get('address')
            )
            
            # 追加フィールドの設定
            if property_data.get('agency_tel'):
                listing.agency_tel = property_data['agency_tel']
            if property_data.get('remarks'):
                listing.remarks = property_data['remarks']
            if property_data.get('summary_remarks'):
                listing.summary_remarks = property_data['summary_remarks']
            
            # 画像を追加
            if property_data.get('image_urls'):
                self.add_property_images(listing, property_data['image_urls'])
            
            # 詳細情報を保存
            listing.detail_info = {
                'transaction_type': property_data.get('transaction_type'),
                'current_status': property_data.get('current_status'),
                'delivery_date': property_data.get('delivery_date'),
                'built_month': property_data.get('built_month')
            }
            listing.detail_fetched_at = datetime.now()
            
            # 多数決による物件情報更新
            self.update_master_property_by_majority(master_property)
            
            # 更新タイプをproperty_dataに設定（統計用）
            property_data['update_type'] = update_type
            property_data['property_saved'] = True
            
            # コミットはscrape_areaメソッドで一括で行うので、ここではflushのみ
            self.session.flush()
            print(f"    → 保存成功")
            return True
            
        except Exception as e:
            # TaskCancelledExceptionの場合は再スロー
            from ..utils.exceptions import TaskCancelledException
            if isinstance(e, TaskCancelledException):
                raise
            print(f"    → 保存エラー: {e}")
            self.session.rollback()
            return False