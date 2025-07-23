#!/usr/bin/env python3
"""
AtHomeのapplication/json scriptタグを抽出
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import json
import re


def extract_json_data():
    """application/json scriptタグを抽出"""
    
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # application/jsonタイプのscriptタグを探す
        json_scripts = soup.find_all('script', type='application/json')
        
        print(f"=== application/json scriptタグ: {len(json_scripts)}個 ===\n")
        
        for i, script in enumerate(json_scripts):
            print(f"--- Script {i+1} ---")
            
            # ID属性を確認
            script_id = script.get('id', 'なし')
            print(f"ID: {script_id}")
            
            # 内容を取得
            content = script.string
            if content:
                print(f"サイズ: {len(content)} chars")
                
                # JSONとして解析
                try:
                    data = json.loads(content)
                    print("✓ 有効なJSON")
                    
                    # データ構造を調査
                    if isinstance(data, dict):
                        print(f"キー: {list(data.keys())[:10]}")
                        
                        # 興味深いキーを探す
                        for key in data.keys():
                            if any(word in key.lower() for word in ['property', 'mansion', 'list', 'data', 'item', 'result']):
                                print(f"\n興味深いキー '{key}':")
                                value = data[key]
                                if isinstance(value, list):
                                    print(f"  リスト長: {len(value)}")
                                    if value:
                                        print(f"  最初の要素: {json.dumps(value[0], ensure_ascii=False, indent=2)[:300]}")
                                elif isinstance(value, dict):
                                    print(f"  辞書キー: {list(value.keys())[:10]}")
                        
                        # APIのURLパターンを探す
                        json_str = json.dumps(data, ensure_ascii=False)
                        urls = re.findall(r'https?://[^\s"]+', json_str)
                        api_urls = [url for url in urls if any(word in url for word in ['api', 'bff', 'backend', 'service'])]
                        
                        if api_urls:
                            print("\nAPI URL候補:")
                            for url in list(set(api_urls))[:10]:
                                print(f"  - {url}")
                        
                        # 物件データのパターンを探す
                        prices = re.findall(r'"price":\s*(\d+)', json_str)
                        if prices:
                            print(f"\n価格データ: {len(prices)}個")
                            print(f"  例: {prices[:5]}")
                        
                        # 建物名パターン
                        building_names = re.findall(r'"(?:building|mansion|property)Name":\s*"([^"]+)"', json_str)
                        if building_names:
                            print(f"\n建物名: {len(building_names)}個")
                            print(f"  例: {building_names[:5]}")
                            
                except json.JSONDecodeError as e:
                    print(f"JSONデコードエラー: {e}")
                    # エラーの場合、内容の一部を表示
                    print(f"内容の一部: {content[:200]}...")
        
        # ld+jsonも確認（構造化データ）
        print("\n\n=== application/ld+json (構造化データ) ===")
        ld_scripts = soup.find_all('script', type='application/ld+json')
        
        for i, script in enumerate(ld_scripts):
            content = script.string
            if content:
                try:
                    data = json.loads(content)
                    print(f"\nLD+JSON {i+1}:")
                    print(f"  @type: {data.get('@type', '不明')}")
                    
                    # 物件情報の可能性を探る
                    if '@graph' in data:
                        graph = data['@graph']
                        if isinstance(graph, list):
                            print(f"  @graph内のアイテム数: {len(graph)}")
                            for item in graph[:3]:
                                if isinstance(item, dict) and '@type' in item:
                                    print(f"    - {item['@type']}")
                                    
                except json.JSONDecodeError:
                    pass


if __name__ == "__main__":
    extract_json_data()