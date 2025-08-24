#!/usr/bin/env python
"""
エラースキップ時のログ出力確認（簡易版）
"""
import os
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')

from sqlalchemy import text
from backend.app.database import SessionLocal
import logging
from datetime import datetime

# ログ設定
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('backend.app.scrapers.base_scraper')

def test_skip_conditions():
    """スキップ条件とログ出力を確認"""
    
    session = SessionLocal()
    
    print("=== エラースキップ時のログ出力確認 ===\n")
    
    # 1. 404エラーでスキップされる物件を確認
    print("1. 404エラーによるスキップ:")
    result = session.execute(text("""
        SELECT url, source_site, error_count, last_error_at,
               CASE 
                   WHEN error_count <= 1 THEN 2
                   WHEN error_count <= 3 THEN 24
                   WHEN error_count <= 5 THEN 72
                   ELSE 168
               END as retry_hours
        FROM url_404_retries
        WHERE 
            (error_count <= 1 AND (NOW() - last_error_at) < INTERVAL '2 hours') OR
            (error_count > 1 AND error_count <= 3 AND (NOW() - last_error_at) < INTERVAL '1 day') OR
            (error_count > 3 AND error_count <= 5 AND (NOW() - last_error_at) < INTERVAL '3 days') OR
            (error_count > 5 AND (NOW() - last_error_at) < INTERVAL '7 days')
        LIMIT 3
    """))
    
    for row in result:
        url, source_site, error_count, last_error_at, retry_hours = row
        hours_since = (datetime.now() - last_error_at).total_seconds() / 3600
        
        # 実際のログと同じメッセージを出力
        logger.warning(
            f"404エラー履歴によりスキップ: {url} "
            f"(エラー回数: {error_count}, "
            f"最終エラーから: {hours_since:.1f}時間, "
            f"再試行間隔: {retry_hours}時間)"
        )
        logger.warning(
            f"404エラー履歴により詳細取得をスキップ: {url} "
            f"(物件ID: 不明)"
        )
    
    # 2. 価格不一致でスキップされる物件を確認
    print("\n2. 価格不一致によるスキップ:")
    result = session.execute(text("""
        SELECT site_property_id, source_site, retry_count, attempted_at,
               CASE 
                   WHEN retry_count <= 1 THEN 2
                   WHEN retry_count <= 3 THEN 24
                   WHEN retry_count <= 5 THEN 72
                   ELSE 168
               END as retry_hours
        FROM price_mismatch_history
        WHERE is_resolved = false AND
            ((retry_count <= 1 AND (NOW() - attempted_at) < INTERVAL '2 hours') OR
             (retry_count > 1 AND retry_count <= 3 AND (NOW() - attempted_at) < INTERVAL '1 day') OR
             (retry_count > 3 AND retry_count <= 5 AND (NOW() - attempted_at) < INTERVAL '3 days') OR
             (retry_count > 5 AND (NOW() - attempted_at) < INTERVAL '7 days'))
        LIMIT 3
    """))
    
    for row in result:
        site_property_id, source_site, retry_count, attempted_at, retry_hours = row
        hours_since = (datetime.now() - attempted_at).total_seconds() / 3600
        
        # 実際のログと同じメッセージを出力
        logger.warning(
            f"価格不一致履歴によりスキップ: ID={site_property_id} "
            f"(エラー回数: {retry_count}, "
            f"最終エラーから: {hours_since:.1f}時間, "
            f"再試行間隔: {retry_hours}時間)"
        )
        logger.warning(
            f"価格不一致エラー履歴により詳細取得をスキップ: (URLは物件による) "
            f"(物件ID: {site_property_id})"
        )
    
    # 3. 検証エラーでスキップされる物件を確認
    print("\n3. 検証エラーによるスキップ:")
    result = session.execute(text("""
        SELECT url, source_site, error_type, error_count, last_error_at,
               CASE 
                   WHEN error_count <= 1 THEN 2
                   WHEN error_count <= 3 THEN 24
                   WHEN error_count <= 5 THEN 72
                   ELSE 168
               END as retry_hours
        FROM property_validation_errors
        WHERE 
            (error_count <= 1 AND (NOW() - last_error_at) < INTERVAL '2 hours') OR
            (error_count > 1 AND error_count <= 3 AND (NOW() - last_error_at) < INTERVAL '1 day') OR
            (error_count > 3 AND error_count <= 5 AND (NOW() - last_error_at) < INTERVAL '3 days') OR
            (error_count > 5 AND (NOW() - last_error_at) < INTERVAL '7 days')
        LIMIT 3
    """))
    
    for row in result:
        url, source_site, error_type, error_count, last_error_at, retry_hours = row
        hours_since = (datetime.now() - last_error_at).total_seconds() / 3600
        
        # 実際のログと同じメッセージを出力
        logger.warning(
            f"検証エラー履歴によりスキップ: {url} "
            f"(エラータイプ: {error_type}, "
            f"エラー回数: {error_count}, "
            f"最終エラーから: {hours_since:.1f}時間, "
            f"再試行間隔: {retry_hours}時間)"
        )
        logger.warning(
            f"検証エラー履歴により詳細取得をスキップ: {url} "
            f"(物件ID: 不明)"
        )
    
    session.close()
    
    print("\n=== まとめ ===")
    print("上記のWARNINGログが実際のスクレイピング実行時に出力されます。")
    print("これらの物件は指定された期間、詳細ページの取得がスキップされます。")
    print("\n段階的な再試行間隔:")
    print("  エラー1回目: 2時間後に再試行")
    print("  エラー2-3回目: 1日後に再試行")
    print("  エラー4-5回目: 3日後に再試行")
    print("  エラー6回目以降: 7日後に再試行")

if __name__ == "__main__":
    test_skip_conditions()