#!/usr/bin/env python3
"""
ノムコムの駅情報取得をテスト
"""

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
    # 駅情報を探す
    print("\n=== 駅情報の探索 ===")
    
    # addressクラスの要素（住所と駅情報が含まれる）
    address_elem = soup.find("p", class_="address")
    if address_elem:
        full_text = address_elem.get_text(strip=True)
        print(f"\naddressクラスの内容: '{full_text}'")
        
        if "｜" in full_text:
            parts = full_text.split("｜")
            if len(parts) >= 2:
                station_part = parts[1].strip()
                print(f"\n駅情報部分: '{station_part}'")
                
                # format_station_info を適用
                from backend.app.scrapers import format_station_info
                formatted = format_station_info(station_part)
                print(f"\nフォーマット後:")
                print(formatted)
    
    # 他の駅情報要素を探す
    print("\n\n=== その他の駅情報要素 ===")
    
    # 「徒歩」を含む要素を探す
    walk_elements = soup.find_all(string=lambda text: text and "徒歩" in text and "分" in text)
    for i, elem in enumerate(walk_elements[:5]):
        parent = elem.parent
        print(f"\n[{i+1}] テキスト: '{elem.strip()}'")
        print(f"   親要素: <{parent.name}> class={parent.get('class', [])}")