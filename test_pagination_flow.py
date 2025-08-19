#!/usr/bin/env python3
"""
ページネーションのフローを確認
"""

import os
import sys
sys.path.append('/home/ubuntu/realestate')
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.scrapers.homes_scraper import HomesScraper

def test_flow():
    """実際のフローをシミュレート"""
    scraper = HomesScraper()
    base_url = "https://www.homes.co.jp/mansion/chuko/tokyo/chiyoda-city/list"
    
    print("=== base_scraper.pyのフローをシミュレート ===\n")
    
    page = 1
    while True:
        # URLを生成（get_search_urlメソッドと同じ）
        if page == 1:
            url = f"{base_url}/"
        else:
            url = f"{base_url}/?page={page}"
        
        print(f"[ページ {page}]")
        print(f"  1. fetch_page({url})")
        
        # ページ取得
        soup = scraper.fetch_page(url)
        
        if not soup:
            print(f"    → fetch_pageがNoneを返した（404エラー）")
            print(f"    → base_scraper: 「ページ {page} の取得に失敗」と警告")
            print(f"  2. ループ終了")
            break
        
        print(f"    → ページ取得成功")
        
        # 物件数確認
        building_blocks = soup.select('.mod-mergeBuilding--sale')
        print(f"  2. parse_property_list() → {len(building_blocks)}件の物件")
        
        # is_last_page判定
        is_last = scraper.is_last_page(soup)
        print(f"  3. is_last_page() → {is_last}")
        
        if is_last:
            print(f"    → 最終ページと判定、ループ終了")
            break
        else:
            print(f"    → 最終ページではない、次のページへ")
        
        page += 1
        print()

def check_actual_data():
    """実際のデータを確認"""
    scraper = HomesScraper()
    
    print("\n=== 実際のページ状況 ===")
    
    # ページ3とページ4を確認
    urls = [
        ("ページ3", "https://www.homes.co.jp/mansion/chuko/tokyo/chiyoda-city/list/?page=3"),
        ("ページ4", "https://www.homes.co.jp/mansion/chuko/tokyo/chiyoda-city/list/?page=4"),
    ]
    
    for label, url in urls:
        print(f"\n{label}: {url}")
        soup = scraper.fetch_page(url)
        if soup:
            blocks = soup.select('.mod-mergeBuilding--sale')
            print(f"  物件数: {len(blocks)}件")
            
            # li.nextPage要素を確認
            next_li = soup.select_one('li.nextPage')
            if next_li:
                next_a = next_li.select_one('a')
                if next_a:
                    print(f"  li.nextPage > a: あり（href={next_a.get('href', '')[:50]}）")
                else:
                    print(f"  li.nextPage: あり、但しaタグなし")
            else:
                print(f"  li.nextPage: なし")
                
            is_last = scraper.is_last_page(soup)
            print(f"  is_last_page: {is_last}")
        else:
            print(f"  → 404エラー")

def main():
    test_flow()
    check_actual_data()

if __name__ == "__main__":
    main()