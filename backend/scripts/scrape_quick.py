#!/usr/bin/env python3
"""
各スクレイパーを1ページずつ実行
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.nomu_scraper import NomuScraper

def main():
    # スクレイパーのリスト
    scrapers = [
        ("SUUMO", SuumoScraper()),
        ("REHOUSE", RehouseScraper()),
        ("HOMES", HomesScraper()),
        ("NOMU", NomuScraper())
    ]
    
    # 各スクレイパーを実行（1ページのみ）
    for name, scraper in scrapers:
        print(f"\n{name}のスクレイピングを開始...")
        
        try:
            # 港区の物件を1ページ分取得
            scraper.scrape_area("minato", max_pages=1)
            print(f"{name}のスクレイピングが完了しました。")
        except Exception as e:
            print(f"{name}のスクレイピング中にエラーが発生しました: {e}")
    
    print("\n全てのスクレイピングが完了しました。")

if __name__ == "__main__":
    main()