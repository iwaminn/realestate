#!/usr/bin/env python3
"""
LIFULL HOME'Sスクレイパーの単体テスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper import HomesScraper

def test_single_property():
    """単一物件のスクレイピングをテスト"""
    print("=== LIFULL HOME'S 単体テスト ===\n")
    
    scraper = HomesScraper()
    
    # 一覧ページから最初の物件を取得
    list_url = scraper.get_search_url("港区", page=1)
    print(f"一覧ページURL: {list_url}")
    
    soup = scraper.fetch_page(list_url)
    if not soup:
        print("エラー: 一覧ページの取得に失敗しました")
        return
    
    properties = scraper.parse_property_list(soup)
    print(f"一覧ページから{len(properties)}件の物件を取得\n")
    
    if not properties:
        print("エラー: 物件が見つかりませんでした")
        return
    
    # 最初の物件を詳細取得
    test_property = properties[0]
    print(f"テスト物件:")
    print(f"  URL: {test_property.get('url')}")
    print(f"  建物名: {test_property.get('building_name', '不明')}")
    print(f"  サイトID: {test_property.get('site_property_id', '不明')}")
    
    # save_propertyメソッドを実行
    print("\nsave_propertyメソッドを実行...")
    
    # エラーを確認するため、詳細にログを出力
    try:
        scraper.save_property(test_property)
        print("✓ 正常に完了しました")
    except Exception as e:
        print(f"✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    # エラー統計を表示
    print(f"\nエラー統計:")
    print(f"  総試行数: {scraper.error_stats['total_attempts']}")
    print(f"  総エラー数: {scraper.error_stats['total_errors']}")
    print(f"  エラー率: {scraper.error_rate:.2%}")
    
    # セッションをコミット
    scraper.session.commit()
    print("\n完了")


def main():
    try:
        test_single_property()
    except Exception as e:
        print(f"予期しないエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()