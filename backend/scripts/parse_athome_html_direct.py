#!/usr/bin/env python3
"""Parse AtHome HTML directly"""

import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

def parse_html_direct():
    url = "https://www.athome.co.jp/mansion/chuko/tokyo/minato-city/list/?page=1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Save HTML for inspection
        with open('/tmp/athome_page.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print("Saved HTML to /tmp/athome_page.html")
        
        # Look for Angular/React/Vue markers
        print("\n=== Framework Detection ===")
        
        # Angular
        ng_apps = soup.find_all(attrs={'ng-app': True})
        if ng_apps:
            print(f"Found Angular app: {ng_apps}")
        
        # Look for _ngcontent attributes (Angular)
        ng_content = soup.find_all(attrs=lambda x: x and any(k.startswith('_ngcontent') for k in x))
        if ng_content:
            print(f"Found {len(ng_content)} Angular elements")
            
        # React
        react_root = soup.find(id='root') or soup.find(id='app')
        if react_root:
            print(f"Found React/Vue root element")
            
        # Look for property cards in common patterns
        print("\n=== Looking for property cards ===")
        
        # Common card patterns
        card_selectors = [
            'div.property-unit',
            'div.object-item',
            'article.property-card',
            'div.search-item',
            'li[class*="item"]',
            'div[class*="card"]',
            'a[href*="/mansion/"][class*="item"]',
            'div[class*="result"]',
        ]
        
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards and len(cards) > 5:  # Likely property cards
                print(f"\nFound {len(cards)} elements with selector: {selector}")
                
                # Analyze first card
                first_card = cards[0]
                print("First card analysis:")
                
                # Get all text
                card_text = first_card.get_text(separator=' ', strip=True)
                print(f"  Text length: {len(card_text)} chars")
                print(f"  Text preview: {card_text[:200]}...")
                
                # Look for price
                price_pattern = re.compile(r'(\d{3,})\s*万円')
                price_match = price_pattern.search(card_text)
                if price_match:
                    print(f"  Price found: {price_match.group()}")
                
                # Look for area
                area_pattern = re.compile(r'(\d+\.?\d*)\s*m²')
                area_match = area_pattern.search(card_text)
                if area_match:
                    print(f"  Area found: {area_match.group()}")
                
                # Look for layout
                layout_pattern = re.compile(r'([1-9]\d*[SLDK]+|ワンルーム)')
                layout_match = layout_pattern.search(card_text)
                if layout_match:
                    print(f"  Layout found: {layout_match.group()}")
                
                # Look for links
                links = first_card.find_all('a', href=True)
                if links:
                    print(f"  Found {len(links)} links")
                    for link in links[:3]:
                        href = link.get('href')
                        if '/mansion/' in href or '/ahto/' in href:
                            print(f"    Link: {href}")
                            
        # Look in the entire page for patterns
        print("\n=== Page-wide search ===")
        
        # Find all links to properties
        property_links = soup.find_all('a', href=re.compile(r'/mansion/\d+/|/ahto/'))
        if property_links:
            print(f"Found {len(property_links)} property links")
            for link in property_links[:5]:
                print(f"  {link.get('href')}")

if __name__ == "__main__":
    parse_html_direct()