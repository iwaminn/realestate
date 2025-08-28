#!/usr/bin/env python3
"""
部分的必須フィールドの仕組みのテスト
"""

import os
import sys

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DATABASE_URL'] = "postgresql://realestate:realestate_pass@localhost:5432/realestate"

from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.livable_scraper import LivableScraper
from backend.app.scrapers.suumo_scraper import SuumoScraper

def test_partial_required_fields():
    """各スクレイパーの部分的必須フィールド設定をテスト"""
    
    print("=== 部分的必須フィールドのテスト ===\n")
    
    # SUUMO
    suumo = SuumoScraper()
    print("SUUMO:")
    print(f"  必須フィールド: {suumo.get_required_detail_fields()}")
    print(f"  オプショナル必須フィールド: {suumo.get_optional_required_fields()}")
    print(f"  部分的必須フィールド: {suumo.get_partial_required_fields()}")
    print()
    
    # HOMES
    homes = HomesScraper()
    print("HOMES:")
    print(f"  必須フィールド: {homes.get_required_detail_fields()}")
    print(f"  オプショナル必須フィールド: {homes.get_optional_required_fields()}")
    print(f"  部分的必須フィールド: {homes.get_partial_required_fields()}")
    print()
    
    # Livable
    livable = LivableScraper()
    print("Livable:")
    print(f"  必須フィールド: {livable.get_required_detail_fields()}")
    print(f"  オプショナル必須フィールド: {livable.get_optional_required_fields()}")
    print(f"  部分的必須フィールド: {livable.get_partial_required_fields()}")
    print()
    
    # 部分的必須フィールドのチェックロジックをテスト
    print("=== 部分的必須フィールドのチェックロジックテスト ===\n")
    
    # HOMESで間取りが取れない物件をシミュレート
    test_property_data = {
        'site_property_id': 'test123',
        'price': 5000,
        'building_name': 'テストマンション',
        'address': '東京都港区テスト',
        'area': 75.5,
        'built_year': 2010,
        'layout': '-'  # 空の値
    }
    
    # validate_property_dataの処理（簡易版）
    print("HOMESで間取りが'-'の場合の処理:")
    partial_required = homes.get_partial_required_fields()
    if 'layout' in partial_required:
        config = partial_required['layout']
        if test_property_data.get('layout') in config['empty_values']:
            print(f"  間取りが空値（{test_property_data['layout']}）として検出されました")
            print(f"  最大許容欠損率: {config['max_missing_rate']*100}%")
            print(f"  最小サンプル数: {config['min_sample_size']}件")
            # 実際の処理では統計を更新してエラー率をチェック
    print()

if __name__ == "__main__":
    test_partial_required_fields()