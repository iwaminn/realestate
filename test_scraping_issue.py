#!/usr/bin/env python3
"""
スクレイピングの問題を特定するためのテストスクリプト
"""

import sys
import os
import traceback
from datetime import datetime

# Pythonパスの設定
sys.path.insert(0, '/home/ubuntu/realestate/backend')

def test_database_connection():
    """データベース接続をテスト"""
    print("\n=== データベース接続テスト ===")
    try:
        from app.database import get_db_for_scraping, engine
        
        # 接続テスト
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print("✓ データベース接続成功")
            
        # セッション作成テスト
        session = get_db_for_scraping()
        print("✓ セッション作成成功")
        
        # トランザクションテスト
        session.begin()
        print("✓ トランザクション開始成功")
        
        session.rollback()
        print("✓ ロールバック成功")
        
        session.close()
        print("✓ セッションクローズ成功")
        
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        traceback.print_exc()
        return False

def test_building_creation():
    """建物作成処理をテスト"""
    print("\n=== 建物作成テスト ===")
    try:
        from app.database import get_db_for_scraping
        from app.models import Building
        
        session = get_db_for_scraping()
        
        # テスト用建物データ
        test_building_name = f"テスト建物_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_address = "東京都港区テスト1-2-3"
        
        print(f"テスト建物名: {test_building_name}")
        print(f"テスト住所: {test_address}")
        
        # 既存の建物を確認
        existing = session.query(Building).filter(
            Building.normalized_name == test_building_name
        ).first()
        
        if existing:
            print(f"既存の建物が見つかりました (ID: {existing.id})")
        else:
            # 新規建物を作成
            building = Building(
                normalized_name=test_building_name,
                address=test_address,
                total_floors=10,
                built_year=2020
            )
            session.add(building)
            print("✓ 建物をセッションに追加")
            
            # コミットを試みる
            try:
                session.commit()
                print(f"✓ 建物作成成功 (ID: {building.id})")
                
                # 確認のため再度取得
                created = session.query(Building).filter(
                    Building.id == building.id
                ).first()
                
                if created:
                    print(f"✓ 建物の保存を確認 (ID: {created.id}, 名前: {created.normalized_name})")
                else:
                    print("✗ 建物が保存されていません")
                    
            except Exception as commit_error:
                print(f"✗ コミットエラー: {commit_error}")
                session.rollback()
                traceback.print_exc()
                
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        traceback.print_exc()
        return False

def test_property_listing_creation():
    """物件掲載情報の作成をテスト"""
    print("\n=== 物件掲載情報作成テスト ===")
    try:
        from app.database import get_db_for_scraping
        from app.models import Building, MasterProperty, PropertyListing
        from app.utils.property_matcher import PropertyMatcher
        
        session = get_db_for_scraping()
        matcher = PropertyMatcher(session)
        
        # テスト用データ
        test_data = {
            'building_name': 'テストマンション',
            'address': '東京都港区テスト1-2-3',
            'floor_number': 5,
            'area': 65.5,
            'layout': '2LDK',
            'direction': '南',
            'price': 5000,
            'url': f'https://test.example.com/property_{datetime.now().timestamp()}',
            'source_site': 'suumo',
            'site_property_id': f'test_{datetime.now().timestamp()}'
        }
        
        print(f"テストデータ: {test_data}")
        
        try:
            # 建物を作成または取得
            building = session.query(Building).filter(
                Building.normalized_name == test_data['building_name']
            ).first()
            
            if not building:
                building = Building(
                    normalized_name=test_data['building_name'],
                    address=test_data['address']
                )
                session.add(building)
                session.flush()  # IDを取得するためflush
                print(f"✓ 建物作成 (ID: {building.id})")
            else:
                print(f"✓ 既存建物を使用 (ID: {building.id})")
            
            # マスター物件を作成または取得
            master = matcher.find_or_create_master_property(
                building_id=building.id,
                floor_number=test_data['floor_number'],
                area=test_data['area'],
                layout=test_data['layout'],
                direction=test_data['direction']
            )
            
            if master:
                print(f"✓ マスター物件取得/作成 (ID: {master.id})")
            else:
                print("✗ マスター物件の作成に失敗")
                
            # 掲載情報を作成
            listing = PropertyListing(
                master_property_id=master.id,
                source_site=test_data['source_site'],
                site_property_id=test_data['site_property_id'],
                url=test_data['url'],
                current_price=test_data['price'],
                is_active=True,
                first_seen_at=datetime.now(),
                last_scraped_at=datetime.now()
            )
            session.add(listing)
            print("✓ 掲載情報をセッションに追加")
            
            # コミット
            session.commit()
            print(f"✓ 掲載情報作成成功 (ID: {listing.id})")
            
            # 確認
            saved = session.query(PropertyListing).filter(
                PropertyListing.id == listing.id
            ).first()
            
            if saved:
                print(f"✓ 掲載情報の保存を確認 (ID: {saved.id}, URL: {saved.url})")
            else:
                print("✗ 掲載情報が保存されていません")
                
        except Exception as process_error:
            print(f"✗ 処理エラー: {process_error}")
            session.rollback()
            traceback.print_exc()
            
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        traceback.print_exc()
        return False

