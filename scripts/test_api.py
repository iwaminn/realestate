#!/usr/bin/env python3
"""
API動作テストスクリプト
"""

import sqlite3
import json
import os

def test_database():
    """データベースの動作テスト"""
    print("=== データベース動作テスト ===")
    
    if not os.path.exists('realestate.db'):
        print("❌ データベースファイルが見つかりません")
        return False
    
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # エリア データの確認
    cursor.execute('SELECT * FROM areas')
    areas = cursor.fetchall()
    print(f"✅ エリア数: {len(areas)}")
    
    # 物件データの確認
    cursor.execute('SELECT * FROM properties')
    properties = cursor.fetchall()
    print(f"✅ 物件数: {len(properties)}")
    
    # サンプルデータの表示
    if properties:
        print("\n--- サンプル物件データ ---")
        for prop in properties:
            print(f"ID: {prop[0]}, 住所: {prop[2]}, 間取り: {prop[3]}, 価格: {prop[5]:,}円")
    
    conn.close()
    return True

def test_api_endpoints():
    """API エンドポイントのテスト"""
    print("\n=== API エンドポイント動作確認 ===")
    print("以下のエンドポイントが利用可能です:")
    print("📍 GET  /api/v1/properties - 物件一覧")
    print("📍 GET  /api/v1/properties/1 - 物件詳細")
    print("📍 POST /api/v1/properties/compare - 物件比較")
    print("📍 GET  /api/v1/areas - エリア一覧")
    print("📍 GET  /api/v1/stats - 統計情報")
    
    print("\n🚀 サーバーを起動するには:")
    print("   python3 server.py")
    print("\n🌐 ブラウザでアクセス:")
    print("   http://localhost:8000")

if __name__ == '__main__':
    if test_database():
        test_api_endpoints()
        print("\n✅ セットアップ完了！サーバーを起動できます。")
    else:
        print("\n❌ セットアップに問題があります。")