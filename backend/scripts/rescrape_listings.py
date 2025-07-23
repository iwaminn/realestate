#!/usr/bin/env python3
"""
既存の掲載情報を再スクレイピングするスクリプト
掲載が終了した物件は削除フラグを立てる
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
from datetime import datetime
from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty
from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from sqlalchemy import func
import requests
from bs4 import BeautifulSoup
import time

def check_listing_exists(url: str) -> bool:
    """URLが有効かチェック（404エラーでないか確認）"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        
        # 404エラーまたはリダイレクトの場合は掲載終了と判断
        if response.status_code == 404:
            return False
            
        # ページの内容を確認（物件が見つからないメッセージがないか）
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # SUUMO特有の掲載終了パターン
        if 'suumo.jp' in url:
            if soup.find(string=lambda t: t and ('物件が見つかりませんでした' in t or '掲載終了' in t)):
                return False
                
        # HOMES特有の掲載終了パターン
        elif 'homes.co.jp' in url:
            if soup.find(string=lambda t: t and ('物件が見つかりません' in t or '掲載終了' in t)):
                return False
        
        return True
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return False

def rescrape_listings(source_site: str = None, limit: int = None):
    """既存の掲載情報を再スクレイピング"""
    session = SessionLocal()
    
    try:
        # アクティブな掲載を取得
        query = session.query(PropertyListing).filter(
            PropertyListing.is_active == True
        )
        
        if source_site:
            query = query.filter(PropertyListing.source_site == source_site)
            
        if limit:
            query = query.limit(limit)
            
        listings = query.all()
        
        print(f"=== 再スクレイピング開始 ===")
        print(f"対象: {len(listings)}件の掲載")
        
        # スクレイパーの準備
        scrapers = {
            'SUUMO': SuumoScraper(force_detail_fetch=True),
            'HOMES': HomesScraper(force_detail_fetch=True)
        }
        
        checked_count = 0
        delisted_count = 0
        updated_count = 0
        
        for i, listing in enumerate(listings, 1):
            print(f"\n[{i}/{len(listings)}] {listing.title}")
            print(f"  URL: {listing.url}")
            print(f"  サイト: {listing.source_site}")
            
            # URLの有効性をチェック
            if not check_listing_exists(listing.url):
                print(f"  → 掲載終了を検出")
                listing.is_active = False
                listing.delisted_at = datetime.now()
                delisted_count += 1
                
                # マスター物件の全掲載を確認
                master_property = listing.master_property
                active_listings = session.query(PropertyListing).filter(
                    PropertyListing.master_property_id == master_property.id,
                    PropertyListing.is_active == True,
                    PropertyListing.id != listing.id  # 現在処理中の掲載を除く
                ).count()
                
                if active_listings == 0:
                    print(f"  → マスター物件 {master_property.id} の全掲載が終了")
                
            else:
                # スクレイパーで詳細情報を再取得
                scraper = scrapers.get(listing.source_site)
                if scraper:
                    try:
                        # 詳細ページを解析
                        detail_data = scraper.parse_property_detail(listing.url)
                        
                        if detail_data:
                            # 価格が変更されている場合
                            if detail_data.get('price') and detail_data['price'] != listing.current_price:
                                print(f"  → 価格変更: {listing.current_price}万円 → {detail_data['price']}万円")
                                listing.current_price = detail_data['price']
                                updated_count += 1
                                
                            # その他の情報も更新
                            if detail_data.get('management_fee'):
                                listing.management_fee = detail_data['management_fee']
                            if detail_data.get('repair_fund'):
                                listing.repair_fund = detail_data['repair_fund']
                            if detail_data.get('agency_name'):
                                listing.agency_name = detail_data['agency_name']
                            if detail_data.get('agency_tel'):
                                listing.agency_tel = detail_data['agency_tel']
                            if detail_data.get('station_info'):
                                listing.station_info = detail_data['station_info']
                            if detail_data.get('remarks'):
                                listing.remarks = detail_data['remarks']
                            if detail_data.get('published_at') and not listing.published_at:
                                listing.published_at = detail_data['published_at']
                                
                            # 建物情報の更新
                            master_property = listing.master_property  # master_propertyを定義
                            building = master_property.building
                            detail_info = detail_data.get('detail_info', {})
                            
                            if detail_info.get('total_floors') and not building.total_floors:
                                building.total_floors = detail_info['total_floors']
                            if detail_info.get('basement_floors') is not None and not building.basement_floors:
                                building.basement_floors = detail_info['basement_floors']
                            if detail_info.get('land_rights') and not building.land_rights:
                                building.land_rights = detail_info['land_rights']
                            if detail_info.get('parking_info') and not building.parking_info:
                                building.parking_info = detail_info['parking_info']
                                
                            listing.last_scraped_at = datetime.now()
                            listing.last_fetched_at = datetime.now()
                            listing.detail_fetched_at = datetime.now()
                            
                            print(f"  → 情報を更新しました")
                        else:
                            print(f"  → 詳細情報の取得に失敗")
                            
                    except Exception as e:
                        print(f"  → エラー: {e}")
                        
            checked_count += 1
            
            # 10件ごとにコミット
            if checked_count % 10 == 0:
                session.commit()
                print(f"\n{checked_count}件処理済み...")
                
            # リクエスト間隔
            time.sleep(2)
        
        # 最終コミット
        session.commit()
        
        print(f"\n=== 再スクレイピング完了 ===")
        print(f"チェック済み: {checked_count}件")
        print(f"掲載終了: {delisted_count}件")
        print(f"情報更新: {updated_count}件")
        
        # 統計情報
        total_active = session.query(func.count(PropertyListing.id)).filter(
            PropertyListing.is_active == True
        ).scalar()
        
        total_delisted = session.query(func.count(PropertyListing.id)).filter(
            PropertyListing.is_active == False
        ).scalar()
        
        print(f"\n現在の状況:")
        print(f"  アクティブな掲載: {total_active}件")
        print(f"  掲載終了: {total_delisted}件")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def main():
    parser = argparse.ArgumentParser(description='既存の掲載情報を再スクレイピング')
    parser.add_argument('--site', choices=['SUUMO', 'HOMES'], help='特定のサイトのみ処理')
    parser.add_argument('--limit', type=int, help='処理する最大件数')
    
    args = parser.parse_args()
    
    rescrape_listings(source_site=args.site, limit=args.limit)

if __name__ == "__main__":
    main()