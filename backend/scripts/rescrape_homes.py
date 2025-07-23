#!/usr/bin/env python3
"""HOMESから再スクレイピングして既存の建物情報を更新"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.homes_scraper import HomesScraper
from app.database import SessionLocal
from app.models import PropertyListing
from datetime import datetime

def rescrape_homes():
    """HOMESから再スクレイピング"""
    
    # データベースセッション
    session = SessionLocal()
    
    try:
        # 既存のHOMES物件を一旦すべて非アクティブにする
        print("既存のHOMES物件を非アクティブ化...")
        updated = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True
        ).update({
            'is_active': False,
            'delisted_at': datetime.now()
        })
        session.commit()
        print(f"  → {updated}件を非アクティブ化")
        
        # HOMESスクレイパーを実行
        print("\nHOMESから再スクレイピングを開始...")
        scraper = HomesScraper()
        
        # エリアを指定してスクレイピング（港区）
        scraper.scrape_area('東京都港区', max_pages=10)  # 最大10ページ
        
        print("\n再スクレイピング完了")
        
        # 結果を確認
        active_count = session.query(PropertyListing).filter(
            PropertyListing.source_site == 'HOMES',
            PropertyListing.is_active == True
        ).count()
        
        print(f"\nアクティブなHOMES物件数: {active_count}件")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    rescrape_homes()