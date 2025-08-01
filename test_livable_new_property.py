#!/usr/bin/env python3
"""
東急リバブルスクレイパーで新規物件の詳細取得をテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.livable_scraper import LivableScraper

# テスト用スクレイパー
scraper = LivableScraper()

# 実際に存在する物件URLでテスト
test_urls = [
    'https://www.livable.co.jp/mansion/C48256376/',  # オリエンタル南麻布（先ほど成功した物件）
    'https://www.livable.co.jp/mansion/C48257738/',  # 最近の物件
]

print("東急リバブル - 詳細取得テスト（住所確認）")
print("="*50)

for url in test_urls:
    print(f"\nURL: {url}")
    
    try:
        # parse_property_detailを直接呼び出し
        result = scraper.parse_property_detail(url)
        
        if result:
            print("  ✓ 詳細取得成功")
            print(f"    建物名: {result.get('building_name', '未取得')}")
            print(f"    住所: {result.get('address', '未取得')}")
            print(f"    価格: {result.get('price', '未取得')}万円")
            print(f"    階数: {result.get('floor_number', '未取得')}階")
            print(f"    総階数: {result.get('total_floors', '未取得')}階")
            print(f"    面積: {result.get('area', '未取得')}㎡")
            
            # 住所が取得できているかチェック
            if result.get('address'):
                print("  ✓ 住所取得: OK")
            else:
                print("  ✗ 住所取得: NG - 必須情報不足エラーの原因")
        else:
            print("  ✗ 詳細取得失敗")
            
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()