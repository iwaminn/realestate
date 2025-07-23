#!/usr/bin/env python3
"""
AtHomeの最終確認 - 最新のブラウザをシミュレート
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import re


def final_check():
    """最新のブラウザヘッダーで最終確認"""
    
    # Chrome 120の完全なヘッダーセット
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }
    
    session = requests.Session()
    
    # メインページにアクセス
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/"
    response = session.get(url, headers=headers, timeout=30)
    
    print(f"ステータス: {response.status_code}")
    print(f"レスポンスサイズ: {len(response.content)} bytes")
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # noscriptタグを確認（JSが無効な場合の内容）
        print("\n=== noscriptタグの確認 ===")
        noscripts = soup.find_all('noscript')
        for i, noscript in enumerate(noscripts):
            content = noscript.get_text(strip=True)
            if content:
                print(f"noscript {i+1}: {content[:200]}")
        
        # metaタグでリダイレクトやAPIヒントを探す
        print("\n=== 特殊なmetaタグ ===")
        metas = soup.find_all('meta')
        for meta in metas:
            name = meta.get('name', '')
            content = meta.get('content', '')
            if any(keyword in name.lower() for keyword in ['api', 'data', 'config']):
                print(f"<meta name='{name}' content='{content}'>")
        
        # base要素を確認
        base = soup.find('base')
        if base:
            print(f"\n<base href='{base.get('href')}'>")
        
        # 特定のクラスやIDを持つ要素を探す
        print("\n=== アプリケーションコンテナの検索 ===")
        app_containers = soup.find_all(id=re.compile(r'app|root|__next|react'))
        for container in app_containers:
            print(f"ID: {container.get('id')}, 内容長: {len(str(container))} chars")
            
            # data属性を確認
            for attr, value in container.attrs.items():
                if attr.startswith('data-'):
                    print(f"  {attr}: {value[:100] if isinstance(value, str) else value}")
        
        # フォームを探す（検索パラメータのヒント）
        print("\n=== フォーム要素の検索 ===")
        forms = soup.find_all('form')
        for form in forms:
            action = form.get('action', '')
            method = form.get('method', '')
            if action:
                print(f"Form: action='{action}' method='{method}'")
                
                # input要素を確認
                inputs = form.find_all('input')
                for inp in inputs[:5]:
                    name = inp.get('name', '')
                    value = inp.get('value', '')
                    if name:
                        print(f"  <input name='{name}' value='{value[:50] if value else ''}'>")
        
        # カスタムスクリプトタグの種類を確認
        print("\n=== スクリプトタグの種類 ===")
        scripts = soup.find_all('script')
        script_types = {}
        for script in scripts:
            script_type = script.get('type', 'text/javascript')
            src = script.get('src', 'inline')
            
            if script_type not in script_types:
                script_types[script_type] = []
            script_types[script_type].append(src)
        
        for stype, srcs in script_types.items():
            print(f"\ntype='{stype}': {len(srcs)}個")
            for src in srcs[:3]:
                print(f"  - {src}")
        
        # CSSファイルも確認（APIのヒントがあるかも）
        print("\n=== CSSファイル ===")
        links = soup.find_all('link', rel='stylesheet')
        for link in links[:3]:
            href = link.get('href', '')
            if href:
                print(f"CSS: {href}")


if __name__ == "__main__":
    final_check()