#!/usr/bin/env python3
"""
ノムコム詳細ページの最初のテーブル構造を詳しく確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# テスト用スクレイパー
scraper = NomuScraper()

# 実際の詳細ページURL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print("ノムコム詳細ページ - 最初のテーブル構造")
print(f"URL: {test_url}")
print("="*60)

# ページを取得
soup = scraper.fetch_page(test_url)
if soup:
    # 最初のテーブルを詳しく調査
    tables = soup.find_all("table")
    if tables:
        first_table = tables[0]
        print("\n最初のテーブルの詳細:")
        print(f"  class: {first_table.get('class', [])}")
        print(f"  id: {first_table.get('id', 'なし')}")
        
        rows = first_table.find_all("tr")
        print(f"\n  行数: {len(rows)}")
        
        for i, row in enumerate(rows):
            print(f"\n  [行{i+1}]")
            cells = row.find_all(['th', 'td'])
            for j, cell in enumerate(cells):
                tag = cell.name
                text = cell.get_text(strip=True)
                colspan = cell.get('colspan', '1')
                print(f"    セル{j+1} <{tag}> colspan={colspan}: {text}")
        
        # HTMLも出力
        print("\n\n最初のテーブルのHTML（最初の200文字）:")
        print(str(first_table)[:200] + "...")