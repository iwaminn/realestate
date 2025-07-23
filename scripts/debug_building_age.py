#!/usr/bin/env python3
"""
築年月データのデバッグ用スクリプト
実際のSUUMOページから築年月情報を取得
"""

import requests
from bs4 import BeautifulSoup
import re
import time

def debug_suumo_building_age():
    """SUUMOページから築年月情報を詳細に調査"""
    url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        property_items = soup.find_all('div', class_='property_unit-info')
        
        print(f"=== 築年月デバッグ: {len(property_items)} 物件を調査 ===")
        
        for i, item in enumerate(property_items[:3]):  # 最初の3件のみ
            print(f"\n--- 物件 {i+1} ---")
            
            # 物件名
            name_elem = item.find('dd')
            building_name = name_elem.get_text(strip=True) if name_elem else "名前不明"
            print(f"物件名: {building_name}")
            
            # 全てのテキストを取得
            item_text = item.get_text()
            print(f"全文: {item_text[:500]}...")
            
            # 築年月関連のパターンを探す
            age_patterns = [
                r'築(\d+)年',
                r'築年数(\d+)年',
                r'築(\d+)',
                r'(\d{4})年(\d{1,2})月築',
                r'(\d{4})年築',
                r'建築(\d{4})年',
                r'竣工(\d{4})年',
                r'完成(\d{4})年'
            ]
            
            found_age = False
            for pattern in age_patterns:
                matches = re.findall(pattern, item_text)
                if matches:
                    print(f"築年月パターン '{pattern}' で発見: {matches}")
                    found_age = True
            
            if not found_age:
                print("❌ 築年月情報が見つかりません")
            
            # 個別の要素を確認
            dts = item.find_all('dt')
            for dt in dts:
                dt_text = dt.get_text(strip=True)
                if '築' in dt_text or '年' in dt_text or '建築' in dt_text:
                    dd = dt.find_next('dd')
                    dd_text = dd.get_text(strip=True) if dd else "N/A"
                    print(f"関連要素: {dt_text} -> {dd_text}")
        
        # HTMLをファイルに保存
        with open('suumo_building_age_debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n💾 HTMLを suumo_building_age_debug.html に保存しました")
        
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    debug_suumo_building_age()