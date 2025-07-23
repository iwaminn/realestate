#!/usr/bin/env python3
"""
不動産サイトスクレイピング機能
SUUMO、アットホーム、ホームズから物件情報を収集
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import json
import re
import hashlib
from datetime import datetime, date
from urllib.parse import urljoin, urlparse
import sys
import random
import logging
from urllib.robotparser import RobotFileParser

class RealEstateScraper:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.session = requests.Session()
        
        # 規約遵守のための設定
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # レート制限設定
        self.rate_limits = {
            'suumo': {'min_delay': 3, 'max_delay': 6, 'max_pages': 5},
            'athome': {'min_delay': 4, 'max_delay': 8, 'max_pages': 3},
            'homes': {'min_delay': 5, 'max_delay': 10, 'max_pages': 3}
        }
        
        self.scraped_count = 0
        self.robots_cache = {}
        
        # ログ設定
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
    def get_db_connection(self):
        """データベース接続を取得"""
        conn = sqlite3.connect(self.db_path)
        return conn
    
    def check_robots_txt(self, site_url, user_agent='*'):
        """robots.txtをチェックしてアクセス可能かどうかを確認"""
        try:
            if site_url not in self.robots_cache:
                robots_url = urljoin(site_url, '/robots.txt')
                rp = RobotFileParser()
                rp.set_url(robots_url)
                rp.read()
                self.robots_cache[site_url] = rp
            
            return self.robots_cache[site_url]
        except:
            # robots.txtが取得できない場合は制限なしとして扱う
            return None
    
    def can_fetch(self, site_url, path, user_agent='*'):
        """指定のパスにアクセス可能かどうかをチェック"""
        rp = self.check_robots_txt(site_url, user_agent)
        if rp:
            return rp.can_fetch(user_agent, path)
        return True
    
    def respectful_delay(self, site_name):
        """サイトに応じた適切な遅延を実行"""
        if site_name in self.rate_limits:
            min_delay = self.rate_limits[site_name]['min_delay']
            max_delay = self.rate_limits[site_name]['max_delay']
            delay = random.uniform(min_delay, max_delay)
            self.logger.info(f"{site_name}: {delay:.1f}秒待機中...")
            time.sleep(delay)
        else:
            time.sleep(random.uniform(2, 5))  # デフォルト遅延
    
    def save_property(self, property_data):
        """物件データをデータベースに保存"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 物件のハッシュを生成（重複チェック用）
            hash_data = f"{property_data['address']}{property_data['room_layout']}{property_data['floor_area']}"
            property_hash = hashlib.md5(hash_data.encode()).hexdigest()
            
            # 既存物件をチェック
            cursor.execute('SELECT id FROM properties WHERE master_property_hash = ?', (property_hash,))
            existing = cursor.fetchone()
            
            if existing:
                property_id = existing[0]
                # 価格を更新
                cursor.execute('''
                    UPDATE properties 
                    SET current_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (property_data['current_price'], property_id))
            else:
                # 新規物件を挿入
                cursor.execute('''
                    INSERT INTO properties 
                    (area_id, address, building_name, room_layout, floor_area, building_age, 
                     current_price, first_listed_at, master_property_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (
                    property_data['area_id'],
                    property_data['address'],
                    property_data.get('building_name', ''),
                    property_data['room_layout'],
                    property_data['floor_area'],
                    property_data.get('building_age'),
                    property_data['current_price'],
                    property_data.get('first_listed_at', date.today().isoformat()),
                    property_hash
                ))
                property_id = cursor.lastrowid
            
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
            print(f"データベース保存エラー: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def scrape_suumo(self, area_code='13103'):
        """SUUMOから物件情報を取得（規約遵守版）"""
        self.logger.info("🏠 SUUMOスクレイピング開始...")
        
        base_url = 'https://suumo.jp/jj/bukken/ichiran/JJ010FV001/'
        site_url = 'https://suumo.jp'
        
        # robots.txtチェック
        if not self.can_fetch(site_url, '/jj/bukken/ichiran/JJ010FV001/'):
            self.logger.warning("⚠️  robots.txtによりSUUMOへのアクセスが制限されています")
            return 0
        
        params = {
            'ar': '030',      # 関東
            'bs': '040',      # 中古マンション
            'ta': '13',       # 東京都
            'sc': area_code,  # 港区
            'pn': 1
        }
        
        count = 0
        max_pages = self.rate_limits['suumo']['max_pages']
        
        for page in range(1, max_pages + 1):
            params['pn'] = page
            
            try:
                self.logger.info(f"📄 SUUMOページ {page}/{max_pages} を処理中...")
                
                # 適切な遅延を実行
                if page > 1:
                    self.respectful_delay('suumo')
                
                response = self.session.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 物件リストを取得
                property_items = soup.find_all('div', class_='cassetteitem')
                
                if not property_items:
                    self.logger.info(f"ページ {page} に物件が見つかりません")
                    break
                
                for item in property_items:
                    page_count = self.parse_suumo_item(item)
                    count += page_count
                
                self.logger.info(f"ページ {page} 完了: {len(property_items)} 件処理")
                
            except requests.RequestException as e:
                self.logger.error(f"SUUMOページ {page} の取得エラー: {e}")
                break
            except Exception as e:
                self.logger.error(f"SUUMOページ {page} の解析エラー: {e}")
                continue
        
        self.logger.info(f"✅ SUUMO完了: {count} 件の物件を取得")
        return count
    
    def parse_suumo_item(self, item):
        """SUUMO物件アイテムを解析"""
        count = 0
        
        try:
            # 基本情報
            title_elem = item.find('div', class_='cassetteitem_content-title')
            if not title_elem:
                return 0
            
            building_name = title_elem.get_text(strip=True)
            
            # 住所情報
            address_elem = item.find('li', class_='cassetteitem_detail-col1')
            if not address_elem:
                return 0
            
            address = address_elem.get_text(strip=True)
            
            # 各部屋の情報
            room_items = item.find_all('tbody')
            for tbody in room_items:
                rows = tbody.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 8:
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
                        
                        # 築年数
                        age_text = cols[5].get_text(strip=True)
                        building_age = self.parse_building_age(age_text)
                        
                        # 詳細リンク
                        link_elem = cols[8].find('a')
                        detail_url = ''
                        if link_elem and link_elem.get('href'):
                            detail_url = urljoin('https://suumo.jp', link_elem['href'])
                        
                        # 物件データを構築
                        property_data = {
                            'area_id': 1,  # 港区
                            'address': address,
                            'building_name': building_name,
                            'room_layout': layout_text,
                            'floor_area': floor_area,
                            'building_age': building_age,
                            'current_price': price,
                            'source_site': 'suumo',
                            'source_url': detail_url,
                            'agent_company': 'SUUMO掲載',
                            'first_listed_at': date.today().isoformat()
                        }
                        
                        # データベースに保存
                        if self.save_property(property_data):
                            count += 1
                            self.scraped_count += 1
                            
                            if count <= 3:  # 最初の3件だけ詳細表示
                                print(f"  📍 {address} {layout_text} {floor_area}㎡ {price:,}円")
        
        except Exception as e:
            print(f"SUUMO物件解析エラー: {e}")
        
        return count
    
    def scrape_athome(self, area_code='tokyo/minato-city'):
        """アットホームから物件情報を取得（規約遵守版）"""
        self.logger.info("🏠 アットホームスクレイピング開始...")
        
        base_url = f'https://www.athome.co.jp/kodate/chuko/{area_code}/list/'
        site_url = 'https://www.athome.co.jp'
        
        # robots.txtチェック
        if not self.can_fetch(site_url, f'/kodate/chuko/{area_code}/list/'):
            self.logger.warning("⚠️  robots.txtによりアットホームへのアクセスが制限されています")
            return 0
        
        try:
            self.logger.info("📄 アットホーム物件リストを取得中...")
            
            # 適切な遅延を実行
            self.respectful_delay('athome')
            
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 物件リストを取得
            property_items = soup.find_all('div', class_='property-unit')
            
            if not property_items:
                self.logger.info("アットホームで物件が見つかりませんでした")
                return 0
            
            count = 0
            max_items = min(len(property_items), 10)  # 最大10件まで
            
            for i, item in enumerate(property_items[:max_items]):
                if i > 0:
                    # 各物件間でも適切な遅延
                    time.sleep(random.uniform(1, 2))
                
                if self.parse_athome_item(item):
                    count += 1
                    self.scraped_count += 1
            
            self.logger.info(f"✅ アットホーム完了: {count} 件の物件を取得")
            return count
            
        except requests.RequestException as e:
            self.logger.error(f"アットホーム取得エラー: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"アットホーム解析エラー: {e}")
            return 0
    
    def parse_athome_item(self, item):
        """アットホーム物件アイテムを解析"""
        try:
            # 価格
            price_elem = item.find('span', class_='price')
            if not price_elem:
                return False
            
            price_text = price_elem.get_text(strip=True)
            price = self.parse_price(price_text)
            if price == 0:
                return False
            
            # 住所
            address_elem = item.find('div', class_='address')
            if not address_elem:
                return False
            
            address = address_elem.get_text(strip=True)
            
            # 間取り・面積
            details = item.find('div', class_='property-detail')
            if not details:
                return False
            
            detail_text = details.get_text(strip=True)
            
            # 間取りを抽出
            layout_match = re.search(r'(\d+[SLDK]+)', detail_text)
            room_layout = layout_match.group(1) if layout_match else '不明'
            
            # 面積を抽出
            area_match = re.search(r'(\d+\.?\d*)㎡', detail_text)
            floor_area = float(area_match.group(1)) if area_match else 0
            
            if floor_area == 0:
                return False
            
            # 築年数を抽出
            age_match = re.search(r'築(\d+)年', detail_text)
            building_age = int(age_match.group(1)) if age_match else None
            
            # 詳細リンク
            link_elem = item.find('a')
            detail_url = ''
            if link_elem and link_elem.get('href'):
                detail_url = urljoin('https://www.athome.co.jp', link_elem['href'])
            
            # 物件データを構築
            property_data = {
                'area_id': 1,  # 港区
                'address': address,
                'building_name': '',
                'room_layout': room_layout,
                'floor_area': floor_area,
                'building_age': building_age,
                'current_price': price,
                'source_site': 'athome',
                'source_url': detail_url,
                'agent_company': 'アットホーム掲載',
                'first_listed_at': date.today().isoformat()
            }
            
            # データベースに保存
            if self.save_property(property_data):
                print(f"  📍 {address} {room_layout} {floor_area}㎡ {price:,}円")
                return True
            
        except Exception as e:
            print(f"アットホーム物件解析エラー: {e}")
        
        return False
    
    def parse_price(self, price_text):
        """価格文字列を数値に変換"""
        try:
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
            
            return price
            
        except (ValueError, IndexError):
            return 0
    
    def parse_area(self, area_text):
        """面積文字列を数値に変換"""
        try:
            match = re.search(r'(\d+\.?\d*)', area_text)
            if match:
                return float(match.group(1))
            return 0
        except ValueError:
            return 0
    
    def parse_building_age(self, age_text):
        """築年数文字列を数値に変換"""
        try:
            match = re.search(r'(\d+)', age_text)
            if match:
                return int(match.group(1))
            return None
        except ValueError:
            return None
    
    def scrape_all(self):
        """全サイトからスクレイピング実行（規約遵守版）"""
        self.logger.info("🚀 不動産スクレイピング開始")
        self.logger.info("=" * 50)
        self.logger.info("⚠️  各サイトの利用規約とrobots.txtを遵守してスクレイピングを実行します")
        self.logger.info("📋 取得制限: SUUMO最大5ページ、アットホーム最大10件")
        
        total_count = 0
        
        # SUUMO
        try:
            self.logger.info("1/2 SUUMO処理開始...")
            suumo_count = self.scrape_suumo()
            total_count += suumo_count
            
            # サイト間の十分な間隔
            inter_site_delay = random.uniform(10, 15)
            self.logger.info(f"次のサイトまで {inter_site_delay:.1f}秒待機...")
            time.sleep(inter_site_delay)
            
        except Exception as e:
            self.logger.error(f"SUUMOスクレイピングエラー: {e}")
        
        # アットホーム
        try:
            self.logger.info("2/2 アットホーム処理開始...")
            athome_count = self.scrape_athome()
            total_count += athome_count
            
        except Exception as e:
            self.logger.error(f"アットホームスクレイピングエラー: {e}")
        
        self.logger.info("=" * 50)
        self.logger.info(f"🎉 スクレイピング完了: 合計 {total_count} 件の物件を取得")
        self.logger.info("📊 規約遵守のため、取得件数を制限しています")
        
        return total_count

def main():
    """メイン実行関数"""
    if len(sys.argv) > 1 and sys.argv[1] == '--area':
        area = sys.argv[2] if len(sys.argv) > 2 else 'minato'
        print(f"対象エリア: {area}")
    
    scraper = RealEstateScraper()
    
    try:
        total_count = scraper.scrape_all()
        print(f"\n📊 スクレイピング結果: {total_count} 件")
        
        # 結果確認
        conn = scraper.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_properties = cursor.fetchone()[0]
        print(f"💾 データベース内総物件数: {total_properties} 件")
        conn.close()
        
    except KeyboardInterrupt:
        print("\n⚠️  スクレイピングが中断されました")
    except Exception as e:
        print(f"❌ スクレイピングエラー: {e}")

if __name__ == '__main__':
    main()