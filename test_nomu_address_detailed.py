#!/usr/bin/env python3
"""
ノムコムの住所取得を詳細に確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper

# テスト用スクレイパー
scraper = NomuScraper()

# 問題のあった物件のURL
test_urls = [
    "https://www.nomu.com/mansion/id/EF416025/",  # 物件ID 5772
    "https://www.nomu.com/mansion/id/E9316014/",  # セザール西落合
]

for url in test_urls:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    print('='*60)
    
    # ページを取得
    soup = scraper.fetch_page(url)
    if soup:
        # 1. テーブル内の「所在地」を探す
        print("\n1. テーブル内の「所在地」行を探す:")
        found_address = False
        
        tables = soup.find_all("table")
        print(f"   テーブル数: {len(tables)}")
        
        for i, table in enumerate(tables):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                for j in range(len(cells) - 1):
                    if cells[j].get_text(strip=True) == "所在地":
                        print(f"\n   テーブル{i+1}で「所在地」を発見!")
                        print(f"   テーブルclass: {table.get('class', [])}")
                        
                        next_cell = cells[j + 1]
                        print(f"   次のセルのHTML: {str(next_cell)[:200]}...")
                        
                        # p要素を探す
                        p_elem = next_cell.find("p")
                        if p_elem:
                            address_text = p_elem.get_text(strip=True)
                            print(f"   <p>タグ内の住所: {address_text}")
                            
                            # aタグがあるか確認
                            a_tags = p_elem.find_all("a")
                            if a_tags:
                                print(f"   ⚠️ <a>タグが{len(a_tags)}個含まれています")
                                for a in a_tags:
                                    print(f"      - {a.get_text(strip=True)}")
                        else:
                            # p要素がない場合
                            cell_text = next_cell.get_text(strip=True)
                            print(f"   セルの直接テキスト: {cell_text}")
                        
                        found_address = True
                        break
                if found_address:
                    break
            if found_address:
                break
        
        if not found_address:
            print("   ✗ 「所在地」行が見つかりません")
        
        # 2. p class="address"も確認
        print("\n2. <p class='address'>要素を探す:")
        address_p = soup.find("p", {"class": "address"})
        if address_p:
            print(f"   ✓ 見つかりました: {address_p.get_text(strip=True)}")
        else:
            print("   ✗ 見つかりません")
        
        # 3. 実際のparse_property_detailメソッドを実行
        print("\n3. parse_property_detail()の実行結果:")
        detail_data = scraper.parse_property_detail(url)
        if detail_data:
            print(f"   住所: {detail_data.get('address', '取得失敗')}")
            print(f"   建物名: {detail_data.get('building_name', '取得失敗')}")
            print(f"   価格: {detail_data.get('price', '取得失敗')}")
        else:
            print("   詳細データの取得に失敗")