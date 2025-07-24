#!/usr/bin/env python3
"""
LIFULL HOME'Sの現在のHTML構造を確認するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper import HomesScraper
from bs4 import BeautifulSoup

def test_homes_selectors():
    """LIFULL HOME'Sのセレクタをテスト"""
    print("=== LIFULL HOME'S セレクタテスト ===\n")
    
    scraper = HomesScraper()
    
    # まず一覧ページから物件URLを取得
    print("1. 一覧ページから物件URLを取得...")
    list_url = scraper.get_search_url("港区", page=1)
    print(f"   URL: {list_url}")
    
    soup = scraper.fetch_page(list_url)
    if not soup:
        print("   エラー: 一覧ページの取得に失敗しました")
        return
    
    # 新しいparse_property_listを使用
    properties = scraper.parse_property_list(soup)
    print(f"   取得した物件数: {len(properties)}件")
    
    if not properties:
        print("   エラー: 物件が見つかりませんでした")
        # セレクタのデバッグ
        print("\n2. セレクタのデバッグ...")
        print("   .mod-objectCollection__item の数:", len(soup.select('.mod-objectCollection__item')))
        print("   .p-object-cassette の数:", len(soup.select('.p-object-cassette')))
        print("   .prg-objectListUnit の数:", len(soup.select('.prg-objectListUnit')))
        
        # ページに含まれる主要なクラス名を表示
        print("\n   ページに含まれる主要なクラス名:")
        all_classes = set()
        for elem in soup.find_all(class_=True):
            for cls in elem.get('class', []):
                if 'object' in cls.lower() or 'property' in cls.lower() or 'list' in cls.lower() or 'item' in cls.lower():
                    all_classes.add(cls)
        
        for cls in sorted(all_classes)[:20]:
            print(f"     - {cls}")
        return
    
    # 最初の物件の詳細ページをテスト
    print("\n2. 詳細ページのセレクタをテスト...")
    test_property = properties[0]
    test_url = test_property.get('url')
    
    if not test_url:
        print("   エラー: URLが取得できませんでした")
        return
    
    print(f"   テスト用URL: {test_url}")
    
    # 詳細ページを取得
    detail_soup = scraper.fetch_page(test_url)
    if not detail_soup:
        print("   エラー: 詳細ページの取得に失敗しました")
        return
    
    # 現在のセレクタをテスト
    print("\n3. 現在のセレクタの検証...")
    
    # タイトル系
    title_selectors = [
        'h1.bukkenHead-title',
        '.object-r__title',
        'h1.prg-detailHeader__name',
        '.mod-bukkenTitle',
        'h1[class*="title"]',
        'h1[class*="name"]'
    ]
    
    print("   タイトル系セレクタ:")
    found_title = False
    for selector in title_selectors:
        elem = detail_soup.select_one(selector)
        if elem:
            print(f"     ✓ {selector}: {elem.get_text(strip=True)[:50]}...")
            found_title = True
        else:
            print(f"     ✗ {selector}")
    
    # テーブル系
    table_selectors = [
        '.rentTbl',
        '.detail-table',
        '.mod-rentTbl',
        'table.prg-detailTbl',
        'table[class*="detail"]',
        'table[class*="spec"]',
        '.prg-detailSpec',
        '.mod-detailSpec'
    ]
    
    print("\n   テーブル系セレクタ:")
    found_table = False
    for selector in table_selectors:
        elem = detail_soup.select_one(selector)
        if elem:
            print(f"     ✓ {selector}")
            found_table = True
        else:
            print(f"     ✗ {selector}")
    
    # 価格情報
    print("\n   価格情報の検索:")
    price_text = detail_soup.get_text()
    if '万円' in price_text:
        print("     ✓ ページに価格情報（万円）が含まれています")
        # 価格の周辺テキストを表示
        index = price_text.find('万円')
        print(f"     周辺テキスト: ...{price_text[max(0, index-20):index+10]}...")
    
    # 推奨される新しいセレクタ
    if not found_title or not found_table:
        print("\n4. 推奨される修正:")
        if not found_title:
            print("   タイトルセレクタの更新が必要です")
        if not found_table:
            print("   テーブルセレクタの更新が必要です")


def main():
    try:
        test_homes_selectors()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()