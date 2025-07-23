#!/usr/bin/env python3
"""
スクレイピング機能のテストスクリプト
実際のスクレイピングは実行せず、機能をテストします
"""

import sqlite3
import sys
import os

def test_database_setup():
    """データベース設定のテスト"""
    print("📊 データベース設定テスト...")
    
    if not os.path.exists('realestate.db'):
        print("❌ データベースファイルが見つかりません")
        return False
    
    conn = sqlite3.connect('realestate.db')
    cursor = conn.cursor()
    
    # テーブルの存在確認
    tables = ['areas', 'properties', 'property_listings', 'price_history']
    for table in tables:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cursor.fetchone():
            print(f"❌ テーブル '{table}' が見つかりません")
            return False
    
    print("✅ データベース設定OK")
    conn.close()
    return True

def test_scraper_import():
    """スクレイピングモジュールのインポートテスト"""
    print("📦 スクレイピングモジュールテスト...")
    
    try:
        # 必要なライブラリが不足している場合はモックでテスト
        sys.path.append('.')
        
        # 基本的なクラス構造のテスト
        import scraper
        
        # レート制限設定のテスト
        test_scraper = scraper.RealEstateScraper()
        
        if not hasattr(test_scraper, 'rate_limits'):
            print("❌ レート制限設定が見つかりません")
            return False
        
        required_sites = ['suumo', 'athome']
        for site in required_sites:
            if site not in test_scraper.rate_limits:
                print(f"❌ {site}のレート制限設定が見つかりません")
                return False
        
        print("✅ スクレイピングモジュールOK")
        return True
        
    except ImportError as e:
        print(f"⚠️  モジュールインポートエラー: {e}")
        print("📋 必要なライブラリをインストールしてください:")
        print("   pip install requests beautifulsoup4")
        return False
    except Exception as e:
        print(f"❌ スクレイピングモジュールエラー: {e}")
        return False

def test_compliance_features():
    """規約遵守機能のテスト"""
    print("⚖️  規約遵守機能テスト...")
    
    try:
        import scraper
        test_scraper = scraper.RealEstateScraper()
        
        # robots.txtチェック機能
        if not hasattr(test_scraper, 'check_robots_txt'):
            print("❌ robots.txtチェック機能が見つかりません")
            return False
        
        # 遅延機能
        if not hasattr(test_scraper, 'respectful_delay'):
            print("❌ 遅延機能が見つかりません")
            return False
        
        # レート制限設定のチェック
        for site, limits in test_scraper.rate_limits.items():
            required_keys = ['min_delay', 'max_delay', 'max_pages']
            for key in required_keys:
                if key not in limits:
                    print(f"❌ {site}の{key}設定が見つかりません")
                    return False
        
        print("✅ 規約遵守機能OK")
        return True
        
    except Exception as e:
        print(f"❌ 規約遵守機能エラー: {e}")
        return False

def show_usage_instructions():
    """使用方法の説明"""
    print("\n" + "="*50)
    print("📋 スクレイピング実行方法")
    print("="*50)
    
    print("\n🔧 基本実行:")
    print("   python3 scraper.py")
    
    print("\n🔧 エリア指定実行:")
    print("   python3 scraper.py --area minato")
    
    print("\n⚠️  実行前の重要事項:")
    print("   1. scraping_guidelines.mdを必ず確認")
    print("   2. 各サイトの利用規約を確認")
    print("   3. robots.txtが自動チェックされます")
    print("   4. 適切な遅延が自動で実行されます")
    
    print("\n📊 取得制限:")
    print("   - SUUMO: 最大5ページ")
    print("   - アットホーム: 最大10件")
    print("   - 各サイト間: 10-15秒の遅延")
    
    print("\n📝 必要なライブラリ:")
    print("   pip install requests beautifulsoup4")

def main():
    """メインテスト実行"""
    print("🧪 スクレイピング機能テスト開始")
    print("="*50)
    
    tests = [
        ("データベース設定", test_database_setup),
        ("スクレイピングモジュール", test_scraper_import),
        ("規約遵守機能", test_compliance_features),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}テスト:")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name}テストが失敗しました")
    
    print("\n" + "="*50)
    print(f"🎯 テスト結果: {passed}/{total} 合格")
    
    if passed == total:
        print("✅ すべてのテストが合格しました")
        show_usage_instructions()
    else:
        print("❌ いくつかのテストが失敗しました")
        print("📋 エラーを修正してから再実行してください")

if __name__ == '__main__':
    main()