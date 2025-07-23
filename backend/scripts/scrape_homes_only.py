#!/usr/bin/env python3
"""
HOMESのみスクレイピング
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper_v2 import HomesScraperV2


def scrape_homes():
    """HOMESのみスクレイピング"""
    print("HOMESのスクレイピングを開始...")
    
    scraper = HomesScraperV2()
    
    try:
        with scraper:
            scraper.scrape_area("minato", max_pages=2)
        print("HOMESのスクレイピングが完了しました。")
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    scrape_homes()