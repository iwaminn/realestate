#!/usr/bin/env python
"""
エラースキップ時のログ出力確認スクリプト
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')

from sqlalchemy import create_engine, text
from backend.app.database import SessionLocal, engine

def setup_test_data():
    """テスト用のエラーデータをセットアップ"""
    
    session = SessionLocal()
    
    print("=== エラースキップログ確認用データのセットアップ ===\n")
    
    # 1. 404エラーのテストデータ
    print("1. 404エラーのテストデータを追加...")
    session.execute(text("""
        INSERT INTO url_404_retries 
        (url, source_site, first_error_at, last_error_at, error_count)
        VALUES 
        ('https://test.suumo.jp/property/404test', 'SUUMO', NOW() - INTERVAL '1 hour', NOW() - INTERVAL '1 hour', 1)
        ON CONFLICT (url, source_site) 
        DO UPDATE SET 
            last_error_at = NOW() - INTERVAL '1 hour',
            error_count = 1
    """))
    
    # 2. 価格不一致のテストデータ（段階的）
    print("2. 価格不一致のテストデータを追加...")
    
    # エラー回数1回（2時間スキップ）
    session.execute(text("""
        INSERT INTO price_mismatch_history 
        (source_site, site_property_id, property_url, list_price, detail_price, 
         attempted_at, retry_count, is_resolved)
        VALUES 
        ('SUUMO', 'TEST_PRICE_001', 'https://test.suumo.jp/property/price001', 
         5000, 5100, NOW() - INTERVAL '30 minutes', 1, false)
        ON CONFLICT (source_site, site_property_id) 
        DO UPDATE SET 
            attempted_at = NOW() - INTERVAL '30 minutes',
            retry_count = 1,
            is_resolved = false
    """))
    
    # エラー回数3回（1日スキップ）
    session.execute(text("""
        INSERT INTO price_mismatch_history 
        (source_site, site_property_id, property_url, list_price, detail_price, 
         attempted_at, retry_count, is_resolved)
        VALUES 
        ('SUUMO', 'TEST_PRICE_003', 'https://test.suumo.jp/property/price003', 
         7000, 7200, NOW() - INTERVAL '6 hours', 3, false)
        ON CONFLICT (source_site, site_property_id) 
        DO UPDATE SET 
            attempted_at = NOW() - INTERVAL '6 hours',
            retry_count = 3,
            is_resolved = false
    """))
    
    # 3. 検証エラーのテストデータ
    print("3. 検証エラーのテストデータを追加...")
    session.execute(text("""
        INSERT INTO property_validation_errors 
        (url, source_site, site_property_id, error_type, error_details,
         first_error_at, last_error_at, error_count)
        VALUES 
        ('https://test.suumo.jp/property/validation001', 'SUUMO', 'TEST_VAL_001',
         'building_name_mismatch', '一覧: テストマンション, 詳細: テストレジデンス',
         NOW() - INTERVAL '45 minutes', NOW() - INTERVAL '45 minutes', 1)
        ON CONFLICT (url, source_site) 
        DO UPDATE SET 
            last_error_at = NOW() - INTERVAL '45 minutes',
            error_count = 1
    """))
    
    session.commit()
    session.close()
    print("\n✅ テストデータのセットアップ完了")
    
def test_skip_logging():
    """実際のスキップ処理を実行してログを確認"""
    
    print("\n=== スキップ判定とログ出力のテスト ===\n")
    
    from backend.app.scrapers.base_scraper import BaseScraper
    from backend.app.scrapers.constants import SourceSite
    from backend.app.database import SessionLocal
    import logging
    
    # ログレベルをINFO以上に設定（WARNING以上が表示される）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # SUUMOスクレイパーのインスタンスを作成
    class TestScraper(BaseScraper):
        def __init__(self):
            super().__init__(source_site=SourceSite.SUUMO)
            self.session = SessionLocal()
    
    scraper = TestScraper()
    
    print("1. 404エラーのスキップ判定:")
    url_404 = 'https://test.suumo.jp/property/404test'
    if scraper._should_skip_url_due_to_404(url_404):
        print(f"   → スキップされました: {url_404}")
    else:
        print(f"   → 再試行可能: {url_404}")
    
    print("\n2. 価格不一致のスキップ判定:")
    
    # エラー回数1回（2時間スキップ中）
    site_id_1 = 'TEST_PRICE_001'
    if scraper._should_skip_due_to_price_mismatch(site_id_1):
        print(f"   → スキップされました: {site_id_1} (エラー1回)")
    else:
        print(f"   → 再試行可能: {site_id_1}")
    
    # エラー回数3回（1日スキップ中）
    site_id_3 = 'TEST_PRICE_003'
    if scraper._should_skip_due_to_price_mismatch(site_id_3):
        print(f"   → スキップされました: {site_id_3} (エラー3回)")
    else:
        print(f"   → 再試行可能: {site_id_3}")
    
    print("\n3. 検証エラーのスキップ判定:")
    url_val = 'https://test.suumo.jp/property/validation001'
    if scraper._should_skip_url_due_to_validation_error(url_val):
        print(f"   → スキップされました: {url_val}")
    else:
        print(f"   → 再試行可能: {url_val}")
    
    scraper.session.close()
    print("\n✅ ログ出力テスト完了")
    print("\n※ 上記でWARNINGレベルのログが表示されていれば正常です")

if __name__ == "__main__":
    setup_test_data()
    test_skip_logging()