def test_scraper_minimal():
    """スクレイパーの最小限のテスト"""
    print("\n=== スクレイパー最小テスト ===")
    try:
        from app.scrapers.suumo_scraper import SuumoScraper
        
        # スクレイパーを初期化（最大1件のみ）
        scraper = SuumoScraper(max_properties=1)
        print("✓ スクレイパー初期化成功")
        
        # セッション状態を確認
        print(f"セッションの状態: {scraper.session}")
        print(f"autoflush: {scraper.session.autoflush}")
        
        # 簡単なデータで保存をテスト
        test_property = {
            'url': 'https://suumo.jp/test/12345/',
            'site_property_id': 'test_12345',
            'building_name': 'テストビル',
            'address': '東京都港区1-2-3',
            'price': 3000,
            'floor_number': 3,
            'area': 50.0,
            'layout': '1LDK',
            'direction': '南',
            'property_saved': False,
            'detail_fetched': True
        }
        
        print(f"\nテスト物件データ: {test_property}")
        
        # save_property_commonを直接呼び出し
        try:
            result = scraper.save_property_common(test_property)
            print(f"✓ save_property_common結果: {result}")
            
            if test_property.get('property_saved'):
                print("✓ property_savedフラグがTrueに設定されました")
            else:
                print("✗ property_savedフラグがFalseのままです")
                
        except Exception as save_error:
            print(f"✗ 保存エラー: {save_error}")
            traceback.print_exc()
            
        # セッションをクリーンアップ
        scraper.session.close()
        
        return True
        
    except Exception as e:
        print(f"✗ エラー: {e}")
        traceback.print_exc()
        return False

def main():
    """メインテスト実行"""
    print("スクレイピング問題診断テストを開始します...")
    print("=" * 50)
    
    # 各テストを実行
    tests = [
        ("データベース接続", test_database_connection),
        ("建物作成", test_building_creation),
        ("物件掲載情報作成", test_property_listing_creation),
        ("スクレイパー最小テスト", test_scraper_minimal)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n{test_name}で予期しないエラー: {e}")
            results.append((test_name, False))
    
    # 結果サマリー
    print("\n" + "=" * 50)
    print("テスト結果サマリー:")
    for test_name, success in results:
        status = "✓ 成功" if success else "✗ 失敗"
        print(f"  {test_name}: {status}")
    
    # 全体の成功/失敗
    all_success = all(success for _, success in results)
    if all_success:
        print("\n✓ すべてのテストが成功しました")
    else:
        print("\n✗ 一部のテストが失敗しました")
        print("\n失敗したテストの詳細を確認してください")

if __name__ == "__main__":
    main()