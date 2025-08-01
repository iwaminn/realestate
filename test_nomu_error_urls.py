#!/usr/bin/env python3
"""
エラーが発生したノムコムURLをテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
import time

# テスト用スクレイパー
scraper = NomuScraper()

# エラーが発生したURL
error_urls = [
    "https://www.nomu.com/mansion/id/EB314012/",  # クレストフォルム田町ベイフロントスクエア
    "https://www.nomu.com/mansion/id/RB334120/",  # 芝浦アイランドグローブタワー
    "https://www.nomu.com/mansion/id/EF415009/",  # ロイヤルシーズン南麻布
]

print("ノムコムエラーURL調査")
print("="*60)

for url in error_urls:
    print(f"\nテスト: {url}")
    
    try:
        # ページ取得をテスト
        soup = scraper.fetch_page(url)
        if soup:
            print("  ✓ ページ取得成功")
            
            # 詳細データ取得をテスト
            detail_data = scraper.parse_property_detail(url)
            if detail_data:
                print("  ✓ 詳細データ取得成功")
                print(f"    建物名: {detail_data.get('building_name', '未取得')}")
                print(f"    価格: {detail_data.get('price', '未取得')}")
                print(f"    住所: {detail_data.get('address', '未取得')}")
            else:
                print("  ✗ 詳細データ取得失敗")
        else:
            print("  ✗ ページ取得失敗")
            
    except Exception as e:
        print(f"  ✗ エラー発生: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # レート制限を守る
    time.sleep(2)