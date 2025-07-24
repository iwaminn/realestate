#!/usr/bin/env python3
"""
各不動産サイトの一覧表示件数パラメータをテストするスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import time

def test_homes_display_count():
    """LIFULL HOME'Sの表示件数パラメータをテスト"""
    print("=== LIFULL HOME'S 表示件数テスト ===")
    
    base_url = "https://www.homes.co.jp/mansion/chuko/tokyo/minato-city/list/"
    
    # 可能性のあるパラメータ名
    params_to_test = [
        ("limit", [50, 100]),
        ("count", [50, 100]),
        ("display", [50, 100]),
        ("pagesize", [50, 100]),
        ("per_page", [50, 100]),
        ("rows", [50, 100]),
        ("mode", ["pc"])  # PC版表示モード
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # デフォルトの件数を確認
    try:
        response = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント
        property_items = soup.select('.mod-mergeBuilding')
        default_count = len(property_items)
        print(f"デフォルト表示件数: {default_count}件")
        
        # 各パラメータをテスト
        for param_name, values in params_to_test:
            for value in values:
                url = f"{base_url}?{param_name}={value}"
                print(f"\nテスト: {url}")
                
                time.sleep(2)  # レート制限
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                property_items = soup.select('.mod-mergeBuilding')
                count = len(property_items)
                
                if count != default_count:
                    print(f"  → 成功！ {count}件表示（デフォルト: {default_count}件）")
                    print(f"  → パラメータ: {param_name}={value}")
                else:
                    print(f"  → 変化なし: {count}件")
                    
    except Exception as e:
        print(f"エラー: {e}")


def test_nomu_display_count():
    """ノムコムの表示件数パラメータをテスト"""
    print("\n\n=== ノムコム 表示件数テスト ===")
    
    base_url = "https://www.nomu.com/mansion/area_tokyo/13103/"
    
    # 可能性のあるパラメータ名
    params_to_test = [
        ("limit", [50, 100]),
        ("count", [50, 100]),
        ("display", [50, 100]),
        ("pagesize", [50, 100]),
        ("per_page", [50, 100]),
        ("rows", [50, 100]),
        ("disp", [50, 100]),
        ("view", [50, 100])
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # デフォルトの件数を確認
    try:
        response = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント
        property_items = soup.select('.p-article-search-result-body')
        default_count = len(property_items)
        print(f"デフォルト表示件数: {default_count}件")
        
        # 各パラメータをテスト
        for param_name, values in params_to_test:
            for value in values:
                url = f"{base_url}?{param_name}={value}"
                print(f"\nテスト: {url}")
                
                time.sleep(2)  # レート制限
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                property_items = soup.select('.p-article-search-result-body')
                count = len(property_items)
                
                if count != default_count:
                    print(f"  → 成功！ {count}件表示（デフォルト: {default_count}件）")
                    print(f"  → パラメータ: {param_name}={value}")
                else:
                    print(f"  → 変化なし: {count}件")
                    
    except Exception as e:
        print(f"エラー: {e}")


def test_rehouse_display_count():
    """三井のリハウスの表示件数パラメータをテスト"""
    print("\n\n=== 三井のリハウス 表示件数テスト ===")
    
    base_url = "https://www.rehouse.co.jp/kounyu/jyouken/area/list/18/2055/"
    
    # 可能性のあるパラメータ名
    params_to_test = [
        ("limit", [50, 100]),
        ("count", [50, 100]),
        ("display", [50, 100]),
        ("pagesize", [50, 100]),
        ("per_page", [50, 100]),
        ("rows", [50, 100]),
        ("n", [50, 100]),  # 表示件数
        ("view", [50, 100])
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # デフォルトの件数を確認
    try:
        response = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント
        property_items = soup.select('.p-bk-card')
        default_count = len(property_items)
        print(f"デフォルト表示件数: {default_count}件")
        
        # 各パラメータをテスト
        for param_name, values in params_to_test:
            for value in values:
                url = f"{base_url}?{param_name}={value}"
                print(f"\nテスト: {url}")
                
                time.sleep(2)  # レート制限
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                property_items = soup.select('.p-bk-card')
                count = len(property_items)
                
                if count != default_count:
                    print(f"  → 成功！ {count}件表示（デフォルト: {default_count}件）")
                    print(f"  → パラメータ: {param_name}={value}")
                else:
                    print(f"  → 変化なし: {count}件")
                    
    except Exception as e:
        print(f"エラー: {e}")


def main():
    print("各不動産サイトの表示件数パラメータをテストします")
    print("※ このテストは実際のWebサイトにアクセスします")
    print("※ レート制限を守るため、各リクエスト間に2秒の遅延を設けています")
    print()
    
    # 各サイトをテスト
    test_homes_display_count()
    test_nomu_display_count()
    test_rehouse_display_count()
    
    print("\n\nテスト完了")


if __name__ == "__main__":
    main()