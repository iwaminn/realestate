#!/usr/bin/env python3
"""
各スクレイパーから指定件数の物件を取得するスクリプト
"""

import sys
import os
import argparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.suumo_scraper import SuumoScraper
from app.scrapers.homes_scraper import HomesScraper
from app.scrapers.rehouse_scraper import RehouseScraper

def scrape_properties(count=200, scrapers=None, area='13103'):
    """各サイトから指定件数の物件を取得
    
    Args:
        count: 取得する物件数（デフォルト: 200）
        scrapers: 実行するスクレイパーのリスト（デフォルト: 全て）
        area: エリアコード（デフォルト: 13103 = 港区）
    """
    
    if scrapers is None:
        scrapers = ['suumo', 'homes', 'rehouse']
    
    print(f"=== 各サイトから{count}件ずつ物件を取得 ===")
    print(f"対象エリア: {area}")
    print(f"対象サイト: {', '.join(scrapers)}\n")
    
    # SUUMO
    if 'suumo' in scrapers:
        print(f"1. SUUMOから{count}件取得...")
        try:
            with SuumoScraper(max_properties=count) as scraper:
                scraper.scrape_area(area)
            print("✓ SUUMO完了\n")
        except Exception as e:
            print(f"✗ SUUMOエラー: {e}\n")
    
    # HOMES
    if 'homes' in scrapers:
        print(f"2. HOMESから{count}件取得...")
        try:
            with HomesScraper(max_properties=count) as scraper:
                scraper.scrape_area(area)
            print("✓ HOMES完了\n")
        except Exception as e:
            print(f"✗ HOMESエラー: {e}\n")
    
    # 三井のリハウス
    if 'rehouse' in scrapers:
        print(f"3. 三井のリハウスから{count}件取得...")
        try:
            with RehouseScraper(max_properties=count) as scraper:
                scraper.scrape_area(area)
            print("✓ 三井のリハウス完了\n")
        except Exception as e:
            print(f"✗ 三井のリハウスエラー: {e}\n")
    
    print("=== 全てのスクレイピングが完了しました ===")

def main():
    parser = argparse.ArgumentParser(
        description='各不動産サイトから物件情報を取得',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 各サイトから200件ずつ取得（デフォルト）
  python scrape_200_each.py
  
  # 各サイトから100件ずつ取得
  python scrape_200_each.py --count 100
  
  # SUUMOとHOMESから50件ずつ取得
  python scrape_200_each.py --count 50 --scrapers suumo homes
  
  # 渋谷区（13109）から300件取得
  python scrape_200_each.py --count 300 --area 13109
        """
    )
    
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=200,
        help='取得する物件数（デフォルト: 200）'
    )
    
    parser.add_argument(
        '--scrapers', '-s',
        nargs='+',
        choices=['suumo', 'homes', 'rehouse'],
        help='実行するスクレイパー（デフォルト: 全て）'
    )
    
    parser.add_argument(
        '--area', '-a',
        type=str,
        default='13103',
        help='エリアコード（デフォルト: 13103 = 港区）'
    )
    
    args = parser.parse_args()
    
    scrape_properties(
        count=args.count,
        scrapers=args.scrapers,
        area=args.area
    )

if __name__ == "__main__":
    main()