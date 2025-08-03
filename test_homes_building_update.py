#!/usr/bin/env python3
"""
HOMESの建物名更新が管理画面に正しく表示されるかテスト
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 環境変数を設定
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.scrapers.homes_scraper import HomesScraper
from backend.scripts.run_scrapers import run_single_scraper
import json

def test_homes_building_update():
    """管理画面のようにスクレイピングを実行してログを確認"""
    try:
        # 単一のスクレイパーを実行（1ページのみ）
        result = run_single_scraper(
            scraper_name='homes',
            area='港区',
            max_pages=1,
            max_properties=5,
            force_detail_fetch=True
        )
        
        print(f"\nスクレイピング結果:")
        print(f"Status: {result['status']}")
        print(f"Properties processed: {result['properties_processed']}")
        
        # ログを確認
        if 'logs' in result:
            print(f"\n物件更新履歴（{len(result['logs'])}件）:")
            for log in result['logs'][:10]:  # 最初の10件のみ表示
                print(f"\n[{log['timestamp']}] {log['message']}")
                if 'update_details' in log:
                    print(f"  更新内容: {log['update_details']}")
                    
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_homes_building_update()