#!/usr/bin/env python3
"""
AtHomeのAPIエンドポイントを探す
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import re
import json


def find_api_endpoints():
    """AtHomeのAPIエンドポイントを探す"""
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        html_text = response.text
        
        # JavaScriptファイルを探す
        print("=== JavaScriptファイルの検索 ===")
        scripts = soup.find_all('script', src=True)
        js_files = []
        for script in scripts:
            src = script.get('src', '')
            if src and ('.js' in src or not '.' in src.split('/')[-1]):
                full_url = src if src.startswith('http') else f"https://www.athome.co.jp{src}"
                js_files.append(full_url)
                print(f"JS: {full_url}")
        
        # APIパターンを探す
        print("\n=== APIパターンの検索 ===")
        api_patterns = [
            r'["\'](/api/[^"\']+)["\']',
            r'["\'](/v\d+/[^"\']+)["\']',
            r'["\']https?://[^"\']*api[^"\']+["\']',
            r'endpoint["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'url["\']?\s*[:=]\s*["\']([^"\']+api[^"\']+)["\']',
            r'fetch\s*\(["\']([^"\']+)["\']',
            r'axios\.[a-z]+\s*\(["\']([^"\']+)["\']',
            r'XMLHttpRequest.*open\s*\(["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in api_patterns:
            matches = re.findall(pattern, html_text, re.IGNORECASE)
            if matches:
                print(f"\nパターン: {pattern}")
                for match in set(matches):
                    if 'api' in match.lower() or '/v' in match:
                        print(f"  - {match}")
        
        # 主要なJSファイルをダウンロードして解析
        print("\n=== JavaScriptファイルの解析 ===")
        for js_url in js_files[:5]:  # 最初の5個のみ
            try:
                print(f"\n解析中: {js_url}")
                js_response = session.get(js_url, headers=headers, timeout=10)
                if js_response.status_code == 200:
                    js_content = js_response.text[:50000]  # 最初の50KB
                    
                    # APIエンドポイントを探す
                    api_matches = []
                    for pattern in api_patterns:
                        matches = re.findall(pattern, js_content, re.IGNORECASE)
                        api_matches.extend(matches)
                    
                    if api_matches:
                        print("  APIエンドポイント候補:")
                        for match in set(api_matches):
                            if len(match) > 5 and ('api' in match.lower() or '/search' in match or '/property' in match or '/mansion' in match):
                                print(f"    - {match}")
                    
                    # 特定のキーワードを探す
                    keywords = ['searchUrl', 'apiUrl', 'endpoint', 'baseUrl', 'propertySearch', 'mansionSearch']
                    for keyword in keywords:
                        if keyword in js_content:
                            # キーワードの周辺を抽出
                            idx = js_content.find(keyword)
                            context = js_content[max(0, idx-100):idx+200]
                            if 'http' in context or '/' in context:
                                print(f"  {keyword}の周辺:")
                                print(f"    {context.strip()}")
                                
            except Exception as e:
                print(f"  エラー: {e}")
        
        # ネットワークタブで見られるようなXHRリクエストのヒントを探す
        print("\n=== XHR/Fetchヒントの検索 ===")
        xhr_patterns = [
            r'new XMLHttpRequest',
            r'\.ajax\(',
            r'fetch\(',
            r'axios\.',
            r'\$\.get\(',
            r'\$\.post\(',
        ]
        
        for pattern in xhr_patterns:
            if re.search(pattern, html_text):
                print(f"検出: {pattern}")
        
        # data属性を探す
        print("\n=== data属性の検索 ===")
        elements_with_data = soup.find_all(attrs={"data-api": True})
        elements_with_data.extend(soup.find_all(attrs={"data-url": True}))
        elements_with_data.extend(soup.find_all(attrs={"data-endpoint": True}))
        
        for elem in elements_with_data[:10]:
            for attr, value in elem.attrs.items():
                if 'data-' in attr and value:
                    print(f"{attr}: {value}")


if __name__ == "__main__":
    find_api_endpoints()