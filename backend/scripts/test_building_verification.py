#!/usr/bin/env python3
"""
建物属性検証メソッドのテストスクリプト
少なくとも2つの属性が一致する必要があることを確認
"""

import sys
import os

# Dockerコンテナ内のパスを追加
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/backend')

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.scrapers.suumo_scraper import SuumoScraper
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_verify_building_attributes():
    """_verify_building_attributes メソッドのテスト"""
    
    session = SessionLocal()
    
    # SuumoScraperを使用（BaseScraperの具体的な実装）
    scraper = SuumoScraper()
    scraper.session = session
    scraper.logger = logger
    
    # テスト用の建物オブジェクトを作成（実際にDBに保存はしない）
    test_building = Building(
        normalized_name="テストマンション",
        address="東京都港区テスト1-1-1",
        total_floors=10,
        built_year=2020,
        built_month=3,
        total_units=50
    )
    
    print("=" * 60)
    print("建物属性検証テスト")
    print("=" * 60)
    print(f"テスト建物: 総階数={test_building.total_floors}, 築年={test_building.built_year}, "
          f"築月={test_building.built_month}, 総戸数={test_building.total_units}")
    print("")
    
    # テストケース1: すべての属性が一致（3つ以上一致 → OK）
    print("テスト1: すべての属性が一致")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=10, 
        built_year=2020, 
        built_month=3,
        total_units=50
    )
    print(f"  結果: {result} (期待値: True)")
    assert result == True, "すべての属性が一致する場合はTrue"
    print("")
    
    # テストケース2: 2つの属性が一致（総階数と築年）→ OK
    print("テスト2: 総階数と築年が一致、総戸数がNULL")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=10, 
        built_year=2020,
        built_month=None,  # 築月はNULL
        total_units=None   # 総戸数はNULL
    )
    print(f"  結果: {result} (期待値: True)")
    assert result == True, "2つの属性が一致する場合はTrue"
    print("")
    
    # テストケース3: 1つの属性のみ一致（総階数のみ）→ NG
    print("テスト3: 総階数のみ一致")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=10, 
        built_year=None,
        built_month=None,
        total_units=None
    )
    print(f"  結果: {result} (期待値: False)")
    assert result == False, "1つの属性のみ一致する場合はFalse"
    print("")
    
    # テストケース4: 築年と築月の両方が一致（年月で1つとカウント）、総階数も一致 → OK
    print("テスト4: 築年月（年と月）と総階数が一致")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=10, 
        built_year=2020,
        built_month=3,     # 築月も一致
        total_units=None
    )
    print(f"  結果: {result} (期待値: True)")
    assert result == True, "築年月と総階数の2つが一致するのでTrue"
    print("")
    
    # テストケース5: 築年は一致するが築月が異なる → NG
    print("テスト5: 築年は一致するが築月が異なる")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=None, 
        built_year=2020,
        built_month=5,     # 築月が異なる（3月 vs 5月）
        total_units=None
    )
    print(f"  結果: {result} (期待値: False)")
    assert result == False, "築月が異なる場合はFalse"
    print("")
    
    # テストケース6: 総階数が異なる → NG
    print("テスト6: 総階数が異なる、他は一致")
    result = scraper._verify_building_attributes(
        test_building, 
        total_floors=15,   # 総階数が異なる（10 vs 15）
        built_year=2020,
        built_month=3,
        total_units=50
    )
    print(f"  結果: {result} (期待値: False)")
    assert result == False, "総階数が異なる場合はFalse"
    print("")
    
    # テストケース7: 既存建物の属性がNULLばかり → NG
    null_building = Building(
        normalized_name="属性なしマンション",
        address="東京都港区テスト2-2-2",
        total_floors=None,
        built_year=None,
        built_month=None,
        total_units=None
    )
    print("テスト7: 既存建物の属性がすべてNULL")
    result = scraper._verify_building_attributes(
        null_building, 
        total_floors=10, 
        built_year=2020,
        built_month=3,
        total_units=50
    )
    print(f"  結果: {result} (期待値: False)")
    assert result == False, "比較可能な属性がない場合はFalse"
    print("")
    
    print("=" * 60)
    print("すべてのテストが成功しました！")
    print("=" * 60)
    
    session.close()

if __name__ == "__main__":
    test_verify_building_attributes()