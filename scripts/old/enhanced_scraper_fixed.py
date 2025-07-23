#!/usr/bin/env python3
"""
改良版不動産スクレイピングエンジン（修正版）
実際のSUUMOデータの取得機能
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
import json
import os

class EnhancedRealEstateScraper:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.scraped_count = 0
        self.session = requests.Session()
        
        # Headers for requests
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session.headers.update(self.headers)
        
        # Rate limiting
        self.rate_limits = {
            'suumo': {'min_delay': 5, 'max_delay': 10, 'max_pages': 10, 'max_items': 200},
        }
        
        # Logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Create necessary directories
        os.makedirs('cache', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
    
    def respectful_delay(self, site):
        """サイトに応じた適切な遅延"""
        config = self.rate_limits.get(site, {'min_delay': 3, 'max_delay': 8})
        delay = random.uniform(config['min_delay'], config['max_delay'])
        self.logger.info(f"{site}: {delay:.1f}秒待機中...")
        time.sleep(delay)
    
    def safe_request(self, url, max_retries=3):
        """安全なリクエスト送信"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                self.logger.warning(f"リクエスト失敗 (試行 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(2, 5))
                else:
                    self.logger.error(f"リクエスト最終失敗: {url}")
                    return None
    
    def enhanced_parse_suumo(self, html_content):
        """実際のSUUMO形式の解析"""
        soup = BeautifulSoup(html_content, 'html.parser')
        properties = []
        
        # property_unit-info クラスを探す (実際のデータが含まれる)
        property_items = soup.find_all('div', class_='property_unit-info')
        
        self.logger.info(f"物件要素を {len(property_items)} 個発見")
        
        for item in property_items:
            try:
                # 物件名の取得
                building_name = ""
                name_elem = item.find('dd')
                if name_elem:
                    building_name = name_elem.get_text(strip=True)
                
                # 価格の取得
                price = 0
                price_elem = item.find('span', class_='dottable-value')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'(\d+)万円', price_text)
                    if price_match:
                        price = int(price_match.group(1)) * 10000
                
                # 間取りの取得
                layout = ""
                item_text = item.get_text()
                layout_patterns = [r'(\d+DK)', r'(\d+LDK)', r'(\d+K)', r'(\d+R)']
                for pattern in layout_patterns:
                    match = re.search(pattern, item_text)
                    if match:
                        layout = match.group(1)
                        break
                
                # 面積の取得
                area = 0
                
                # 方法1: dt/dd要素から「専有面積」を探す
                area_elem = item.find('dt', text='専有面積')
                if area_elem:
                    area_dd = area_elem.find_next('dd')
                    if area_dd:
                        area_text = area_dd.get_text(strip=True)
                        # 「25.61m²（登記）」や「18.97m<sup>2</sup>（壁芯）」形式から面積を抽出
                        area_patterns = [
                            r'(\d+(?:\.\d+)?)m.*?2',  # 25.61m²や18.97m<sup>2</sup>に対応
                            r'(\d+(?:\.\d+)?)㎡',
                            r'(\d+(?:\.\d+)?)平米'
                        ]
                        
                        for pattern in area_patterns:
                            area_match = re.search(pattern, area_text)
                            if area_match:
                                area = float(area_match.group(1))
                                break
                
                # 方法2: テキスト全体から面積パターンを探す（フォールバック）
                if area == 0:
                    area_patterns = [
                        r'(\d+(?:\.\d+)?)m.*?2',
                        r'(\d+(?:\.\d+)?)㎡', 
                        r'(\d+(?:\.\d+)?)平米'
                    ]
                    
                    for pattern in area_patterns:
                        area_match = re.search(pattern, item_text)
                        if area_match:
                            area = float(area_match.group(1))
                            break
                
                # 住所の取得
                address = "東京都港区"
                address_elem = item.find('dt', text='所在地')
                if address_elem:
                    address_dd = address_elem.find_next('dd')
                    if address_dd:
                        address = address_dd.get_text(strip=True)
                
                # 築年月・築年数の取得（改良版）
                building_age = None
                construction_year = None
                construction_month = None
                construction_date = None
                
                # 方法1: dt/dd要素から「築年月」を探す
                building_age_elem = item.find('dt', text='築年月')
                if building_age_elem:
                    building_age_dd = building_age_elem.find_next('dd')
                    if building_age_dd:
                        building_age_text = building_age_dd.get_text(strip=True)
                        # 「1981年12月」形式から築年月と築年数を抽出
                        year_month_match = re.search(r'(\d{4})年(\d{1,2})月', building_age_text)
                        if year_month_match:
                            built_year = int(year_month_match.group(1))
                            built_month = int(year_month_match.group(2))
                            current_year = datetime.now().year
                            building_age = current_year - built_year
                            construction_year = built_year
                            construction_month = built_month
                            construction_date = f"{built_year}-{built_month:02d}-01"
                        else:
                            # 年のみの場合
                            year_match = re.search(r'(\d{4})年', building_age_text)
                            if year_match:
                                built_year = int(year_match.group(1))
                                current_year = datetime.now().year
                                building_age = current_year - built_year
                                construction_year = built_year
                
                # 方法2: テキストから築年数パターンを探す（フォールバック）
                if building_age is None:
                    age_patterns = [
                        r'築(\d+)年',
                        r'築年数(\d+)年',
                        r'築(\d+)',
                        r'(\d{4})年(\d{1,2})月築'
                    ]
                    
                    for pattern in age_patterns:
                        age_match = re.search(pattern, item_text)
                        if age_match:
                            if pattern.startswith(r'(\d{4})'):
                                # 年月形式の場合は計算
                                built_year = int(age_match.group(1))
                                current_year = datetime.now().year
                                building_age = current_year - built_year
                            else:
                                # 直接の築年数
                                building_age = int(age_match.group(1))
                            break
                
                # 詳細ページのURLと物件IDを取得
                detail_url = ""
                source_property_id = ""
                # 親要素のリンクを探す
                parent_link = item.find_parent().find('a', href=True)
                if parent_link:
                    detail_url = parent_link['href']
                    if not detail_url.startswith('http'):
                        detail_url = f"https://suumo.jp{detail_url}"
                    
                    # URLから物件IDを抽出
                    property_id_match = re.search(r'/nc_(\d+)/', detail_url)
                    if property_id_match:
                        source_property_id = f"nc_{property_id_match.group(1)}"
                
                # 最低限の情報があれば保存
                if price > 0:
                    property_data = {
                        'address': address,
                        'building_name': building_name or "物件名不明",
                        'room_layout': layout or "間取り不明",
                        'floor_area': area or 0,
                        'floor': None,
                        'building_age': building_age,
                        'construction_year': construction_year,
                        'construction_month': construction_month,
                        'construction_date': construction_date,
                        'structure': None,
                        'current_price': price,
                        'management_fee': 0,
                        'transport_info': "",
                        'source_site': 'suumo',
                        'source_url': detail_url,
                        'source_property_id': source_property_id,
                        'agent_company': 'SUUMO掲載',
                        'first_listed_at': date.today().isoformat()
                    }
                    
                    properties.append(property_data)
                    
            except Exception as e:
                self.logger.warning(f"物件情報解析エラー: {e}")
                continue
        
        return properties
    
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
    
    def calculate_property_hash(self, property_data):
        """物件の一意性を判定するハッシュ値を計算"""
        hash_string = f"{property_data['address']}_{property_data['room_layout']}_{property_data['floor_area']}_{property_data['building_age']}"
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    def save_property_enhanced(self, property_data):
        """改良版物件データ保存"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # ハッシュ値を計算
            prop_hash = self.calculate_property_hash(property_data)
            
            # 重複チェック
            cursor.execute('SELECT id FROM properties WHERE master_property_hash = ?', (prop_hash,))
            existing = cursor.fetchone()
            
            if existing:
                self.logger.debug(f"重複物件をスキップ: {property_data['building_name']}")
                return False
            
            # エリアの取得または作成
            cursor.execute('SELECT id FROM areas WHERE ward_name = ?', ('港区',))
            area_result = cursor.fetchone()
            
            if area_result:
                area_id = area_result[0]
            else:
                cursor.execute('''
                    INSERT INTO areas (prefecture_name, ward_name) 
                    VALUES (?, ?)
                ''', ('東京都', '港区'))
                area_id = cursor.lastrowid
            
            # 物件を保存
            cursor.execute('''
                INSERT INTO properties (
                    area_id, address, room_layout, floor_area, current_price,
                    first_listed_at, building_name, building_age, 
                    construction_year, construction_month, construction_date,
                    master_property_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                area_id, property_data['address'], property_data['room_layout'],
                property_data['floor_area'], property_data['current_price'],
                property_data['first_listed_at'], property_data['building_name'],
                property_data['building_age'], property_data['construction_year'],
                property_data['construction_month'], property_data['construction_date'],
                prop_hash
            ))
            
            property_id = cursor.lastrowid
            
            # リスティング情報を保存
            cursor.execute('''
                INSERT INTO property_listings (
                    property_id, source_site, agent_company, listed_price,
                    source_url, source_property_id, is_active, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ''', (
                property_id, property_data['source_site'], property_data['agent_company'],
                property_data['current_price'], property_data['source_url'],
                property_data['source_property_id']
            ))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"物件保存エラー: {e}")
            return False
    
    def run_enhanced_scraping(self):
        """改良版スクレイピングを実行"""
        self.logger.info("🚀 改良版不動産スクレイピング開始")
        self.logger.info("=" * 50)
        
        total_count = 0
        
        try:
            # SUUMO
            self.logger.info("改良版SUUMO処理開始...")
            suumo_count = self.enhanced_scrape_suumo()
            total_count += suumo_count
            
            # 次のサイトへの待機時間
            if total_count > 0:
                delay = random.uniform(15, 25)
                self.logger.info(f"次のサイトまで {delay:.1f}秒待機...")
                time.sleep(delay)
            
        except Exception as e:
            self.logger.error(f"SUUMOスクレイピングエラー: {e}")
        
        self.logger.info("=" * 50)
        self.logger.info(f"🎉 改良版スクレイピング完了: 合計 {total_count} 件")
        
        return total_count
    
    def print_stats(self):
        """データベース統計を表示"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_properties = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM property_listings')
        total_listings = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT source_site, COUNT(*) 
            FROM property_listings 
            GROUP BY source_site
        ''')
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
    scraper = EnhancedRealEstateScraper()
    
    print("🚀 改良版不動産スクレイピングエンジン")
    print("=" * 40)
    
    # 統計表示
    scraper.print_stats()
    
    # スクレイピング実行
    scraped_count = scraper.run_enhanced_scraping()
    
    print(f"\n🎉 スクレイピング完了: {scraped_count} 件のデータを取得")

if __name__ == "__main__":
    main()