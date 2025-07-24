#!/usr/bin/env python3
"""
全スクレイパーを実行して東京都港区の物件を収集
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.scrapers.livable_scraper import LivableScraper

def main():
    # スクレイパーのリスト
    scrapers = [
        ("SUUMO", SuumoScraper()),
        ("REHOUSE", RehouseScraper()),
        ("HOMES", HomesScraper()),
        ("NOMU", NomuScraper()),
        ("LIVABLE", LivableScraper())
    ]
    
    # 各スクレイパーを実行
    for name, scraper in scrapers:
        print(f"\n{'='*50}")
        print(f"{name}のスクレイピングを開始...")
        print('='*50)
        
        try:
            # 港区の物件を2ページ分取得
            scraper.scrape_area("minato", max_pages=2)
            print(f"{name}のスクレイピングが完了しました。")
        except Exception as e:
            print(f"{name}のスクレイピング中にエラーが発生しました: {e}")
    
    print("\n全てのスクレイピングが完了しました。")

if __name__ == "__main__":
    main()