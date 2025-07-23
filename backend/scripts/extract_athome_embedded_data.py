#!/usr/bin/env python3
"""
AtHomeのHTMLに埋め込まれたデータを抽出
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import re
import json


def extract_embedded_data():
    """HTMLに埋め込まれたデータを抽出"""
    
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        html = response.text
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print("=== Next.js データの検索 ===")
        # Next.jsの__NEXT_DATA__を探す
        next_data_pattern = r'<script\s+id="__NEXT_DATA__"\s+type="application/json">([^<]+)</script>'
        match = re.search(next_data_pattern, html)
        
        if match:
            print("__NEXT_DATA__を発見!")
            try:
                data = json.loads(match.group(1))
                print(f"データ構造のキー: {list(data.keys())}")
                
                # propsを探す
                if 'props' in data:
                    props = data['props']
                    print(f"\npropsのキー: {list(props.keys())}")
                    
                    # pagePropsを探す
                    if 'pageProps' in props:
                        page_props = props['pageProps']
                        print(f"\npagePropsのキー: {list(page_props.keys())}")
                        
                        # 物件データを探す
                        for key in page_props:
                            if any(word in key.lower() for word in ['property', 'mansion', 'list', 'item', 'data']):
                                print(f"\n興味深いキー '{key}' を発見:")
                                value = page_props[key]
                                if isinstance(value, list) and len(value) > 0:
                                    print(f"  リスト長: {len(value)}")
                                    print(f"  最初の要素: {json.dumps(value[0], ensure_ascii=False, indent=2)[:500]}")
                                elif isinstance(value, dict):
                                    print(f"  辞書のキー: {list(value.keys())[:10]}")
                
                # buildIdを確認（APIのバージョニングに使われるかも）
                if 'buildId' in data:
                    print(f"\nbuildId: {data['buildId']}")
                    
            except json.JSONDecodeError as e:
                print(f"JSONデコードエラー: {e}")
        else:
            print("__NEXT_DATA__が見つかりません")
        
        # その他のパターンを探す
        print("\n\n=== その他のデータパターンの検索 ===")
        
        # window.に代入されているデータを探す
        window_assignments = re.findall(r'window\.(\w+)\s*=\s*({[^}]+}|\[[^\]]+\])', html)
        for var_name, var_value in window_assignments[:5]:
            print(f"\nwindow.{var_name} = ...")
            try:
                data = json.loads(var_value)
                if isinstance(data, dict):
                    print(f"  キー: {list(data.keys())[:5]}")
                elif isinstance(data, list):
                    print(f"  リスト長: {len(data)}")
            except:
                print(f"  内容: {var_value[:100]}...")
        
        # data-属性を持つ要素を探す
        print("\n\n=== data-属性の検索 ===")
        elements = soup.find_all(attrs={"data-properties": True})
        elements.extend(soup.find_all(attrs={"data-items": True}))
        elements.extend(soup.find_all(attrs={"data-list": True}))
        elements.extend(soup.find_all(attrs={"data-json": True}))
        
        for elem in elements[:5]:
            for attr, value in elem.attrs.items():
                if attr.startswith('data-') and value and len(value) > 10:
                    print(f"\n{attr}: {value[:200]}...")
                    try:
                        data = json.loads(value)
                        print("  → 有効なJSON!")
                    except:
                        pass
        
        # 物件情報が含まれそうなscriptブロックを探す
        print("\n\n=== 物件データを含むscriptの検索 ===")
        scripts = soup.find_all('script')
        for i, script in enumerate(scripts):
            if script.string and len(script.string) > 1000:
                content = script.string
                # 物件情報のパターンを探す
                if any(word in content for word in ['万円', 'mansion', 'property', '港区', 'minato']):
                    print(f"\nScript {i+1} (物件データの可能性):")
                    # 価格パターンを探す
                    prices = re.findall(r'(\d{3,5})万円', content)
                    if prices:
                        print(f"  価格: {prices[:5]}")
                    
                    # 建物名パターンを探す
                    buildings = re.findall(r'([ァ-ヴー]{4,}(?:マンション|ハイム|コーポ))', content)
                    if buildings:
                        print(f"  建物名候補: {list(set(buildings))[:5]}")


if __name__ == "__main__":
    extract_embedded_data()