#!/usr/bin/env python3
"""
SUUMOの一覧ページの構造を確認
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 環境変数を設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.scrapers.suumo_scraper import SuumoScraper
from bs4 import BeautifulSoup

def test_suumo_list_structure():
    """SUUMOの一覧ページの構造を確認"""
    scraper = SuumoScraper()
    
    # 港区の一覧ページを取得
    # SUUMOの場合、直接URLを構築
    url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/?pc=100"
    print(f"URL: {url}")
    
    soup = scraper.fetch_page(url)
    if not soup:
        print("ページの取得に失敗しました")
        return
        
    # 最初の物件の構造を詳しく確認
    property_units = soup.select('.property_unit')[:3]  # 最初の3件
    
    for i, unit in enumerate(property_units):
        print(f"\n=== 物件 {i+1} ===")
        
        # タイトル要素の構造を確認
        title_elem = unit.select_one('.property_unit-title')
        if title_elem:
            print(f"タイトル全体: {title_elem.get_text(strip=True)}")
            
            # タイトル内のリンク要素
            title_link = title_elem.select_one('a')
            if title_link:
                print(f"リンクテキスト: {title_link.get_text(strip=True)}")
                
            # 建物名を含む可能性のある要素を探す
            for elem in title_elem.find_all():
                if elem.name in ['span', 'div']:
                    text = elem.get_text(strip=True)
                    if text and '万円' not in text:
                        print(f"  {elem.name}: {text}")
        
        # 物件詳細情報のテーブルを確認
        print("\n物件詳細テーブルの確認:")
        
        # テーブル内の各行を確認
        tables = unit.select('table')
        for table in tables:
            rows = table.select('tr')
            for row in rows:
                cells = row.select('td')
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    if cell_text and '万円' not in cell_text and '分' not in cell_text:
                        print(f"  セル: {cell_text}")
                        
        # 物件情報を含むdivを探す
        property_body = unit.select_one('.property_unit-body')
        if property_body:
            # property_unit-body内の構造を確認
            print("\nproperty_unit-body内の構造:")
            
            # 各divを確認
            for div in property_body.select('div'):
                div_text = div.get_text(strip=True)
                # クラス名も確認
                classes = ' '.join(div.get('class', []))
                if div_text and len(div_text) > 5:
                    print(f"  div[class='{classes}']: {div_text[:50]}...")
                    
            # 「物件名」という項目を探す
            print("\n「物件名」項目を探す:")
            
            # dlタグ（定義リスト）を探す
            dl_elements = property_body.select('dl')
            for dl in dl_elements:
                dt_elements = dl.select('dt')
                dd_elements = dl.select('dd')
                
                for dt, dd in zip(dt_elements, dd_elements):
                    if '物件名' in dt.get_text():
                        building_name = dd.get_text(strip=True)
                        print(f"  物件名（dlタグ）: {building_name}")
                        
            # 「物件名」を含むテキストノードを探す
            for elem in property_body.find_all(string=lambda text: text and '物件名' in text):
                print(f"  「物件名」を含む要素: {elem.strip()}")
                # 次の兄弟要素を確認
                parent = elem.parent
                if parent:
                    next_sibling = parent.find_next_sibling()
                    if next_sibling:
                        print(f"    次の要素: {next_sibling.get_text(strip=True)}")

if __name__ == "__main__":
    test_suumo_list_structure()