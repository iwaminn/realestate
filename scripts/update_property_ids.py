#!/usr/bin/env python3
"""
既存のURLから物件IDを抽出してデータベースを更新
"""

import sqlite3
import re
from urllib.parse import urlparse

def extract_property_id_from_url(url, source_site):
    """URLから物件IDを抽出"""
    if not url:
        return None
    
    if source_site == 'suumo':
        # SUUMOのURL形式: https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77778991/
        match = re.search(r'/nc_(\d+)/', url)
        if match:
            return f"nc_{match.group(1)}"
    
    # 他のサイトの場合は将来的に追加
    return None

def update_property_ids():
    """既存のデータの物件IDを更新"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # 全てのリスティングを取得
    cursor.execute('SELECT id, source_url, source_site FROM property_listings')
    listings = cursor.fetchall()
    
    updated_count = 0
    
    for listing_id, source_url, source_site in listings:
        property_id = extract_property_id_from_url(source_url, source_site)
        
        if property_id:
            cursor.execute('''
                UPDATE property_listings 
                SET source_property_id = ? 
                WHERE id = ?
            ''', (property_id, listing_id))
            updated_count += 1
            print(f"Updated ID {listing_id}: {property_id}")
    
    conn.commit()
    conn.close()
    
    print(f"✅ {updated_count} 件のリスティングを更新しました")

if __name__ == "__main__":
    update_property_ids()