#!/usr/bin/env python3
"""
ノムコムの価格要素を詳しく調査
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# テスト用スクレイパー
scraper = NomuScraper()

# 問題の物件URL
test_url = "https://www.nomu.com/mansion/id/EF416025/"

print(f"ノムコム価格要素の詳細調査")
print(f"URL: {test_url}")
print("="*60)

# ページを取得
soup = scraper.fetch_page(test_url)
if soup:
    # class="price"のdiv要素を詳しく調査
    price_divs = soup.find_all("div", {"class": "price"})
    print(f"\n見つかった価格要素: {len(price_divs)}個")
    
    for i, price_div in enumerate(price_divs[:5]):
        print(f"\n[価格要素 {i+1}]")
        print(f"  テキスト: {price_div.get_text(strip=True)}")
        print(f"  HTML: {str(price_div)[:200]}...")
        
        # 親要素も確認
        parent = price_div.parent
        if parent:
            print(f"  親要素: <{parent.name}> class={parent.get('class', [])}")
            
        # 価格の抽出を試す
        from backend.app.utils.data_normalizer import extract_price
        price_text = price_div.get_text(strip=True)
        extracted_price = extract_price(price_text)
        print(f"  抽出された価格: {extracted_price}万円" if extracted_price else "  価格抽出失敗")
    
    # p class="priceTxt"も確認
    print("\n\n=== p class='priceTxt'の確認 ===")
    price_p = soup.find("p", {"class": "priceTxt"})
    if price_p:
        print(f"  テキスト: {price_p.get_text(strip=True)}")
        price_text = price_p.get_text(strip=True)
        extracted_price = extract_price(price_text)
        print(f"  抽出された価格: {extracted_price}万円" if extracted_price else "  価格抽出失敗")