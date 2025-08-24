#!/usr/bin/env python
"""
エラースキップ機能の動作確認スクリプト
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
from backend.app.database import SessionLocal

def test_error_skip():
    """エラースキップ機能をテスト"""
    
    session = SessionLocal()
    
    print("=== エラースキップ機能のテスト ===\n")
    
    # 1. 404エラーの確認
    print("1. 404エラー履歴:")
    result = session.execute(text("""
        SELECT url, source_site, error_count, last_error_at,
               CASE 
                   WHEN error_count <= 1 THEN '2時間後'
                   WHEN error_count <= 3 THEN '1日後'
                   WHEN error_count <= 5 THEN '3日後'
                   ELSE '7日後'
               END as retry_interval,
               CASE
                   WHEN error_count <= 1 AND (NOW() - last_error_at) < INTERVAL '2 hours' THEN 'スキップ'
                   WHEN error_count <= 3 AND (NOW() - last_error_at) < INTERVAL '1 day' THEN 'スキップ'
                   WHEN error_count <= 5 AND (NOW() - last_error_at) < INTERVAL '3 days' THEN 'スキップ'
                   WHEN error_count > 5 AND (NOW() - last_error_at) < INTERVAL '7 days' THEN 'スキップ'
                   ELSE '再試行可能'
               END as status
        FROM url_404_retries
        ORDER BY last_error_at DESC
        LIMIT 5
    """))
    
    for row in result:
        print(f"   URL: {row[0][:50]}...")
        print(f"   サイト: {row[1]}, エラー回数: {row[2]}")
        print(f"   最終エラー: {row[3]}, 再試行間隔: {row[4]}, 状態: {row[5]}")
        print()
    
    # 2. 価格不一致エラーの確認
    print("\n2. 価格不一致履歴:")
    result = session.execute(text("""
        SELECT site_property_id, source_site, list_price, detail_price,
               attempted_at, retry_count,
               CASE 
                   WHEN retry_count <= 1 THEN '2時間後'
                   WHEN retry_count <= 3 THEN '1日後'
                   WHEN retry_count <= 5 THEN '3日後'
                   ELSE '7日後'
               END as retry_interval,
               CASE
                   WHEN retry_count <= 1 AND (NOW() - attempted_at) < INTERVAL '2 hours' THEN 'スキップ'
                   WHEN retry_count <= 3 AND (NOW() - attempted_at) < INTERVAL '1 day' THEN 'スキップ'
                   WHEN retry_count <= 5 AND (NOW() - attempted_at) < INTERVAL '3 days' THEN 'スキップ'
                   WHEN retry_count > 5 AND (NOW() - attempted_at) < INTERVAL '7 days' THEN 'スキップ'
                   ELSE '再試行可能'
               END as status
        FROM price_mismatch_history
        WHERE is_resolved = false
        ORDER BY attempted_at DESC
        LIMIT 5
    """))
    
    for row in result:
        print(f"   物件ID: {row[0]}")
        print(f"   サイト: {row[1]}, 一覧価格: {row[2]}万円, 詳細価格: {row[3]}万円")
        print(f"   検出日時: {row[4]}, エラー回数: {row[5]}")
        print(f"   再試行間隔: {row[6]}, 状態: {row[7]}")
        print()
    
    # 3. 検証エラーの確認
    print("\n3. 検証エラー履歴:")
    result = session.execute(text("""
        SELECT url, source_site, error_type, error_count, last_error_at,
               CASE 
                   WHEN error_count <= 1 THEN '2時間後'
                   WHEN error_count <= 3 THEN '1日後'
                   WHEN error_count <= 5 THEN '3日後'
                   ELSE '7日後'
               END as retry_interval,
               CASE
                   WHEN error_count <= 1 AND (NOW() - last_error_at) < INTERVAL '2 hours' THEN 'スキップ'
                   WHEN error_count <= 3 AND (NOW() - last_error_at) < INTERVAL '1 day' THEN 'スキップ'
                   WHEN error_count <= 5 AND (NOW() - last_error_at) < INTERVAL '3 days' THEN 'スキップ'
                   WHEN error_count > 5 AND (NOW() - last_error_at) < INTERVAL '7 days' THEN 'スキップ'
                   ELSE '再試行可能'
               END as status
        FROM property_validation_errors
        ORDER BY last_error_at DESC
        LIMIT 5
    """))
    
    for row in result:
        print(f"   URL: {row[0][:50]}...")
        print(f"   サイト: {row[1]}, エラータイプ: {row[2]}")
        print(f"   エラー回数: {row[3]}, 最終エラー: {row[4]}")
        print(f"   再試行間隔: {row[5]}, 状態: {row[6]}")
        print()
    
    # 4. テストデータを追加（デモ用）
    print("\n4. テストデータを追加してスキップ動作を確認:")
    
    # 価格不一致のテストデータ
    test_site_id = "TEST_PROPERTY_001"
    test_url = "https://example.com/test/property001"
    
    # 既存のテストデータを削除
    session.execute(text("""
        DELETE FROM price_mismatch_history 
        WHERE site_property_id = :site_id AND source_site = 'TEST'
    """), {'site_id': test_site_id})
    
    # 新規テストデータを追加
    session.execute(text("""
        INSERT INTO price_mismatch_history 
        (source_site, site_property_id, property_url, list_price, detail_price, retry_after)
        VALUES ('TEST', :site_id, :url, 3000, 3100, NOW() + INTERVAL '1 day')
    """), {'site_id': test_site_id, 'url': test_url})
    
    session.commit()
    
    print(f"   → テスト物件を追加: {test_site_id}")
    print(f"     価格不一致: 一覧3000万円 vs 詳細3100万円")
    print(f"     再試行可能日時: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')}")
    
    # スキップ判定のシミュレーション
    print("\n   スキップ判定のシミュレーション:")
    
    # 価格不一致のスキップ判定（直接SQLで確認）
    result = session.execute(text("""
        SELECT 
            CASE 
                WHEN NOW() < retry_after THEN true
                ELSE false
            END as should_skip
        FROM price_mismatch_history
        WHERE site_property_id = :site_id AND source_site = 'TEST'
    """), {'site_id': test_site_id})
    
    should_skip = result.scalar()
    print(f"   価格不一致によるスキップ判定: {'スキップする' if should_skip else '再試行可能'}")
    
    session.close()
    print("\n✅ テスト完了")

if __name__ == "__main__":
    test_error_skip()