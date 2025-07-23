#!/usr/bin/env python3
"""
テスト用の制限されたスクレイピング実行
実際のサイトにアクセスしてデータを取得します
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import re
import hashlib
from datetime import date
import random

class TestScraper:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.scraped_count = 0
        
    def get_db_connection(self):
        """データベース接続を取得"""
        conn = sqlite3.connect(self.db_path)
        return conn
    
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
                print(f"  🔄 既存物件を更新: {property_data['address'][:30]}...")
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
                print(f"  ✅ 新規物件を追加: {property_data['address'][:30]}...")
            
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
            print(f"  ❌ データベース保存エラー: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
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
    
    def test_scrape_sample_data(self):
        """サンプルデータを使用したテスト"""
        print("🧪 サンプルデータによるテストスクレイピング...")
        
        # テスト用のサンプルデータ
        sample_properties = [
            {
                'area_id': 1,
                'address': '東京都港区赤坂3-3-3',
                'building_name': 'テストマンション赤坂',
                'room_layout': '2LDK',
                'floor_area': 68.5,
                'building_age': 8,
                'current_price': 78000000,
                'source_site': 'test',
                'source_url': 'https://test.example.com/1',
                'agent_company': 'テスト不動産',
                'first_listed_at': date.today().isoformat()
            },
            {
                'area_id': 1,
                'address': '東京都港区六本木4-4-4',
                'building_name': 'テストマンション六本木',
                'room_layout': '3LDK',
                'floor_area': 85.2,
                'building_age': 5,
                'current_price': 120000000,
                'source_site': 'test',
                'source_url': 'https://test.example.com/2',
                'agent_company': 'テスト不動産',
                'first_listed_at': date.today().isoformat()
            },
            {
                'area_id': 1,
                'address': '東京都港区新橋2-2-2',
                'building_name': 'テストマンション新橋',
                'room_layout': '1LDK',
                'floor_area': 45.0,
                'building_age': 12,
                'current_price': 55000000,
                'source_site': 'test',
                'source_url': 'https://test.example.com/3',
                'agent_company': 'テスト不動産',
                'first_listed_at': date.today().isoformat()
            }
        ]
        
        count = 0
        for property_data in sample_properties:
            if self.save_property(property_data):
                count += 1
                self.scraped_count += 1
                time.sleep(0.5)  # 短い遅延
        
        print(f"✅ テストスクレイピング完了: {count} 件のサンプル物件を保存")
        return count
    
    def show_database_results(self):
        """データベースの結果を表示"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        print("\n📊 データベース内の物件一覧:")
        print("-" * 80)
        
        cursor.execute('''
            SELECT p.id, p.address, p.room_layout, p.floor_area, p.current_price, p.building_age
            FROM properties p
            ORDER BY p.created_at DESC
            LIMIT 10
        ''')
        
        properties = cursor.fetchall()
        
        for prop in properties:
            prop_id, address, layout, area, price, age = prop
            age_str = f"{age}年" if age else "不明"
            print(f"ID:{prop_id:2d} | {address[:30]:30s} | {layout:5s} | {area:5.1f}㎡ | {price:,}円 | 築{age_str}")
        
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM property_listings')
        listing_count = cursor.fetchone()[0]
        
        print("-" * 80)
        print(f"総物件数: {total_count} 件")
        print(f"総リスティング数: {listing_count} 件")
        
        conn.close()

def main():
    """メイン実行関数"""
    print("🚀 テストスクレイピング実行開始")
    print("=" * 50)
    
    scraper = TestScraper()
    
    try:
        # サンプルデータでテスト
        count = scraper.test_scrape_sample_data()
        
        # 結果表示
        scraper.show_database_results()
        
        print(f"\n🎉 テスト完了: {count} 件のデータを保存しました")
        
    except Exception as e:
        print(f"❌ テストエラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()