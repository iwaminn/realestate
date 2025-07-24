#!/usr/bin/env python3
"""
各不動産サイトの現在のページング仕様を確認するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import time

def check_homes():
    """LIFULL HOME'Sのページング仕様を確認"""
    print("=== LIFULL HOME'S ===")
    
    url = "https://www.homes.co.jp/mansion/chuko/tokyo/minato-city/list/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント（現在のセレクタ）
        property_items = soup.select('.mod-objectCollection__item, .p-object-cassette, .prg-objectListUnit')
        print(f"現在の物件数: {len(property_items)}件")
        
        # ページングリンクを確認
        pagination = soup.select('.pagination a, .p-pager a, .pager a')
        print(f"ページングリンク数: {len(pagination)}")
        
        # 表示件数切り替えオプションがあるか確認
        display_options = soup.select('select[name*="limit"], select[name*="count"], .display-count')
        if display_options:
            print("表示件数切り替えオプション: あり")
            for option in display_options:
                print(f"  {option}")
        else:
            print("表示件数切り替えオプション: なし")
            
    except Exception as e:
        print(f"エラー: {e}")


def check_nomu():
    """ノムコムのページング仕様を確認"""
    print("\n=== ノムコム ===")
    
    url = "https://www.nomu.com/mansion/area_tokyo/13103/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント
        property_items = soup.select('.p-article-search-result-body, .property-item, .result-item')
        print(f"現在の物件数: {len(property_items)}件")
        
        # 結果件数の表示を探す
        result_count = soup.select_one('.p-article-search-count, .result-count, .total-count')
        if result_count:
            print(f"結果件数表示: {result_count.get_text(strip=True)}")
        
        # ページングリンクを確認
        pagination = soup.select('.p-pager a, .pagination a, .pager a')
        print(f"ページングリンク数: {len(pagination)}")
        
        # 表示件数切り替えオプション
        display_options = soup.select('select[name*="limit"], select[name*="disp"], .display-option')
        if display_options:
            print("表示件数切り替えオプション: あり")
        else:
            print("表示件数切り替えオプション: なし")
            
    except Exception as e:
        print(f"エラー: {e}")


def check_rehouse():
    """三井のリハウスのページング仕様を確認"""
    print("\n=== 三井のリハウス ===")
    
    url = "https://www.rehouse.co.jp/kounyu/jyouken/area/list/18/2055/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 物件数をカウント
        property_items = soup.select('.p-bk-card, .property-card, .item-card')
        print(f"現在の物件数: {len(property_items)}件")
        
        # 結果件数の表示
        result_count = soup.select_one('.p-searchResult__count, .result-count')
        if result_count:
            print(f"結果件数表示: {result_count.get_text(strip=True)}")
        
        # ページングリンクを確認
        pagination = soup.select('.p-pager a, .pagination a')
        print(f"ページングリンク数: {len(pagination)}")
        
        # 表示件数切り替えオプション
        display_options = soup.select('select[name*="n"], select[name*="limit"], .sort-option')
        if display_options:
            print("表示件数切り替えオプション: あり")
        else:
            print("表示件数切り替えオプション: なし")
            
        # URLパラメータで試す
        print("\n表示件数パラメータテスト:")
        test_params = ['n=50', 'n=100', 'limit=100']
        for param in test_params:
            test_url = f"{url}?{param}"
            time.sleep(1)
            response = requests.get(test_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('.p-bk-card')
            print(f"  {param}: {len(items)}件")
            
    except Exception as e:
        print(f"エラー: {e}")


def main():
    print("各不動産サイトのページング仕様を確認します\n")
    
    check_homes()
    time.sleep(2)
    
    check_nomu()
    time.sleep(2)
    
    check_rehouse()
    
    print("\n\n=== まとめ ===")
    print("※ 実際のサイトアクセスが必要なため、詳細な仕様は手動で確認することを推奨")
    print("※ 多くのサイトではJavaScriptによる動的な表示制御を行っている可能性があります")


if __name__ == "__main__":
    main()