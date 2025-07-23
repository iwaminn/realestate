#!/usr/bin/env python3
"""
築年月の詳細データを保存するためのデータベース改善
"""

import sqlite3
from datetime import datetime

def add_construction_date_columns():
    """築年月の詳細カラムを追加"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    try:
        # 築年（建築年）カラムを追加
        cursor.execute('ALTER TABLE properties ADD COLUMN construction_year INTEGER')
        print("✅ construction_year カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ construction_year カラムは既に存在します")
        else:
            print(f"❌ construction_year カラムの追加でエラー: {e}")
    
    try:
        # 築月（建築月）カラムを追加
        cursor.execute('ALTER TABLE properties ADD COLUMN construction_month INTEGER')
        print("✅ construction_month カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ construction_month カラムは既に存在します")
        else:
            print(f"❌ construction_month カラムの追加でエラー: {e}")
    
    try:
        # 築年月（日付形式）カラムを追加
        cursor.execute('ALTER TABLE properties ADD COLUMN construction_date DATE')
        print("✅ construction_date カラムを追加しました")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ construction_date カラムは既に存在します")
        else:
            print(f"❌ construction_date カラムの追加でエラー: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n📊 データベース構造の改善が完了しました")

def populate_construction_dates():
    """既知の築年月データを設定"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # 実際のSUUMOから取得した築年月データ
    building_dates = {
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
    }
    
    updated_count = 0
    
    for building_name, date_info in building_dates.items():
        year = date_info['year']
        month = date_info['month']
        
        # 日付文字列を作成（月の最初の日として）
        construction_date = f"{year}-{month:02d}-01"
        
        cursor.execute('''
            UPDATE properties 
            SET construction_year = ?, 
                construction_month = ?, 
                construction_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE building_name = ?
        ''', (year, month, construction_date, building_name))
        
        if cursor.rowcount > 0:
            print(f"✅ {building_name}: {year}年{month}月築")
            updated_count += 1
        else:
            print(f"⚠️ {building_name}: データベースで見つかりません")
    
    conn.commit()
    conn.close()
    
    print(f"\n📊 築年月データ設定完了: {updated_count} 件")

def show_construction_date_summary():
    """築年月データの概要を表示"""
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # 築年月データの統計
    cursor.execute('''
        SELECT 
            COUNT(*) as total_properties,
            COUNT(construction_year) as with_year,
            COUNT(construction_month) as with_month,
            COUNT(construction_date) as with_date
        FROM properties
    ''')
    
    stats = cursor.fetchone()
    total, with_year, with_month, with_date = stats
    
    print(f"\n📊 築年月データの統計:")
    print(f"総物件数: {total}")
    print(f"築年データあり: {with_year} ({with_year/total*100:.1f}%)")
    print(f"築月データあり: {with_month} ({with_month/total*100:.1f}%)")
    print(f"築年月日付あり: {with_date} ({with_date/total*100:.1f}%)")
    
    # 詳細な築年月データを表示
    cursor.execute('''
        SELECT building_name, construction_year, construction_month, construction_date
        FROM properties
        WHERE construction_year IS NOT NULL
        ORDER BY construction_year, construction_month
        LIMIT 10
    ''')
    
    details = cursor.fetchall()
    
    print(f"\n🏠 築年月データの例 (最初の10件):")
    for building_name, year, month, date in details:
        print(f"  {building_name}: {year}年{month}月築 ({date})")
    
    conn.close()

if __name__ == "__main__":
    print("🏗️ 築年月データベース改善")
    print("=" * 40)
    
    # 1. カラムを追加
    add_construction_date_columns()
    
    # 2. データを設定
    populate_construction_dates()
    
    # 3. 結果を表示
    show_construction_date_summary()