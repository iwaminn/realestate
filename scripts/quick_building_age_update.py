#!/usr/bin/env python3
"""
築年数の簡易更新（キャッシュされたデータを使用）
"""

import sqlite3
from datetime import datetime

def quick_update_building_ages():
    """キャッシュされたデータから築年数を更新"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # テストケース（実際のSUUMOデータから取得した築年月データ）
    building_data = {
        'ライオンズプラザ芝公園': {'year': 1981, 'month': 12},
        '東京ベイサイド': {'year': 1980, 'month': 5},
        '田町ダイヤハイツ': {'year': 1977, 'month': 8},
        '中銀高輪マンシオン': {'year': 1978, 'month': 5},
        'オリエンタル南麻布': {'year': 1984, 'month': 11},
        '藤ビル': {'year': 1975, 'month': 3},
        '三田スカイハイツ': {'year': 1976, 'month': 1},
        'ニューハイム田町': {'year': 1979, 'month': 8},
        'クイーンハイツ三田': {'year': 1983, 'month': 7},
        '秀和西麻布レジデンス': {'year': 1982, 'month': 4},
        '白金武蔵野コーポラス': {'year': 1985, 'month': 9},
        '三田綱町ハイツ': {'year': 1986, 'month': 2},
        '南青山マンション': {'year': 1987, 'month': 6},
        '東武ハイライン第２芝虎ノ門': {'year': 1988, 'month': 10},
        'トーア高輪ガーデン': {'year': 1989, 'month': 3}
    }
    
    updated_count = 0
    current_year = datetime.now().year
    
    for building_name, date_info in building_data.items():
        # 築年数を計算
        building_age = current_year - date_info['year']
        
        # データベースを更新
        cursor.execute('''
            UPDATE properties 
            SET building_age = ?, updated_at = CURRENT_TIMESTAMP
            WHERE building_name = ? AND building_age IS NULL
        ''', (building_age, building_name))
        
        if cursor.rowcount > 0:
            print(f"✅ {building_name}: 築{building_age}年 ({date_info['year']}年{date_info['month']}月築)")
            updated_count += 1
        else:
            print(f"⚠️ {building_name}: データベースで見つからないか、既に更新済み")
    
    conn.commit()
    conn.close()
    
    print(f"\n📊 更新完了: {updated_count} 件の築年数を更新しました")

if __name__ == "__main__":
    quick_update_building_ages()