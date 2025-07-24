#!/usr/bin/env python3
"""
LIFULL HOME'Sスクレイパーの完全テスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper import HomesScraper

def test_scrape_area():
    """scrape_areaメソッドをテスト（1ページのみ）"""
    print("=== LIFULL HOME'S scrape_areaテスト ===\n")
    
    scraper = HomesScraper()
    
    # エラーハンドリングを一時的に緩和
    import os
    os.environ['SCRAPER_ERROR_THRESHOLD'] = '0.9'  # 90%まで許容
    os.environ['SCRAPER_CONSECUTIVE_ERROR_LIMIT'] = '50'  # 連続エラー50件まで許容
    
    print("港区の物件を1ページ分スクレイピング...")
    
    # 1ページのみスクレイピング
    try:
        scraper.scrape_area("港区", max_pages=1)
        print("\n✓ スクレイピング完了")
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    # エラー統計を表示
    print(f"\nエラー統計:")
    print(f"  総試行数: {scraper.error_stats['total_attempts']}")
    print(f"  総エラー数: {scraper.error_stats['total_errors']}")
    if scraper.error_stats['total_attempts'] > 0:
        error_rate = scraper.error_stats['total_errors'] / scraper.error_stats['total_attempts']
        print(f"  エラー率: {error_rate:.2%}")
    
    # 成功統計も表示
    print(f"\n成功統計:")
    print(f"  価格なし: {scraper._stats.get('price_missing', 0)}")
    print(f"  建物情報なし: {scraper._stats.get('building_info_missing', 0)}")
    print(f"  詳細取得失敗: {scraper._stats.get('detail_fetch_failed', 0)}")


def main():
    try:
        test_scrape_area()
    except Exception as e:
        print(f"予期しないエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()