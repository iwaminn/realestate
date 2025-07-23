#!/usr/bin/env python3
"""
既存物件の築年数データを更新
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import re
from datetime import datetime
import time
import random

def extract_building_age_from_url(url):
    """URLから築年数を抽出"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 築年月要素を探す
        building_age_elem = soup.find('dt', text='築年月')
        if building_age_elem:
            building_age_dd = building_age_elem.find_next('dd')
            if building_age_dd:
                building_age_text = building_age_dd.get_text(strip=True)
                # 「1981年12月」形式から築年数を計算
                year_match = re.search(r'(\d{4})年', building_age_text)
                if year_match:
                    built_year = int(year_match.group(1))
                    current_year = datetime.now().year
                    building_age = current_year - built_year
                    return building_age
        
        return None
        
    except Exception as e:
        print(f"URLエラー {url}: {e}")
        return None

def update_existing_building_ages():
    """既存物件の築年数を更新"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # 築年数がNULLの物件を取得
    cursor.execute('''
        SELECT p.id, p.building_name, pl.source_property_id
        FROM properties p
        JOIN property_listings pl ON p.id = pl.property_id
        WHERE p.building_age IS NULL AND pl.source_site = 'suumo'
    ''')
    
    properties = cursor.fetchall()
    
    print(f"📊 築年数を更新する物件: {len(properties)} 件")
    
    updated_count = 0
    
    for prop_id, building_name, source_property_id in properties:
        print(f"\n🏠 処理中: {building_name} (ID: {prop_id})")
        
        # SUUMOのURLを構築
        url = f"https://suumo.jp/ms/chuko/tokyo/sc_minato/{source_property_id}/"
        print(f"URL: {url}")
        
        # 築年数を取得
        building_age = extract_building_age_from_url(url)
        
        if building_age:
            # データベースを更新
            cursor.execute('''
                UPDATE properties 
                SET building_age = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (building_age, prop_id))
            
            print(f"✅ 築年数更新: {building_age}年")
            updated_count += 1
        else:
            print(f"❌ 築年数取得失敗")
        
        # レート制限のための待機
        delay = random.uniform(2, 5)
        print(f"⏳ {delay:.1f}秒待機...")
        time.sleep(delay)
    
    conn.commit()
    conn.close()
    
    print(f"\n📊 更新完了: {updated_count}/{len(properties)} 件の築年数を更新しました")

if __name__ == "__main__":
    update_existing_building_ages()