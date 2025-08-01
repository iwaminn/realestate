#!/usr/bin/env python3
"""
ノムコムの住所要素を詳しく確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# テスト用スクレイパー
scraper = NomuScraper()

# 実際の詳細ページURL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print("ノムコム住所要素の確認")
print(f"URL: {test_url}")
print("="*60)

# ページを取得
soup = scraper.fetch_page(test_url)
if soup:
    # 1. p class="address"を探す
    print("\n1. <p class='address'>要素の確認:")
    address_p = soup.find("p", {"class": "address"})
    if address_p:
        print(f"  ✓ 見つかりました")
        print(f"  内容: {address_p.get_text(strip=True)}")
        print(f"  HTML: {str(address_p)[:200]}...")
    else:
        print("  ✗ 見つかりません")
    
    # 2. テーブル内の「所在地」を探す
    print("\n2. テーブル内の「所在地」行の確認:")
    found_address_in_table = False
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            for i in range(len(cells)):
                if cells[i].get_text(strip=True) == "所在地":
                    found_address_in_table = True
                    print(f"  ✓ 見つかりました")
                    print(f"  テーブルclass: {table.get('class', [])}")
                    if i + 1 < len(cells):
                        next_cell = cells[i + 1]
                        print(f"  次のセル: {next_cell.get_text(strip=True)}")
                        p_in_cell = next_cell.find("p")
                        if p_in_cell:
                            print(f"  <p>タグ内: {p_in_cell.get_text(strip=True)}")
                    break
            if found_address_in_table:
                break
    
    if not found_address_in_table:
        print("  ✗ テーブル内に「所在地」が見つかりません")
    
    # 3. その他の住所らしい要素を探す
    print("\n3. その他の住所要素の確認:")
    # classやidに"address"を含む要素
    address_elements = soup.find_all(class_=lambda x: x and 'address' in str(x).lower())
    print(f"  'address'を含むclass要素: {len(address_elements)}個")
    for elem in address_elements[:3]:
        print(f"    <{elem.name}> class={elem.get('class', [])}: {elem.get_text(strip=True)[:50]}")
    
    # 東京都を含むテキストで住所っぽいもの
    print("\n  '東京都'を含むテキスト（最初の5個）:")
    tokyo_texts = soup.find_all(string=lambda text: text and "東京都" in text and "港区" in text)
    for i, text in enumerate(tokyo_texts[:5]):
        parent = text.parent
        print(f"    [{i+1}] {text.strip()[:50]} (親: <{parent.name}> class={parent.get('class', [])})")