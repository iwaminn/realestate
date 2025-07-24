#!/usr/bin/env python3
"""
datetime JSONシリアライズのテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.utils.scraper_error_logger import ScraperErrorLogger
from datetime import datetime

def test_datetime_serialization():
    """datetimeオブジェクトを含むエラーログのテスト"""
    print("=== DateTime JSONシリアライズテスト ===\n")
    
    logger = ScraperErrorLogger("TEST")
    
    # datetimeオブジェクトを含むproperty_data
    property_data = {
        "url": "https://example.com/property/123",
        "building_name": "テストマンション",
        "price": 5000,
        "published_at": datetime.now(),  # datetimeオブジェクト
        "first_published_at": datetime(2025, 1, 1),  # datetimeオブジェクト
        "area": 75.5,
        "layout": "3LDK"
    }
    
    print("テストデータ:")
    for key, value in property_data.items():
        print(f"  {key}: {value} (type: {type(value).__name__})")
    
    print("\nエラーログに記録...")
    
    try:
        logger.log_property_error(
            error_type="test",
            url=property_data["url"],
            building_name=property_data["building_name"],
            property_data=property_data,
            error=ValueError("テストエラー"),
            phase="test_phase"
        )
        print("✓ 正常に記録されました")
    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    # ログファイルの内容を確認
    import json
    log_path = os.path.join("logs", "scraper_errors.json")
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            if logs:
                latest_log = logs[-1]
                print(f"\n最新のログエントリ:")
                print(f"  タイムスタンプ: {latest_log.get('timestamp')}")
                print(f"  エラータイプ: {latest_log.get('error_type')}")
                if 'property_data' in latest_log and latest_log['property_data']:
                    print(f"  published_at: {latest_log['property_data'].get('published_at')}")
                    print(f"  first_published_at: {latest_log['property_data'].get('first_published_at')}")


def main():
    try:
        test_datetime_serialization()
    except Exception as e:
        print(f"予期しないエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()