#!/usr/bin/env python3
"""
LIFULL HOME'Sと三井のリハウスのスクレイパーテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper

print("=== LIFULL HOME'Sのテスト ===")
homes_scraper = HomesScraper()

# 問題のあったURL
test_url_homes = "https://www.homes.co.jp/mansion/b-35006090000018/"
print(f"\nテストURL: {test_url_homes}")

# 一覧ページを取得（港区）
# area_config.pyでのHOMES用コード変換を確認
from backend.app.scrapers.area_config import get_homes_city_code
city_code = get_homes_city_code("13103")  # 港区
print(f"HOMES city code for 港区: {city_code}")
list_url = f"https://www.homes.co.jp/mansion/chuko/tokyo/{city_code}/list/"
print(f"List URL: {list_url}")
soup = homes_scraper.fetch_page(list_url)
if soup:
    properties = homes_scraper.parse_property_list(soup)
    print(f"取得した物件数: {len(properties)}")
    
    if properties:
        # 最初の物件を確認
        prop = properties[0]
        print(f"\n最初の物件:")
        print(f"  URL: {prop.get('url')}")
        print(f"  site_property_id: {prop.get('site_property_id', 'なし')}")
        print(f"  価格: {prop.get('price', 'なし')}万円")

print("\n\n=== 三井のリハウスのテスト ===")
rehouse_scraper = RehouseScraper()

# 港区の一覧ページを取得
soup = rehouse_scraper.fetch_page("https://www.rehouse.co.jp/buy/mansion/prefecture/13/city/13103/")
if soup:
    properties = rehouse_scraper.parse_property_list(soup)
    print(f"取得した物件数: {len(properties)}")
    
    if properties:
        # 最初の物件を確認
        prop = properties[0]
        print(f"\n最初の物件:")
        print(f"  URL: {prop.get('url')}")
        print(f"  site_property_id: {prop.get('site_property_id', 'なし')}")
        print(f"  価格: {prop.get('price', 'なし')}万円")
        
        # 詳細ページを取得
        if prop.get('url'):
            print(f"\n詳細ページを取得中...")
            detail = rehouse_scraper.parse_property_detail(prop['url'])
            if detail:
                print(f"詳細取得成功:")
                print(f"  建物名: {detail.get('building_name', 'なし')}")
                print(f"  価格: {detail.get('price', 'なし')}万円")
                print(f"  住所: {detail.get('address', 'なし')}")
                print(f"  間取り: {detail.get('layout', 'なし')}")
                print(f"  面積: {detail.get('area', 'なし')}㎡")
                print(f"  階数: {detail.get('floor_number', 'なし')}階")
            else:
                print("詳細取得失敗")