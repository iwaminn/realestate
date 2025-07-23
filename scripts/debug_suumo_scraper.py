#!/usr/bin/env python3
"""
SUUMOスクレイパーのデバッグ
"""

import requests
from bs4 import BeautifulSoup

# テストURL
url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77936729/"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

print("=== タイトル ===")
title_elem = soup.select_one('h1.section_h1-header-title, .bukkenTitle')
if title_elem:
    print(f"Found: {title_elem.get_text(strip=True)}")
else:
    h1_tags = soup.find_all('h1')
    print(f"All h1 tags: {[h1.get_text(strip=True) for h1 in h1_tags]}")

print("\n=== 価格 ===")
price_elem = soup.select_one('.kakaku_main')
if price_elem:
    print(f"Found: {price_elem.get_text(strip=True)}")
else:
    # 他の価格要素を探す
    price_candidates = soup.find_all(text=lambda text: text and '万円' in text)
    print(f"Price candidates: {[p.strip() for p in price_candidates[:5]]}")

print("\n=== 詳細テーブル ===")
tables = soup.find_all('table')
print(f"Found {len(tables)} tables")
for i, table in enumerate(tables[:2]):
    print(f"\nTable {i}:")
    rows = table.find_all('tr')[:5]
    for row in rows:
        cells = row.find_all(['th', 'td'])
        if cells:
            print(f"  {' | '.join([cell.get_text(strip=True) for cell in cells])}")

# HTMLの一部を保存
with open('scripts/suumo_debug.html', 'w', encoding='utf-8') as f:
    f.write(str(soup.prettify()[:5000]))