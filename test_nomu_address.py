#!/usr/bin/env python3
"""
ノムコムの特定物件の住所取得をテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# テスト用スクレイパー
scraper = NomuScraper()

# 問題の物件URL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print(f"ノムコム住所取得テスト")
print(f"URL: {test_url}")
print("="*60)

# 詳細データを取得
detail_data = scraper.parse_property_detail(test_url)

if detail_data:
    print("\n取得したデータ:")
    for key, value in detail_data.items():
        if key != 'detail_info':  # detail_infoは長いので別途表示
            print(f"  {key}: {value}")
    
    # 必須フィールドのチェック
    print("\n必須フィールドの確認:")
    required_fields = ['building_name', 'price', 'address']
    for field in required_fields:
        if field in detail_data and detail_data[field]:
            print(f"  ✓ {field}: {detail_data[field]}")
        else:
            print(f"  ✗ {field}: 取得できませんでした")
            
    # detail_infoも確認
    if 'detail_info' in detail_data:
        print("\n詳細情報:")
        for key, value in detail_data['detail_info'].items():
            print(f"  {key}: {value}")
else:
    print("詳細データの取得に失敗しました")