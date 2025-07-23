#!/usr/bin/env python3
"""
SUUMO詳細ページのパースをテスト
"""

import sys
sys.path.append('/home/ubuntu/realestate/src')

from scrapers.suumo_scraper import SuumoScraper
import requests
from bs4 import BeautifulSoup

scraper = SuumoScraper()

# テストURL
url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77936729/"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

# パース実行
result = scraper.parse_property_detail(soup, url)

if result:
    print("=== パース成功 ===")
    for key, value in result.items():
        print(f"{key}: {value}")
else:
    print("=== パース失敗 ===")

# 必須フィールドチェック
required_fields = ['title', 'price', 'area', 'layout']
if result:
    missing = [field for field in required_fields if field not in result or result[field] is None]
    if missing:
        print(f"\n不足フィールド: {missing}")
        
        # テーブル情報を確認
        print("\n=== テーブル構造を確認 ===")
        tables = soup.find_all('table')
        print(f"テーブル数: {len(tables)}")
        
        # 各テーブルの最初の数行を表示
        for i, table in enumerate(tables[:3]):
            print(f"\nTable {i}:")
            rows = table.find_all('tr')[:5]
            for row in rows:
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    print(f"  {cells[0].get_text(strip=True)} : {cells[1].get_text(strip=True)}")
    else:
        print("\n必須フィールドはすべて存在")