#!/usr/bin/env python3
"""
HOMES詳細ページからの建物名取得を検証
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper_v2 import HomesScraperV2
import re


def verify_detail_extraction():
    """詳細ページからの建物名取得を検証"""
    scraper = HomesScraperV2()
    
    # 一覧で確認した物件のURL
    test_urls = [
        ("アクシアフォレスタ麻布", "https://www.homes.co.jp/mansion/b-1090830004751/"),
        ("パルロイヤルアレフ赤坂", "https://www.homes.co.jp/mansion/b-1090830004706/"),
        ("シティハウス南麻布一丁目", "https://www.homes.co.jp/mansion/b-35005010002458/"),
    ]
    
    with scraper:
        for expected_name, url in test_urls:
            print(f"\n{'='*60}")
            print(f"期待される建物名: {expected_name}")
            print(f"URL: {url}")
            print('='*60)
            
            soup = scraper.fetch_page(url)
            if not soup:
                print("ページ取得失敗")
                continue
            
            # 現在のparse_property_detailメソッドでの結果
            property_data = scraper.parse_property_detail(soup)
            if property_data:
                extracted_name = property_data.get('building_name', '未取得')
                print(f"現在の抽出結果: {extracted_name}")
                
                if expected_name in extracted_name or extracted_name in expected_name:
                    print("✓ 正常に取得できています")
                else:
                    print("✗ 取得できていません")
            else:
                print("✗ 物件データの解析に失敗")
            
            # ページ内のテキストから建物名を探す
            print("\n--- ページ内のテキスト分析 ---")
            page_text = soup.get_text()
            
            # h1タグ
            h1_tags = soup.find_all('h1')
            for h1 in h1_tags:
                h1_text = h1.get_text(strip=True)
                if h1_text and expected_name in h1_text:
                    print(f"h1タグで発見: {h1_text}")
            
            # titleタグ
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                if expected_name in title_text:
                    print(f"titleタグで発見: {title_text}")
            
            # og:titleメタタグ
            og_title = soup.find('meta', property='og:title')
            if og_title:
                og_content = og_title.get('content', '')
                if expected_name in og_content:
                    print(f"og:titleで発見: {og_content}")


if __name__ == "__main__":
    verify_detail_extraction()