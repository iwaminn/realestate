"""
AtHome Seleniumスクレイパー
JavaScriptを実行できるSeleniumを使用してathome.co.jpから中古マンション情報を取得
"""

import re
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper


class AtHomeScraper(BaseScraper):
    """AtHomeのSeleniumスクレイパー"""
    
    def __init__(self, delay: float = 2.0, force_detail_fetch=False, max_properties=None):
        super().__init__("AtHome", force_detail_fetch, max_properties)  # source_site, force_detail_fetch, max_propertiesを渡す
        self.delay = delay
        self.driver = None
        
    def setup_driver(self):
        """WebDriverのセットアップ"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # ヘッドレスモード
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Docker環境でのChromeDriver設定
        try:
            # Docker環境では事前インストールされたchromedriverを使用
            service = Service('/usr/local/bin/chromedriver')
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        except:
            # ローカル環境ではwebdriver-managerを使用
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        self.driver.implicitly_wait(10)
        
        # JavaScriptで検出回避
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def close_driver(self):
        """WebDriverを閉じる"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def scrape_area(self, area: str, max_pages: int = 50):
        """エリアの物件をスクレイピング（base_scraperインターフェース）"""
        # エリアコードをエリア名に変換
        area_names = {
            "13103": "minato",
            "13113": "shibuya",
            "13104": "shinjuku",
            "13101": "chiyoda",
            "13102": "chuo",
            "13109": "shinagawa",
            "13110": "meguro",
            "13112": "setagaya"
        }
        
        area_name = area_names.get(area, area)
        
        # 最大ページ数を計算（max_properties設定がある場合）
        if self.max_properties:
            # AtHomeは1ページ30件表示
            max_pages = min(max_pages, (self.max_properties + 29) // 30)
        
        # runメソッドを呼び出す
        self.run(area=area_name, max_pages=max_pages)
    
    def run(self, area: str = "minato", max_pages: int = 3, max_price: int = 50000):
        """メイン実行メソッド"""
        try:
            self.setup_driver()
            
            all_properties = []
            
            for page in range(1, max_pages + 1):
                print(f"\nページ {page} を取得中...")
                
                # ページURLを構築
                # エリア名をURLパスに変換
                area_path = {
                    "minato": "minato-city",
                    "shibuya": "shibuya-city",
                    "shinjuku": "shinjuku-city",
                    "chiyoda": "chiyoda-city",
                    "chuo": "chuo-city",
                    "shinagawa": "shinagawa-city",
                    "meguro": "meguro-city",
                    "setagaya": "setagaya-city"
                }.get(area, "minato-city")
                
                url = f"https://www.athome.co.jp/mansion/chuko/tokyo/{area_path}/list/?page={page}"
                
                try:
                    self.driver.get(url)
                    
                    # ページが完全に読み込まれるまで待機
                    wait = WebDriverWait(self.driver, 20)
                    
                    # ページロード後、少し待機
                    time.sleep(3)
                    
                    # JavaScriptチェックを回避
                    self.driver.execute_script("""
                        if (window.navigator && window.navigator.webdriver) {
                            Object.defineProperty(window.navigator, 'webdriver', {
                                get: () => false
                            });
                        }
                    """)
                    
                    # 物件リストが表示されるまで待機
                    try:
                        # 複数のセレクタを試す
                        selectors = [
                            '.item-cassette',
                            '.p-property',
                            '.property-unit',
                            '.item-list',
                            'a[href*="/chuko/"]'
                        ]
                        
                        element_found = False
                        for selector in selectors:
                            try:
                                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                                element_found = True
                                break
                            except TimeoutException:
                                continue
                        
                        if not element_found:
                            print(f"ページ {page} で物件リストが見つかりません")
                            
                            # JavaScript検証ページの可能性をチェック
                            if "javascript" in self.driver.page_source.lower() or "認証" in self.driver.page_source:
                                print("JavaScript検証ページが検出されました")
                                # スクリーンショットを保存
                                self.driver.save_screenshot(f'/tmp/athome_page_{page}_blocked.png')
                                print(f"スクリーンショット保存: /tmp/athome_page_{page}_blocked.png")
                    except TimeoutException:
                        print(f"ページ {page} でタイムアウト")
                    
                    # ページソースを取得してBeautifulSoupで解析
                    page_source = self.driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # 物件情報を抽出
                    properties = self.parse_property_list_selenium(soup)
                    
                    if not properties:
                        print(f"ページ {page} に物件が見つかりません")
                        # スクリーンショットを保存（デバッグ用）
                        # self.driver.save_screenshot(f'/tmp/athome_page_{page}.png')
                        break
                    
                    print(f"ページ {page} から {len(properties)} 件の物件を取得")
                    all_properties.extend(properties)
                    
                    # ページ間で遅延
                    time.sleep(self.delay)
                    
                except Exception as e:
                    print(f"ページ {page} の取得エラー: {e}")
                    continue
            
            # 物件を保存
            self.save_properties(all_properties)
            
        finally:
            self.close_driver()
    
    def parse_property_list_selenium(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Seleniumで取得したページから物件情報を抽出"""
        properties = []
        
        # まずBFFデータをチェック（もしあれば）
        json_script = soup.find('script', type='application/json', id='serverApp-state')
        if json_script and json_script.string:
            try:
                server_state = json.loads(json_script.string)
                if 'first-view-ITEMS' in server_state:
                    first_view = server_state['first-view-ITEMS']
                    if 'bukkenData' in first_view and 'bukkenList' in first_view['bukkenData']:
                        bukken_list = first_view['bukkenData']['bukkenList']
                        print(f"BFFデータから{len(bukken_list)}件の物件を発見")
                        for bukken in bukken_list:
                            property_data = self.parse_bukken_data(bukken)
                            if property_data:
                                properties.append(property_data)
                        return properties
            except Exception as e:
                print(f"BFFデータの解析エラー: {e}")
        
        # HTMLから直接パース
        # 物件アイテムを探す（複数のセレクタを試す）
        selectors = [
            '.p-property',
            '.property-unit',
            '.item-cassette',
            'li[class*="property"]',
            'div[class*="bukken"]',
            'article[class*="property"]'
        ]
        
        property_items = []
        for selector in selectors:
            items = soup.select(selector)
            if items:
                property_items = items
                print(f"セレクタ '{selector}' で {len(items)} 件の物件要素を発見")
                break
        
        if not property_items:
            # より汎用的なセレクタを試す
            links = soup.select('a[href*="/chuko/"][href*="/B"]')
            if links:
                print(f"物件リンクから {len(links)} 件を発見")
                for link in links:
                    property_data = self.parse_property_from_link(link)
                    if property_data:
                        properties.append(property_data)
                return properties
        
        # 各物件をパース
        for item in property_items:
            try:
                property_data = self.parse_property_item(item)
                if property_data:
                    properties.append(property_data)
            except Exception as e:
                print(f"物件パースエラー: {e}")
                continue
        
        return properties
    
    def parse_property_from_link(self, link_elem) -> Optional[Dict[str, Any]]:
        """リンク要素から物件情報を抽出"""
        try:
            property_data = {}
            
            # URL
            url = link_elem.get('href', '')
            if not url:
                return None
            
            if not url.startswith('http'):
                url = f"https://www.athome.co.jp{url}"
            
            property_data['url'] = url
            property_data['source_site'] = 'AtHome'
            
            # リンクテキストから情報を抽出
            link_text = link_elem.get_text(strip=True)
            
            # 建物名の抽出（簡易版）
            building_name = link_text.split()[0] if link_text else None
            if building_name and len(building_name) > 2:
                property_data['building_name'] = building_name
            
            # 親要素から追加情報を探す
            parent = link_elem.parent
            if parent:
                # 価格を探す
                price_elem = parent.find(text=re.compile(r'\d+万円'))
                if price_elem:
                    price_match = re.search(r'(\d+(?:,\d+)?)\s*万円', price_elem)
                    if price_match:
                        property_data['price'] = int(price_match.group(1).replace(',', ''))
                
                # 間取りを探す
                layout_match = re.search(r'([1-9]\d*[SLDK]+|ワンルーム)', str(parent))
                if layout_match:
                    property_data['layout'] = layout_match.group(1)
                
                # 面積を探す
                area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m²|㎡)', str(parent))
                if area_match:
                    property_data['area'] = float(area_match.group(1))
            
            # 最低限の情報があれば返す
            if 'price' in property_data:
                return property_data
            
        except Exception as e:
            print(f"リンクパースエラー: {e}")
        
        return None
    
    def parse_property_item(self, item) -> Optional[Dict[str, Any]]:
        """物件アイテムから情報を抽出"""
        try:
            property_data = {}
            property_data['source_site'] = 'AtHome'
            
            # URL
            link = item.find('a', href=re.compile(r'/chuko/'))
            if not link:
                return None
            
            url = link.get('href', '')
            if not url.startswith('http'):
                url = f"https://www.athome.co.jp{url}"
            property_data['url'] = url
            
            # タイトル/建物名
            title_elem = item.find(['h2', 'h3', 'h4']) or link
            title = title_elem.get_text(strip=True)
            
            # 建物名の抽出
            building_name = self.extract_building_name(title)
            if building_name:
                property_data['building_name'] = building_name
            
            # 価格
            price_elem = item.find(text=re.compile(r'\d+万円'))
            if price_elem:
                price_match = re.search(r'(\d+(?:,\d+)?)\s*万円', price_elem)
                if price_match:
                    property_data['price'] = int(price_match.group(1).replace(',', ''))
            
            # 間取り
            layout_elem = item.find(text=re.compile(r'[1-9]\d*[SLDK]+|ワンルーム'))
            if layout_elem:
                layout_match = re.search(r'([1-9]\d*[SLDK]+|ワンルーム)', layout_elem)
                if layout_match:
                    property_data['layout'] = layout_match.group(1)
            
            # 面積
            area_elem = item.find(text=re.compile(r'\d+(?:\.\d+)?\s*(?:m²|㎡)'))
            if area_elem:
                area_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m²|㎡)', area_elem)
                if area_match:
                    property_data['area'] = float(area_match.group(1))
            
            # 住所
            address_elem = item.find(text=re.compile(r'東京都港区'))
            if address_elem:
                property_data['address'] = address_elem.strip()
            
            # 階数
            floor_elem = item.find(text=re.compile(r'\d+階'))
            if floor_elem:
                floor_match = re.search(r'(\d+)階', floor_elem)
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))
            
            # 築年
            age_elem = item.find(text=re.compile(r'築\d+年'))
            if age_elem:
                age_match = re.search(r'築(\d+)年', age_elem)
                if age_match:
                    property_data['building_age'] = int(age_match.group(1))
            
            # タイトルを設定
            property_data['title'] = title
            
            # 最低限必要な情報があるかチェック
            if 'price' in property_data and 'url' in property_data:
                return property_data
                
        except Exception as e:
            print(f"物件アイテムパースエラー: {e}")
            
        return None
    
    def extract_building_name(self, text: str) -> Optional[str]:
        """テキストから建物名を抽出"""
        # 階数や間取りの前までを建物名とする
        match = re.match(r'^(.+?)\s+(?:\d+階|ワンルーム|[1-9]\d*[SLDK]+)', text)
        if match:
            building_name = match.group(1).strip()
            # 駅名や住所っぽいものは除外
            if any(word in building_name for word in ['駅', '丁目', '東京都', '港区']):
                return None
            return building_name
        
        # マッチしない場合は最初の部分を返す
        parts = text.split()
        if parts and len(parts[0]) > 2:
            return parts[0]
        
        return None
    
    def parse_bukken_data(self, bukken: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """BFF物件データをパース（v3スクレイパーと同じ）"""
        try:
            property_data = {}
            
            # タイトルから建物名を抽出
            title = bukken.get('title', '')
            
            # 住所パターンを除外
            if '（' in title and '）' in title and any(keyword in title for keyword in ['駅', '丁目']):
                return None
            
            # 建物名の抽出
            building_name = self.extract_building_name(title)
            if not building_name:
                return None
            
            property_data['building_name'] = building_name
            property_data['title'] = title
            
            # URL (urlLongフィールドを使用)
            detail_url = bukken.get('urlLong', bukken.get('detailUrl', ''))
            if detail_url:
                if not detail_url.startswith('http'):
                    detail_url = f"https://www.athome.co.jp{detail_url}"
                property_data['url'] = detail_url
            else:
                return None
            
            # 価格 (kakakuフィールドを使用)
            price_str = bukken.get('kakaku', '')
            if price_str:
                # すでに数値の場合
                if isinstance(price_str, (int, float)):
                    property_data['price'] = int(price_str)
                else:
                    # 文字列の場合
                    price_match = re.search(r'(\d+(?:,\d+)?)', str(price_str))
                    if price_match:
                        property_data['price'] = int(price_match.group(1).replace(',', ''))
            
            # 管理費・修繕積立金 (kanriHi, shuzenTsumitatekinフィールドを使用)
            kanri_str = bukken.get('kanriHi', '')
            if kanri_str and kanri_str != '-':
                kanri_match = re.search(r'(\d+(?:,\d+)?)', str(kanri_str))
                if kanri_match:
                    property_data['management_fee'] = int(kanri_match.group(1).replace(',', '')) // 10000
            
            shuzen_str = bukken.get('shuzenTsumitatekin', '')
            if shuzen_str and shuzen_str != '-':
                shuzen_match = re.search(r'(\d+(?:,\d+)?)', str(shuzen_str))
                if shuzen_match:
                    property_data['repair_fund'] = int(shuzen_match.group(1).replace(',', '')) // 10000
            
            # 間取り (madoriフィールドを使用)
            layout = bukken.get('madori', '')
            if layout:
                property_data['layout'] = layout
            
            # 専有面積 (senyuMensekiフィールドを使用)
            area_str = bukken.get('senyuMenseki', '')
            if area_str:
                area_match = re.search(r'(\d+(?:\.\d+)?)', str(area_str))
                if area_match:
                    property_data['area'] = float(area_match.group(1))
            
            # 所在地 (locationフィールドを使用)
            address = bukken.get('location', '')
            if address:
                property_data['address'] = address
            
            # 交通情報 (trafficフィールドを使用)
            traffic = bukken.get('traffic', '')
            if traffic:
                property_data['station_info'] = traffic
            
            # 所在階 (kaisuフィールドを使用)
            floor_str = bukken.get('kaisu', '')
            if floor_str:
                floor_match = re.search(r'(\d+)階', str(floor_str))
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))
            
            # 築年月 (chikunengetsuフィールドを使用)
            built_date = bukken.get('chikunengetsu', '')
            if built_date:
                built_match = re.search(r'(\d{4})年(\d{1,2})月', str(built_date))
                if built_match:
                    built_year = int(built_match.group(1))
                    current_year = datetime.now().year
                    property_data['building_age'] = current_year - built_year
            
            # その他の情報
            property_data['source_site'] = 'AtHome'
            property_data['site_property_id'] = bukken.get('bukkenKanriNo', bukken.get('bukkenId', ''))
            
            # 必須項目の確認
            if all(key in property_data for key in ['building_name', 'url', 'price']):
                return property_data
            
        except Exception as e:
            print(f"BFF物件データのパースエラー: {e}")
        
        return None
    
    def save_properties(self, properties: List[Dict[str, Any]]):
        """物件を保存"""
        print(f"\n合計 {len(properties)} 件の物件を保存します...")
        
        saved_count = 0
        skipped_count = 0
        
        for i, property_data in enumerate(properties, 1):
            print(f"[{i}/{len(properties)}] {property_data.get('building_name', 'Unknown')}")
            
            # データの妥当性を検証
            if not self.validate_property_data(property_data):
                print(f"  → データ検証失敗、スキップ")
                skipped_count += 1
                continue
            
            try:
                self.save_property(property_data)
                saved_count += 1
                
            except Exception as e:
                print(f"  → エラー: {e}")
                skipped_count += 1
                continue
        
        # 非アクティブな掲載をマーク
        active_urls = [p['url'] for p in properties if 'url' in p]
        self.mark_inactive_listings(active_urls)
        
        print(f"\n保存完了: {saved_count} 件")
        print(f"スキップ: {skipped_count} 件")