#!/usr/bin/env python3
"""
HOMESページの視覚的な確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.scrapers.homes_scraper_v2 import HomesScraperV2
import re


def visual_check():
    """HOMESページの構造を視覚的に確認"""
    scraper = HomesScraperV2()
    
    url = "https://www.homes.co.jp/mansion/b-1216390034692/"
    
    with scraper:
        soup = scraper.fetch_page(url)
        if not soup:
            print("ページ取得失敗")
            return
        
        print(f"URL: {url}\n")
        
        # すべてのテキストノードから建物名らしきものを探す
        print("### 可能性のある建物名（テキストノードから） ###")
        
        # テキスト要素を全て取得
        all_text_elements = soup.find_all(text=True)
        
        # 建物名の可能性がある文字列を収集
        potential_names = []
        for text in all_text_elements:
            text = text.strip()
            # 空白、改行、スクリプト内容を除外
            if (text and 
                len(text) > 5 and 
                len(text) < 100 and
                not text.startswith('{') and
                not text.startswith('//') and
                '\n' not in text):
                
                # マンション名の可能性があるパターン
                if any(keyword in text for keyword in ['マンション', 'ハイツ', 'コーポ', 'レジデンス', 'ビル', 'ハウス', 'パレス', 'タワー']):
                    potential_names.append(text)
                # カタカナが多く含まれる場合
                elif re.search(r'[ァ-ヴー]{3,}', text):
                    potential_names.append(text)
        
        # 重複を除去して表示
        seen = set()
        for name in potential_names:
            if name not in seen:
                print(f"  - {name}")
                seen.add(name)
        
        print("\n### 主要な要素のテキスト ###")
        
        # h1, h2, h3要素
        for tag in ['h1', 'h2', 'h3']:
            elements = soup.find_all(tag)
            if elements:
                print(f"\n{tag}タグ:")
                for elem in elements[:5]:
                    text = elem.get_text(strip=True)
                    if text:
                        print(f"  - {text}")
        
        # span要素で大きめのフォント
        print("\n### 大きめのspan要素 ###")
        spans = soup.find_all('span')
        for span in spans:
            text = span.get_text(strip=True)
            # styleやclassで大きさを判定
            style = span.get('style', '')
            classes = ' '.join(span.get('class', []))
            if text and ('font-size' in style or 'heading' in classes or 'title' in classes):
                print(f"  - {text}")
        
        # divで特定のクラスを持つもの
        print("\n### 特定のクラスを持つdiv ###")
        important_classes = ['building', 'property', 'title', 'name', 'heading', 'mansion']
        for class_name in important_classes:
            divs = soup.find_all('div', class_=re.compile(class_name, re.I))
            for div in divs[:3]:
                text = div.get_text(strip=True)
                if text and len(text) < 100:
                    print(f"  {class_name}: {text}")


if __name__ == "__main__":
    visual_check()