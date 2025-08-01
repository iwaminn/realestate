#!/usr/bin/env python3
"""
東急リバブルの特定物件の詳細ページをテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.livable_scraper import LivableScraper

# テスト用スクレイパー
scraper = LivableScraper()

# エラーが出た物件の詳細ページを確認
test_urls = [
    "https://www.livable.co.jp/mansion/C13256790/",  # グランドメゾン白金・三光坂
    "https://www.livable.co.jp/mansion/C48256376/",  # オリエンタル南麻布
]

for url in test_urls:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    # 詳細データを取得（parse_property_detailはURLを受け取る）
    detail_data = scraper.parse_property_detail(url)
    
    if detail_data:
            print("\n取得したデータ:")
            for key, value in detail_data.items():
                print(f"  {key}: {value}")
            
            # 必須フィールドのチェック
            print("\n必須フィールドの確認:")
            required_fields = ['building_name', 'price', 'address']
            for field in required_fields:
                if field in detail_data and detail_data[field]:
                    print(f"  ✓ {field}: {detail_data[field]}")
                else:
                    print(f"  ✗ {field}: 取得できませんでした")
    else:
        print("詳細データの取得に失敗しました")