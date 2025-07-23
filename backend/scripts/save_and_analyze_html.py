#!/usr/bin/env python3
"""
HTMLを保存して構造を詳しく分析
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper_v3 import SuumoScraperV3
from backend.app.scrapers.homes_scraper import HomesScraper
import re
from bs4 import BeautifulSoup

def save_and_analyze_suumo():
    """SUUMOページのHTMLを保存して分析"""
    scraper = SuumoScraperV3()
    
    # 詳細ページ
    detail_url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77989325/"
    detail_soup = scraper.fetch_page(detail_url)
    
    if detail_soup:
        # HTMLを保存
        with open('/tmp/suumo_detail.html', 'w', encoding='utf-8') as f:
            f.write(str(detail_soup.prettify()))
        print("SUUMOの詳細ページHTMLを /tmp/suumo_detail.html に保存しました")
        
        # 特定の要素を探す
        print("\nSUUMO詳細ページの分析:")
        
        # すべてのテーブルの内容を確認
        tables = detail_soup.find_all('table')
        print(f"\nテーブル数: {len(tables)}")
        for i, table in enumerate(tables[:5]):
            print(f"\n--- テーブル{i+1} ---")
            # 最初の3行を表示
            rows = table.find_all('tr')[:3]
            for row in rows:
                cells = row.find_all(['th', 'td'])
                row_text = ' | '.join([cell.get_text(strip=True)[:30] for cell in cells])
                print(f"  {row_text}")
        
        # class属性を持つdivの統計
        all_divs = detail_soup.find_all('div', class_=True)
        class_counts = {}
        for div in all_divs:
            classes = div.get('class', [])
            for cls in classes:
                class_counts[cls] = class_counts.get(cls, 0) + 1
        
        print("\n主要なクラス名（div要素）:")
        sorted_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
        for cls, count in sorted_classes[:20]:
            print(f"  {cls}: {count}個")
    
    # 一覧ページ
    list_url = "https://suumo.jp/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=011&sc=13103&ta=13&po=0&pj=1&pc=100"
    list_soup = scraper.fetch_page(list_url)
    
    if list_soup:
        with open('/tmp/suumo_list.html', 'w', encoding='utf-8') as f:
            f.write(str(list_soup.prettify()))
        print("\nSUUMOの一覧ページHTMLを /tmp/suumo_list.html に保存しました")
        
        # 物件要素を探す
        print("\nSUUMO一覧ページの分析:")
        property_units = list_soup.find_all('div', class_='property_unit')
        print(f"property_unit要素: {len(property_units)}個")
        
        if property_units:
            unit = property_units[0]
            # 不動産会社情報を探す
            company_candidates = unit.find_all(['div', 'span'], string=re.compile(r'.*(不動産|ハウス|住宅|リアルティ|エステート).*'))
            for elem in company_candidates[:3]:
                print(f"\n会社名候補: {elem.get_text(strip=True)}")
                print(f"  タグ: {elem.name}, クラス: {elem.get('class')}")


def save_and_analyze_homes():
    """HOMESページのHTMLを保存して分析"""
    scraper = HomesScraper()
    
    # 詳細ページ
    detail_url = "https://www.homes.co.jp/mansion/b-1397180000123/"
    detail_soup = scraper.fetch_page(detail_url)
    
    if detail_soup:
        with open('/tmp/homes_detail.html', 'w', encoding='utf-8') as f:
            f.write(str(detail_soup.prettify()))
        print("\n\nHOMESの詳細ページHTMLを /tmp/homes_detail.html に保存しました")
        
        print("\nHOMES詳細ページの分析:")
        
        # すべてのテーブルをチェック
        tables = detail_soup.find_all('table')
        print(f"\nテーブル数: {len(tables)}")
        for i, table in enumerate(tables[:5]):
            print(f"\n--- テーブル{i+1} ---")
            # クラス名
            print(f"  クラス: {table.get('class')}")
            # 最初の3行
            rows = table.find_all('tr')[:3]
            for row in rows:
                cells = row.find_all(['th', 'td'])
                row_text = ' | '.join([cell.get_text(strip=True)[:30] for cell in cells])
                print(f"  {row_text}")
        
        # 情報提供会社の周辺を詳しく見る
        for text in detail_soup.find_all(string=re.compile(r'情報提供会社')):
            print(f"\n'情報提供会社'を含む要素:")
            current = text.parent
            # 5階層上まで見る
            for i in range(5):
                if current:
                    print(f"  {i}階層上: {current.name} {current.get('class')}")
                    # aタグを探す
                    links = current.find_all('a')
                    for link in links[:3]:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        if text and '/company/' in href:
                            print(f"    会社リンク: {text} -> {href}")
                    current = current.parent
    
    # 一覧ページ
    list_url = "https://www.homes.co.jp/mansion/chuko/tokyo/minato-city/list/"
    list_soup = scraper.fetch_page(list_url)
    
    if list_soup:
        with open('/tmp/homes_list.html', 'w', encoding='utf-8') as f:
            f.write(str(list_soup.prettify()))
        print("\nHOMESの一覧ページHTMLを /tmp/homes_list.html に保存しました")
        
        print("\nHOMES一覧ページの分析:")
        
        # 様々なパターンで物件要素を探す
        patterns = [
            ('mod-mergeBuilding', 'div'),
            ('buildingCassette', 'div'),
            ('searchResultBlock', 'div'),
            ('property', 'article'),
            ('item', 'div'),
            ('cassette', 'div')
        ]
        
        for pattern, tag in patterns:
            elements = list_soup.find_all(tag, class_=re.compile(pattern, re.I))
            if elements:
                print(f"\nパターン '{pattern}' ({tag}タグ): {len(elements)}個")
                # 最初の要素の構造を見る
                elem = elements[0]
                # 子要素のクラスを調べる
                children = elem.find_all(['div', 'span'], class_=True)[:10]
                child_classes = set()
                for child in children:
                    child_classes.update(child.get('class', []))
                print(f"  子要素のクラス: {list(child_classes)[:10]}")


if __name__ == "__main__":
    save_and_analyze_suumo()
    save_and_analyze_homes()