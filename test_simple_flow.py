#!/usr/bin/env python3
"""
シンプルなテスト（SQLAlchemyを使わない）
"""

import sys
import os
sys.path.append('/home/ubuntu/realestate')

# 最小限の環境変数設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'
os.environ['LOG_LEVEL'] = 'INFO'

from backend.app.scrapers.homes_scraper import HomesScraper
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')

def test():
    """基本的なページネーションテスト"""
    scraper = HomesScraper()
    
    # ページ3を直接テスト
    url = "https://www.homes.co.jp/mansion/chuko/tokyo/chiyoda-city/list/?page=3"
    print(f"テストURL: {url}")
    
    soup = scraper.fetch_page(url)
    if soup:
        is_last = scraper.is_last_page(soup)
        print(f"is_last_page結果: {is_last}")
        
        # li.nextPage要素を確認
        next_li = soup.select_one('li.nextPage')
        print(f"li.nextPage要素: {'あり' if next_li else 'なし'}")
    else:
        print("ページ取得失敗")

if __name__ == "__main__":
    test()