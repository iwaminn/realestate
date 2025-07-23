#!/usr/bin/env python3
"""
元サイトリンク機能をテストするスクリプト
"""

import sqlite3
import sys
import os

# web_frontend.pyと同じ関数を使用
def build_property_url(source_site, source_property_id):
    """物件IDからURLを構築"""
    if not source_property_id:
        return None
    
    if source_site == 'suumo':
        return f"https://suumo.jp/ms/chuko/tokyo/sc_minato/{source_property_id}/"
    elif source_site == 'athome':
        return f"https://athome.jp/mansions/{source_property_id}/"
    elif source_site == 'homes':
        return f"https://homes.co.jp/chuko/{source_property_id}/"
    
    return None

def get_site_display_name(source_site):
    """サイト名の表示用名称を取得"""
    site_names = {
        'suumo': 'SUUMO',
        'athome': 'アットホーム',
        'homes': 'ホームズ',
        'rakumachi': '楽待'
    }
    return site_names.get(source_site, source_site.upper())

def test_property_links(property_id):
    """指定された物件のリンクをテスト"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # 物件情報を取得
    cursor.execute('''
        SELECT p.id, p.address, p.building_name
        FROM properties p
        WHERE p.id = ?
    ''', (property_id,))
    
    property_data = cursor.fetchone()
    if not property_data:
        print(f"❌ 物件ID {property_id} が見つかりません")
        return
    
    prop_id, address, building_name = property_data
    print(f"🏠 物件情報:")
    print(f"  ID: {prop_id}")
    print(f"  住所: {address}")
    print(f"  建物名: {building_name}")
    
    # リスティング情報を取得
    cursor.execute('''
        SELECT source_site, agent_company, listed_price, scraped_at, source_property_id
        FROM property_listings
        WHERE property_id = ? AND is_active = 1
    ''', (property_id,))
    
    listings = cursor.fetchall()
    print(f"\n📋 リスティング情報:")
    
    for listing in listings:
        site, agent, listed_price, scraped_at, source_property_id = listing
        print(f"  サイト: {site}")
        print(f"  業者: {agent}")
        print(f"  価格: {listed_price:,}円")
        print(f"  物件ID: {source_property_id}")
        
        # URLを構築
        source_url = build_property_url(site, source_property_id)
        site_display_name = get_site_display_name(site)
        
        if source_url:
            print(f"  ✅ リンク: {source_url}")
            print(f"  表示名: {site_display_name}")
        else:
            print(f"  ❌ リンク構築に失敗")
        
        print()
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        property_id = int(sys.argv[1])
    else:
        property_id = 6  # デフォルト
    
    test_property_links(property_id)