#!/usr/bin/env python3
"""
現在のノムコム詳細ページフォーマットの確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from bs4 import BeautifulSoup

# テスト用スクレイパー
scraper = NomuScraper()

# 実際の詳細ページURL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print("ノムコム詳細ページフォーマット確認")
print(f"URL: {test_url}")
print("="*60)

# ページ構造の確認
soup = scraper.fetch_page(test_url)
if soup:
    print("\n=== ページ構造の確認 ===")
    
    # 1. タイトル（h1タグ）
    h1_tags = soup.find_all("h1")
    print(f"\nh1タグ数: {len(h1_tags)}")
    for i, h1 in enumerate(h1_tags[:3]):
        print(f"  [{i+1}] class={h1.get('class', [])} text={h1.get_text(strip=True)[:50]}")
    
    # 2. 価格要素
    print(f"\n価格要素の確認:")
    price_divs = soup.find_all("div", {"class": "price"})
    print(f"  div.price数: {len(price_divs)}")
    if price_divs:
        print(f"  最初の価格: {price_divs[0].get_text(strip=True)}")
    
    price_p = soup.find("p", {"class": "priceTxt"})
    if price_p:
        print(f"  p.priceTxt: {price_p.get_text(strip=True)}")
    
    # 3. 住所要素
    print(f"\n住所要素の確認:")
    address_p = soup.find("p", {"class": "address"})
    if address_p:
        print(f"  p.address: {address_p.get_text(strip=True)}")
    
    # 4. 主要な情報テーブル
    print(f"\nテーブル構造:")
    tables = soup.find_all("table")
    print(f"  テーブル総数: {len(tables)}")
    
    # 最初のテーブルの内容を確認
    if tables:
        print(f"\n  最初のテーブルの内容:")
        first_table = tables[0]
        rows = first_table.find_all("tr")[:5]
        for row in rows:
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                print(f"    {cells[0].get_text(strip=True)}: {cells[1].get_text(strip=True)[:50]}")
    
    # 5. 実際に詳細データを取得
    print("\n=== parse_property_detailの実行結果 ===")
    detail_data = scraper.parse_property_detail(test_url)
    
    if detail_data:
        print("\n取得できたフィールド:")
        important_fields = [
            'building_name', 'price', 'address', 'station_info',
            'layout', 'area', 'floor_number', 'direction',
            'management_fee', 'repair_fund', 'built_year',
            'total_floors', 'structure'
        ]
        
        for field in important_fields:
            value = detail_data.get(field, '未取得')
            print(f"  {field}: {value}")
        
        # その他のフィールド
        print("\nその他のフィールド:")
        for key, value in detail_data.items():
            if key not in important_fields and key != 'detail_info':
                print(f"  {key}: {value}")
    else:
        print("詳細データの取得に失敗しました")