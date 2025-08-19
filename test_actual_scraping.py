#!/usr/bin/env python3
"""
実際のスクレイピング処理をテスト
"""

import os
import sys
sys.path.append('/home/ubuntu/realestate')
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.scrapers.homes_scraper import HomesScraper

def test_actual_scraping():
    """実際のscrape_propertiesメソッドをテスト"""
    scraper = HomesScraper(max_properties=100)  # 最大100件で制限
    
    print("=== 実際のスクレイピング処理をテスト（千代田区） ===\n")
    
    # 千代田区でテスト
    properties = scraper.scrape_properties(['千代田区'])
    
    print(f"\n=== 結果 ===")
    print(f"取得した物件数: {len(properties)}件")

if __name__ == "__main__":
    test_actual_scraping()