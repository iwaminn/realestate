"""
LIFULL HOME'Sスクレイパー
homes.co.jpから中古マンション情報を取得
"""

import re
import time
from typing import Dict, List, Optional, Any
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
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(SourceSite.HOMES, force_detail_fetch, max_properties)
        # LIFULL HOME'S用の特別なヘッダー設定
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
        """ページを取得してBeautifulSoupオブジェクトを返す（HOMES用にカスタマイズ）"""
        try:
            # より長い遅延を設定
            time.sleep(3)
            
            # リファラーを設定
            if '/list/' in url:
                # 一覧ページの場合
                self.http_session.headers['Referer'] = 'https://www.homes.co.jp/'
            else:
                # 詳細ページの場合は一覧ページをリファラーに
                self.http_session.headers['Referer'] = 'https://www.homes.co.jp/mansion/chuko/tokyo/list/'
            
            response = self.http_session.get(url, timeout=30, allow_redirects=True)
            
            # ステータスコードの詳細確認
            if response.status_code == 405:
                self.logger.error(f"405 Method Not Allowed for {url} - HOMES may be blocking automated access")
                # 別のアプローチを試す
                self.logger.info("Trying with modified headers...")
                self.http_session.headers['Sec-Fetch-Site'] = 'same-origin'
                self.http_session.headers['Sec-Fetch-Mode'] = 'cors'
                time.sleep(5)  # より長い待機
                response = self.http_session.get(url, timeout=30)
            
            response.raise_for_status()
            
            # レスポンスの内容を確認
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
        
        # エリアコードを取得してからHOMES用のcityコードに変換
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        
        # LIFULL HOME'Sの検索URL
        return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/?page={page}"
    
    def parse_property_list_old(self, soup: BeautifulSoup) -> List[str]:
        """物件一覧から詳細URLを抽出"""
        property_urls = []
        
        # LIFULL HOME'Sの物件リストセレクタ - 2025年7月版
        # パターン1: 建物名アンカー（現在のメインセレクタ）
        property_items = soup.select('a.prg-bukkenNameAnchor[href]')
        
        for item in property_items:
            href = item.get('href')
            if href and '/mansion/b-' in href:
                url = urljoin(self.BASE_URL, href)
                property_urls.append(url)
        
        # パターン2: 新しい構造のヘッダーリンク
        if not property_urls:
            property_items = soup.select('.mod-mergeBuilding--sale h3.heading a[href]')
            for item in property_items:
                href = item.get('href')
                if href and '/mansion/' in href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        # パターン3: 建物詳細ページへのリンク
        if not property_urls:
            property_items = soup.select('a[href*="/mansion/b-"]')
            for item in property_items:
                href = item.get('href')
                if href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        # パターン4: テーブル内の詳細リンク
        if not property_urls:
            property_items = soup.select('tr[data-href*="/mansion/b-"]')
            for item in property_items:
                href = item.get('data-href')
                if href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        return list(set(property_urls))  # 重複を除去
    
    def scrape_area_old(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング（旧方式 - 削除予定）"""
        pass
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            self.logger.info(f"[HOMES] parse_property_detail called for URL: {url}")
            
            # 建物ページURLでも処理を続行（リダイレクトされるため）
            # ログは出力するが、エラーにはしない
            if '/mansion/b-' in url and not re.search(r'/\d{3,4}[A-Z]?/$', url):
                self.logger.info(f"[HOMES] Building URL detected, will be redirected to property: {url}")
            
            # アクセス間隔を保つ
            time.sleep(self.delay)
            
            # 詳細ページを取得
            soup = self.fetch_page(url)
            if not soup:
                # record_errorは呼ばない（base_scraperでカウントされるため）
                return None
                
            # HTML構造の検証（一時的にスキップ - 新しいHTML構造に対応中）
            # required_selectors = {
            #     '物件タイトル': 'h1.font-bold, h1[class*="text-2xl"], h1',
            #     '物件情報テーブル': 'table, dl.h-full, [class*="property"], [class*="detail"]',
            # }
            # 
            # if not self.validate_html_structure(soup, required_selectors):
            #     self.record_error('parsing', url=url, phase='parse_property_detail')
            #     return None
                
            property_data = {
                'url': url
            }
            
            # ページ全体のテキストを取得（後で日付検索に使用）
            page_text = soup.get_text()
            
            # タイトルと建物名、部屋番号
            # まずh1タグから情報を取得（新しいHTML構造）
            h1_elem = soup.select_one('h1.font-bold, h1[class*="text-2xl"], h1')
            if h1_elem:
                h1_text = h1_elem.get_text(strip=True)
                # h1から建物名と部屋番号を抽出
                # パターン: "中古マンションジェイパーク上野アクシス 8階/8044LDK / 14,980万円"
                if '中古マンション' in h1_text:
                    h1_text = h1_text.replace('中古マンション', '').strip()
                
                # 階数情報や価格情報を除去
                parts = h1_text.split('/')
                if parts:
                    property_data['building_name'] = parts[0].strip()
                    # 階数情報から部屋番号を推測（804など）
                    if len(parts) > 1:
                        floor_info = parts[1].strip()
                        floor_match = re.search(r'(\d+)階', floor_info)
                        if floor_match:
                            property_data['floor_number'] = int(floor_match.group(1))
            
            # titleタグまたはog:titleから情報を取得
            title_text = None
            
            # titleタグから取得
            title_elem = soup.select_one('title')
            if title_elem:
                title_text = title_elem.get_text(strip=True)
            
            # og:titleから取得（titleタグがない場合）
            if not title_text:
                og_title = soup.select_one('meta[property="og:title"]')
                if og_title:
                    title_text = og_title.get('content', '')
            
            # パンくずリストから建物名を取得（優先）
            breadcrumb = soup.select_one('.breadList, .breadcrumb, nav[aria-label="breadcrumb"], .topicPath')
            building_name_from_breadcrumb = None
            
            if breadcrumb:
                # パンくずリストのアイテムを取得
                breadcrumb_items = breadcrumb.select('li, .breadList__item, .breadcrumb-item')
                if breadcrumb_items:
                    # 通常、建物名は最後から2番目のアイテム（最後は部屋番号）
                    if len(breadcrumb_items) >= 2:
                        # 最後から2番目のアイテムから建物名を取得
                        building_item = breadcrumb_items[-2]
                        building_text = building_item.get_text(strip=True)
                        # 「〇〇(建物名)の中古マンション」というパターンから建物名を抽出
                        match = re.search(r'(.+?)の中古マンション', building_text)
                        if match:
                            building_name_from_breadcrumb = match.group(1)
                        else:
                            # そのままの文字列を使用（ただし不要な文字は除去）
                            building_name_from_breadcrumb = building_text.replace('中古マンション', '').strip()
                        print(f"    パンくずリストから建物名取得: {building_name_from_breadcrumb}")
            
            if title_text:
                property_data['title'] = title_text
                
                # titleから建物名と部屋番号を抽出
                # パターン: 【ホームズ】アクシアフォレスタ麻布 904｜港区、...
                # または: アクシアフォレスタ麻布 904 | 中古マンション...
                
                # 【ホームズ】を除去
                title_text = title_text.replace('【ホームズ】', '').strip()
                
                # ｜または|で分割して最初の部分を取得
                if '｜' in title_text:
                    property_name_part = title_text.split('｜')[0].strip()
                elif '|' in title_text:
                    property_name_part = title_text.split('|')[0].strip()
                else:
                    property_name_part = title_text.split('、')[0].strip()
                
                # パンくずリストから建物名が取得できた場合はそれを使用
                if building_name_from_breadcrumb:
                    property_data['building_name'] = building_name_from_breadcrumb
                    # タイトルから部屋番号を抽出
                    # パターン: "建物名 部屋番号" or "建物名棟 部屋番号"
                    room_match = re.search(r'\s+(\d{3,4}[A-Z]*)\s*($|｜|\|)', property_name_part)
                    if room_match:
                        property_data['room_number'] = room_match.group(1)
                else:
                    # パンくずリストがない場合は従来の方法
                    # 建物名と部屋番号を分離
                    # パターン1: "建物名 部屋番号" (スペース区切り)
                    parts = property_name_part.split()
                    if len(parts) >= 2:
                        # 最後の部分が数字の場合は部屋番号
                        last_part = parts[-1]
                        if re.match(r'^\d{3,4}[A-Z]*$', last_part):
                            property_data['room_number'] = last_part
                            property_data['building_name'] = ' '.join(parts[:-1])
                        else:
                            property_data['building_name'] = property_name_part
                    else:
                        property_data['building_name'] = property_name_part
                
                # 建物名から余計な文字を除去
                if property_data.get('building_name'):
                    building_name = property_data['building_name']
                    # 中古マンションなどのプレフィックスを除去
                    building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
                    property_data['building_name'] = building_name
            else:
                property_data['title'] = '物件名不明'
            
            # 価格
            # デバッグ：価格情報の探索
            self.logger.info(f"[HOMES] Looking for price information on {url}")
            
            # 様々なセレクタで価格を探す
            price_selectors = [
                'b.text-brand',
                'b[class*="text-brand"]',
                '.priceLabel',
                '.price',
                '[class*="price"]',
                'span[class*="price"]',
                'div[class*="price"]',
                'p[class*="price"]',
                '.bukkenPrice',
                '.detailPrice',
                '[class*="amount"]'
            ]
            
            price_elem = None
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem and '万円' in elem.get_text():
                    price_elem = elem
                    self.logger.info(f"[HOMES] Price found with selector: {selector} - {elem.get_text(strip=True)}")
                    break
            
            if not price_elem:
                # さらに別のパターンを試す（b要素で価格を含むもの）
                for b in soup.select('b'):
                    if '万円' in b.get_text():
                        price_elem = b
                        self.logger.info(f"[HOMES] Price found in b tag: {b.get_text(strip=True)}")
                        break
            
            if not price_elem:
                # strong要素も確認
                for strong in soup.select('strong'):
                    if '万円' in strong.get_text():
                        price_elem = strong
                        self.logger.info(f"[HOMES] Price found in strong tag: {strong.get_text(strip=True)}")
                        break
            
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # データ正規化フレームワークを使用して価格を抽出
                price = extract_price(price_text)
                if price:
                    property_data['price'] = price
                    self.logger.info(f"[HOMES] Price extracted: {price}万円")
                else:
                    self.logger.warning(f"[HOMES] Failed to extract price from: {price_text}")
            
            # 価格が取得できなかった場合の追加処理
            if 'price' not in property_data:
                self.logger.warning("[HOMES] Price not found with selectors, searching in full text...")
                # ページ全体から価格を探す
                page_text = soup.get_text()
                # 価格パターンを検索
                price_matches = re.findall(r'[\d,]+(?:億[\d,]*)?万円', page_text)
                if price_matches:
                    self.logger.info(f"[HOMES] Found {len(price_matches)} price patterns in page text")
                    # 最初の妥当な価格を使用
                    for price_text in price_matches[:5]:  # 最初の5件をログ出力
                        self.logger.info(f"[HOMES] Price candidate: {price_text}")
                        price = extract_price(price_text)
                        if price and price >= 100:  # 100万円以上なら妥当な価格
                            property_data['price'] = price
                            self.logger.info(f"[HOMES] Selected price: {price}万円")
                            break
                else:
                    self.logger.error("[HOMES] No price pattern found in page text")
                    # HTMLの一部をログ出力してデバッグ
                    body = soup.find('body')
                    if body:
                        text_sample = body.get_text()[:500]
                        self.logger.info(f"[HOMES] Page text sample: {text_sample}")
            
            # 詳細情報テーブル
            detail_items = soup.select('.detailInfo dl, .mod-detailInfo dl, [class*="detail"] dl')
            
            for dl in detail_items:
                dt = dl.select_one('dt')
                dd = dl.select_one('dd')
                
                if not dt or not dd:
                    continue
                
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                # 所在地
                if '所在地' in label or '住所' in label:
                    property_data['address'] = value
                
                # 間取り
                elif '間取り' in label:
                    # データ正規化フレームワークを使用して間取りを正規化
                    layout = normalize_layout(value.split('/')[0].strip())
                    if layout:
                        property_data['layout'] = layout
                
                # 専有面積
                elif '専有面積' in label or '面積' in label:
                    # データ正規化フレームワークを使用して面積を抽出
                    area = extract_area(value)
                    if area:
                        property_data['area'] = area
                
                # 築年月
                elif '築年月' in label:
                    # データ正規化フレームワークを使用して築年を抽出
                    built_year = extract_built_year(value)
                    if built_year:
                        property_data['built_year'] = built_year
                        property_data['age'] = datetime.now().year - built_year
                
                # 階数
                elif '階' in label and '建' not in label:
                    property_data['floor'] = value
                    # データ正規化フレームワークを使用して階数を抽出
                    floor_match = re.search(r'(\d+)階/(\d+)階建', value)
                    if floor_match:
                        property_data['floor_number'] = extract_floor_number(floor_match.group(1))
                        property_data['total_floors'] = normalize_integer(floor_match.group(2))
                        # 地下階数も抽出
                        total_floors, basement_floors = extract_total_floors(value)
                        if basement_floors is not None and basement_floors > 0:
                            property_data['basement_floors'] = basement_floors
                    else:
                        floor_match = re.search(r'(\d+)階', value)
                        if floor_match:
                            property_data['floor_number'] = int(floor_match.group(1))
                
                # 交通
                elif '交通' in label or '最寄' in label or '駅' in label:
                    # 不要な文言を削除し、路線ごとに改行を入れる
                    station_info = value
                    # 各路線の開始位置で改行を入れる（HOMESの場合は「、」で区切られていることが多い）
                    # まず「、」で区切られている場合は改行に変換
                    station_info = station_info.replace('、', '\n')
                    # その他の路線名の前でも改行
                    station_info = re.sub(
                        r'(?=東京メトロ|都営|ＪＲ|京王|小田急|東急|京急|京成|新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス)',
                        '\n',
                        station_info
                    ).strip()
                    property_data['station_info'] = station_info
                
                # 方角・主要採光面
                elif '向き' in label or '方角' in label or 'バルコニー' in label or '採光' in label:
                    # データ正規化フレームワークを使用して方角を正規化
                    direction = normalize_direction(value)
                    if direction:
                        property_data['direction'] = direction
                        print(f"    {label}: {property_data['direction']}")
                
                # 管理費
                elif '管理費' in label:
                    # データ正規化フレームワークを使用して月額費用を抽出
                    management_fee = extract_monthly_fee(value)
                    if management_fee:
                        property_data['management_fee'] = management_fee
                
                # 修繕積立金
                elif '修繕積立金' in label:
                    # データ正規化フレームワークを使用して月額費用を抽出
                    repair_fund = extract_monthly_fee(value)
                    if repair_fund:
                        property_data['repair_fund'] = repair_fund
                
                # 部屋番号
                elif '部屋番号' in label or '号室' in label:
                    property_data['room_number'] = value
                
                # 権利形態
                elif '権利' in label and ('土地' in label or '敷地' in label):
                    property_data['land_rights'] = value
                
                # 駐車場
                elif '駐車' in label:
                    property_data['parking_info'] = value
                
                # 情報公開日を取得（最初に公開された日）
                elif '情報公開日' in label:
                    # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['first_published_at'] = datetime(year, month, day)
                        print(f"    売出確認日: {property_data['first_published_at'].strftime('%Y-%m-%d')}")
                
                # 情報提供日を取得（最新の更新日）
                elif '情報提供日' in label or '情報更新日' in label or '登録日' in label:
                    # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['published_at'] = datetime(year, month, day)
                        print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # テーブル形式の詳細情報も解析（HOMESの一般的なtableも含む）
            all_tables = soup.select('table')
            for table in all_tables:
                rows = table.select('tr')
                for row in rows:
                    cells = row.select('th, td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        if '所在地' in label:
                            property_data['address'] = value
                        elif '間取り' in label:
                            # "3LDK（リビング..." のような形式から間取りだけ抽出
                            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
                            if layout_match:
                                property_data['layout'] = layout_match.group(1)
                        elif '専有面積' in label:
                            area_match = re.search(r'([\d.]+)', value)
                            if area_match:
                                property_data['area'] = float(area_match.group(1))
                        elif '管理費等' in label or '管理費' in label:
                            fee_match = re.search(r'([\d,]+)円', value)
                            if fee_match:
                                property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                        elif '修繕積立金' in label:
                            fund_match = re.search(r'([\d,]+)円', value)
                            if fund_match:
                                property_data['repair_fund'] = int(fund_match.group(1).replace(',', ''))
                        elif '所在階' in label and '階数' in label:
                            # "9階 / 10階建 (地下1階)" のような形式から階数情報を抽出
                            floor_match = re.search(r'(\d+)階\s*/\s*(\d+)階建', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                                # 地下情報も含めて総階数を取得
                                property_data['total_floors'] = int(floor_match.group(2))
                                # 地下階数を抽出
                                total_floors, basement_floors = extract_total_floors(value)
                                if basement_floors is not None and basement_floors > 0:
                                    property_data['basement_floors'] = basement_floors
                        elif '築年月' in label:
                            # 築年を抽出
                            year_match = re.search(r'(\d{4})年', value)
                            if year_match:
                                from datetime import datetime
                                property_data['built_year'] = int(year_match.group(1))
                                property_data['age'] = datetime.now().year - int(year_match.group(1))
                        elif 'バルコニー面積' in label or 'バルコニー' in label and '面積' in value:
                            # バルコニー面積
                            area_match = re.search(r'([\d.]+)', value)
                            if area_match:
                                property_data['balcony_area'] = float(area_match.group(1))
                        elif '備考' in label:
                            # 備考
                            property_data['remarks'] = value
                        elif '権利' in label and ('土地' in label or '敷地' in label):
                            # 権利形態
                            property_data['land_rights'] = value
                        elif '駐車' in label:
                            # 駐車場
                            property_data['parking_info'] = value
                        elif '主要採光面' in label:
                            # データ正規化フレームワークを使用して方角を正規化
                            direction = normalize_direction(value)
                            if direction:
                                property_data['direction'] = direction
                                print(f"    主要採光面: {property_data['direction']}")
                        elif '情報提供日' in label or '情報公開日' in label or '情報更新日' in label or '登録日' in label:
                            # データ正規化フレームワークを使用して日付を解析
                            published_date = parse_date(value)
                            if published_date:
                                property_data['published_at'] = published_date
                                print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # 情報公開日を探す（物件概要以外のセクションも確認）
            # パターン1: class="date"や"update"を含む要素
            date_elements = soup.select('[class*="date"], [class*="update"], [class*="公開"], [class*="info"]')
            for elem in date_elements:
                text = elem.get_text(strip=True)
                if '情報公開日' in text or '掲載日' in text or '登録日' in text:
                    # 日付パターンを探す
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', text)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['published_at'] = datetime(year, month, day)
                        print(f"    情報公開日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                        break
            
            # パターン3: HOMESの特定パターン - テキストノードから直接探す
            if 'published_at' not in property_data:
                # ページ内の全テキストから情報公開日パターンを探す
                # "情報公開日：2025年7月17日" または "情報公開日：2025/06/29"のようなパターンを探す
                date_pattern = re.search(r'情報公開日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', page_text)
                if date_pattern:
                    year = int(date_pattern.group(1))
                    month = int(date_pattern.group(2))
                    day = int(date_pattern.group(3))
                    property_data['published_at'] = datetime(year, month, day)
                    print(f"    情報公開日(テキストから): {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # パターン2: dt/dd形式の定義リスト
            dl_elements = soup.select('dl')
            for dl in dl_elements:
                dt_elements = dl.select('dt')
                dd_elements = dl.select('dd')
                for i, dt in enumerate(dt_elements):
                    if i < len(dd_elements):
                        label = dt.get_text(strip=True)
                        value = dd_elements[i].get_text(strip=True)
                        if '情報公開日' in label or '掲載日' in label or '登録日' in label:
                            date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                            if date_match:
                                year = int(date_match.group(1))
                                month = int(date_match.group(2))
                                day = int(date_match.group(3))
                                property_data['published_at'] = datetime(year, month, day)
                                print(f"    情報公開日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                                break
            
            # 不動産会社情報を探す（HOMESの会社情報セクション）
            # パターン1: 会社情報セクション内のテーブルから
            company_sections = soup.select('.companyInfo, .company-info, [class*="company"]')
            for company_section in company_sections:
                # テーブル形式の情報を探す
                company_tables = company_section.select('table')
                for table in company_tables:
                    rows = table.select('tr')
                    for row in rows:
                        cells = row.select('th, td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            
                            if '会社名' in label or '社名' in label:
                                property_data['agency_name'] = value
                                print(f"    不動産会社名(テーブルから): {property_data['agency_name']}")
                            elif 'TEL' in label or '電話' in label:
                                # 電話番号パターンを抽出（日本の電話番号形式）
                                tel_match = re.search(r'[\d\-\(\)]+', value)
                                if tel_match:
                                    tel = tel_match.group(0)
                                    # 括弧を除去してハイフン形式に統一
                                    tel = tel.replace('(', '').replace(')', '-')
                                    property_data['agency_tel'] = tel
                                    print(f"    電話番号: {property_data['agency_tel']}")
            
            # パターン2: ページ全体から会社名を探す
            if 'agency_name' not in property_data:
                # "会社名"や"取扱会社"の後のテキストを探す
                company_pattern = re.search(r'(?:会社名|取扱会社|情報提供元)[：:]\s*([^\n]+)', page_text)
                if company_pattern:
                    company_name = company_pattern.group(1).strip()
                    # 不要な文字を除去
                    company_name = company_name.split('　')[0]  # 全角スペースで分割
                    company_name = company_name.split(' ')[0]   # 半角スペースで分割
                    if len(company_name) > 2 and '株式会社' in company_name or '有限会社' in company_name:
                        property_data['agency_name'] = company_name
                        print(f"    不動産会社名(テキストから): {property_data['agency_name']}")
            
            # パターン3: 問合せ先から会社名を探す
            if 'agency_name' not in property_data:
                inquiry_pattern = re.search(r'問合せ先[：:]\s*([^\n]+)', page_text)
                if inquiry_pattern:
                    company_text = inquiry_pattern.group(1).strip()
                    # 会社名部分を抽出（株式会社などを含む）
                    # 会社名の後に続く不要なテキスト（会社情報、ポイントなど）を除去
                    company_match = re.search(r'((?:株式会社|有限会社)?[^\s　]+(?:株式会社|有限会社)?)', company_text)
                    if company_match:
                        company_name = company_match.group(1)
                        # 「会社情報」「ポイント」などの不要な文字列を除去
                        company_name = re.sub(r'(会社情報|ポイント|〜).*$', '', company_name).strip()
                        if company_name and len(company_name) > 2:
                            property_data['agency_name'] = company_name
                            print(f"    不動産会社名(問合せ先から): {property_data['agency_name']}")
            
            # 電話番号をページ全体から探す（まだ取得できていない場合）
            if 'agency_tel' not in property_data:
                # 問合せ先の電話番号パターン
                tel_pattern = re.search(r'(?:TEL|電話|問合せ)[：:]\s*([\d\-\(\)]+)', page_text)
                if tel_pattern:
                    tel = tel_pattern.group(1)
                    # 括弧を除去してハイフン形式に統一
                    tel = tel.replace('(', '').replace(')', '-')
                    property_data['agency_tel'] = tel
                    print(f"    電話番号(テキストから): {property_data['agency_tel']}")
            
            # 画像URL（複数枚対応）
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
            
            property_data['image_urls'] = image_urls
            if image_urls:
                property_data['image_url'] = image_urls[0]  # 後方互換性のため
            
            # 物件説明
            description_elem = soup.select_one('.comment, .pr-comment, [class*="description"]')
            if description_elem:
                property_data['description'] = description_elem.get_text(strip=True)
            
            # 不動産会社情報を取得
            agency_elem = soup.select_one('.companyName, .agency-name, [class*="company"]')
            if agency_elem:
                property_data['agency_name'] = agency_elem.get_text(strip=True)
            
            # 不動産会社の電話番号
            tel_elem = soup.select_one('.tel, .phone, [class*="tel"]')
            if tel_elem:
                tel_text = tel_elem.get_text(strip=True)
                # 電話番号のパターンをマッチ
                tel_match = re.search(r'[\d\-\(\)]+', tel_text)
                if tel_match:
                    property_data['agency_tel'] = tel_match.group(0)
            
            # デフォルト値設定
            property_data.setdefault('building_type', 'マンション')
            property_data.setdefault('address', '東京都港区')
            
            # 必須フィールドのチェック
            # 建物名が必須
            if not property_data.get('building_name'):
                # 基底クラスのメソッドを使用してエラーを記録
                self.record_field_extraction_error('building_name', url)
                print(f"    [ERROR] 建物名が取得できませんでした")
                # base_scraper.pyで既にカウントされるため、ここではカウントしない
                return None
            
            # 建物ページの場合は、建物名があればOK（価格は個別物件ページで取得）
            if 'building_name' in property_data or 'title' in property_data:
                return property_data
            else:
                self.logger.warning(f"Required fields missing for {url}")
                return None
                
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            self.logger.error(f"Error parsing property detail from {url}: {e}")
            return None
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと最小限の情報のみを抽出"""
        properties = []
        
        # デバッグ: HTMLの一部を出力
        self.logger.info("[HOMES] Parsing property list page")
        
        # まず、ページタイトルを確認
        title = soup.find('title')
        if title:
            self.logger.info(f"[HOMES] Page title: {title.get_text(strip=True)}")
        
        # 建物ブロックを探す
        building_blocks = soup.select('.mod-mergeBuilding--sale')
        self.logger.info(f"[HOMES] Found {len(building_blocks)} building blocks")
        
        for block in building_blocks:
            # 建物リンクを取得
            building_link = block.select_one('h3 a, .heading a')
            if not building_link:
                continue
            
            # 複数物件に対応：各raSpecRowが1つの物件を表す
            price_rows = block.select('tr.raSpecRow')
            
            if not price_rows:
                # raSpecRowがない場合も建物URLを物件URLとして扱う
                href = building_link.get('href', '')
                if '/mansion/b-' in href:
                    full_url = urljoin(self.BASE_URL, href)
                    self.logger.info(f"[HOMES] Building URL without price rows (will redirect to property): {full_url}")
                    
                    # 物件データを作成
                    property_data = {
                        'url': full_url,
                        'has_update_mark': False
                    }
                    properties.append(property_data)
            else:
                # 各物件行を処理
                for row in price_rows:
                    # 物件のURLを取得
                    property_link = row.select_one('a[href*="/mansion/b-"]')
                    if not property_link:
                        continue
                    
                    href = property_link.get('href', '')
                    if '/mansion/b-' not in href:
                        continue
                    
                    full_url = urljoin(self.BASE_URL, href)
                    
                    # URLが建物ページ（部屋番号なし）か個別物件ページ（部屋番号あり）かを判定
                    is_individual_property = re.search(r'/\d{3,4}[A-Z]?/$', href)
                    
                    if is_individual_property:
                        # 個別物件ページの場合はそのまま追加
                        # 価格情報を取得（3番目のtd）
                        price = None
                        tds = row.select('td')
                        if len(tds) > 2:
                            price_text = tds[2].get_text(strip=True)
                            price = extract_price(price_text)
                            if price:
                                self.logger.info(f"[HOMES] Found price: {price}万円 for {href}")
                        
                        # 物件データを作成
                        property_data = {
                            'url': full_url,
                            'has_update_mark': False
                        }
                        
                        if price:
                            property_data['price'] = price
                        
                        # URLから物件IDを抽出
                        # パターン1: /mansion/1234567890/
                        # パターン2: /mansion/b-35006090000018/
                        # パターン3: /detail-1234567890/
                        id_match = re.search(r'/mansion/([0-9]+)/', href) or \
                                   re.search(r'/mansion/b-([^/]+)/', href) or \
                                   re.search(r'/detail-([0-9]+)/', href)
                        if id_match:
                            property_data['site_property_id'] = id_match.group(1)
                            self.logger.info(f"[HOMES] Extracted site_property_id: {property_data['site_property_id']} from {href}")
                        else:
                            self.logger.error(f"[HOMES] サイト物件IDを抽出できません: URL={href}")
                        
                        properties.append(property_data)
                    else:
                        # 建物ページURLの場合でも、実際には個別物件にリダイレクトされるため
                        # そのまま物件URLとして扱う
                        self.logger.info(f"[HOMES] Found building URL (will redirect to property): {full_url}")
                        
                        # 価格情報を取得（3番目のtd）
                        price = None
                        tds = row.select('td')
                        if len(tds) > 2:
                            price_text = tds[2].get_text(strip=True)
                            price = extract_price(price_text)
                            if price:
                                self.logger.info(f"[HOMES] Found price: {price}万円 for {href}")
                        
                        # 物件データを作成（建物URLでもparse_property_detailが処理する）
                        property_data = {
                            'url': full_url,
                            'has_update_mark': False
                        }
                        
                        if price:
                            property_data['price'] = price
                        
                        # URLから物件IDを抽出
                        # パターン1: /mansion/1234567890/
                        # パターン2: /mansion/b-35006090000018/
                        # パターン3: /detail-1234567890/
                        id_match = re.search(r'/mansion/([0-9]+)/', href) or \
                                   re.search(r'/mansion/b-([^/]+)/', href) or \
                                   re.search(r'/detail-([0-9]+)/', href)
                        if id_match:
                            property_data['site_property_id'] = id_match.group(1)
                            self.logger.info(f"[HOMES] Extracted site_property_id: {property_data['site_property_id']} from {href}")
                        else:
                            self.logger.error(f"[HOMES] サイト物件IDを抽出できません: URL={href}")
                        
                        properties.append(property_data)
                    
                    # リアルタイムで統計を更新
                    if hasattr(self, '_scraping_stats'):
                        self._scraping_stats['properties_found'] = len(properties)
                    
                    # 処理上限チェック
                    if self.max_properties and len(properties) >= self.max_properties:
                        self.logger.info(f"[HOMES] Reached max properties limit ({self.max_properties}), stopping collection")
                        return properties
        
        return properties
    
    def _fetch_properties_from_building_page(self, building_url: str, building_name: str = None) -> List[Dict[str, Any]]:
        """建物ページから個別物件を取得"""
        properties = []
        
        self.logger.info(f"[HOMES] Fetching properties from building page: {building_url}")
        
        try:
            # 一時停止チェック
            if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
                self.logger.info("[HOMES] Task paused during building page fetch")
                # 一時停止フラグがクリアされるまで待機
                while self.pause_flag.is_set():
                    if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                        raise TaskCancelledException("Task cancelled during pause")
                    time.sleep(0.1)
                self.logger.info("[HOMES] Resuming from building page fetch")
            
            # 建物ページを取得
            soup = self.fetch_page(building_url)
            if not soup:
                self.logger.warning(f"[HOMES] Failed to fetch building page: {building_url}")
                return properties
            
            # リダイレクトされた場合のチェック（建物ページが個別物件ページにリダイレクトされることがある）
            # 現在のURLを取得（リダイレクト後のURL）
            current_url = building_url  # fetch_pageではリダイレクト後のURLを取得できないため、HTMLから推測
            canonical_link = soup.select_one('link[rel="canonical"]')
            if canonical_link and canonical_link.get('href'):
                current_url = canonical_link.get('href')
                if re.search(r'/mansion/b-[^/]+/\d{3,4}[A-Z]?/?$', current_url):
                    # 個別物件ページにリダイレクトされた場合
                    self.logger.info(f"[HOMES] Building page redirected to property page: {current_url}")
                    property_data = {
                        'url': current_url,
                        'has_update_mark': False
                    }
                    properties.append(property_data)
                    return properties
            
            # 建物名を建物ページから取得（まだ取得していない場合）
            if not building_name:
                # h1要素から建物名を取得
                h1_elem = soup.select_one('h1')
                if h1_elem:
                    h1_text = h1_elem.get_text(strip=True)
                    # 不要なプレフィックスを削除
                    if '中古マンション' in h1_text:
                        building_name = h1_text.replace('中古マンション', '').strip()
                    else:
                        building_name = h1_text
                    
                    # さらに不要な情報を削除（例：「○○駅 徒歩○分」）
                    # 駅名パターンを削除
                    import re
                    building_name = re.sub(r'^[^（]+駅\s*徒歩\d+分[（）]*[^）]*[）]*の中古マンション$', '', building_name).strip()
                    
                    # まだ駅名っぽい場合は、パンくずリストから取得
                    if '駅' in building_name and '徒歩' in building_name:
                        breadcrumb = soup.select_one('.breadList, .breadcrumb, nav[aria-label="breadcrumb"]')
                        if breadcrumb:
                            breadcrumb_items = breadcrumb.select('li, .breadList__item')
                            if len(breadcrumb_items) >= 2:
                                # 最後から2番目のアイテムが建物名の可能性が高い
                                building_item = breadcrumb_items[-2]
                                building_text = building_item.get_text(strip=True)
                                # 建物名パターンを抽出
                                match = re.search(r'(.+?)の中古マンション', building_text)
                                if match:
                                    building_name = match.group(1)
                                elif '中古マンション' not in building_text:
                                    building_name = building_text
                
                # それでも建物名が取得できない場合は、メタデータやtitleタグから取得
                if not building_name or ('駅' in building_name and '徒歩' in building_name):
                    title_elem = soup.select_one('title')
                    if title_elem:
                        title_text = title_elem.get_text(strip=True)
                        # 【ホームズ】を除去
                        title_text = title_text.replace('【ホームズ】', '').strip()
                        # ｜または|で分割して最初の部分を取得
                        if '｜' in title_text:
                            building_name = title_text.split('｜')[0].strip()
                        elif '|' in title_text:
                            building_name = title_text.split('|')[0].strip()
                
                # 最終的なクリーンアップ
                if building_name:
                    building_name = building_name.replace('の中古マンション', '').strip()
                    building_name = building_name.replace('中古マンション', '').strip()
                    
                self.logger.info(f"[HOMES] Building name extracted: {building_name}")
            
            # 建物名が取得できなかった場合は処理を中断
            if not building_name:
                self.logger.warning(f"[HOMES] Could not extract building name from: {building_url}")
                # 建物ページ処理のエラーは通常の物件処理とは別扱い
                # （統計には含めない - 建物ページは物件ではないため）
                
                # エラー情報を記録（ログのみ）
                if hasattr(self, '_error_details') and self._error_details is not None:
                    self._error_details.append({
                        'type': 'building_page_error',
                        'url': building_url,
                        'reason': '建物名なし',
                        'building_name': '',
                        'price': '',
                        'timestamp': datetime.now().isoformat()
                    })
                
                return properties
            
            # 個別物件のリンクを探す
            # まず、すべてのリンクをデバッグ出力
            all_links = soup.select('a[href*="/mansion/b-"]')
            self.logger.info(f"[HOMES] Total links with /mansion/b-: {len(all_links)}")
            for i, link in enumerate(all_links[:5]):  # 最初の5件だけログ出力
                self.logger.info(f"[HOMES] Link {i}: {link.get('href', '')}")
            
            # パターン1: テーブル形式の物件一覧（販売中のみ）
            property_rows = soup.select('tr.prg-row:has(.label--onsale), tr[data-href]:has(.label--onsale), .mod-mergeBuilding__item:has(.label--onsale)')
            
            if property_rows:
                self.logger.info(f"[HOMES] Found {len(property_rows)} properties with onsale label")
            else:
                # 販売中ラベルがない場合は通常のセレクタを試す
                property_rows = soup.select('tr.prg-row, tr[data-href], .mod-mergeBuilding__item')
                if property_rows:
                    self.logger.info(f"[HOMES] Found {len(property_rows)} properties")
            
            if not property_rows:
                # パターン2: リスト形式
                property_rows = soup.select('li.property-item, .bukken-item, .property-unit')
                if property_rows:
                    self.logger.info(f"[HOMES] Found {len(property_rows)} properties in list format")
            
            if not property_rows:
                # パターン3: 直接リンクを探す
                property_links = soup.select('a[href*="/mansion/b-"]')
                # 物件詳細ページのURLパターン: /mansion/b-XXXXX/部屋番号/
                property_links = [link for link in property_links 
                                if re.search(r'/mansion/b-[^/]+/\d{3,4}[A-Z]?/?$', link.get('href', ''))]
                self.logger.info(f"[HOMES] Found {len(property_links)} direct property links")
                
                if property_links:
                    for link in property_links:
                        property_data = {
                            'url': urljoin(self.BASE_URL, link.get('href')),
                            'building_name': building_name,
                            'has_update_mark': False  # 建物ページからは更新マークを取得できない
                        }
                        properties.append(property_data)
                    return properties
            
            # 行形式のデータを処理
            processed_count = 0
            for i, row in enumerate(property_rows):
                # 一時停止チェック
                if hasattr(self, 'pause_flag') and self.pause_flag and self.pause_flag.is_set():
                    self.logger.info(f"[HOMES] Task paused during property processing (processed {processed_count} properties)")
                    # 一時停止フラグがクリアされるまで待機
                    while self.pause_flag.is_set():
                        if hasattr(self, 'cancel_flag') and self.cancel_flag and self.cancel_flag.is_set():
                            raise TaskCancelledException("Task cancelled during pause")
                        time.sleep(0.1)
                    self.logger.info(f"[HOMES] Resuming property processing")
                
                # 処理上限チェック（全体の上限のみチェック）
                # 1建物あたりの制限は設けない
                
                property_data = {}
                
                # URLを取得
                href = None
                if row.get('data-href'):
                    href = row.get('data-href')
                else:
                    link = row.select_one('a[href]')
                    if link:
                        href = link.get('href')
                
                if href and '/mansion/' in href and '/b-' not in href:
                    property_data['url'] = urljoin(self.BASE_URL, href)
                    
                    # URLから物件IDを抽出
                    # パターン1: /mansion/1234567890/
                    # パターン2: /mansion/b-1234567890/
                    # パターン3: /chuko/mansion/detail-1234567890/
                    id_match = re.search(r'/mansion/([0-9]+)/', href) or \
                               re.search(r'/mansion/b-([^/]+)/', href) or \
                               re.search(r'/detail-([0-9]+)/', href)
                    if id_match:
                        property_data['site_property_id'] = id_match.group(1)
                    else:
                        # IDが取得できない場合はエラーログ
                        self.logger.error(f"サイト物件IDを抽出できません: URL={href}")
                    
                    # 部屋番号を取得（URLまたは行データから）
                    # URLから部屋番号を抽出
                    room_match = re.search(r'/([0-9]{3,4}[A-Z]?)/$', href)
                    if room_match:
                        property_data['room_number'] = room_match.group(1)
                    else:
                        # 行内のテキストから部屋番号を探す
                        row_text = row.get_text()
                        room_match = re.search(r'\b([0-9]{3,4}[A-Z]?)\b', row_text)
                        if room_match:
                            property_data['room_number'] = room_match.group(1)
                    
                    # 価格情報（建物ページに表示されている場合）
                    # 様々なセレクタを試す
                    price_selectors = [
                        '.price',
                        'td:nth-child(3)',
                        '[class*="price"]',
                        'td:has(.price)',
                        '.prg-price',
                        '.bukkenPrice'
                    ]
                    
                    price_elem = None
                    for selector in price_selectors:
                        try:
                            elem = row.select_one(selector)
                            if elem and '万円' in elem.get_text():
                                price_elem = elem
                                break
                        except:
                            # :hasなどCSS4セレクタの場合
                            pass
                    
                    # セレクタで見つからない場合は、行全体から価格を探す
                    if not price_elem:
                        row_text = row.get_text()
                        price_match = re.search(r'([\d,]+(?:億[\d,]*)?万円)', row_text)
                        if price_match:
                            # 仮想的な要素を作成
                            class PriceText:
                                def __init__(self, text):
                                    self.text = text
                                def get_text(self, strip=True):
                                    return self.text
                            price_elem = PriceText(price_match.group(0))
                    
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        price = extract_price(price_text)
                        if price:
                            property_data['price'] = price  # priceフィールドとして設定（重要）
                            self.logger.info(f"[HOMES] Price found in building page: {price}万円")
                    
                    # 間取り
                    layout_elem = row.select_one('td:nth-child(4), .layout, [class*="layout"]')
                    if layout_elem:
                        property_data['layout'] = layout_elem.get_text(strip=True)
                    
                    # 階数
                    floor_elem = row.select_one('td:nth-child(2), .floor, [class*="floor"]')
                    if floor_elem:
                        floor_text = floor_elem.get_text(strip=True)
                        floor_match = re.search(r'(\d+)階', floor_text)
                        if floor_match:
                            property_data['floor_number'] = int(floor_match.group(1))
                    
                    property_data['has_update_mark'] = False  # 建物ページからは更新マークを取得できない
                    
                    if property_data.get('url'):
                        properties.append(property_data)
                        processed_count += 1
                        
                        # 進捗更新（必要に応じて）
                        if hasattr(self, 'update_status_callback') and processed_count % 5 == 0:
                            self.update_status_callback("running")
            
            if not properties:
                self.logger.warning(f"[HOMES] No properties found on building page: {building_url}")
            else:
                self.logger.info(f"[HOMES] Successfully extracted {len(properties)} properties from building page")
            
        except Exception as e:
            self.logger.error(f"[HOMES] Error fetching properties from building page {building_url}: {e}")
        
        return properties
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング（スマート版）"""
        self.logger.info(f"[HOMES] Starting scrape for area: {area}, max_pages: {max_pages}, max_properties: {self.max_properties}")
        
        # エリアコードの確認
        from .area_config import get_area_code, get_homes_city_code
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        self.logger.info(f"[HOMES] Area conversion: {area} -> {area_code} -> {city_code}")
        
        # 共通ロジックを使用
        return self.common_scrape_area_logic(area, max_pages)
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（抽象メソッドの実装）"""
        # process_property_dataメソッドを使用
        self.process_property_data(property_data, existing_listing)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（HOMESスクレイパー固有の実装）"""
        # 建物ページURLでも処理を続行（リダイレクトされるため）
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
        """詳細データ取得後の保存処理（内部メソッド）"""
        # 共通の保存処理を使用（例外処理はbase_scraperで行う）
        return self.save_property_common(property_data, existing_listing)
    
    def fetch_and_update_detail(self, listing) -> bool:
        """詳細ページを取得して情報を更新"""
        try:
            # 詳細ページを取得
            detail_data = self.parse_property_detail(listing.url)
            if not detail_data:
                return False
            
            detail_info = {}
            
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
            
            # 部屋番号を更新
            if detail_data.get('room_number') and not listing.master_property.room_number:
                listing.master_property.room_number = detail_data['room_number']
                print(f"    部屋番号を更新: {detail_data['room_number']}")
            
            # バルコニー面積を更新
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
            
            # 不動産会社情報を更新
            if detail_data.get('agency_name'):
                listing.agency_name = detail_data['agency_name']
                print(f"    不動産会社を更新: {detail_data['agency_name']}")
            
            if detail_data.get('agency_tel'):
                listing.agency_tel = detail_data['agency_tel']
                print(f"    不動産会社電話番号を更新: {detail_data['agency_tel']}")
            
            # 備考を更新
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
            for key in ['age', 'floor', 'total_floors']:
                if key in detail_data:
                    detail_info[key] = detail_data[key]
            
            listing.detail_info = detail_info
            listing.detail_fetched_at = datetime.now()
            listing.has_update_mark = False  # 更新マークをクリア
            
            self.session.commit()
            return True
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            print(f"    詳細ページ取得エラー: {e}")
            return False