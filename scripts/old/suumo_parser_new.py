#!/usr/bin/env python3
"""
新しいSUUMO解析用のparser
"""

import re
from bs4 import BeautifulSoup
from datetime import date

def parse_suumo_new(html_content):
    """新しいSUUMO形式の解析"""
    soup = BeautifulSoup(html_content, 'html.parser')
    properties = []
    
    # property_unit-info クラスを探す (実際のデータが含まれる)
    property_items = soup.find_all('div', class_='property_unit-info')
    
    print(f"Found {len(property_items)} property items")
    
    for i, item in enumerate(property_items):
        try:
            if i == 0:  # デバッグ用に最初の要素の構造を出力
                print(f"First item HTML: {str(item)[:500]}...")
            # 物件名の取得
            building_name = ""
            name_elem = item.find('dd')
            if name_elem:
                building_name = name_elem.get_text(strip=True)
            
            # 価格の取得
            price = 0
            price_elem = item.find('span', class_='dottable-value')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'(\d+)万円', price_text)
                if price_match:
                    price = int(price_match.group(1)) * 10000
            
            # 間取りの取得
            layout = ""
            item_text = item.get_text()
            layout_patterns = [r'(\d+DK)', r'(\d+LDK)', r'(\d+K)', r'(\d+R)']
            for pattern in layout_patterns:
                match = re.search(pattern, item_text)
                if match:
                    layout = match.group(1)
                    break
            
            # 面積の取得
            area = 0
            area_match = re.search(r'(\d+(?:\.\d+)?)m²', item_text)
            if area_match:
                area = float(area_match.group(1))
            
            # 住所の取得
            address = "東京都港区"
            address_elem = item.find('dt', text='所在地')
            if address_elem:
                address_dd = address_elem.find_next('dd')
                if address_dd:
                    address = address_dd.get_text(strip=True)
            
            # 築年数の取得
            building_age = None
            age_match = re.search(r'築(\d+)年', item_text)
            if age_match:
                building_age = int(age_match.group(1))
            
            # 詳細ページのURL
            detail_url = ""
            link_elem = item.find('a', href=True)
            if link_elem:
                detail_url = link_elem['href']
                if not detail_url.startswith('http'):
                    detail_url = f"https://suumo.jp{detail_url}"
            
            # デバッグ出力
            print(f"Debug: building_name={building_name}, price={price}, layout={layout}, area={area}")
            
            # 最低限の情報があれば保存
            if price > 0:
                property_data = {
                    'address': address,
                    'building_name': building_name or "物件名不明",
                    'room_layout': layout or "間取り不明",
                    'floor_area': area or 0,
                    'floor': None,
                    'building_age': building_age,
                    'structure': None,
                    'current_price': price,
                    'management_fee': 0,
                    'transport_info': "",
                    'source_site': 'suumo',
                    'source_url': detail_url,
                    'agent_company': 'SUUMO掲載',
                    'first_listed_at': date.today().isoformat()
                }
                
                properties.append(property_data)
                print(f"Property: {building_name} - {price:,}円 - {layout} - {area}m²")
                
        except Exception as e:
            print(f"Error parsing property: {e}")
            continue
    
    return properties

# テスト用
if __name__ == "__main__":
    with open('suumo_debug.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    properties = parse_suumo_new(html_content)
    print(f"\nTotal properties found: {len(properties)}")
    for prop in properties:
        print(f"- {prop['building_name']} | {prop['current_price']:,}円 | {prop['room_layout']} | {prop['floor_area']}m²")