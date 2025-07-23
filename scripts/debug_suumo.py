#!/usr/bin/env python3
"""
SUUMOデバッグ用スクリプト
実際のHTMLを取得して構造を確認
"""

import requests
from bs4 import BeautifulSoup
import re
import time

def debug_suumo():
    """SUUMOページの構造をデバッグ"""
    url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print("=== SUUMO HTML構造デバッグ ===")
        print(f"ページタイトル: {soup.title.text if soup.title else 'N/A'}")
        print(f"HTML長さ: {len(response.text)} 文字")
        
        # 様々なクラス名を探す
        possible_classes = [
            'cassetteitem', 'property-unit', 'js-cassette-link', 'item',
            'js-bukkenList', 'bukken-item', 'result-item', 'listing-item',
            'property-item', 'search-result', 'item-summary'
        ]
        
        print("\n=== 可能性のあるクラス名の検索 ===")
        for class_name in possible_classes:
            elements = soup.find_all(class_=class_name)
            if elements:
                print(f"'{class_name}': {len(elements)} 個見つかりました")
                if len(elements) > 0:
                    print(f"  最初の要素: {str(elements[0])[:200]}...")
        
        # 価格情報を探す
        price_patterns = [r'万円', r'円', r'¥', r'価格']
        print("\n=== 価格情報の検索 ===")
        for pattern in price_patterns:
            price_elements = soup.find_all(text=re.compile(pattern))
            if price_elements:
                print(f"'{pattern}': {len(price_elements)} 個見つかりました")
                for i, elem in enumerate(price_elements[:3]):  # 最初の3つだけ
                    print(f"  {i+1}: {elem.strip()}")
        
        # メタ情報を探す
        print("\n=== メタ情報 ===")
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            if meta.get('name') == 'description':
                print(f"Description: {meta.get('content', '')}")
        
        # JavaScriptの変数を探す
        print("\n=== JavaScript変数 ===")
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'bukken' in script.string:
                print(f"物件関連のJavaScript: {script.string[:200]}...")
                break
        
        # 検索結果の数を探す
        result_count_elements = soup.find_all(text=re.compile(r'件|物件|結果'))
        if result_count_elements:
            print("\n=== 検索結果数 ===")
            for elem in result_count_elements[:5]:
                print(f"  {elem.strip()}")
        
        # ID付きの要素を探す
        print("\n=== ID付きの要素 ===")
        elements_with_id = soup.find_all(id=True)
        for elem in elements_with_id:
            if any(keyword in elem.get('id', '').lower() for keyword in ['bukken', 'list', 'result', 'item']):
                print(f"  ID: {elem.get('id')}, タグ: {elem.name}")
        
        # HTMLの一部を保存
        with open('suumo_debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print("\n=== HTMLを suumo_debug.html に保存しました ===")
        
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    debug_suumo()