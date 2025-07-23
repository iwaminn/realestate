#!/usr/bin/env python3
"""
AtHomeの物件データを探す
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from bs4 import BeautifulSoup
import re


def find_property_data():
    """AtHomeの物件データを探す"""
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        # HTMLテキスト全体から物件情報を探す
        html_text = response.text
        
        # 価格パターンを探す
        print("=== 価格情報の検索 ===")
        price_patterns = [
            r'(\d{1,4})万円',
            r'(\d+),(\d+)万円',
            r'(\d+)億(\d*)万円'
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, html_text)
            if matches:
                print(f"パターン '{pattern}': {len(matches)}件")
                # 最初の5件を表示
                for match in matches[:5]:
                    print(f"  {match}")
        
        # 物件名候補を探す（カタカナ＋建物タイプ）
        print("\n=== 建物名候補の検索 ===")
        building_patterns = [
            r'([ァ-ヴー]{3,}(?:マンション|ハイム|コーポ|ビル|ハウス|レジデンス))',
            r'((?:サン|メゾン|パーク|グラン|エクセル|シティ)[ァ-ヴー一-龥]+)',
        ]
        
        for pattern in building_patterns:
            matches = re.findall(pattern, html_text)
            if matches:
                # 重複を除去
                unique_matches = list(set(matches))
                print(f"パターン '{pattern}': {len(unique_matches)}件")
                for match in unique_matches[:5]:
                    print(f"  {match}")
        
        # HTML内のJSONデータを探す
        print("\n=== JSONデータの検索 ===")
        json_patterns = [
            r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*({[^<]+})\s*</script>',
            r'<script[^>]*>\s*window\.__DATA__\s*=\s*({[^<]+})\s*</script>',
            r'<script[^>]*type="application/json"[^>]*>([^<]+)</script>',
            r'data-json=\'([^\']+)\'',
            r'data-json="([^"]+)"',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, html_text, re.DOTALL)
            if match:
                print(f"JSONデータ発見: パターン '{pattern}'")
                json_str = match.group(1)[:200]
                print(f"  内容: {json_str}...")
        
        # app-rootやdata-appなどのSPAの兆候を探す
        print("\n=== SPAコンテナの検索 ===")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        spa_containers = soup.find_all(['div', 'main'], id=re.compile(r'app|root|container', re.I))
        for container in spa_containers:
            print(f"SPAコンテナ候補: <{container.name} id='{container.get('id', '')}'> 内容: {len(container.get_text())}文字")
        
        # 物件リストコンテナを探す
        print("\n=== 物件リストコンテナの検索 ===")
        list_containers = soup.find_all(['div', 'ul', 'section'], class_=re.compile(r'list|result|property', re.I))
        for container in list_containers[:5]:
            classes = ' '.join(container.get('class', []))
            content = container.get_text(strip=True)[:100]
            print(f"<{container.name} class='{classes}'> {content}...")


if __name__ == "__main__":
    find_property_data()