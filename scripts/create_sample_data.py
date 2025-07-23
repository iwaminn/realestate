#!/usr/bin/env python3
"""
サンプル物件データを作成
"""

import sqlite3
from datetime import datetime, timedelta
import random

def create_sample_data():
    conn = sqlite3.connect('data/realestate.db')
    cursor = conn.cursor()
    
    # まず港区のエリアを追加
    cursor.execute("""
        INSERT OR IGNORE INTO areas (prefecture_name, ward_name, is_active)
        VALUES ('東京都', '港区', 1)
    """)
    cursor.execute("SELECT id FROM areas WHERE ward_name = '港区'")
    area_id = cursor.fetchone()[0]
    
    # サンプル物件データ
    sample_properties = [
        {
            'title': 'パークコート赤坂檜町ザ タワー',
            'price': 28000,
            'address': '東京都港区赤坂9丁目',
            'area': 85.5,
            'layout': '2LDK',
            'age': 5,
            'floor': '15階',
            'building_type': 'マンション',
            'station_info': '東京メトロ千代田線「乃木坂」駅 徒歩3分',
            'source_site': 'SUUMO',
            'url': 'https://suumo.jp/sample1',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '高級タワーマンション。南向きで眺望良好。'
        },
        {
            'title': 'ブリリアタワー東京',
            'price': 15800,
            'address': '東京都港区海岸1丁目',
            'area': 65.3,
            'layout': '1LDK',
            'age': 8,
            'floor': '23階',
            'building_type': 'マンション',
            'station_info': 'JR山手線「浜松町」駅 徒歩5分',
            'source_site': 'AtHome',
            'url': 'https://athome.co.jp/sample1',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '駅近タワーマンション。ペット可。'
        },
        {
            'title': '芝パークタワー',
            'price': 12500,
            'address': '東京都港区芝3丁目',
            'area': 55.8,
            'layout': '1LDK',
            'age': 12,
            'floor': '18階',
            'building_type': 'マンション',
            'station_info': '都営三田線「芝公園」駅 徒歩2分',
            'source_site': 'HOMES',
            'url': 'https://homes.co.jp/sample1',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '東京タワービュー。管理体制良好。'
        },
        {
            'title': 'プラウドタワー白金台',
            'price': 23000,
            'address': '東京都港区白金台4丁目',
            'area': 75.2,
            'layout': '2LDK',
            'age': 3,
            'floor': '8階',
            'building_type': 'マンション',
            'station_info': '東京メトロ南北線「白金台」駅 徒歩4分',
            'source_site': '楽待',
            'url': 'https://rakumachi.jp/sample1',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '高級住宅街の新築マンション。'
        },
        {
            'title': 'ザ・パークハウス 三田ガーデン',
            'price': 18500,
            'address': '東京都港区三田2丁目',
            'area': 68.9,
            'layout': '2LDK',
            'age': 6,
            'floor': '12階',
            'building_type': 'マンション',
            'station_info': '都営浅草線「三田」駅 徒歩6分',
            'source_site': 'SUUMO',
            'url': 'https://suumo.jp/sample2',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '緑豊かな環境。大規模修繕済み。'
        },
        {
            'title': 'グランスイート麻布台ヒルトップタワー',
            'price': 35000,
            'address': '東京都港区麻布台1丁目',
            'area': 95.5,
            'layout': '3LDK',
            'age': 10,
            'floor': '28階',
            'building_type': 'マンション',
            'station_info': '東京メトロ日比谷線「神谷町」駅 徒歩5分',
            'source_site': 'AtHome',
            'url': 'https://athome.co.jp/sample2',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '最上階に近い高層階。360度パノラマビュー。'
        },
        {
            'title': 'パークハビオ赤坂タワー',
            'price': 8900,
            'address': '東京都港区赤坂2丁目',
            'area': 40.5,
            'layout': '1K',
            'age': 7,
            'floor': '10階',
            'building_type': 'マンション',
            'station_info': '東京メトロ千代田線「赤坂」駅 徒歩2分',
            'source_site': 'HOMES',
            'url': 'https://homes.co.jp/sample2',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '単身者向け。セキュリティ充実。'
        },
        {
            'title': 'ラ・トゥール新宿',
            'price': 45000,
            'address': '東京都港区西麻布3丁目',
            'area': 120.3,
            'layout': '3LDK',
            'age': 15,
            'floor': '35階',
            'building_type': 'マンション',
            'station_info': '東京メトロ日比谷線「六本木」駅 徒歩8分',
            'source_site': '楽待',
            'url': 'https://rakumachi.jp/sample2',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '超高級タワーマンション。コンシェルジュサービス付き。'
        },
        {
            'title': 'プラウド南青山',
            'price': 16000,
            'address': '東京都港区南青山5丁目',
            'area': 58.7,
            'layout': '1LDK',
            'age': 4,
            'floor': '5階',
            'building_type': 'マンション',
            'station_info': '東京メトロ銀座線「表参道」駅 徒歩7分',
            'source_site': 'SUUMO',
            'url': 'https://suumo.jp/sample3',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': '表参道エリアの低層マンション。'
        },
        {
            'title': 'ドムス南青山',
            'price': 19800,
            'address': '東京都港区南青山3丁目',
            'area': 72.1,
            'layout': '2LDK',
            'age': 20,
            'floor': '7階',
            'building_type': 'マンション',
            'station_info': '東京メトロ半蔵門線「表参道」駅 徒歩5分',
            'source_site': 'AtHome',
            'url': 'https://athome.co.jp/sample3',
            'image_url': 'https://via.placeholder.com/300x200',
            'description': 'ヴィンテージマンション。リノベーション済み。'
        }
    ]
    
    # 既存データをクリア
    cursor.execute("DELETE FROM property_listings")
    cursor.execute("DELETE FROM properties")
    cursor.execute("DELETE FROM price_history")
    
    # サンプルデータを挿入
    for prop in sample_properties:
        # property_hashを生成
        hash_string = f"{prop['address']}{prop['layout']}{prop['area']}{prop['age']}"
        import hashlib
        property_hash = hashlib.md5(hash_string.encode()).hexdigest()
        
        # propertiesテーブルに挿入
        cursor.execute("""
            INSERT INTO properties (
                area_id, address, room_layout, floor_area, current_price,
                building_name, building_age, property_hash, source_site,
                first_listed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            area_id, prop['address'], prop['layout'], prop['area'],
            prop['price'], prop['title'], prop['age'], property_hash,
            prop['source_site'],
            datetime.now() - timedelta(days=random.randint(1, 30)),
            datetime.now(), datetime.now()
        ))
        
        property_id = cursor.lastrowid
        
        # property_listingsテーブルに挿入
        cursor.execute("""
            INSERT INTO property_listings (
                property_id, source_site, source_url, listing_id,
                agent_company, listed_price, is_active,
                scraped_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            property_id, prop['source_site'], prop['url'],
            f"{prop['source_site']}_{property_id}",
            f"{prop['source_site']}不動産", prop['price'], 1,
            datetime.now(), datetime.now(), datetime.now()
        ))
        
        # 価格履歴を追加（3〜5件）
        base_price = prop['price']
        for i in range(random.randint(3, 5)):
            price_variation = random.randint(-500, 500)
            historical_price = base_price + price_variation
            date_recorded = datetime.now() - timedelta(days=i * 30)
            
            cursor.execute("""
                INSERT INTO price_history (
                    property_id, price, source_site, agent_company, updated_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (property_id, historical_price, prop['source_site'],
                  f"{prop['source_site']}不動産", date_recorded))
    
    # 重複物件をいくつか追加（同じ物件を別サイトから）
    # 最初の2つの物件のproperty_idを取得
    cursor.execute("SELECT id, property_hash FROM properties LIMIT 2")
    existing_properties = cursor.fetchall()
    
    if len(existing_properties) >= 2:
        # 既存物件に別サイトからのリスティングを追加
        duplicate_listings = [
            {
                'property_id': existing_properties[0][0],
                'source_site': 'HOMES',
                'url': 'https://homes.co.jp/duplicate1',
                'price': 27800
            },
            {
                'property_id': existing_properties[1][0],
                'source_site': '楽待',
                'url': 'https://rakumachi.jp/duplicate1',
                'price': 15900
            }
        ]
        
        for dup in duplicate_listings:
            cursor.execute("""
                INSERT INTO property_listings (
                    property_id, source_site, source_url, listing_id,
                    agent_company, listed_price, is_active,
                    scraped_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dup['property_id'], dup['source_site'], dup['url'],
                f"{dup['source_site']}_{dup['property_id']}",
                f"{dup['source_site']}不動産", dup['price'], 1,
                datetime.now(), datetime.now(), datetime.now()
            ))
    
    conn.commit()
    conn.close()
    
    print(f"Created {len(sample_properties)} sample properties with price history")
    print(f"Added duplicate listings for cross-site comparison")

if __name__ == "__main__":
    create_sample_data()