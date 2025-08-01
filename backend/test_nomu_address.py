#!/usr/bin/env python3
"""
ノムコムの住所取得ロジックをテストするスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup
import requests

def test_address_extraction():
    """住所取得ロジックをテスト"""
    url = "https://www.nomu.com/mansion/id/RF470004/"
    
    print(f"URL: {url} からHTMLを取得中...")
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print("\n=== 住所取得テスト ===")
        
        # 1. <th>所在地</th>を探す
        address_th = soup.find("th", text="所在地")
        print(f"1. th要素（所在地）: {'見つかりました' if address_th else '見つかりません'}")
        
        if address_th:
            # 2. 次の<td>を探す
            address_td = address_th.find_next("td")
            print(f"2. td要素: {'見つかりました' if address_td else '見つかりません'}")
            
            if address_td:
                # td内のHTMLを確認
                print(f"   td内のHTML（最初の200文字）: {str(address_td)[:200]}...")
                
                # 3. td内の<p>タグを探す
                address_p = address_td.find("p")
                print(f"3. p要素: {'見つかりました' if address_p else '見つかりません'}")
                
                if address_p:
                    address_text = address_p.get_text(strip=True)
                    print(f"4. 住所テキスト: '{address_text}'")
                else:
                    # p要素がない場合、td直下のテキストを確認
                    td_text = address_td.get_text(strip=True)
                    print(f"   td直下のテキスト: '{td_text}'")
        
        # 別の方法も試す
        print("\n=== 別の住所要素の確認 ===")
        
        # <p class="address">を探す
        p_address = soup.find("p", class_="address")
        if p_address:
            print(f"<p class='address'>が見つかりました: '{p_address.get_text(strip=True)}'")
        
        # 「東京都」を含むp要素を探す
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if "東京都" in text and "区" in text and len(text) < 100:
                print(f"住所候補のp要素: '{text}'")
                break
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    test_address_extraction()