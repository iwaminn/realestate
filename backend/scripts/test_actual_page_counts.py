#!/usr/bin/env python3
"""
各スクレイパーの実際の1ページあたりの取得件数を確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper

def test_homes_page_count():
    """LIFULL HOME'Sの1ページあたりの件数を確認"""
    print("=== LIFULL HOME'S ===")
    
    scraper = HomesScraper()
    
    # 港区のURLを生成
    url = scraper.get_search_url("港区", page=1)
    print(f"URL: {url}")
    
    # ページを取得
    soup = scraper.fetch_page(url)
    if soup:
        # 物件URLを抽出
        urls = scraper.parse_property_urls(soup)
        print(f"1ページ目の物件数: {len(urls)}件")
        
        # 2ページ目も確認
        url2 = scraper.get_search_url("港区", page=2)
        soup2 = scraper.fetch_page(url2)
        if soup2:
            urls2 = scraper.parse_property_urls(soup2)
            print(f"2ページ目の物件数: {len(urls2)}件")
    else:
        print("ページの取得に失敗しました")


def test_nomu_page_count():
    """ノムコムの1ページあたりの件数を確認"""
    print("\n=== ノムコム ===")
    
    scraper = NomuScraper()
    
    # 港区のURLを生成
    url = scraper.get_search_url("13103", page=1)
    print(f"URL: {url}")
    
    # ページを取得
    soup = scraper.fetch_page(url)
    if soup:
        # 物件を抽出
        properties = scraper.parse_property_list(soup)
        print(f"1ページ目の物件数: {len(properties)}件")
        
        # 2ページ目も確認
        url2 = scraper.get_search_url("13103", page=2)
        soup2 = scraper.fetch_page(url2)
        if soup2:
            properties2 = scraper.parse_property_list(soup2)
            print(f"2ページ目の物件数: {len(properties2)}件")
    else:
        print("ページの取得に失敗しました")


def test_rehouse_page_count():
    """三井のリハウスの1ページあたりの件数を確認"""
    print("\n=== 三井のリハウス ===")
    
    scraper = RehouseScraper()
    
    # 港区のURLを生成（area_code_mappingを使用）
    area_code = scraper.area_code_mapping.get("13103")
    if area_code:
        url = scraper.get_list_url(area_code, page=1)
        print(f"URL: {url}")
        
        # ページを取得
        soup = scraper.fetch_page(url)
        if soup:
            # 物件を抽出
            properties = scraper.parse_property_list(soup)
            print(f"1ページ目の物件数: {len(properties)}件")
            
            # 2ページ目も確認
            url2 = scraper.get_list_url(area_code, page=2)
            soup2 = scraper.fetch_page(url2)
            if soup2:
                properties2 = scraper.parse_property_list(soup2)
                print(f"2ページ目の物件数: {len(properties2)}件")
        else:
            print("ページの取得に失敗しました")
    else:
        print("エリアコードのマッピングが見つかりません")


def main():
    print("各スクレイパーの1ページあたりの取得件数を確認します\n")
    
    try:
        test_homes_page_count()
    except Exception as e:
        print(f"LIFULL HOME'Sのテストでエラー: {e}")
    
    try:
        test_nomu_page_count()
    except Exception as e:
        print(f"ノムコムのテストでエラー: {e}")
    
    try:
        test_rehouse_page_count()
    except Exception as e:
        print(f"三井のリハウスのテストでエラー: {e}")
    
    print("\n=== まとめ ===")
    print("※ 実際の件数はサイトの仕様や検索条件により変動する可能性があります")
    print("※ 100件表示が可能な場合は、URLパラメータの追加で対応できる可能性があります")


if __name__ == "__main__":
    main()