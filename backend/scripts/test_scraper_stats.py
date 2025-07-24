#!/usr/bin/env python3
"""
スクレイパー統計トラッキングのテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper import SUUMOScraper
from backend.app.scrapers.homes_scraper import HomesScraper

def test_scraper_stats():
    """スクレイパーの統計トラッキングをテスト"""
    print("=== スクレイパー統計トラッキングテスト ===\n")
    
    # SUUMOスクレイパーのテスト
    print("【SUUMOスクレイパー】")
    suumo = SUUMOScraper(max_properties=5)
    
    print("初期統計:")
    stats = suumo.get_scraping_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n港区の物件を最大5件取得...")
    suumo.scrape_area("minato", max_pages=1)
    
    print("\n最終統計:")
    stats = suumo.get_scraping_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "="*50 + "\n")
    
    # LIFULL HOME'Sスクレイパーのテスト
    print("【LIFULL HOME'Sスクレイパー】")
    homes = HomesScraper(max_properties=5)
    
    print("初期統計:")
    stats = homes.get_scraping_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n港区の物件を最大5件取得...")
    homes.scrape_area("minato", max_pages=1)
    
    print("\n最終統計:")
    stats = homes.get_scraping_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "="*50 + "\n")
    
    # 管理画面用統計（後方互換性）
    print("【管理画面用統計（get_stats）】")
    print("\nSUUMO:")
    stats = suumo.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\nHOMES:")
    stats = homes.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


def main():
    try:
        test_scraper_stats()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()