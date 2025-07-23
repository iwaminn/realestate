#!/usr/bin/env python3
"""
平米数抽出の改善とテスト
"""

from bs4 import BeautifulSoup
import re

def extract_area_improved(item):
    """改良された面積抽出"""
    area = 0
    
    # 方法1: dt/dd要素から「専有面積」を探す
    area_elem = item.find('dt', text='専有面積')
    if area_elem:
        area_dd = area_elem.find_next('dd')
        if area_dd:
            area_text = area_dd.get_text(strip=True)
            print(f"  専有面積要素発見: {area_text}")
            
            # 「25.61m²（登記）」や「18.97m<sup>2</sup>（壁芯）」形式から面積を抽出
            area_patterns = [
                r'(\d+(?:\.\d+)?)m.*?2',  # 25.61m²や18.97m<sup>2</sup>に対応
                r'(\d+(?:\.\d+)?)㎡',
                r'(\d+(?:\.\d+)?)平米'
            ]
            
            for pattern in area_patterns:
                area_match = re.search(pattern, area_text)
                if area_match:
                    area = float(area_match.group(1))
                    print(f"  面積抽出成功: {area}㎡")
                    break
    
    # 方法2: テキスト全体から面積パターンを探す（フォールバック）
    if area == 0:
        item_text = item.get_text()
        area_patterns = [
            r'(\d+(?:\.\d+)?)m.*?2',
            r'(\d+(?:\.\d+)?)㎡',
            r'(\d+(?:\.\d+)?)平米'
        ]
        
        for pattern in area_patterns:
            area_match = re.search(pattern, item_text)
            if area_match:
                area = float(area_match.group(1))
                print(f"  テキストから面積抽出: {area}㎡")
                break
    
    return area

def test_area_extraction():
    """面積抽出のテスト"""
    with open('suumo_building_age_debug.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    property_items = soup.find_all('div', class_='property_unit-info')
    
    print(f"=== 面積抽出テスト: {len(property_items)} 物件 ===")
    
    success_count = 0
    
    for i, item in enumerate(property_items[:5]):  # 最初の5件
        print(f"\n--- 物件 {i+1} ---")
        
        # 物件名
        name_elem = item.find('dd')
        building_name = name_elem.get_text(strip=True) if name_elem else "名前不明"
        print(f"物件名: {building_name}")
        
        # 面積抽出
        area = extract_area_improved(item)
        
        if area > 0:
            print(f"✅ 面積: {area}㎡")
            success_count += 1
        else:
            print(f"❌ 面積取得失敗")
    
    print(f"\n📊 結果: {success_count}/{min(5, len(property_items))} 件成功 ({success_count/min(5, len(property_items))*100:.1f}%)")

if __name__ == "__main__":
    test_area_extraction()