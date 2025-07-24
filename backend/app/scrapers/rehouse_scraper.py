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
        if page > 1:
            return f"{base_url}?p={page}"
        return base_url
    
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
        
        # 建物名を探す
        # h3タグまたはtitleクラスを持つ要素
        building_name = None
        name_elem = item.select_one('h3')
        if name_elem:
            building_name = name_elem.get_text(strip=True)
        else:
            # property-index-card-inner内のテキストから探す
            inner = item.select_one('.property-index-card-inner')
            if inner:
                # 最初の大きなテキスト要素を建物名とする
                for elem in inner.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div']):
                    text = elem.get_text(strip=True)
                    if text and len(text) > 5 and not any(skip in text for skip in ['詳細を見る', '万円', '㎡', '駅']):
                        building_name = text
                        break
        
        if building_name:
            property_data['building_name'] = building_name
        else:
            # URLから建物IDを使用
            code_match = re.search(r'/bkdetail/([^/]+)/', detail_url)
            if code_match:
                property_data['building_name'] = f"物件コード: {code_match.group(1)}"
        
        # property-index-card-inner内の情報を取得
        inner = item.select_one('.property-index-card-inner')
        if not inner:
            return None
        
        # 全テキストを取得
        full_text = inner.get_text(' ', strip=True)
        
        # 建物名を抽出（「NEW」「中古マンション」などを除去）
        name_match = re.match(r'^(?:NEW\s*)?(?:中古マンション\s*)?([^\d]+?)\s*\d+[,\d]*\s*万円', full_text)
        if name_match:
            building_name = name_match.group(1).strip()
            if building_name:
                property_data['building_name'] = building_name
        
        # 価格
        price_match = re.search(r'(\d+(?:,\d{3})*)\s*万円', full_text)
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            property_data['price'] = int(price_str)
        
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
                layout_match = re.search(r'([1-9][LDKS]+|ワンルーム)', desc_text)
                if layout_match:
                    property_data['layout'] = layout_match.group(1)
                
                # 面積
                area_match = re.search(r'(\d+(?:\.\d+)?)\s*㎡', desc_text)
                if area_match:
                    property_data['area'] = float(area_match.group(1))
                
                # 築年
                built_match = re.search(r'(\d{4})年', desc_text)
                if built_match:
                    property_data['built_year'] = int(built_match.group(1))
                
                # 所在階
                floor_match = re.search(r'(\d+)階', desc_text)
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))
        
        return property_data
    
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
        if self.force_detail_fetch:
            print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
            
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 三井のリハウスは東京都のみ対応
        prefecture = "13"  # 東京都
        city = area_code  # 区コード
        
        print(f"エリア: {area} → 東京都 (区コード: {city})")
        
        # ===== フェーズ1: 物件一覧の収集 =====
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            try:
                list_url = self.get_list_url(prefecture, city, page)
                print(f"URL: {list_url}")
                
                soup = self.fetch_page(list_url)
                if not soup:
                    print(f"ページ {page} の取得に失敗しました")
                    break
                
                properties = self.parse_property_list(soup)
                
                if not properties:
                    print(f"ページ {page} に物件が見つかりません")
                    break
                
                print(f"ページ {page} で {len(properties)} 件の物件を発見")
                
                # max_propertiesを超えないように調整
                if self.max_properties and len(all_properties) + len(properties) > self.max_properties:
                    # 必要な分だけ取得
                    remaining = self.max_properties - len(all_properties)
                    properties = properties[:remaining]
                    print(f"  → 最大取得件数に合わせて {remaining} 件のみ使用")
                
                # 物件発見数を記録
                self.record_property_found(len(properties))
                all_properties.extend(properties)
                
                # max_propertiesに達したらループを抜ける
                if self.max_properties and len(all_properties) >= self.max_properties:
                    print(f"最大取得件数（{self.max_properties}件）に達しました")
                    break
                
                # ページ間の遅延
                time.sleep(self.delay)
                
            except Exception as e:
                print(f"ページ {page} でエラー: {e}")
                continue
        
        # 処理対象数を記録（max_properties制限を考慮）
        total_to_process = min(len(all_properties), self.max_properties) if self.max_properties else len(all_properties)
        self.record_property_processed(total_to_process)
        
        # ===== フェーズ2: 詳細取得と保存 =====
        print(f"\n合計 {len(all_properties)} 件の物件を処理します...")
        
        # 既存の掲載を一括で取得（最適化）
        from ..models import PropertyListing
        all_urls = [prop['url'] for prop in all_properties if 'url' in prop]
        existing_listings_query = self.session.query(PropertyListing).filter(
            PropertyListing.url.in_(all_urls)
        ).all()
        existing_listings_map = {listing.url: listing for listing in existing_listings_query}
        
        saved_count = 0
        for i, prop in enumerate(all_properties):
            # 最大取得件数チェック
            if self.max_properties and i >= self.max_properties:
                print(f"最大取得件数 {self.max_properties} に達しました")
                break
                
            print(f"[{i+1}/{total_to_process}] {prop.get('building_name', 'Unknown')}")
            self.record_property_attempted()
            
            if 'url' in prop:
                try:
                    # 既存の掲載を確認（事前に取得済みのマップから）
                    existing_listing = existing_listings_map.get(prop['url'])
                    
                    # 詳細ページの取得が必要かチェック
                    needs_detail = True
                    if not existing_listing:
                        print(f"  → 新規物件です")
                    elif existing_listing and not self.force_detail_fetch:
                        needs_detail = self.needs_detail_fetch(existing_listing)
                        if not needs_detail:
                            print(f"  → 詳細ページの取得をスキップ（最終取得: {existing_listing.detail_fetched_at}）")
                            # 最終確認日時だけは更新（物件がまだアクティブであることを記録）
                            existing_listing.last_confirmed_at = datetime.now()
                            self.session.flush()
                            self.record_listing_skipped()
                            # スキップ時は遅延不要
                            continue
                    
                    # 詳細ページを取得
                    detail_data = self.get_property_detail(prop['url'])
                    if detail_data:
                        self.record_property_scraped()
                        # 一覧ページのデータとマージ
                        prop.update(detail_data)
                        
                        # データベースに保存
                        saved = self.save_property(prop)
                        if saved:
                            saved_count += 1
                    else:
                        self.record_detail_fetch_failed()
                    
                    time.sleep(self.delay)
                    
                except Exception as e:
                    logger.error(f"詳細取得エラー: {e}")
                    self.record_detail_fetch_failed()
                    continue
        
        # 最後にコミット
        try:
            self.session.commit()
        except Exception as e:
            logger.error(f"コミットエラー: {e}")
            self.session.rollback()
        
        # 統計情報を表示
        stats = self.get_scraping_stats()
        print(f"\nスクレイピング完了:")
        print(f"  物件発見数: {stats['properties_found']} 件（一覧ページから発見）")
        print(f"  処理対象数: {stats['properties_processed']} 件（max_properties制限後）")
        print(f"  処理試行数: {stats['properties_attempted']} 件")
        print(f"  詳細取得数: {stats['detail_fetched']} 件")
        print(f"  詳細スキップ数: {stats['detail_skipped']} 件")
        print(f"  新規登録数: {stats['new_listings']} 件")
        print(f"  更新数: {stats['updated_listings']} 件")
        
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
            
            # コミットはscrape_areaメソッドで一括で行うので、ここではflushのみ
            self.session.flush()
            print(f"    → 保存成功")
            return True
            
        except Exception as e:
            print(f"    → 保存エラー: {e}")
            self.session.rollback()
            return False