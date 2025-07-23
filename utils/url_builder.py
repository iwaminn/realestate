#!/usr/bin/env python3
"""
物件IDからURLを構築するヘルパー関数
"""

def build_property_url(source_site, source_property_id):
    """物件IDからURLを構築"""
    if not source_property_id:
        return None
    
    if source_site == 'suumo':
        # SUUMOのURL形式: https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77778991/
        return f"https://suumo.jp/ms/chuko/tokyo/sc_minato/{source_property_id}/"
    
    elif source_site == 'athome':
        # アットホームの場合（将来的に追加）
        return f"https://athome.jp/mansions/{source_property_id}/"
    
    elif source_site == 'homes':
        # ホームズの場合（将来的に追加）
        return f"https://homes.co.jp/chuko/{source_property_id}/"
    
    # その他のサイトは元のURLを返す
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

# テスト用
if __name__ == "__main__":
    # テストケース
    test_cases = [
        ('suumo', 'nc_77778991'),
        ('athome', 'test123'),
        ('homes', 'prop456')
    ]
    
    for site, prop_id in test_cases:
        url = build_property_url(site, prop_id)
        print(f"{site} - {prop_id}: {url}")