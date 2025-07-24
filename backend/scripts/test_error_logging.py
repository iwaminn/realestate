#!/usr/bin/env python3
"""
エラーログ機能のテストスクリプト
実際にエラーを発生させて、ログが正しく記録されることを確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.utils.scraper_error_logger import ScraperErrorLogger
from datetime import datetime
import time


def test_error_logging():
    """エラーログ機能をテスト"""
    print("エラーログ機能のテストを開始します...")
    
    # テスト用のロガーを作成
    logger = ScraperErrorLogger("test_scraper")
    
    # 1. 物件エラーのテスト
    print("\n1. 物件エラーのテスト")
    logger.log_property_error(
        error_type="validation",
        url="https://example.com/property/12345",
        building_name="テストマンション",
        property_data={
            "building_name": "テストマンション",
            "price": None,  # 価格が欠落
            "area": 65.5,
            "layout": "2LDK"
        },
        error=ValueError("価格が取得できませんでした"),
        phase="price_validation"
    )
    print("  → 物件エラーを記録しました")
    
    # 2. パースエラーのテスト
    print("\n2. パースエラーのテスト")
    logger.log_parsing_error(
        url="https://example.com/property/67890",
        missing_selectors=[".price-info", ".building-name", ".property-details"],
        found_selectors={
            "price": False,
            "building_name": False,
            "area": True,
            "layout": True
        },
        html_snippet="<div class='property'>...</div>"
    )
    print("  → パースエラーを記録しました")
    
    # 3. バリデーションエラーのテスト
    print("\n3. バリデーションエラーのテスト")
    logger.log_validation_error(
        property_data={
            "url": "https://example.com/property/11111",
            "building_name": "",  # 空の建物名
            "price": -1000,  # 負の価格
            "area": 5,  # 小さすぎる面積
            "layout": "XXXXXXX"  # 長すぎる間取り
        },
        validation_errors=[
            "建物名が空です",
            "価格が無効です（負の値）",
            "面積が小さすぎます（10㎡未満）",
            "間取りが無効な形式です"
        ],
        url="https://example.com/property/11111"
    )
    print("  → バリデーションエラーを記録しました")
    
    # 4. サーキットブレーカー作動のテスト
    print("\n4. サーキットブレーカー作動のテスト")
    logger.log_circuit_breaker_activation(
        error_rate=0.75,
        total_errors=75,
        total_attempts=100,
        consecutive_errors=15
    )
    print("  → サーキットブレーカー作動を記録しました")
    
    # 5. 複数のエラーを連続で記録（実際の使用パターンをシミュレート）
    print("\n5. 実際の使用パターンのシミュレーション")
    test_urls = [
        "https://example.com/property/A001",
        "https://example.com/property/A002",
        "https://example.com/property/A003",
    ]
    
    for i, url in enumerate(test_urls):
        time.sleep(0.1)  # 少し間隔をあける
        logger.log_property_error(
            error_type="detail_page",
            url=url,
            building_name=f"テストビル{i+1}",
            error=Exception(f"詳細ページの取得に失敗しました: {url}"),
            phase="parse_property_detail"
        )
    print(f"  → {len(test_urls)}件の詳細ページエラーを記録しました")
    
    # 6. エラーサマリーの取得
    print("\n6. エラーサマリーの取得")
    summary = logger.get_error_summary(hours=1)
    print(f"  → 過去1時間のエラー数: {summary['total_errors']}")
    print(f"  → エラータイプ別: {summary['error_types']}")
    
    # 7. セレクタ変更の検出
    print("\n7. セレクタ変更の検出テスト")
    # 同じセレクタが繰り返し失敗するケースをシミュレート
    for i in range(12):
        logger.log_parsing_error(
            url=f"https://example.com/property/SEL{i:03d}",
            missing_selectors=[".new-price-class", ".new-building-class"],
            found_selectors={
                "old_price": False,
                "old_building": False,
                "area": True
            }
        )
    
    problematic_selectors = logger.check_selector_changes()
    print(f"  → 問題のあるセレクタ数: {len(problematic_selectors)}")
    for selector_info in problematic_selectors:
        print(f"    - {selector_info['selector']}: {selector_info['error_count']}回失敗")
        if selector_info['possible_change']:
            print(f"      ⚠️ サイト構造が変更された可能性があります")
    
    print("\n✅ すべてのテストが完了しました")
    print(f"エラーログは logs/scraper_errors.json に保存されています")


if __name__ == "__main__":
    test_error_logging()