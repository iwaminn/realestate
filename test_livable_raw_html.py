#!/usr/bin/env python3
"""
東急リバブルの生のHTMLを確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.livable_scraper import LivableScraper

# テスト用スクレイパー
scraper = LivableScraper()

# エラーが出た物件のページを確認
url = "https://www.livable.co.jp/mansion/C13256790/"
print(f"URL: {url}")

soup = scraper.fetch_page(url)
if soup:
    # HTMLを出力してJavaScriptが含まれているか確認
    html_content = str(soup)
    
    # dataLayerが含まれているか
    if 'dataLayer.push' in html_content:
        print("✓ dataLayer.pushが見つかりました")
        # dataLayerの内容を抽出
        import re
        matches = re.findall(r'dataLayer\.push\([^)]+\)', html_content)
        for match in matches[:2]:  # 最初の2つだけ表示
            print(f"\n{match[:200]}...")
    else:
        print("✗ dataLayer.pushが見つかりません")
    
    # gmapParmsが含まれているか
    if 'gmapParms' in html_content:
        print("\n✓ gmapParmsが見つかりました")
        # gmapParmsの内容を抽出
        matches = re.findall(r'var gmapParms = \{[^}]+\}', html_content)
        for match in matches:
            print(f"\n{match}")
    else:
        print("\n✗ gmapParmsが見つかりません")