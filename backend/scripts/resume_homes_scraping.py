#!/usr/bin/env python3
"""HOMESの再スクレイピングを再開"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.homes_scraper import HomesScraper
from app.database import SessionLocal

def resume_homes_scraping():
    """HOMESスクレイピングを再開"""
    
    print("HOMESスクレイピングを再開...")
    
    # HOMESスクレイパーを実行
    scraper = HomesScraper()
    
    # エリアを指定してスクレイピング（港区）
    scraper.scrape_area('東京都港区', max_pages=10)
    
    # 結果を確認
    session = SessionLocal()
    try:
        from app.models import PropertyListing
        active_count = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True
        ).count()
        
        print(f"\nアクティブなHOMES物件数: {active_count}件")
        
    finally:
        session.close()

if __name__ == "__main__":
    resume_homes_scraping()