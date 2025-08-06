#!/usr/bin/env python3
"""統合履歴を使った建物マッチングのテスト"""

import os
import sys
sys.path.append('/home/ubuntu/realestate')

# 環境変数設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.scrapers.base_scraper import BaseScraper
from backend.app.models import Building, BuildingMergeHistory

def test_building_matching():
    """統合履歴を使った建物マッチングをテスト"""
    
    # セッション作成
    session = SessionLocal()
    
    # BaseScraper のインスタンスを作成（テスト用）
    class TestScraper(BaseScraper):
        def __init__(self):
            super().__init__("test")
            self.session = session
    
    scraper = TestScraper()
    
    print("=== 統合履歴を使った建物マッチングのテスト ===\n")
    
    # テスト1: 統合された建物名で検索
    print("テスト1: 統合された建物名「パークコート麻布十番」で検索")
    print("期待結果: 「パークコート麻布十番ザ・タワー」が見つかる\n")
    
    # get_or_create_buildingメソッドを呼び出し
    building, room_number = scraper.get_or_create_building(
        building_name="パークコート麻布十番",
        address="東京都港区三田１"
    )
    
    if building:
        print(f"✅ 建物が見つかりました:")
        print(f"  ID: {building.id}")
        print(f"  名前: {building.normalized_name}")
        print(f"  住所: {building.address}")
        
        if building.normalized_name == "パークコート麻布十番ザ・タワー":
            print("\n✅ 統合履歴が正しく機能しています！")
            print("  「パークコート麻布十番」→「パークコート麻布十番ザ・タワー」にマッチしました")
        else:
            print("\n❌ 期待と異なる建物が返されました")
    else:
        print("❌ 建物が見つかりませんでした（新規作成になる）")
    
    # テスト2: 統合履歴にない建物名で検索
    print("\n" + "="*50)
    print("\nテスト2: 統合履歴にない建物名「テストマンション」で検索")
    print("期待結果: 建物が見つからない（新規作成になる）\n")
    
    building2, room_number2 = scraper.get_or_create_building(
        building_name="テストマンション",
        address="東京都港区三田１"
    )
    
    if building2:
        if building2.normalized_name == "テストマンション":
            print(f"新規建物として作成されました:")
            print(f"  ID: {building2.id}")
            print(f"  名前: {building2.normalized_name}")
            # ロールバック（テストデータを残さない）
            session.rollback()
            print("\n（テストデータはロールバックしました）")
        else:
            print(f"❌ 既存の建物が返されました: {building2.normalized_name}")
    else:
        print("✅ 建物が見つかりませんでした（期待通り）")
    
    session.close()
    print("\n=== テスト完了 ===")

if __name__ == "__main__":
    test_building_matching()