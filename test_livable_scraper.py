#!/usr/bin/env python3
"""
東急リバブルスクレイパーのテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.livable_scraper import LivableScraper

# テスト用スクレイパー
scraper = LivableScraper(max_properties=5)  # 5件だけテスト

print("東急リバブルスクレイパーのテスト開始")
print("="*50)

# 港区でテスト
try:
    scraper.scrape_area("13103")  # 港区のコード
    print("\nテスト完了")
except Exception as e:
    print(f"\nエラーが発生しました: {e}")
    import traceback
    traceback.print_exc()