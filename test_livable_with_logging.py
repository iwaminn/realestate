#!/usr/bin/env python3
"""
東急リバブルスクレイパーのログレベルを上げてテスト
"""

import sys
import os
import logging

# ログレベルをDEBUGに設定
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.livable_scraper import LivableScraper

# テスト用スクレイパー
scraper = LivableScraper()

# エラーが出た物件の詳細ページを確認
test_urls = [
    "https://www.livable.co.jp/mansion/C13256790/",  # グランドメゾン白金・三光坂
]

for url in test_urls:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    # 詳細データを取得
    detail_data = scraper.parse_property_detail(url)
    
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
    else:
        print("詳細データの取得に失敗しました")