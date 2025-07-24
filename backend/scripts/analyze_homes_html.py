#!/usr/bin/env python3
"""
LIFULL HOME'Sの詳細ページのHTML構造を分析
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper import HomesScraper
from bs4 import BeautifulSoup

def analyze_homes_html():
    """LIFULL HOME'SのHTML構造を分析"""
    print("=== LIFULL HOME'S HTML構造分析 ===\n")
    
    scraper = HomesScraper()
    
    # 一覧ページから物件URLを取得
    list_url = scraper.get_search_url("港区", page=1)
    soup = scraper.fetch_page(list_url)
    
    if not soup:
        print("エラー: 一覧ページの取得に失敗しました")
        return
    
    properties = scraper.parse_property_list(soup)
    if not properties:
        print("エラー: 物件が見つかりませんでした")
        return
    
    # 詳細ページを取得
    test_url = properties[0].get('url')
    print(f"テストURL: {test_url}\n")
    
    detail_soup = scraper.fetch_page(test_url)
    if not detail_soup:
        print("エラー: 詳細ページの取得に失敗しました")
        return
    
    # 1. 主要な要素を探す
    print("1. 主要な要素の探索:")
    
    # タイトル要素
    print("\n  タイトル要素候補:")
    for tag in ['h1', 'h2']:
        elements = detail_soup.find_all(tag)
        for elem in elements[:3]:  # 最初の3つ
            text = elem.get_text(strip=True)
            if text and len(text) > 5:  # 意味のあるテキストのみ
                classes = elem.get('class', [])
                print(f"    <{tag} class=\"{' '.join(classes)}\">: {text[:50]}...")
    
    # 価格を含む要素
    print("\n  価格情報を含む要素:")
    price_elements = detail_soup.find_all(text=lambda t: t and '万円' in t)
    for elem in price_elements[:5]:
        parent = elem.parent
        if parent and parent.name not in ['script', 'style']:
            classes = parent.get('class', [])
            print(f"    <{parent.name} class=\"{' '.join(classes)}\">: {elem.strip()[:50]}...")
    
    # テーブル要素
    print("\n  テーブル要素:")
    tables = detail_soup.find_all('table')
    for i, table in enumerate(tables[:3]):
        classes = table.get('class', [])
        print(f"    table[{i}] class=\"{' '.join(classes)}\"")
        # テーブルの最初の行を表示
        first_row = table.find('tr')
        if first_row:
            cells = first_row.find_all(['th', 'td'])
            if cells:
                print(f"      最初の行: {' | '.join([c.get_text(strip=True)[:20] for c in cells[:3]])}")
    
    # dl要素（定義リスト）
    print("\n  定義リスト要素:")
    dls = detail_soup.find_all('dl')
    for i, dl in enumerate(dls[:3]):
        classes = dl.get('class', [])
        print(f"    dl[{i}] class=\"{' '.join(classes)}\"")
        dt = dl.find('dt')
        dd = dl.find('dd')
        if dt and dd:
            print(f"      {dt.get_text(strip=True)}: {dd.get_text(strip=True)[:30]}...")
    
    # 2. React/Next.jsアプリケーションの可能性を確認
    print("\n2. JavaScript フレームワークの確認:")
    
    # script要素を確認
    scripts = detail_soup.find_all('script')
    react_found = False
    next_found = False
    
    for script in scripts:
        src = script.get('src', '')
        text = script.string or ''
        
        if 'react' in src.lower() or 'react' in text.lower():
            react_found = True
        if 'next' in src.lower() or '_next' in src:
            next_found = True
    
    if react_found:
        print("  ✓ Reactが使用されています")
    if next_found:
        print("  ✓ Next.jsが使用されています")
    
    # JSON-LDデータの確認
    print("\n3. 構造化データ（JSON-LD）の確認:")
    json_lds = detail_soup.find_all('script', type='application/ld+json')
    if json_lds:
        print(f"  ✓ {len(json_lds)}個のJSON-LDデータが見つかりました")
        for i, json_ld in enumerate(json_lds[:2]):
            try:
                import json
                data = json.loads(json_ld.string)
                print(f"    JSON-LD[{i}] type: {data.get('@type', 'unknown')}")
            except:
                pass
    
    # 3. 物件情報が含まれる可能性のある要素を探す
    print("\n4. 物件情報を含む可能性のある要素:")
    
    # よくあるクラス名パターン
    patterns = ['property', 'detail', 'spec', 'info', 'data', 'content']
    found_elements = []
    
    for pattern in patterns:
        elements = detail_soup.find_all(attrs={'class': lambda x: x and any(pattern in cls.lower() for cls in x)})
        for elem in elements[:10]:  # 最初の10個
            if elem.name in ['div', 'section', 'article'] and len(elem.get_text(strip=True)) > 50:
                classes = ' '.join(elem.get('class', []))
                if classes not in [' '.join(e.get('class', [])) for e in found_elements]:
                    found_elements.append(elem)
                    print(f"    <{elem.name} class=\"{classes}\">")
                    # 子要素の一部を表示
                    children = elem.find_all(['p', 'span', 'div'])[:3]
                    for child in children:
                        text = child.get_text(strip=True)
                        if text and '万円' in text or '㎡' in text or '階' in text:
                            print(f"      → {text[:50]}...")


def main():
    try:
        analyze_homes_html()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()