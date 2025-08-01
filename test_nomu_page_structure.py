#!/usr/bin/env python3
"""
ノムコムのページ構造を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from bs4 import BeautifulSoup

# テスト用スクレイパー
scraper = NomuScraper()

# 問題の物件URL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print(f"ノムコムページ構造確認")
print(f"URL: {test_url}")
print("="*60)

# ページを取得
soup = scraper.fetch_page(test_url)
if soup:
    print("\n=== h1タグを探す ===")
    h1_tags = soup.find_all("h1")
    for i, h1 in enumerate(h1_tags[:5]):
        print(f"[{i+1}] {h1.get('class', [])} : {h1.get_text(strip=True)[:50]}")
    
    print("\n=== 建物名らしい要素を探す ===")
    # クラス名で探す
    for class_name in ["item_title", "property-title", "building-name", "title"]:
        elem = soup.find(attrs={"class": class_name})
        if elem:
            print(f"  class='{class_name}': {elem.get_text(strip=True)[:50]}")
    
    print("\n=== 価格情報を探す ===")
    # 価格らしいテキストを探す
    price_texts = soup.find_all(string=lambda text: text and "万円" in text)
    for i, text in enumerate(price_texts[:5]):
        parent = text.parent
        print(f"[{i+1}] {text.strip()[:30]} (親: <{parent.name}> class={parent.get('class', [])})")
    
    # tableのデバッグ情報
    print("\n=== テーブル構造 (propertyDetails) ===")
    property_details = soup.find("table", {"id": "propertyDetails"})
    if property_details:
        print("  ✓ propertyDetailsテーブル発見")
        rows = property_details.find_all("tr")
        for i, row in enumerate(rows[:10]):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                print(f"  [{i+1}] {th.get_text(strip=True)}: {td.get_text(strip=True)[:50]}")
    else:
        print("  ✗ propertyDetailsテーブルが見つかりません")