#!/usr/bin/env python3
"""
実際のページをフェッチして詳細に分析
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.suumo_scraper_v3 import SuumoScraperV3
from backend.app.scrapers.homes_scraper import HomesScraper
import re
from bs4 import BeautifulSoup

def analyze_suumo_page():
    """SUUMOページを実際にフェッチして分析"""
    scraper = SuumoScraperV3()
    
    # 詳細ページのサンプルURL
    url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77989325/"
    
    print("=== SUUMO詳細ページ分析 ===")
    print(f"URL: {url}")
    
    soup = scraper.fetch_page(url)
    if not soup:
        print("ページの取得に失敗しました")
        return
    
    print("\n1. 不動産会社情報の探索:")
    
    # パターン1: class="cassette"内の会社情報
    cassettes = soup.find_all('div', class_='cassette')
    print(f"  cassette要素: {len(cassettes)}個")
    
    # パターン2: id="company"や"shop"を含む要素
    company_divs = soup.find_all(['div', 'section'], id=re.compile(r'company|shop|realtor', re.I))
    print(f"  company ID要素: {len(company_divs)}個")
    
    # パターン3: お問い合わせセクション
    inquire_sections = soup.find_all(['div', 'section'], class_=re.compile(r'inquire|contact|toiawase', re.I))
    print(f"  お問い合わせセクション: {len(inquire_sections)}個")
    
    # パターン4: 「取扱店舗」「不動産会社」を含むテキストの親要素
    for text in soup.find_all(string=re.compile(r'取扱店舗|不動産会社|仲介会社')):
        parent = text.parent
        if parent:
            print(f"\n  '取扱店舗'の親要素: {parent.name}")
            # 次の兄弟要素を探す
            next_elem = parent.find_next_sibling()
            if next_elem:
                print(f"    次の要素: {next_elem.get_text(strip=True)[:50]}")
    
    print("\n2. バルコニー面積の探索:")
    
    # すべてのテーブルをチェック
    tables = soup.find_all('table')
    for i, table in enumerate(tables):
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            for j in range(len(cells)-1):
                cell_text = cells[j].get_text(strip=True)
                if 'バルコニー' in cell_text or 'ベランダ' in cell_text:
                    print(f"\n  テーブル{i+1}で発見:")
                    print(f"    ラベル: {cell_text}")
                    if j+1 < len(cells):
                        print(f"    値: {cells[j+1].get_text(strip=True)}")
    
    # DLリストもチェック
    dls = soup.find_all('dl')
    for i, dl in enumerate(dls):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            dt_text = dt.get_text(strip=True)
            if 'バルコニー' in dt_text or 'ベランダ' in dt_text or ('面積' in dt_text and 'バルコニー' in dd.get_text()):
                print(f"\n  DLリスト{i+1}で発見:")
                print(f"    ラベル: {dt_text}")
                print(f"    値: {dd.get_text(strip=True)}")
    
    print("\n3. 備考・特記事項の探索:")
    
    # 物件のアピールポイント
    appeal_sections = soup.find_all(['div', 'section'], class_=re.compile(r'appeal|feature|point|description', re.I))
    for section in appeal_sections[:3]:
        text = section.get_text(strip=True)
        if len(text) > 20:
            print(f"\n  アピールセクション: {text[:100]}...")
    
    # コメント系の要素
    comment_divs = soup.find_all(['div', 'p'], class_=re.compile(r'comment|note|remark', re.I))
    for div in comment_divs[:3]:
        text = div.get_text(strip=True)
        if len(text) > 20:
            print(f"\n  コメント要素: {text[:100]}...")


def analyze_homes_page():
    """HOMESページを実際にフェッチして分析"""
    scraper = HomesScraper()
    
    # 詳細ページのサンプルURL
    url = "https://www.homes.co.jp/mansion/b-1397180000123/"
    
    print("\n\n=== HOMES詳細ページ分析 ===")
    print(f"URL: {url}")
    
    soup = scraper.fetch_page(url)
    if not soup:
        print("ページの取得に失敗しました")
        return
    
    print("\n1. 不動産会社情報の探索:")
    
    # HOMESの会社情報パターン
    # パターン1: mod-会社情報系のクラス
    company_mods = soup.find_all(['div', 'section'], class_=re.compile(r'mod-.*company|mod-.*shop|mod-.*realtor', re.I))
    print(f"  mod-会社情報要素: {len(company_mods)}個")
    
    # パターン2: 「情報提供会社」を含むテキストの周辺
    for text in soup.find_all(string=re.compile(r'情報提供会社|取扱.*会社|不動産会社')):
        parent = text.parent
        if parent:
            print(f"\n  '情報提供会社'の親要素: {parent.name}")
            # 親の親要素の中を探す
            grandparent = parent.parent
            if grandparent:
                # 会社名を探す
                links = grandparent.find_all('a')
                for link in links:
                    link_text = link.get_text(strip=True)
                    if link_text and not link_text.isdigit():
                        print(f"    会社名候補: {link_text}")
                # 電話番号を探す
                tel_pattern = re.compile(r'[\d\-\(\)]+')
                tel_matches = tel_pattern.findall(grandparent.get_text())
                for tel in tel_matches:
                    if len(tel) >= 10:
                        print(f"    電話番号候補: {tel}")
    
    print("\n2. 一覧ページの構造分析:")
    
    # 一覧ページも分析
    list_url = "https://www.homes.co.jp/mansion/chuko/tokyo/minato-city/list/"
    list_soup = scraper.fetch_page(list_url)
    
    if list_soup:
        print(f"\n一覧ページURL: {list_url}")
        
        # 物件アイテムの探索
        # パターン1: mod-mergeBuilding（現在動作している）
        items = list_soup.find_all('div', class_='mod-mergeBuilding')
        print(f"  mod-mergeBuilding: {len(items)}個")
        
        if items:
            item = items[0]
            # 新着・更新マークを探す
            # すべてのspan, divでlabel系のクラスを持つもの
            labels = item.find_all(['span', 'div', 'p'], class_=re.compile(r'label|mark|icon|badge', re.I))
            for label in labels:
                text = label.get_text(strip=True)
                if text and len(text) < 20:  # 短いテキストのみ（ラベルの可能性が高い）
                    print(f"    ラベル候補: [{label.get('class')}] = {text}")
            
            # imgタグでnew/updateを含むもの
            imgs = item.find_all('img', alt=re.compile(r'new|update|新着|更新', re.I))
            for img in imgs:
                print(f"    画像ラベル: alt='{img.get('alt')}' src='{img.get('src')}'")


if __name__ == "__main__":
    analyze_suumo_page()
    analyze_homes_page()