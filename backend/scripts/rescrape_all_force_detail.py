#!/usr/bin/env python3
"""
全サイトの全エリアを強制詳細取得モードで再スクレイピング
listing_building_nameを更新するため
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper
from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.scrapers.livable_scraper import LivableScraper
from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from sqlalchemy import func
import time

# 東京23区のエリアリスト
TOKYO_23_AREAS = [
    '千代田区', '中央区', '港区', '新宿区', '文京区', '台東区',
    '墨田区', '江東区', '品川区', '目黒区', '大田区', '世田谷区',
    '渋谷区', '中野区', '杉並区', '豊島区', '北区', '荒川区',
    '板橋区', '練馬区', '足立区', '葛飾区', '江戸川区'
]

def main():
    # スクレイパーの設定
    scrapers = {
        'SUUMO': SuumoScraper,
        'LIFULL HOME\'S': HomesScraper,
        '三井のリハウス': RehouseScraper,
        'ノムコム': NomuScraper,
        '東急リバブル': LivableScraper
    }
    
    # 処理上限数を設定（各エリア・各サイトごと）
    max_properties_per_area = 100
    
    print(f"=== 強制詳細取得モードで再スクレイピング開始 ===")
    print(f"対象エリア: {len(TOKYO_23_AREAS)}区")
    print(f"対象サイト: {len(scrapers)}サイト")
    print(f"各エリアの処理上限: {max_properties_per_area}件")
    print("")
    
    # 開始前の状況を確認
    db = SessionLocal()
    try:
        total_listings = db.query(func.count()).select_from(
            db.query(db.raw_query.PropertyListing).filter_by(is_active=True).subquery()
        ).scalar()
        listings_with_name = db.query(func.count()).select_from(
            db.query(db.raw_query.PropertyListing).filter(
                db.raw_query.PropertyListing.is_active == True,
                db.raw_query.PropertyListing.listing_building_name != None
            ).subquery()
        ).scalar()
        
        print(f"開始前の状況:")
        print(f"  アクティブな掲載情報: {total_listings}件")
        print(f"  listing_building_name設定済み: {listings_with_name}件")
        print("")
    finally:
        db.close()
    
    total_processed = 0
    total_errors = 0
    
    # 各スクレイパーで各エリアを処理
    for scraper_name, scraper_class in scrapers.items():
        print(f"\n--- {scraper_name} ---")
        
        for area in TOKYO_23_AREAS:
            print(f"\n{scraper_name} - {area}:")
            
            try:
                # 強制詳細取得モードでスクレイパーを作成
                scraper = scraper_class(
                    force_detail_fetch=True,
                    max_properties=max_properties_per_area
                )
                
                # スクレイピング実行
                start_time = time.time()
                result = scraper.scrape_area(area)
                elapsed_time = time.time() - start_time
                
                # 結果を表示
                if result:
                    print(f"  完了: {result}件処理 ({elapsed_time:.1f}秒)")
                    total_processed += result
                else:
                    print(f"  スキップまたはエラー")
                
                # 負荷軽減のため少し待機
                time.sleep(2)
                
            except Exception as e:
                print(f"  エラー: {e}")
                total_errors += 1
                continue
    
    print(f"\n=== 再スクレイピング完了 ===")
    print(f"処理件数: {total_processed}件")
    print(f"エラー数: {total_errors}件")
    
    # 終了後の状況を確認
    db = SessionLocal()
    try:
        total_listings = db.query(func.count()).select_from(
            db.query(db.raw_query.PropertyListing).filter_by(is_active=True).subquery()
        ).scalar()
        listings_with_name = db.query(func.count()).select_from(
            db.query(db.raw_query.PropertyListing).filter(
                db.raw_query.PropertyListing.is_active == True,
                db.raw_query.PropertyListing.listing_building_name != None
            ).subquery()
        ).scalar()
        
        properties_with_display_name = db.query(func.count()).select_from(
            db.query(db.raw_query.MasterProperty).filter(
                db.raw_query.MasterProperty.display_building_name != None
            ).subquery()
        ).scalar()
        
        print(f"\n終了後の状況:")
        print(f"  アクティブな掲載情報: {total_listings}件")
        print(f"  listing_building_name設定済み: {listings_with_name}件")
        print(f"  display_building_name設定済み物件: {properties_with_display_name}件")
    finally:
        db.close()

if __name__ == "__main__":
    main()