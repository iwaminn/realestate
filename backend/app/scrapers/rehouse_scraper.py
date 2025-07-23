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

from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class RehouseScraper(BaseScraper):
    """三井のリハウス用スクレイパー"""
    
    SOURCE_SITE = "rehouse"
    BASE_URL = "https://www.rehouse.co.jp"
    
    # 都道府県と市区町村のコード（東京都港区の例）
    # 実際の運用では設定ファイルから読み込む
    AREA_CONFIG = {
        "tokyo_minato": {
            "prefecture": "13",  # 東京都
            "city": "13103"      # 港区
        }
    }
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties)
        self.http_session = requests.Session()
        self.http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
        })
    
    def get_list_url(self, prefecture: str = "13", city: str = "13103", page: int = 1) -> str:
        """一覧ページのURLを生成"""
        # 三井のリハウスのURLパターン
        base_url = f"{self.BASE_URL}/buy/mansion/prefecture/{prefecture}/city/{city}/"
        
        # ページングパラメータ
        if page > 1:
            return f"{base_url}?p={page}"
        return base_url
    
    def parse_property_list(self, html: str) -> List[Dict]:
        """一覧ページから物件情報を抽出"""
        soup = BeautifulSoup(html, 'html.parser')
        properties = []
        
        # 物件リストのセレクタを試す（複数のパターン）
        selectors = [
            'article.property-item',
            'div.property-item',
            'li.property-item',
            'div.bukken-item',
            'article[class*="property"]',
            'div[class*="bukken"]',
            '.propertyUnit',
            '.property-unit',
            'section.property'
        ]
        
        property_items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                property_items = items
                logger.info(f"Found {len(items)} properties using selector: {selector}")
                break
        
        if not property_items:
            # より一般的なパターンで探す
            # 物件情報を含む可能性のある要素を探す
            all_divs = soup.find_all('div', class_=True)
            for div in all_divs:
                text = div.get_text()
                # 物件情報の特徴的なパターン
                if '万円' in text and ('㎡' in text or '平米' in text):
                    classes = div.get('class', [])
                    # 広告やヘッダー要素を除外
                    if not any(skip in ' '.join(classes).lower() for skip in ['header', 'footer', 'nav', 'ad']):
                        property_items.append(div)
        
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
        
        # 詳細ページへのリンク
        link_elem = item.select_one('a[href*="/bkdetail/"], a[href*="/detail/"]')
        if not link_elem:
            # すべてのリンクから探す
            all_links = item.select('a[href]')
            for link in all_links:
                href = link.get('href', '')
                if '/bkdetail/' in href or '/detail/' in href:
                    link_elem = link
                    break
        
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
        
        # 建物名
        building_name = None
        # 複数のパターンで建物名を探す
        name_selectors = ['h3', 'h4', '.title', '.name', '.building-name', '.bukken-name']
        for selector in name_selectors:
            name_elem = item.select_one(selector)
            if name_elem:
                building_name = name_elem.get_text(strip=True)
                break
        
        if not building_name and link_elem:
            # リンクのテキストから取得
            building_name = link_elem.get_text(strip=True)
        
        if building_name:
            property_data['building_name'] = building_name
        
        # 価格
        price_text = item.get_text()
        price_match = re.search(r'(\d+(?:,\d{3})*)\s*万円', price_text)
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            property_data['price'] = int(price_str)
        
        # 面積
        area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|平米|m²)', price_text)
        if area_match:
            property_data['area'] = float(area_match.group(1))
        
        # 間取り
        layout_match = re.search(r'([1-9][LDKS]+|ワンルーム)', price_text)
        if layout_match:
            property_data['layout'] = layout_match.group(1)
        
        # 所在階
        floor_match = re.search(r'(\d+)階(?!建)', price_text)
        if floor_match:
            property_data['floor_number'] = int(floor_match.group(1))
        
        # 総階数
        total_floors_match = re.search(r'(\d+)階建', price_text)
        if total_floors_match:
            property_data['total_floors'] = int(total_floors_match.group(1))
        
        # 住所（エリア情報）
        address_patterns = [
            r'(東京都[^\s]+区[^\s]+?)(?:GoogleMaps|$)',
            r'([^\s]+区[^\s]+(?:丁目|番地))(?:GoogleMaps|$)',
            r'([^\s]+区[^\s]+?)(?:GoogleMaps|$)'
        ]
        
        for pattern in address_patterns:
            address_match = re.search(pattern, price_text)
            if address_match:
                property_data['address'] = address_match.group(1).strip()
                break
        
        return property_data
    
    def get_property_detail(self, url: str) -> Optional[Dict]:
        """詳細ページから物件情報を取得"""
        try:
            response = self.http_session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            property_data = {'url': url, 'source_site': self.SOURCE_SITE}
            
            # 物件名
            h1_elem = soup.find('h1')
            if h1_elem:
                property_data['building_name'] = h1_elem.get_text(strip=True)
            
            # 価格
            price_elem = soup.find(text=re.compile(r'\d+万円'))
            if price_elem:
                price_match = re.search(r'(\d+(?:,\d{3})*)\s*万円', price_elem)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    property_data['price'] = int(price_str)
            
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
                            # 構造情報のみ処理
                            if 'total_floors' not in property_data:
                                # 「地上14階建」や「14階建」などのパターンに対応
                                total_floors_match = re.search(r'(?:地上)?(\d+)階建', value)
                                if total_floors_match:
                                    property_data['total_floors'] = int(total_floors_match.group(1))
                        
                        # 専有面積
                        elif '専有面積' in label or '面積' in label:
                            area_match = re.search(r'(\d+(?:\.\d+)?)', value)
                            if area_match:
                                property_data['area'] = float(area_match.group(1))
                        
                        # 間取り
                        elif '間取り' in label:
                            property_data['layout'] = value
                        
                        # バルコニー面積
                        elif 'バルコニー' in label and '面積' in label:
                            balcony_match = re.search(r'(\d+(?:\.\d+)?)', value)
                            if balcony_match:
                                property_data['balcony_area'] = float(balcony_match.group(1))
                        
                        # 向き/主要採光面
                        elif '向き' in label or '採光' in label or 'バルコニー' in label:
                            direction_patterns = ['南', '北', '東', '西', '南東', '南西', '北東', '北西']
                            for direction in direction_patterns:
                                if direction in value:
                                    property_data['direction'] = direction
                                    break
                        
                        # 築年月
                        elif '築年月' in label:
                            year_match = re.search(r'(\d{4})年', value)
                            month_match = re.search(r'(\d{1,2})月', value)
                            if year_match:
                                property_data['built_year'] = int(year_match.group(1))
                                if month_match:
                                    property_data['built_month'] = int(month_match.group(1))
                        
                        # 管理費
                        elif '管理費' in label:
                            fee_match = re.search(r'(\d+(?:,\d{3})*)', value)
                            if fee_match:
                                property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                        
                        # 修繕積立金
                        elif '修繕積立金' in label or '修繕積立費' in label:
                            fee_match = re.search(r'(\d+(?:,\d{3})*)', value)
                            if fee_match:
                                property_data['repair_reserve_fund'] = int(fee_match.group(1).replace(',', ''))
                        
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
            logger.error(f"Error fetching property detail from {url}: {e}")
            return None
    
    def scrape_area(self, area: str = "minato", max_pages: int = 5):
        """エリアの物件をスクレイピング（東京都港区に対応）"""
        # 三井のリハウスは東京都港区のみ対応しているため、areaは無視して固定値を使用
        area_config = self.AREA_CONFIG["tokyo_minato"]
        prefecture = area_config["prefecture"]
        city = area_config["city"]
        
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            try:
                list_url = self.get_list_url(prefecture, city, page)
                print(f"URL: {list_url}")
                
                response = self.http_session.get(list_url)
                response.raise_for_status()
                
                properties = self.parse_property_list(response.text)
                
                if not properties:
                    print(f"ページ {page} に物件が見つかりません")
                    break
                
                print(f"ページ {page} で {len(properties)} 件の物件を発見")
                
                # 詳細情報を取得してデータベースに保存
                saved_count = 0
                for i, prop in enumerate(properties):
                    if 'url' in prop:
                        print(f"  物件 {i+1}/{len(properties)}: {prop.get('building_name', 'Unknown')}")
                        
                        try:
                            # 詳細ページを取得
                            detail_data = self.get_property_detail(prop['url'])
                            if detail_data:
                                # 一覧ページのデータとマージ
                                prop.update(detail_data)
                                
                                # データベースに保存
                                saved = self.save_property(prop)
                                if saved:
                                    saved_count += 1
                            
                            time.sleep(self.delay)
                            
                        except Exception as e:
                            logger.error(f"詳細取得エラー: {e}")
                            continue
                
                print(f"ページ {page} から {saved_count} 件を保存")
                all_properties.extend(properties)
                
                # 最大取得件数に達したら終了
                if self.max_properties and len(all_properties) >= self.max_properties:
                    print(f"最大取得件数 {self.max_properties} に達しました")
                    break
                
                time.sleep(self.delay)
                
            except Exception as e:
                print(f"ページ {page} でエラー: {e}")
                continue
        
        print(f"合計 {len(all_properties)} 件の物件を取得")
        return all_properties
    
    def save_property(self, property_data: Dict[str, Any]) -> bool:
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
            listing = self.create_or_update_listing(
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
            
            self.session.commit()
            print(f"    → 保存成功")
            return True
            
        except Exception as e:
            print(f"    → 保存エラー: {e}")
            self.session.rollback()
            return False