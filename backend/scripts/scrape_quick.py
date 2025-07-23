#!/usr/bin/env python3
"""
各スクレイパーを1ページずつ実行
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.suumo_scraper import SuumoScraper
from src.scrapers.athome_scraper import AtHomeScraper
from src.scrapers.homes_scraper import HomesScraper

def main():
    # データベースパス
    db_path = "data/realestate.db"
    
    # スクレイパーのリスト
    scrapers = [
        ("SUUMO", SuumoScraper(db_path=db_path)),
        ("AtHome", AtHomeScraper(db_path=db_path)),
        ("HOMES", HomesScraper(db_path=db_path))
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