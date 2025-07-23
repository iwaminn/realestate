#!/usr/bin/env python3
"""
保存されたHTMLから適切なセレクタを抽出
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bs4 import BeautifulSoup
import re

def analyze_suumo_detail():
    """SUUMO詳細ページのセレクタを分析"""
    try:
        with open('/tmp/suumo_detail.html', 'r', encoding='utf-8') as f:
            html = f.read()
    except:
        print("SUUMOの詳細HTMLが見つかりません")
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    print("=== SUUMO詳細ページのセレクタ分析 ===")
    
    # 1. 物件概要セクションを探す
    print("\n1. 物件概要セクション:")
    outline_sections = soup.find_all(['section', 'div'], class_=re.compile(r'outline|detail|spec', re.I))
    for section in outline_sections[:3]:
        print(f"  - {section.name}.{section.get('class')}")
        # その中のテーブルを見る
        tables = section.find_all('table')
        if tables:
            print(f"    内部テーブル: {len(tables)}個")
    
    # 2. テーブル内のバルコニー情報
    print("\n2. バルコニー面積の検索:")
    all_tds = soup.find_all('td')
    for td in all_tds:
        text = td.get_text(strip=True)
        if 'バルコニー' in text or 'ベランダ' in text:
            print(f"  発見: {text[:50]}")
            # 親のtr要素を取得
            tr = td.find_parent('tr')
            if tr:
                # 同じ行の全セルを表示
                cells = tr.find_all(['th', 'td'])
                print(f"    行の内容: {' | '.join([c.get_text(strip=True)[:20] for c in cells])}")
    
    # 3. 取扱店舗情報
    print("\n3. 取扱店舗情報:")
    # 「取扱店舗」を含む要素の次の要素を探す
    for elem in soup.find_all(string=re.compile('取扱店舗')):
        parent = elem.parent
        print(f"  '取扱店舗'の親: {parent.name}")
        # 次の兄弟要素
        next_sibling = parent.find_next_sibling()
        if next_sibling:
            print(f"    次の要素: {next_sibling.name}")
            # その中のテキストやリンクを探す
            links = next_sibling.find_all('a')
            for link in links[:2]:
                print(f"      リンク: {link.get_text(strip=True)}")
            # divやspanも探す
            for tag in ['div', 'span', 'p']:
                elems = next_sibling.find_all(tag)
                for elem in elems[:3]:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 5:
                        print(f"      {tag}: {text[:50]}")
    
    # 4. フリーコールを探す
    print("\n4. 電話番号の検索:")
    freecall_elems = soup.find_all(string=re.compile(r'無料|フリーコール|0120|0800'))
    for elem in freecall_elems[:5]:
        text = elem.strip()
        if re.search(r'\d{4}-\d{2}-\d{4}|\d{10,}', text):
            print(f"  電話番号候補: {text}")
            # 親要素の情報
            parent = elem.parent
            if parent:
                print(f"    親要素: {parent.name}.{parent.get('class')}")


def analyze_homes_selectors():
    """HOMES詳細ページから実際に動作するセレクタを見つける"""
    # 実際のページを取得してセレクタを確認
    from backend.app.scrapers.homes_scraper import HomesScraper
    
    scraper = HomesScraper()
    
    # テスト用URL
    test_urls = [
        "https://www.homes.co.jp/mansion/b-1397180000123/",
        "https://www.homes.co.jp/mansion/b-1090830004751/"
    ]
    
    print("\n\n=== HOMES実際のセレクタテスト ===")
    
    for url in test_urls:
        print(f"\nURL: {url}")
        soup = scraper.fetch_page(url)
        
        if not soup:
            print("  ページ取得失敗")
            continue
        
        # 1. 新しい構造の会社情報を探す
        print("\n  不動産会社情報:")
        
        # パターン1: companyNameクラス
        company_names = soup.find_all(class_='companyName')
        for elem in company_names[:2]:
            print(f"    会社名(companyName): {elem.get_text(strip=True)}")
        
        # パターン2: 「提供」を含むテキストの周辺
        for text in soup.find_all(string=re.compile(r'提供|取扱|会社')):
            parent = text.parent
            if parent and parent.name in ['p', 'div', 'span']:
                # 親要素内のリンクを探す
                links = parent.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    if '/company/' in href:
                        print(f"    会社リンク: {link.get_text(strip=True)}")
        
        # パターン3: data-*属性を持つ要素
        company_divs = soup.find_all(['div', 'section'], attrs={'data-company-name': True})
        for div in company_divs:
            print(f"    会社名(data属性): {div.get('data-company-name')}")
        
        # 2. バルコニー面積
        print("\n  バルコニー面積:")
        # 現在のparse_property_detailメソッドでの取得を確認
        property_data = scraper.parse_property_detail(url)
        if property_data and 'balcony_area' in property_data:
            print(f"    現在の取得値: {property_data['balcony_area']}㎡")
        else:
            print("    現在は取得できていません")
        
        # 3. 備考
        print("\n  備考情報:")
        if property_data and 'remarks' in property_data:
            print(f"    現在の取得値: {property_data['remarks'][:100]}...")
        else:
            print("    現在は取得できていません")


if __name__ == "__main__":
    analyze_suumo_detail()
    analyze_homes_selectors()