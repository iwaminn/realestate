#!/usr/bin/env python3
"""
改良版不動産スクレイピングエンジン
より高精度なデータ取得と処理を実現
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import re
import hashlib
import random
import logging
from datetime import datetime, date
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import json
import os

class EnhancedScraper:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.session = requests.Session()
        
        # より詳細なUser-Agent設定
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        ]
        
        # レート制限設定（より保守的に）
        self.rate_limits = {
            'suumo': {'min_delay': 5, 'max_delay': 10, 'max_pages': 3, 'max_items': 30},
            'athome': {'min_delay': 6, 'max_delay': 12, 'max_pages': 2, 'max_items': 20},
            'homes': {'min_delay': 8, 'max_delay': 15, 'max_pages': 2, 'max_items': 20}
        }
        
        # キャッシュ設定
        self.cache_dir = 'cache'
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # ログ設定
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.scraped_count = 0
        self.robots_cache = {}
        
        # セッション設定
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def get_db_connection(self):
        """データベース接続を取得"""
        return sqlite3.connect(self.db_path)
    
    def rotate_user_agent(self):
        """User-Agentをローテーション"""
        ua = random.choice(self.user_agents)
        self.session.headers['User-Agent'] = ua
        self.logger.debug(f"User-Agent rotated: {ua[:50]}...")
    
    def respectful_delay(self, site_name):
        """サイトに応じた適切な遅延を実行"""
        if site_name in self.rate_limits:
            min_delay = self.rate_limits[site_name]['min_delay']
            max_delay = self.rate_limits[site_name]['max_delay']
            delay = random.uniform(min_delay, max_delay)
            
            # 時間帯による調整
            current_hour = datetime.now().hour
            if 9 <= current_hour <= 18:  # 営業時間帯は遅延を増加
                delay *= 1.5
            
            self.logger.info(f"{site_name}: {delay:.1f}秒待機中...")
            time.sleep(delay)
        else:
            time.sleep(random.uniform(3, 7))
    
    def get_cached_response(self, url):
        """キャッシュされたレスポンスを取得"""
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                # 1時間以内のキャッシュを使用
                if datetime.now().timestamp() - cache_data['timestamp'] < 3600:
                    self.logger.debug(f"キャッシュを使用: {url}")
                    return cache_data['content']
        
        return None
    
    def cache_response(self, url, content):
        """レスポンスをキャッシュ"""
        cache_key = hashlib.md5(url.encode()).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        cache_data = {
            'url': url,
            'content': content,
            'timestamp': datetime.now().timestamp()
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)
    
    def safe_request(self, url, retries=3):
        """安全なリクエスト実行"""
        for attempt in range(retries):
            try:
                # User-Agentをローテーション
                self.rotate_user_agent()
                
                # キャッシュをチェック
                cached_content = self.get_cached_response(url)
                if cached_content:
                    return cached_content
                
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # レスポンスをキャッシュ
                self.cache_response(url, response.text)
                
                return response.text
                
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"リクエスト失敗 (試行 {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(2, 5))
                else:
                    self.logger.error(f"リクエスト最終失敗: {url}")
                    return None
    
    def enhanced_parse_suumo(self, html_content):
        """改良版SUUMOページ解析"""
        soup = BeautifulSoup(html_content, 'html.parser')
        properties = []
        
        # より詳細な物件情報を取得（実際のSUUMOクラス名を使用）
        property_items = soup.find_all('div', class_='property_unit-info')
        
        # 物件が見つからない場合はデバッグ用に構造を確認
        if not property_items:
            self.logger.warning("物件要素が見つかりません。HTMLの構造をチェックしています...")
            # 価格を含む要素を探す
            price_elements = soup.find_all(text=re.compile(r'万円|円'))
            if price_elements:
                self.logger.info(f"価格関連の要素が {len(price_elements)} 個見つかりました")
                # 価格周辺の要素を親要素として取得
                for price_elem in price_elements[:3]:  # 最初の3つだけ
                    parent = price_elem.parent
                    if parent:
                        property_items.append(parent.parent if parent.parent else parent)
            else:
                self.logger.warning("価格情報も見つかりません")
        
        for item in property_items:
            try:
                # 基本情報
                title_elem = item.find('div', class_='cassetteitem_content-title')
                if not title_elem:
                    continue
                
                building_name = title_elem.get_text(strip=True)
                
                # 住所情報
                address_elem = item.find('li', class_='cassetteitem_detail-col1')
                if not address_elem:
                    continue
                
                address = address_elem.get_text(strip=True)
                
                # 交通情報
                transport_elem = item.find('li', class_='cassetteitem_detail-col2')
                transport_info = transport_elem.get_text(strip=True) if transport_elem else ""
                
                # 構造・築年数
                detail_elem = item.find('li', class_='cassetteitem_detail-col3')
                structure_age = detail_elem.get_text(strip=True) if detail_elem else ""
                
                # 築年数を抽出
                building_age = self.extract_building_age(structure_age)
                structure = self.extract_structure(structure_age)
                
                # 各部屋の情報
                room_tables = item.find_all('table', class_='cassetteitem_other')
                for table in room_tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 8:
                            try:
                                # 階数
                                floor_info = cols[1].get_text(strip=True)
                                floor = self.extract_floor(floor_info)
                                
                                # 価格
                                price_text = cols[2].get_text(strip=True)
                                price = self.parse_price(price_text)
                                if price == 0:
                                    continue
                                
                                # 間取り
                                layout_text = cols[3].get_text(strip=True)
                                
                                # 専有面積
                                area_text = cols[4].get_text(strip=True)
                                floor_area = self.parse_area(area_text)
                                if floor_area == 0:
                                    continue
                                
                                # 管理費・修繕積立金
                                management_fee = self.parse_management_fee(cols[5].get_text(strip=True))
                                
                                # 詳細リンク
                                detail_url = self.extract_detail_url(cols[8])
                                
                                property_data = {
                                    'area_id': 1,  # 港区
                                    'address': address,
                                    'building_name': building_name,
                                    'room_layout': layout_text,
                                    'floor_area': floor_area,
                                    'building_age': building_age,
                                    'floor': floor,
                                    'structure': structure,
                                    'current_price': price,
                                    'management_fee': management_fee,
                                    'transport_info': transport_info,
                                    'source_site': 'suumo',
                                    'source_url': detail_url,
                                    'agent_company': 'SUUMO掲載',
                                    'first_listed_at': date.today().isoformat()
                                }
                                
                                properties.append(property_data)
                                
                            except Exception as e:
                                self.logger.warning(f"部屋情報解析エラー: {e}")
                                continue
                
            except Exception as e:
                self.logger.warning(f"物件情報解析エラー: {e}")
                continue
        
        return properties
    
    def extract_building_age(self, text):
        """築年数を抽出"""
        match = re.search(r'築(\d+)年', text)
        if match:
            return int(match.group(1))
        return None
    
    def extract_structure(self, text):
        """構造を抽出"""
        structures = ['RC', 'SRC', '鉄筋コンクリート', '鉄骨鉄筋コンクリート', '木造', '鉄骨造']
        for structure in structures:
            if structure in text:
                return structure
        return None
    
    def extract_floor(self, text):
        """階数を抽出"""
        match = re.search(r'(\d+)階', text)
        if match:
            return int(match.group(1))
        return None
    
    def parse_management_fee(self, text):
        """管理費を解析"""
        if not text or text == '-':
            return 0
        
        match = re.search(r'(\d+,?\d*)', text.replace(',', ''))
        if match:
            return int(match.group(1).replace(',', ''))
        return 0
    
    def extract_detail_url(self, cell):
        """詳細URLを抽出"""
        link = cell.find('a')
        if link and link.get('href'):
            return urljoin('https://suumo.jp', link['href'])
        return ''
    
    def parse_price(self, price_text):
        """価格文字列を数値に変換（改良版）"""
        if not price_text or price_text == '-':
            return 0
        
        try:
            # 価格範囲の場合は最低価格を使用
            if '～' in price_text:
                price_text = price_text.split('～')[0]
            
            # 数字と単位を抽出
            numbers = re.findall(r'[\d,]+', price_text)
            if not numbers:
                return 0
            
            price_str = numbers[0].replace(',', '')
            price = int(price_str)
            
            # 単位を確認
            if '億' in price_text:
                price *= 100000000
            elif '万' in price_text:
                price *= 10000
            elif 'thousand' in price_text.lower():
                price *= 1000
            
            return price
            
        except (ValueError, IndexError):
            return 0
    
    def parse_area(self, area_text):
        """面積文字列を数値に変換（改良版）"""
        if not area_text or area_text == '-':
            return 0
        
        try:
            # 面積範囲の場合は最初の値を使用
            if '～' in area_text:
                area_text = area_text.split('～')[0]
            
            match = re.search(r'(\d+\.?\d*)', area_text)
            if match:
                return float(match.group(1))
            return 0
        except ValueError:
            return 0
    
    def save_property_enhanced(self, property_data):
        """改良版物件データ保存"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 物件のハッシュを生成（より詳細な情報で重複チェック）
            hash_data = f"{property_data['address']}{property_data['room_layout']}{property_data['floor_area']}{property_data.get('floor', '')}"
            property_hash = hashlib.md5(hash_data.encode()).hexdigest()
            
            # 既存物件をチェック
            cursor.execute('SELECT id FROM properties WHERE master_property_hash = ?', (property_hash,))
            existing = cursor.fetchone()
            
            if existing:
                property_id = existing[0]
                # 価格を更新
                cursor.execute('''
                    UPDATE properties 
                    SET current_price = ?, management_fee = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (property_data['current_price'], property_data.get('management_fee', 0), property_id))
                
                self.logger.info(f"  🔄 物件更新: {property_data['address'][:30]}...")
            else:
                # 新規物件を挿入
                cursor.execute('''
                    INSERT INTO properties 
                    (area_id, address, building_name, room_layout, floor_area, building_age, 
                     floor, structure, current_price, management_fee, first_listed_at, 
                     master_property_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (
                    property_data['area_id'],
                    property_data['address'],
                    property_data.get('building_name', ''),
                    property_data['room_layout'],
                    property_data['floor_area'],
                    property_data.get('building_age'),
                    property_data.get('floor'),
                    property_data.get('structure'),
                    property_data['current_price'],
                    property_data.get('management_fee', 0),
                    property_data.get('first_listed_at', date.today().isoformat()),
                    property_hash
                ))
                property_id = cursor.lastrowid
                
                self.logger.info(f"  ✅ 新規物件: {property_data['address'][:30]}...")
            
            # リスティング情報を保存
            listing_id = hashlib.md5(f"{property_data['source_site']}{property_data['source_url']}".encode()).hexdigest()
            cursor.execute('''
                INSERT OR REPLACE INTO property_listings
                (property_id, source_site, source_url, listing_id, agent_company, 
                 listed_price, is_active, scraped_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                property_id,
                property_data['source_site'],
                property_data['source_url'],
                listing_id,
                property_data.get('agent_company', ''),
                property_data['current_price']
            ))
            
            conn.commit()
            return property_id
            
        except Exception as e:
            self.logger.error(f"データベース保存エラー: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def enhanced_scrape_suumo(self, area_code='13103'):
        """改良版SUUMOスクレイピング"""
        self.logger.info("🏠 改良版SUUMOスクレイピング開始...")
        
        base_url = 'https://suumo.jp/ms/chuko/tokyo/sc_minato/'
        
        count = 0
        max_pages = self.rate_limits['suumo']['max_pages']
        max_items = self.rate_limits['suumo']['max_items']
        
        for page in range(1, max_pages + 1):
            if count >= max_items:
                self.logger.info(f"最大取得件数 ({max_items}) に達しました")
                break
            
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}?page={page}"
            
            try:
                self.logger.info(f"📄 SUUMOページ {page}/{max_pages} を処理中...")
                
                if page > 1:
                    self.respectful_delay('suumo')
                
                html_content = self.safe_request(url)
                if not html_content:
                    self.logger.error(f"ページ {page} の取得に失敗しました")
                    continue
                
                properties = self.enhanced_parse_suumo(html_content)
                
                if not properties:
                    self.logger.info(f"ページ {page} に物件が見つかりません")
                    break
                
                page_saved = 0
                for prop in properties:
                    if count >= max_items:
                        break
                    
                    if self.save_property_enhanced(prop):
                        page_saved += 1
                        count += 1
                        self.scraped_count += 1
                
                self.logger.info(f"ページ {page} 完了: {page_saved} 件保存")
                
            except Exception as e:
                self.logger.error(f"SUUMOページ {page} 処理エラー: {e}")
                continue
        
        self.logger.info(f"✅ SUUMO完了: {count} 件の物件を取得")
        return count
    
    def run_enhanced_scraping(self):
        """改良版スクレイピング実行"""
        self.logger.info("🚀 改良版不動産スクレイピング開始")
        self.logger.info("=" * 50)
        
        total_count = 0
        
        # SUUMO
        try:
            self.logger.info("改良版SUUMO処理開始...")
            suumo_count = self.enhanced_scrape_suumo()
            total_count += suumo_count
            
            # 十分な間隔を空ける
            inter_site_delay = random.uniform(15, 25)
            self.logger.info(f"次のサイトまで {inter_site_delay:.1f}秒待機...")
            time.sleep(inter_site_delay)
            
        except Exception as e:
            self.logger.error(f"SUUMOスクレイピングエラー: {e}")
        
        self.logger.info("=" * 50)
        self.logger.info(f"🎉 改良版スクレイピング完了: 合計 {total_count} 件")
        
        # 統計情報を表示
        self.show_scraping_statistics()
        
        return total_count
    
    def show_scraping_statistics(self):
        """スクレイピング統計を表示"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_properties = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM property_listings')
        total_listings = cursor.fetchone()[0]
        
        cursor.execute('SELECT source_site, COUNT(*) FROM property_listings GROUP BY source_site')
        site_stats = cursor.fetchall()
        
        print("\n📊 スクレイピング統計:")
        print(f"総物件数: {total_properties}")
        print(f"総リスティング数: {total_listings}")
        print("サイト別リスティング:")
        for site, count in site_stats:
            print(f"  - {site}: {count} 件")
        
        conn.close()

def main():
    """メイン実行関数"""
    scraper = EnhancedScraper()
    
    print("🚀 改良版不動産スクレイピングエンジン")
    print("=" * 40)
    
    try:
        total_count = scraper.run_enhanced_scraping()
        print(f"\n🎉 スクレイピング完了: {total_count} 件のデータを取得")
        
    except KeyboardInterrupt:
        print("\n⚠️  スクレイピングが中断されました")
    except Exception as e:
        print(f"❌ スクレイピングエラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()