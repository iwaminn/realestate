#!/usr/bin/env python3
"""
築年数抽出ロジックのテスト
"""

from bs4 import BeautifulSoup
import re
from datetime import datetime

def extract_building_age_improved(item):
    """改良された築年数抽出"""
    item_text = item.get_text()
    building_age = None
    
    # 方法1: dt/dd要素から「築年月」を探す
    building_age_elem = item.find('dt', text='築年月')
    if building_age_elem:
        building_age_dd = building_age_elem.find_next('dd')
        if building_age_dd:
            building_age_text = building_age_dd.get_text(strip=True)
            print(f"  築年月要素発見: {building_age_text}")
            # 「1981年12月」形式から築年数を計算
            year_match = re.search(r'(\d{4})年', building_age_text)
            if year_match:
                built_year = int(year_match.group(1))
                current_year = datetime.now().year
                building_age = current_year - built_year
                print(f"  築年数計算: {current_year} - {built_year} = {building_age}年")
    
    # 方法2: テキストから築年数パターンを探す（フォールバック）
    if building_age is None:
        age_patterns = [
            r'築(\d+)年',
            r'築年数(\d+)年',
            r'築(\d+)',
            r'(\d{4})年(\d{1,2})月築'
        ]
        
        for pattern in age_patterns:
            age_match = re.search(pattern, item_text)
            if age_match:
                print(f"  パターン '{pattern}' でマッチ: {age_match.groups()}")
                if pattern.startswith(r'(\d{4})'):
                    # 年月形式の場合は計算
                    built_year = int(age_match.group(1))
                    current_year = datetime.now().year
                    building_age = current_year - built_year
                else:
                    # 直接の築年数
                    building_age = int(age_match.group(1))
                break
    
    return building_age

def test_building_age_extraction():
    """築年数抽出のテスト"""
    with open('suumo_building_age_debug.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    property_items = soup.find_all('div', class_='property_unit-info')
    
    print(f"=== 築年数抽出テスト: {len(property_items)} 物件 ===")
    
    success_count = 0
    
    for i, item in enumerate(property_items[:5]):  # 最初の5件
        print(f"\n--- 物件 {i+1} ---")
        
        # 物件名
        name_elem = item.find('dd')
        building_name = name_elem.get_text(strip=True) if name_elem else "名前不明"
        print(f"物件名: {building_name}")
        
        # 築年数抽出
        building_age = extract_building_age_improved(item)
        
        if building_age:
            print(f"✅ 築年数: {building_age}年")
            success_count += 1
        else:
            print(f"❌ 築年数取得失敗")
    
    print(f"\n📊 結果: {success_count}/{min(5, len(property_items))} 件成功 ({success_count/min(5, len(property_items))*100:.1f}%)")

if __name__ == "__main__":
    test_building_age_extraction()