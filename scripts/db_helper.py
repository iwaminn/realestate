#!/usr/bin/env python3
"""
SQLiteデータベース管理ヘルパー
psqlコマンドの代わりにSQLiteデータベースを操作するためのツール
"""

import sqlite3
import sys
import json
from datetime import datetime

class DatabaseHelper:
    def __init__(self, db_path='realestate.db'):
        self.db_path = db_path
    
    def connect(self):
        """データベースに接続"""
        return sqlite3.connect(self.db_path)
    
    def show_tables(self):
        """テーブル一覧を表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("📋 テーブル一覧:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  - {table[0]:20s} ({count} 件)")
        
        conn.close()
    
    def show_schema(self, table_name):
        """テーブル構造を表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        print(f"🏗️  {table_name}テーブルの構造:")
        print("カラム名             | データ型   | NOT NULL | デフォルト値")
        print("-" * 60)
        for col in columns:
            null_str = "Yes" if col[3] else "No"
            default = col[4] or "None"
            print(f"{col[1]:20s} | {col[2]:10s} | {null_str:8s} | {default}")
        
        conn.close()
    
    def show_properties(self, limit=10):
        """物件データを表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute(f'''
            SELECT id, address, building_name, room_layout, floor_area, 
                   current_price, building_age, created_at
            FROM properties 
            ORDER BY current_price DESC 
            LIMIT {limit}
        ''')
        
        properties = cursor.fetchall()
        
        print(f"🏠 物件データ (上位{limit}件):")
        print("ID | 住所                       | 建物名           | 間取り | 面積    | 価格        | 築年数 | 登録日")
        print("-" * 110)
        
        for prop in properties:
            prop_id, address, building, layout, area, price, age, created = prop
            age_str = f"{age}年" if age else "不明"
            building_str = building[:15] if building else "なし"
            created_str = created[:10] if created else "不明"
            
            print(f"{prop_id:2d} | {address[:25]:25s} | {building_str:15s} | {layout:6s} | {area:6.1f}㎡ | {price:,}円 | {age_str:6s} | {created_str}")
        
        conn.close()
    
    def show_listings(self, limit=10):
        """リスティング情報を表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute(f'''
            SELECT pl.id, pl.property_id, p.address, pl.source_site, 
                   pl.agent_company, pl.listed_price, pl.is_active, pl.created_at
            FROM property_listings pl
            JOIN properties p ON pl.property_id = p.id
            ORDER BY pl.created_at DESC
            LIMIT {limit}
        ''')
        
        listings = cursor.fetchall()
        
        print(f"📝 リスティング情報 (最新{limit}件):")
        print("ID | 物件ID | 住所                       | サイト    | 業者           | 価格        | 有効 | 登録日")
        print("-" * 110)
        
        for listing in listings:
            list_id, prop_id, address, site, agent, price, active, created = listing
            active_str = "有効" if active else "無効"
            created_str = created[:10] if created else "不明"
            
            print(f"{list_id:2d} | {prop_id:6d} | {address[:25]:25s} | {site:9s} | {agent[:13]:13s} | {price:,}円 | {active_str:4s} | {created_str}")
        
        conn.close()
    
    def show_areas(self):
        """エリア情報を表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT a.id, a.prefecture_name, a.city_name, a.ward_name, 
                   a.is_active, COUNT(p.id) as property_count
            FROM areas a
            LEFT JOIN properties p ON a.id = p.area_id
            GROUP BY a.id
            ORDER BY a.id
        ''')
        
        areas = cursor.fetchall()
        
        print("🗺️  エリア情報:")
        print("ID | 都道府県 | 市区町村 | 区名   | 有効 | 物件数")
        print("-" * 50)
        
        for area in areas:
            area_id, prefecture, city, ward, active, count = area
            active_str = "有効" if active else "無効"
            city_str = city or ""
            ward_str = ward or ""
            
            print(f"{area_id:2d} | {prefecture:8s} | {city_str:8s} | {ward_str:6s} | {active_str:4s} | {count:6d}")
        
        conn.close()
    
    def execute_query(self, query):
        """任意のクエリを実行"""
        conn = self.connect()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                
                # カラム名を取得
                columns = [description[0] for description in cursor.description]
                print(f"📊 クエリ結果 ({len(results)} 件):")
                print(" | ".join(columns))
                print("-" * (len(" | ".join(columns))))
                
                for row in results:
                    print(" | ".join(str(item) for item in row))
            else:
                conn.commit()
                print("✅ クエリが実行されました")
                
        except Exception as e:
            print(f"❌ エラー: {e}")
        finally:
            conn.close()
    
    def show_statistics(self):
        """統計情報を表示"""
        conn = self.connect()
        cursor = conn.cursor()
        
        print("📊 データベース統計:")
        print("-" * 40)
        
        # 各テーブルの件数
        tables = ['areas', 'properties', 'property_listings', 'price_history']
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"{table:20s}: {count:6d} 件")
        
        print("\n💰 価格統計:")
        cursor.execute('''
            SELECT 
                MIN(current_price) as min_price,
                MAX(current_price) as max_price,
                AVG(current_price) as avg_price,
                COUNT(*) as total_count
            FROM properties
        ''')
        
        stats = cursor.fetchone()
        min_price, max_price, avg_price, total_count = stats
        
        print(f"最低価格: {min_price:,}円")
        print(f"最高価格: {max_price:,}円")
        print(f"平均価格: {avg_price:,.0f}円")
        print(f"総物件数: {total_count} 件")
        
        print("\n🏠 間取り別統計:")
        cursor.execute('''
            SELECT room_layout, COUNT(*) as count, AVG(current_price) as avg_price
            FROM properties
            GROUP BY room_layout
            ORDER BY count DESC
        ''')
        
        layout_stats = cursor.fetchall()
        for layout, count, avg_price in layout_stats:
            print(f"{layout:6s}: {count:2d} 件 (平均 {avg_price:,.0f}円)")
        
        conn.close()

def main():
    """コマンドライン実行"""
    db = DatabaseHelper()
    
    if len(sys.argv) == 1:
        print("🗄️  SQLiteデータベースヘルパー")
        print("=" * 40)
        print("使用方法:")
        print("  python3 db_helper.py tables          # テーブル一覧")
        print("  python3 db_helper.py schema TABLE    # テーブル構造")
        print("  python3 db_helper.py properties      # 物件データ")
        print("  python3 db_helper.py listings        # リスティング情報")
        print("  python3 db_helper.py areas           # エリア情報")
        print("  python3 db_helper.py stats           # 統計情報")
        print("  python3 db_helper.py query 'SQL'     # 任意のクエリ実行")
        print()
        print("例:")
        print("  python3 db_helper.py query 'SELECT * FROM properties LIMIT 3'")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'tables':
        db.show_tables()
    elif command == 'schema':
        if len(sys.argv) < 3:
            print("❌ テーブル名を指定してください")
            return
        db.show_schema(sys.argv[2])
    elif command == 'properties':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        db.show_properties(limit)
    elif command == 'listings':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        db.show_listings(limit)
    elif command == 'areas':
        db.show_areas()
    elif command == 'stats':
        db.show_statistics()
    elif command == 'query':
        if len(sys.argv) < 3:
            print("❌ クエリを指定してください")
            return
        db.execute_query(sys.argv[2])
    else:
        print(f"❌ 不明なコマンド: {command}")

if __name__ == '__main__':
    main()