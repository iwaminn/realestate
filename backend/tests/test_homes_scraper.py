"""LIFULL HOME'Sスクレイパーのテスト"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from bs4 import BeautifulSoup

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.homes_scraper import HomesScraper


class TestHomesScraper:
    """LIFULL HOME'Sスクレイパーのテストクラス"""

    @pytest.fixture
    def scraper(self):
        """テスト用スクレイパーインスタンス"""
        with patch('app.scrapers.base_scraper.Session'):
            scraper = HomesScraper()
            scraper.session = Mock()
            scraper.logger = Mock()
            return scraper

    def test_building_name_extraction(self, scraper):
        """建物名の抽出テスト"""
        # 駅名が含まれるHTMLの例
        html = """
        <html>
            <head>
                <title>【ホームズ】パークハウス港南台 | 中古マンション</title>
            </head>
            <body>
                <h1>中古マンションパークハウス港南台</h1>
                <nav class="breadList">
                    <li>HOME</li>
                    <li>東京都</li>
                    <li>港区</li>
                    <li>パークハウス港南台の中古マンション</li>
                    <li>詳細</li>
                </nav>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # _fetch_properties_from_building_pageのロジックを部分的にテスト
        building_name = None
        
        # h1要素から建物名を取得
        h1_elem = soup.select_one('h1')
        if h1_elem:
            h1_text = h1_elem.get_text(strip=True)
            if '中古マンション' in h1_text:
                building_name = h1_text.replace('中古マンション', '').strip()
        
        assert building_name == "パークハウス港南台"

    def test_price_extraction(self, scraper):
        """価格情報の抽出テスト"""
        # 価格が含まれるHTMLの例
        html = """
        <tr class="prg-row">
            <td>3階</td>
            <td>301</td>
            <td class="price">5,980万円</td>
            <td>3LDK</td>
        </tr>
        """
        soup = BeautifulSoup(html, 'html.parser')
        row = soup.select_one('tr')
        
        # 価格抽出ロジックのテスト
        from app.scrapers import extract_price
        
        price_elem = row.select_one('.price')
        if price_elem and '万円' in price_elem.get_text():
            price_text = price_elem.get_text(strip=True)
            price = extract_price(price_text)
            
        assert price == 5980

    def test_parse_property_detail(self, scraper):
        """物件詳細ページの解析テスト"""
        html = """
        <html>
            <head>
                <title>【ホームズ】パークハウス港南台 301｜港区、...</title>
            </head>
            <body>
                <h1>中古マンションパークハウス港南台 3階/301号室</h1>
                <b class="text-brand">5,980万円</b>
                <table>
                    <tr>
                        <th>間取り</th>
                        <td>3LDK</td>
                    </tr>
                    <tr>
                        <th>専有面積</th>
                        <td>70.5㎡</td>
                    </tr>
                    <tr>
                        <th>管理費</th>
                        <td>15,000円</td>
                    </tr>
                    <tr>
                        <th>修繕積立金</th>
                        <td>12,000円</td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        with patch.object(scraper, 'fetch_page', return_value=BeautifulSoup(html, 'html.parser')):
            result = scraper.parse_property_detail('https://example.com/property/123')
        
        assert result is not None
        assert result['building_name'] == 'パークハウス港南台'
        assert result['room_number'] == '301'
        assert result['price'] == 5980
        assert result['layout'] == '3LDK'
        assert result['area'] == 70.5
        assert result['management_fee'] == 15000
        assert result['repair_fund'] == 12000