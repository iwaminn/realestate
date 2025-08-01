#!/usr/bin/env python3
"""
ノムコムの詳細スキップ問題を調査
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.database import SessionLocal
from backend.app.models import PropertyListing

# 強制詳細取得モードでスクレイパーを作成
scraper = NomuScraper(force_detail_fetch=True)
print(f"スクレイパーの設定:")
print(f"  force_detail_fetch: {scraper.force_detail_fetch}")
print(f"  enable_smart_scraping: {scraper.enable_smart_scraping}")
print(f"  detail_refetch_days: {scraper.detail_refetch_days}")

# データベースセッションを作成
db = SessionLocal()

# 既存のノムコム物件を1件取得
existing_listing = db.query(PropertyListing).filter(
    PropertyListing.source_site == 'nomu',
    PropertyListing.is_active == True
).first()

if existing_listing:
    print(f"\n既存物件の確認:")
    print(f"  ID: {existing_listing.site_property_id}")
    print(f"  建物名: {existing_listing.master_property.building.normalized_name}")
    print(f"  価格: {existing_listing.current_price}万円")
    print(f"  詳細取得日: {existing_listing.detail_fetched_at}")
    
    # テスト用の物件データ（既存物件と同じ）
    test_data = {
        'url': existing_listing.url,
        'site_property_id': existing_listing.site_property_id,
        'price': existing_listing.current_price,  # 同じ価格
        'building_name': existing_listing.master_property.building.normalized_name,
        'address': existing_listing.master_property.building.address,
        'layout': existing_listing.master_property.layout,
        'area': float(existing_listing.master_property.area),
        'floor_number': existing_listing.master_property.floor_number
    }
    
    print(f"\nprocess_property_dataを実行...")
    # process_property_dataを実行
    result = scraper.process_property_data(test_data, existing_listing)
    print(f"結果: {result}")
    
    # property_dataの内容を確認
    print(f"\nプロパティデータの確認:")
    print(f"  detail_fetched: {test_data.get('detail_fetched', '未設定')}")
    print(f"  detail_fetch_attempted: {test_data.get('detail_fetch_attempted', '未設定')}")
    print(f"  update_type: {test_data.get('update_type', '未設定')}")

db.close()