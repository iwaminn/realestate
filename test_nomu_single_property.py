#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from bs4 import BeautifulSoup

# テスト用スクレイパー
scraper = NomuScraper()

# 特定の物件詳細ページを取得
url = "https://www.nomu.com/mansion/id/RF470004/"
print(f"Fetching: {url}")

soup = scraper.fetch_page(url)
if soup:
    detail_data = scraper.parse_property_detail(soup, url)
    if detail_data:
        print(f"\n取得した詳細データ:")
        for key, value in detail_data.items():
            print(f"  {key}: {value}")
        
        # 特に住所を確認
        if 'address' in detail_data:
            print(f"\n✓ 住所を取得しました: {detail_data['address']}")
        else:
            print("\n✗ 住所が取得できませんでした")
    else:
        print("詳細データの解析に失敗しました")
else:
    print("ページの取得に失敗しました")