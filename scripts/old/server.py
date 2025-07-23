#!/usr/bin/env python3
"""
Laravel-like development server in Python
不動産サイト用の開発サーバー
"""

import json
import sqlite3
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import sys

class RealEstateServer(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.setup_database()
        super().__init__(*args, **kwargs)
    
    def setup_database(self):
        """SQLiteデータベースの初期化"""
        self.db_path = 'realestate.db'
        if not os.path.exists(self.db_path):
            self.init_database()
    
    def init_database(self):
        """データベーステーブルの作成"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Areas table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS areas (
                id INTEGER PRIMARY KEY,
                prefecture_code TEXT,
                city_code TEXT,
                ward_code TEXT,
                prefecture_name TEXT,
                city_name TEXT,
                ward_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Properties table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY,
                area_id INTEGER,
                address TEXT,
                building_name TEXT,
                room_layout TEXT,
                floor_area REAL,
                building_age INTEGER,
                floor INTEGER,
                total_floors INTEGER,
                structure TEXT,
                current_price INTEGER,
                management_fee INTEGER,
                repair_reserve_fund INTEGER,
                first_listed_at DATE,
                master_property_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id)
            )
        ''')
        
        # Property listings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS property_listings (
                id INTEGER PRIMARY KEY,
                property_id INTEGER,
                source_site TEXT,
                source_url TEXT,
                listing_id TEXT,
                agent_company TEXT,
                agent_contact TEXT,
                listed_price INTEGER,
                is_active BOOLEAN DEFAULT 1,
                scraped_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        ''')
        
        # Price history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY,
                property_id INTEGER,
                price INTEGER,
                source_site TEXT,
                agent_company TEXT,
                updated_at TIMESTAMP,
                first_listed_at DATE,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        ''')
        
        # 初期データの投入
        cursor.execute('''
            INSERT INTO areas (prefecture_code, ward_code, prefecture_name, ward_name, is_active)
            VALUES ('13', '103', '東京都', '港区', 1)
        ''')
        
        # サンプル物件データ
        cursor.execute('''
            INSERT INTO properties (area_id, address, room_layout, floor_area, building_age, current_price, first_listed_at, master_property_hash)
            VALUES (1, '東京都港区赤坂1-1-1', '3LDK', 75.5, 10, 85000000, '2024-01-01', 'sample_hash_1')
        ''')
        
        cursor.execute('''
            INSERT INTO properties (area_id, address, room_layout, floor_area, building_age, current_price, first_listed_at, master_property_hash)
            VALUES (1, '東京都港区六本木2-2-2', '2LDK', 65.0, 5, 95000000, '2024-01-02', 'sample_hash_2')
        ''')
        
        conn.commit()
        conn.close()
        print("Database initialized with sample data")
    
    def do_GET(self):
        """GET リクエストの処理"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        if path == '/':
            self.serve_welcome_page()
        elif path.startswith('/api/v1/properties'):
            if path == '/api/v1/properties':
                self.serve_properties_api(query_params)
            elif '/api/v1/properties/' in path:
                property_id = path.split('/')[-1]
                self.serve_property_detail_api(property_id)
        elif path == '/api/v1/areas':
            self.serve_areas_api()
        elif path == '/api/v1/stats':
            self.serve_stats_api()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """POST リクエストの処理"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        if path == '/api/v1/properties/compare':
            self.serve_compare_api()
        else:
            self.send_error(404, "Not Found")
    
    def serve_welcome_page(self):
        """ウェルカムページの提供"""
        with open('resources/views/welcome.blade.php', 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    def serve_properties_api(self, query_params):
        """物件一覧API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT p.*, a.prefecture_name, a.ward_name
            FROM properties p
            JOIN areas a ON p.area_id = a.id
            WHERE a.is_active = 1
        '''
        
        # フィルタリング
        params = []
        if 'min_price' in query_params:
            query += ' AND p.current_price >= ?'
            params.append(int(query_params['min_price'][0]))
        if 'max_price' in query_params:
            query += ' AND p.current_price <= ?'
            params.append(int(query_params['max_price'][0]))
        if 'room_layout' in query_params:
            query += ' AND p.room_layout = ?'
            params.append(query_params['room_layout'][0])
        
        # ソート
        sort_by = query_params.get('sort_by', ['current_price'])[0]
        sort_order = query_params.get('sort_order', ['asc'])[0]
        query += f' ORDER BY p.{sort_by} {sort_order}'
        
        # ページネーション
        per_page = int(query_params.get('per_page', ['20'])[0])
        page = int(query_params.get('page', ['1'])[0])
        offset = (page - 1) * per_page
        
        query += f' LIMIT {per_page} OFFSET {offset}'
        
        cursor.execute(query, params)
        properties = cursor.fetchall()
        
        # 結果を辞書形式に変換
        columns = [description[0] for description in cursor.description]
        results = []
        for prop in properties:
            prop_dict = dict(zip(columns, prop))
            results.append(prop_dict)
        
        # 総件数を取得
        count_query = '''
            SELECT COUNT(*)
            FROM properties p
            JOIN areas a ON p.area_id = a.id
            WHERE a.is_active = 1
        '''
        cursor.execute(count_query)
        total = cursor.fetchone()[0]
        
        conn.close()
        
        response = {
            'data': results,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total': total,
                'last_page': (total + per_page - 1) // per_page
            }
        }
        
        self.send_json_response(response)
    
    def serve_property_detail_api(self, property_id):
        """物件詳細API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.*, a.prefecture_name, a.ward_name
            FROM properties p
            JOIN areas a ON p.area_id = a.id
            WHERE p.id = ?
        ''', (property_id,))
        
        property_data = cursor.fetchone()
        if not property_data:
            self.send_error(404, "Property not found")
            return
        
        columns = [description[0] for description in cursor.description]
        property_dict = dict(zip(columns, property_data))
        
        # 価格履歴を取得
        cursor.execute('''
            SELECT * FROM price_history
            WHERE property_id = ?
            ORDER BY updated_at DESC
        ''', (property_id,))
        
        price_history = cursor.fetchall()
        history_columns = [description[0] for description in cursor.description]
        history_list = [dict(zip(history_columns, row)) for row in price_history]
        
        conn.close()
        
        response = {
            'property': property_dict,
            'price_history': history_list
        }
        
        self.send_json_response(response)
    
    def serve_areas_api(self):
        """エリア一覧API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.*, COUNT(p.id) as properties_count
            FROM areas a
            LEFT JOIN properties p ON a.id = p.area_id
            WHERE a.is_active = 1
            GROUP BY a.id
            ORDER BY a.prefecture_name, a.ward_name
        ''')
        
        areas = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, area)) for area in areas]
        
        conn.close()
        
        response = {'areas': results}
        self.send_json_response(response)
    
    def serve_stats_api(self):
        """統計情報API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 総物件数
        cursor.execute('SELECT COUNT(*) FROM properties')
        total_properties = cursor.fetchone()[0]
        
        # 平均価格
        cursor.execute('SELECT AVG(current_price) FROM properties')
        avg_price = cursor.fetchone()[0] or 0
        
        # 価格帯別分布
        cursor.execute('SELECT COUNT(*) FROM properties WHERE current_price < 50000000')
        under_50m = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM properties WHERE current_price BETWEEN 50000000 AND 100000000')
        between_50m_100m = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM properties WHERE current_price > 100000000')
        over_100m = cursor.fetchone()[0]
        
        # 間取り別分布
        cursor.execute('SELECT room_layout, COUNT(*) as count FROM properties GROUP BY room_layout ORDER BY count DESC')
        room_distribution = cursor.fetchall()
        
        conn.close()
        
        response = {
            'total_properties': total_properties,
            'average_price': int(avg_price),
            'price_ranges': {
                'under_50m': under_50m,
                '50m_to_100m': between_50m_100m,
                'over_100m': over_100m
            },
            'room_layout_distribution': [{'room_layout': row[0], 'count': row[1]} for row in room_distribution]
        }
        
        self.send_json_response(response)
    
    def serve_compare_api(self):
        """物件比較API"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            property_ids = data.get('property_ids', [])
            
            if not property_ids or len(property_ids) < 2:
                self.send_error(400, "At least 2 property IDs required")
                return
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            placeholders = ','.join(['?' for _ in property_ids])
            cursor.execute(f'''
                SELECT p.*, a.prefecture_name, a.ward_name
                FROM properties p
                JOIN areas a ON p.area_id = a.id
                WHERE p.id IN ({placeholders})
            ''', property_ids)
            
            properties = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            results = [dict(zip(columns, prop)) for prop in properties]
            
            conn.close()
            
            response = {'comparison': results}
            self.send_json_response(response)
            
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
    
    def send_json_response(self, data):
        """JSON レスポンスの送信"""
        response = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))

def run_server():
    """サーバーの起動"""
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, RealEstateServer)
    print("中古不動産横断検索サーバーを起動中...")
    print("http://localhost:8000 でアクセス可能")
    print("API エンドポイント:")
    print("  GET  /api/v1/properties - 物件一覧")
    print("  GET  /api/v1/properties/{id} - 物件詳細")
    print("  POST /api/v1/properties/compare - 物件比較")
    print("  GET  /api/v1/areas - エリア一覧")
    print("  GET  /api/v1/stats - 統計情報")
    print("サーバーを停止するには Ctrl+C を押してください")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しています...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()