#!/usr/bin/env python3
"""
ノムコムの詳細取得と住所の処理を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# 強制詳細取得モードでスクレイパーを作成
scraper = NomuScraper(force_detail_fetch=True)

# 港区の一覧ページを取得
print("港区の一覧ページを取得中...")
soup = scraper.fetch_page('https://www.nomu.com/mansion/area_tokyo/01/')

if soup:
    properties = scraper.parse_property_list(soup)
    print(f"取得した物件数: {len(properties)}")
    
    if properties:
        # 最初の物件で詳細テスト
        test_prop = properties[0]
        print(f"\nテスト物件:")
        print(f"  建物名: {test_prop.get('building_name')}")
        print(f"  URL: {test_prop.get('url')}")
        print(f"  住所（一覧）: {test_prop.get('address', 'なし')}")
        
        # 詳細ページを取得
        print(f"\n詳細ページを取得中...")
        detail_data = scraper.parse_property_detail(test_prop['url'])
        
        if detail_data:
            print(f"詳細取得成功:")
            print(f"  住所（詳細）: {detail_data.get('address', 'なし')}")
            print(f"  建物名: {detail_data.get('building_name', 'なし')}")
            print(f"  価格: {detail_data.get('price', 'なし')}万円")
            print(f"  間取り: {detail_data.get('layout', 'なし')}")
            print(f"  面積: {detail_data.get('area', 'なし')}㎡")
            print(f"  階数: {detail_data.get('floor_number', 'なし')}階")
            
            # 一覧データと詳細データをマージ
            merged_data = {**test_prop, **detail_data}
            print(f"\nマージ後の住所: {merged_data.get('address', 'なし')}")
            
            # validate_property_dataのテスト
            print(f"\n妥当性チェック:")
            is_valid = scraper.validate_property_data(merged_data)
            print(f"  結果: {is_valid}")
            
            if not is_valid and not merged_data.get('address'):
                print("  → 住所がないため妥当性チェックに失敗")
        else:
            print("詳細取得失敗")