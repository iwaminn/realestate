"""
LIFULL HOME'Sスクレイパー
homes.co.jpから中古マンション情報を取得
"""

import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper
from ..models import PropertyListing


class HomesScraper(BaseScraper):
    """LIFULL HOME'Sのスクレイパー"""
    
    BASE_URL = "https://www.homes.co.jp"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__("HOMES", force_detail_fetch, max_properties)
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """HOME'Sの検索URLを生成"""
        # 港区の中古マンション検索URL
        if area.lower() == "minato":
            # LIFULL HOME'Sの港区URL（更新版 - 正しいパターン）
            return f"{self.BASE_URL}/mansion/chuko/tokyo/minato-city/list/?page={page}"
        else:
            # 他のエリア用
            return f"{self.BASE_URL}/mansion/chuko/tokyo/list/?page={page}"
    
    def parse_property_list_old(self, soup: BeautifulSoup) -> List[str]:
        """物件一覧から詳細URLを抽出"""
        property_urls = []
        
        # LIFULL HOME'Sの物件リストセレクタ - 2025年7月版
        # パターン1: 建物名アンカー（現在のメインセレクタ）
        property_items = soup.select('a.prg-bukkenNameAnchor[href]')
        
        for item in property_items:
            href = item.get('href')
            if href and '/mansion/b-' in href:
                url = urljoin(self.BASE_URL, href)
                property_urls.append(url)
        
        # パターン2: 新しい構造のヘッダーリンク
        if not property_urls:
            property_items = soup.select('.mod-mergeBuilding--sale h3.heading a[href]')
            for item in property_items:
                href = item.get('href')
                if href and '/mansion/' in href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        # パターン3: 建物詳細ページへのリンク
        if not property_urls:
            property_items = soup.select('a[href*="/mansion/b-"]')
            for item in property_items:
                href = item.get('href')
                if href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        # パターン4: テーブル内の詳細リンク
        if not property_urls:
            property_items = soup.select('tr[data-href*="/mansion/b-"]')
            for item in property_items:
                href = item.get('data-href')
                if href:
                    url = urljoin(self.BASE_URL, href)
                    property_urls.append(url)
        
        return list(set(property_urls))  # 重複を除去
    
    def scrape_area_old(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング（旧方式 - 削除予定）"""
        pass
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            # 詳細ページを取得
            soup = self.fetch_page(url)
            if not soup:
                return None
                
            property_data = {
                'url': url
            }
            
            # デバッグ：ページ全体から情報公開日を探す
            page_text = soup.get_text()
            if '情報公開日' in page_text:
                print("    [DEBUG] ページに'情報公開日'というテキストが含まれています")
                # 情報公開日の周辺テキストを表示
                index = page_text.find('情報公開日')
                print(f"    [DEBUG] 周辺テキスト: ...{page_text[max(0, index-50):index+100]}...")
            
            # デバッグ：不動産会社情報を探す
            if '会社情報' in page_text or '情報提供元' in page_text or '取扱会社' in page_text:
                print("    [DEBUG] ページに会社情報が含まれています")
                # 会社情報の周辺テキストを表示
                for keyword in ['会社情報', '情報提供元', '取扱会社', '不動産会社']:
                    if keyword in page_text:
                        index = page_text.find(keyword)
                        print(f"    [DEBUG] {keyword}の周辺: ...{page_text[max(0, index-20):index+150]}...")
            
            # タイトルと建物名、部屋番号
            # まずtitleタグまたはog:titleから情報を取得
            title_text = None
            
            # titleタグから取得
            title_elem = soup.select_one('title')
            if title_elem:
                title_text = title_elem.get_text(strip=True)
            
            # og:titleから取得（titleタグがない場合）
            if not title_text:
                og_title = soup.select_one('meta[property="og:title"]')
                if og_title:
                    title_text = og_title.get('content', '')
            
            # パンくずリストから建物名を取得（優先）
            breadcrumb = soup.select_one('.breadList, .breadcrumb, nav[aria-label="breadcrumb"], .topicPath')
            building_name_from_breadcrumb = None
            
            if breadcrumb:
                # パンくずリストのアイテムを取得
                breadcrumb_items = breadcrumb.select('li, .breadList__item, .breadcrumb-item')
                if breadcrumb_items:
                    # 通常、建物名は最後から2番目のアイテム（最後は部屋番号）
                    if len(breadcrumb_items) >= 2:
                        # 最後から2番目のアイテムから建物名を取得
                        building_item = breadcrumb_items[-2]
                        building_text = building_item.get_text(strip=True)
                        # 「〇〇(建物名)の中古マンション」というパターンから建物名を抽出
                        match = re.search(r'(.+?)の中古マンション', building_text)
                        if match:
                            building_name_from_breadcrumb = match.group(1)
                        else:
                            # そのままの文字列を使用（ただし不要な文字は除去）
                            building_name_from_breadcrumb = building_text.replace('中古マンション', '').strip()
                        print(f"    パンくずリストから建物名取得: {building_name_from_breadcrumb}")
            
            if title_text:
                property_data['title'] = title_text
                
                # titleから建物名と部屋番号を抽出
                # パターン: 【ホームズ】アクシアフォレスタ麻布 904｜港区、...
                # または: アクシアフォレスタ麻布 904 | 中古マンション...
                
                # 【ホームズ】を除去
                title_text = title_text.replace('【ホームズ】', '').strip()
                
                # ｜または|で分割して最初の部分を取得
                if '｜' in title_text:
                    property_name_part = title_text.split('｜')[0].strip()
                elif '|' in title_text:
                    property_name_part = title_text.split('|')[0].strip()
                else:
                    property_name_part = title_text.split('、')[0].strip()
                
                # パンくずリストから建物名が取得できた場合はそれを使用
                if building_name_from_breadcrumb:
                    property_data['building_name'] = building_name_from_breadcrumb
                    # タイトルから部屋番号を抽出
                    # パターン: "建物名 部屋番号" or "建物名棟 部屋番号"
                    room_match = re.search(r'\s+(\d{3,4}[A-Z]*)\s*($|｜|\|)', property_name_part)
                    if room_match:
                        property_data['room_number'] = room_match.group(1)
                else:
                    # パンくずリストがない場合は従来の方法
                    # 建物名と部屋番号を分離
                    # パターン1: "建物名 部屋番号" (スペース区切り)
                    parts = property_name_part.split()
                    if len(parts) >= 2:
                        # 最後の部分が数字の場合は部屋番号
                        last_part = parts[-1]
                        if re.match(r'^\d{3,4}[A-Z]*$', last_part):
                            property_data['room_number'] = last_part
                            property_data['building_name'] = ' '.join(parts[:-1])
                        else:
                            property_data['building_name'] = property_name_part
                    else:
                        property_data['building_name'] = property_name_part
                
                # 建物名から余計な文字を除去
                if property_data.get('building_name'):
                    building_name = property_data['building_name']
                    # 中古マンションなどのプレフィックスを除去
                    building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
                    property_data['building_name'] = building_name
            else:
                property_data['title'] = '物件名不明'
            
            # 価格
            # 新しいセレクタパターンも追加
            price_elem = soup.select_one('.text-brand, .priceLabel, .price, [class*="price"]')
            if not price_elem:
                # さらに別のパターンを試す（b要素で価格を含むもの）
                for b in soup.select('b'):
                    if '万円' in b.get_text():
                        price_elem = b
                        break
            
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # 億円パターン
                oku_match = re.search(r'(\d+)億\s*(\d*)万?円', price_text)
                if oku_match:
                    oku = int(oku_match.group(1)) * 10000
                    man = int(oku_match.group(2)) if oku_match.group(2) else 0
                    property_data['price'] = oku + man
                else:
                    # 万円パターン（カンマ対応）
                    man_match = re.search(r'([\d,]+)万円', price_text)
                    if man_match:
                        property_data['price'] = int(man_match.group(1).replace(',', ''))
            
            # 価格が取得できなかった場合の追加処理
            if 'price' not in property_data:
                # ページ全体から価格を探す
                page_text = soup.get_text()
                # 最初に見つかった価格パターンを使用
                price_matches = re.findall(r'([\d,]+)万円', page_text)
                if price_matches:
                    # 最初の妥当な価格を使用（100万円以上）
                    for price_str in price_matches:
                        price = int(price_str.replace(',', ''))
                        if price >= 100:  # 100万円以上なら妥当な価格
                            property_data['price'] = price
                            break
            
            # 詳細情報テーブル
            detail_items = soup.select('.detailInfo dl, .mod-detailInfo dl, [class*="detail"] dl')
            
            for dl in detail_items:
                dt = dl.select_one('dt')
                dd = dl.select_one('dd')
                
                if not dt or not dd:
                    continue
                
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                # 所在地
                if '所在地' in label or '住所' in label:
                    property_data['address'] = value
                
                # 間取り
                elif '間取り' in label:
                    property_data['layout'] = value.split('/')[0].strip()  # "2LDK/60㎡"のような形式から間取りだけ抽出
                
                # 専有面積
                elif '専有面積' in label or '面積' in label:
                    area_match = re.search(r'([\d.]+)m²|([\d.]+)㎡', value)
                    if area_match:
                        property_data['area'] = float(area_match.group(1) or area_match.group(2))
                
                # 築年月
                elif '築年月' in label:
                    # 築年数を計算
                    year_match = re.search(r'(\d{4})年', value)
                    if year_match:
                        from datetime import datetime
                        built_year = int(year_match.group(1))
                        property_data['age'] = datetime.now().year - built_year
                    else:
                        age_match = re.search(r'築(\d+)年', value)
                        if age_match:
                            property_data['age'] = int(age_match.group(1))
                
                # 階数
                elif '階' in label and '建' not in label:
                    property_data['floor'] = value
                    # 階数情報を抽出
                    floor_match = re.search(r'(\d+)階/(\d+)階建', value)
                    if floor_match:
                        property_data['floor_number'] = int(floor_match.group(1))
                        # 地下情報も含めて総階数を取得
                        property_data['total_floors'] = int(floor_match.group(2))
                        basement_match = re.search(r'地下(\d+)階', value)
                        if basement_match:
                            property_data['basement_floors'] = int(basement_match.group(1))
                        else:
                            property_data['basement_floors'] = 0
                    else:
                        floor_match = re.search(r'(\d+)階', value)
                        if floor_match:
                            property_data['floor_number'] = int(floor_match.group(1))
                
                # 交通
                elif '交通' in label or '最寄' in label or '駅' in label:
                    # 不要な文言を削除し、路線ごとに改行を入れる
                    station_info = value
                    # 各路線の開始位置で改行を入れる（HOMESの場合は「、」で区切られていることが多い）
                    # まず「、」で区切られている場合は改行に変換
                    station_info = station_info.replace('、', '\n')
                    # その他の路線名の前でも改行
                    station_info = re.sub(
                        r'(?=東京メトロ|都営|ＪＲ|京王|小田急|東急|京急|京成|新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス)',
                        '\n',
                        station_info
                    ).strip()
                    property_data['station_info'] = station_info
                
                # 方角・主要採光面
                elif '向き' in label or '方角' in label or 'バルコニー' in label or '採光' in label:
                    # 方角を抽出
                    direction_patterns = ['南東', '南西', '北東', '北西', '南', '北', '東', '西']
                    for direction in direction_patterns:
                        if direction in value:
                            property_data['direction'] = direction
                            print(f"    {label}: {property_data['direction']}")
                            break
                
                # 管理費
                elif '管理費' in label:
                    fee_match = re.search(r'([\d,]+)円', value)
                    if fee_match:
                        property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                
                # 修繕積立金
                elif '修繕積立金' in label:
                    fund_match = re.search(r'([\d,]+)円', value)
                    if fund_match:
                        property_data['repair_fund'] = int(fund_match.group(1).replace(',', ''))
                
                # 部屋番号
                elif '部屋番号' in label or '号室' in label:
                    property_data['room_number'] = value
                
                # 権利形態
                elif '権利' in label and ('土地' in label or '敷地' in label):
                    property_data['land_rights'] = value
                
                # 駐車場
                elif '駐車' in label:
                    property_data['parking_info'] = value
                
                # 情報公開日を取得（最初に公開された日）
                elif '情報公開日' in label:
                    # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['first_published_at'] = datetime(year, month, day)
                        print(f"    売出確認日: {property_data['first_published_at'].strftime('%Y-%m-%d')}")
                    else:
                        print(f"    [DEBUG] 情報公開日のラベルを検出したが、日付パターンがマッチしませんでした: {value}")
                
                # 情報提供日を取得（最新の更新日）
                elif '情報提供日' in label or '情報更新日' in label or '登録日' in label:
                    # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['published_at'] = datetime(year, month, day)
                        print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                    else:
                        print(f"    [DEBUG] 情報提供日のラベルを検出したが、日付パターンがマッチしませんでした: {value}")
                elif '更新日' in label or '登録' in label or '掲載' in label:
                    # デバッグ用：関連しそうなラベルをログ出力
                    print(f"    [DEBUG] 日付関連ラベル検出: {label} = {value}")
            
            # テーブル形式の詳細情報も解析（HOMESの一般的なtableも含む）
            all_tables = soup.select('table')
            for table in all_tables:
                rows = table.select('tr')
                for row in rows:
                    cells = row.select('th, td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        # デバッグ：全てのラベルを出力して情報公開日を探す
                        if '情報' in label or '公開' in label or '更新' in label or '登録' in label or '掲載' in label:
                            print(f"    [DEBUG] 日付関連ラベル発見: {label} = {value}")
                        
                        if '所在地' in label:
                            property_data['address'] = value
                        elif '間取り' in label:
                            # "3LDK（リビング..." のような形式から間取りだけ抽出
                            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
                            if layout_match:
                                property_data['layout'] = layout_match.group(1)
                        elif '専有面積' in label:
                            area_match = re.search(r'([\d.]+)', value)
                            if area_match:
                                property_data['area'] = float(area_match.group(1))
                        elif '管理費等' in label or '管理費' in label:
                            fee_match = re.search(r'([\d,]+)円', value)
                            if fee_match:
                                property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                        elif '修繕積立金' in label:
                            fund_match = re.search(r'([\d,]+)円', value)
                            if fund_match:
                                property_data['repair_fund'] = int(fund_match.group(1).replace(',', ''))
                        elif '所在階' in label and '階数' in label:
                            # "9階 / 10階建 (地下1階)" のような形式から階数情報を抽出
                            floor_match = re.search(r'(\d+)階\s*/\s*(\d+)階建', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                                # 地下情報も含めて総階数を取得
                                property_data['total_floors'] = int(floor_match.group(2))
                                basement_match = re.search(r'地下(\d+)階', value)
                                if basement_match:
                                    property_data['basement_floors'] = int(basement_match.group(1))
                                else:
                                    property_data['basement_floors'] = 0
                        elif '築年月' in label:
                            # 築年を抽出
                            year_match = re.search(r'(\d{4})年', value)
                            if year_match:
                                from datetime import datetime
                                property_data['built_year'] = int(year_match.group(1))
                                property_data['age'] = datetime.now().year - int(year_match.group(1))
                        elif 'バルコニー面積' in label or 'バルコニー' in label and '面積' in value:
                            # バルコニー面積
                            area_match = re.search(r'([\d.]+)', value)
                            if area_match:
                                property_data['balcony_area'] = float(area_match.group(1))
                        elif '備考' in label:
                            # 備考
                            property_data['remarks'] = value
                        elif '権利' in label and ('土地' in label or '敷地' in label):
                            # 権利形態
                            property_data['land_rights'] = value
                        elif '駐車' in label:
                            # 駐車場
                            property_data['parking_info'] = value
                        elif '主要採光面' in label:
                            # 主要採光面から方角を取得
                            direction_patterns = ['南東', '南西', '北東', '北西', '南', '北', '東', '西']
                            for direction in direction_patterns:
                                if direction in value:
                                    property_data['direction'] = direction
                                    print(f"    主要採光面: {property_data['direction']}")
                                    break
                        elif '情報提供日' in label or '情報公開日' in label or '情報更新日' in label or '登録日' in label:
                            # 情報提供日を取得
                            # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                            date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                            if date_match:
                                year = int(date_match.group(1))
                                month = int(date_match.group(2))
                                day = int(date_match.group(3))
                                property_data['published_at'] = datetime(year, month, day)
                                print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # 情報公開日を探す（物件概要以外のセクションも確認）
            # パターン1: class="date"や"update"を含む要素
            date_elements = soup.select('[class*="date"], [class*="update"], [class*="公開"], [class*="info"]')
            for elem in date_elements:
                text = elem.get_text(strip=True)
                if '情報公開日' in text or '掲載日' in text or '登録日' in text:
                    print(f"    [DEBUG] 日付要素発見: {text}")
                    # 日付パターンを探す
                    date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', text)
                    if date_match:
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        property_data['published_at'] = datetime(year, month, day)
                        print(f"    情報公開日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                        break
            
            # パターン3: HOMESの特定パターン - テキストノードから直接探す
            if 'published_at' not in property_data:
                # ページ内の全テキストから情報公開日パターンを探す
                # "情報公開日：2025年7月17日" または "情報公開日：2025/06/29"のようなパターンを探す
                date_pattern = re.search(r'情報公開日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', page_text)
                if date_pattern:
                    year = int(date_pattern.group(1))
                    month = int(date_pattern.group(2))
                    day = int(date_pattern.group(3))
                    property_data['published_at'] = datetime(year, month, day)
                    print(f"    情報公開日(テキストから): {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # パターン2: dt/dd形式の定義リスト
            dl_elements = soup.select('dl')
            for dl in dl_elements:
                dt_elements = dl.select('dt')
                dd_elements = dl.select('dd')
                for i, dt in enumerate(dt_elements):
                    if i < len(dd_elements):
                        label = dt.get_text(strip=True)
                        value = dd_elements[i].get_text(strip=True)
                        if '情報公開日' in label or '掲載日' in label or '登録日' in label:
                            print(f"    [DEBUG] DL形式で日付発見: {label} = {value}")
                            date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                            if date_match:
                                year = int(date_match.group(1))
                                month = int(date_match.group(2))
                                day = int(date_match.group(3))
                                property_data['published_at'] = datetime(year, month, day)
                                print(f"    情報公開日: {property_data['published_at'].strftime('%Y-%m-%d')}")
                                break
            
            # 不動産会社情報を探す（HOMESの会社情報セクション）
            # パターン1: 会社情報セクション内のテーブルから
            company_sections = soup.select('.companyInfo, .company-info, [class*="company"]')
            for company_section in company_sections:
                print("    [DEBUG] 会社情報セクションを発見")
                # テーブル形式の情報を探す
                company_tables = company_section.select('table')
                for table in company_tables:
                    rows = table.select('tr')
                    for row in rows:
                        cells = row.select('th, td')
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            
                            if '会社名' in label or '社名' in label:
                                property_data['agency_name'] = value
                                print(f"    不動産会社名(テーブルから): {property_data['agency_name']}")
                            elif 'TEL' in label or '電話' in label:
                                # 電話番号パターンを抽出（日本の電話番号形式）
                                tel_match = re.search(r'[\d\-\(\)]+', value)
                                if tel_match:
                                    tel = tel_match.group(0)
                                    # 括弧を除去してハイフン形式に統一
                                    tel = tel.replace('(', '').replace(')', '-')
                                    property_data['agency_tel'] = tel
                                    print(f"    電話番号: {property_data['agency_tel']}")
            
            # パターン2: ページ全体から会社名を探す
            if 'agency_name' not in property_data:
                # "会社名"や"取扱会社"の後のテキストを探す
                company_pattern = re.search(r'(?:会社名|取扱会社|情報提供元)[：:]\s*([^\n]+)', page_text)
                if company_pattern:
                    company_name = company_pattern.group(1).strip()
                    # 不要な文字を除去
                    company_name = company_name.split('　')[0]  # 全角スペースで分割
                    company_name = company_name.split(' ')[0]   # 半角スペースで分割
                    if len(company_name) > 2 and '株式会社' in company_name or '有限会社' in company_name:
                        property_data['agency_name'] = company_name
                        print(f"    不動産会社名(テキストから): {property_data['agency_name']}")
            
            # パターン3: 問合せ先から会社名を探す
            if 'agency_name' not in property_data:
                inquiry_pattern = re.search(r'問合せ先[：:]\s*([^\n]+)', page_text)
                if inquiry_pattern:
                    company_text = inquiry_pattern.group(1).strip()
                    # 会社名部分を抽出（株式会社などを含む）
                    # 会社名の後に続く不要なテキスト（会社情報、ポイントなど）を除去
                    company_match = re.search(r'((?:株式会社|有限会社)?[^\s　]+(?:株式会社|有限会社)?)', company_text)
                    if company_match:
                        company_name = company_match.group(1)
                        # 「会社情報」「ポイント」などの不要な文字列を除去
                        company_name = re.sub(r'(会社情報|ポイント|〜).*$', '', company_name).strip()
                        if company_name and len(company_name) > 2:
                            property_data['agency_name'] = company_name
                            print(f"    不動産会社名(問合せ先から): {property_data['agency_name']}")
            
            # 電話番号をページ全体から探す（まだ取得できていない場合）
            if 'agency_tel' not in property_data:
                # 問合せ先の電話番号パターン
                tel_pattern = re.search(r'(?:TEL|電話|問合せ)[：:]\s*([\d\-\(\)]+)', page_text)
                if tel_pattern:
                    tel = tel_pattern.group(1)
                    # 括弧を除去してハイフン形式に統一
                    tel = tel.replace('(', '').replace(')', '-')
                    property_data['agency_tel'] = tel
                    print(f"    電話番号(テキストから): {property_data['agency_tel']}")
            
            # 画像URL（複数枚対応）
            image_urls = []
            # メイン画像
            main_image = soup.select_one('.mainPhoto img, .photo img, [class*="main-image"] img')
            if main_image and main_image.get('src'):
                image_urls.append(urljoin(self.BASE_URL, main_image.get('src')))
            
            # サブ画像
            sub_images = soup.select('.subPhoto img, .thumbs img, [class*="sub-image"] img, .gallery img')
            for img in sub_images[:9]:  # 最大10枚（メイン1枚 + サブ9枚）
                if img.get('src'):
                    image_urls.append(urljoin(self.BASE_URL, img.get('src')))
            
            property_data['image_urls'] = image_urls
            if image_urls:
                property_data['image_url'] = image_urls[0]  # 後方互換性のため
            
            # 物件説明
            description_elem = soup.select_one('.comment, .pr-comment, [class*="description"]')
            if description_elem:
                property_data['description'] = description_elem.get_text(strip=True)
            
            # 不動産会社情報を取得
            agency_elem = soup.select_one('.companyName, .agency-name, [class*="company"]')
            if agency_elem:
                property_data['agency_name'] = agency_elem.get_text(strip=True)
            
            # 不動産会社の電話番号
            tel_elem = soup.select_one('.tel, .phone, [class*="tel"]')
            if tel_elem:
                tel_text = tel_elem.get_text(strip=True)
                # 電話番号のパターンをマッチ
                tel_match = re.search(r'[\d\-\(\)]+', tel_text)
                if tel_match:
                    property_data['agency_tel'] = tel_match.group(0)
            
            # デフォルト値設定
            property_data.setdefault('building_type', 'マンション')
            property_data.setdefault('address', '東京都港区')
            
            # 必須フィールドのチェック
            # 建物ページの場合は、建物名があればOK（価格は個別物件ページで取得）
            if 'building_name' in property_data or 'title' in property_data:
                return property_data
            else:
                self.logger.warning(f"Required fields missing for {url}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error parsing property detail from {url}: {e}")
            return None
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと最小限の情報のみを抽出"""
        properties = []
        
        # 物件リストを取得（2025年7月版のセレクタ）
        property_items = soup.select('.mod-mergeBuilding--sale')
        
        if not property_items:
            # 別のセレクタも試す
            property_items = soup.select('.mod-mergeBuilding')
        
        for item in property_items:
            property_data = {}
            
            # 物件詳細へのリンク
            # パターン1: h3.heading内のリンク
            link = item.select_one('h3.heading a[href*="/mansion/b-"]')
            if not link:
                # パターン2: 直接リンク
                link = item.select_one('a[href*="/mansion/b-"]')
            
            if link:
                property_data['url'] = urljoin(self.BASE_URL, link.get('href'))
                
                # 建物名を取得（一時的な識別用）
                building_name = link.get_text(strip=True)
                if building_name.startswith('中古マンション'):
                    building_name = building_name.replace('中古マンション', '').strip()
                property_data['building_name'] = building_name
            
            # 新着・更新マークを検出（詳細ページ取得の判定用）
            new_icon = item.select_one('.newIcon, .icon-new')
            is_new = bool(new_icon and 'NEW' in new_icon.get_text(strip=True))
            is_updated = bool(item.select_one('.labelUpdate, .label--update, .icon-update, [class*="updateIcon"], [class*="update-label"]'))
            property_data['has_update_mark'] = is_new or is_updated
            
            # 更新日の取得（もしあれば）
            update_date_elem = item.select_one('.updateDate, .update-date, [class*="update-time"]')
            if update_date_elem:
                update_text = update_date_elem.get_text(strip=True)
                date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', update_text)
                if date_match:
                    property_data['list_update_date'] = date_match.group(1)
            
            # URLと建物名があれば追加（価格は詳細ページから取得）
            if property_data.get('url') and property_data.get('building_name'):
                properties.append(property_data)
        
        return properties
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング（スマート版）"""
        if self.force_detail_fetch:
            print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
        
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            search_url = self.get_search_url(area, page)
            soup = self.fetch_page(search_url)
            
            if not soup:
                print(f"ページ {page} の取得に失敗しました")
                break
            
            # 物件情報を一覧から抽出
            properties = self.parse_property_list(soup)
            
            if not properties:
                print(f"ページ {page} に物件が見つかりません")
                break
            
            print(f"ページ {page} で {len(properties)} 件の物件を発見")
            all_properties.extend(properties)
            
            # 最大件数に達した場合は終了
            if self.max_properties and len(all_properties) >= self.max_properties:
                all_properties = all_properties[:self.max_properties]
                print(f"最大取得件数（{self.max_properties}件）に達しました")
                break
            
            # ページ間で遅延
            time.sleep(self.delay)
        
        # 各物件を保存
        print(f"\\n合計 {len(all_properties)} 件の物件を処理します...")
        
        saved_count = 0
        
        for i, property_data in enumerate(all_properties, 1):
            print(f"[{i}/{len(all_properties)}] {property_data.get('building_name', 'Unknown')}")
            print(f"  URL: {property_data.get('url')}")
            
            try:
                # 既存の掲載を確認
                existing_listing = self.session.query(PropertyListing).filter(
                    PropertyListing.url == property_data['url']
                ).first()
                
                # 詳細ページの取得が必要かチェック
                needs_detail = True
                if existing_listing:
                    needs_detail = self.needs_detail_fetch(existing_listing)
                    if not needs_detail:
                        print(f"  → 詳細ページの取得をスキップ（最終取得: {existing_listing.detail_fetched_at}）")
                        # 一覧ページの情報で更新マークだけ更新
                        self.update_listing_from_list(existing_listing, property_data)
                        saved_count += 1
                        continue
                
                # 詳細ページから全ての情報を取得
                detail_data = self.parse_property_detail(property_data['url'])
                if not detail_data:
                    print(f"  → 詳細ページの取得に失敗しました")
                    continue
                
                # 詳細データで property_data を更新
                property_data.update(detail_data)
                
                # 価格が取得できているか確認
                if not property_data.get('price'):
                    print(f"  → 価格情報が取得できませんでした")
                    continue
                
                print(f"  価格: {property_data.get('price')}万円")
                print(f"  間取り: {property_data.get('layout', '不明')}")
                print(f"  面積: {property_data.get('area', '不明')}㎡")
                print(f"  階数: {property_data.get('floor_number', '不明')}階")
                
                # 建物を取得または作成
                building, extracted_room_number = self.get_or_create_building(
                    property_data.get('building_name', ''),
                    property_data.get('address', ''),
                    built_year=property_data.get('built_year'),
                    total_floors=property_data.get('total_floors'),
                    basement_floors=property_data.get('basement_floors'),
                    total_units=property_data.get('total_units'),
                    structure=property_data.get('structure'),
                    land_rights=property_data.get('land_rights'),
                    parking_info=property_data.get('parking_info')
                )
                
                if not building:
                    print(f"  → 建物情報が不足")
                    continue
                
                # 部屋番号の決定（抽出された部屋番号を優先）
                room_number = property_data.get('room_number', '')
                if extracted_room_number and not room_number:
                    room_number = extracted_room_number
                    print(f"  → 建物名から部屋番号を抽出: {room_number}")
                
                # マスター物件を取得または作成
                master_property = self.get_or_create_master_property(
                    building=building,
                    room_number=room_number,
                    floor_number=property_data.get('floor_number'),
                    area=property_data.get('area'),
                    layout=property_data.get('layout'),
                    direction=property_data.get('direction'),
                    url=property_data.get('url')
                )
                
                # バルコニー面積を設定
                if property_data.get('balcony_area'):
                    master_property.balcony_area = property_data['balcony_area']
                
                # 掲載情報を作成または更新
                listing = self.create_or_update_listing(
                    master_property=master_property,
                    url=property_data.get('url', ''),
                    title=property_data.get('title', property_data.get('building_name', '')),
                    price=property_data.get('price'),
                    agency_name=property_data.get('agency_name'),
                    station_info=property_data.get('station_info'),
                    management_fee=property_data.get('management_fee'),
                    repair_fund=property_data.get('repair_fund'),
                    description=property_data.get('description'),
                    published_at=property_data.get('published_at'),
                    first_published_at=property_data.get('first_published_at'),
                    # 掲載サイトごとの物件属性
                    listing_floor_number=property_data.get('floor_number'),
                    listing_area=property_data.get('area'),
                    listing_layout=property_data.get('layout'),
                    listing_direction=property_data.get('direction'),
                    listing_total_floors=property_data.get('total_floors'),
                    listing_balcony_area=property_data.get('balcony_area'),
                    listing_address=building.address if building else None
                )
                
                # agency_telとremarksは別途設定
                if property_data.get('agency_tel'):
                    listing.agency_tel = property_data['agency_tel']
                if property_data.get('remarks'):
                    listing.remarks = property_data['remarks']
                
                # 一覧ページの情報で更新（新着・更新マークなど）
                self.update_listing_from_list(listing, property_data)
                
                # 画像を追加
                if property_data.get('image_urls'):
                    self.add_property_images(listing, property_data['image_urls'])
                
                # 詳細情報を保存
                listing.detail_info = {
                    'age': property_data.get('age'),
                    'floor': property_data.get('floor'),
                    'total_floors': property_data.get('total_floors')
                }
                listing.detail_fetched_at = datetime.now()
                
                # 多数決による物件情報更新
                self.update_master_property_by_majority(master_property)
                
                saved_count += 1
                print(f"  → 保存完了")
                
            except Exception as e:
                print(f"  → エラー: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 変更をコミット
        self.session.commit()
        print(f"\\nスクレイピング完了: {saved_count} 件保存")
    
    def fetch_and_update_detail(self, listing) -> bool:
        """詳細ページを取得して情報を更新"""
        try:
            # 詳細ページを取得
            detail_data = self.parse_property_detail(listing.url)
            if not detail_data:
                return False
            
            detail_info = {}
            
            # マスター物件の情報を更新
            if detail_data.get('floor_number') and not listing.master_property.floor_number:
                listing.master_property.floor_number = detail_data['floor_number']
                print(f"    階数を更新: {detail_data['floor_number']}階")
            
            if detail_data.get('area') and not listing.master_property.area:
                listing.master_property.area = detail_data['area']
                print(f"    面積を更新: {detail_data['area']}㎡")
            
            if detail_data.get('layout') and not listing.master_property.layout:
                listing.master_property.layout = detail_data['layout']
                print(f"    間取りを更新: {detail_data['layout']}")
            
            if detail_data.get('direction') and not listing.master_property.direction:
                listing.master_property.direction = detail_data['direction']
                print(f"    方角を更新: {detail_data['direction']}")
            
            # 部屋番号を更新
            if detail_data.get('room_number') and not listing.master_property.room_number:
                listing.master_property.room_number = detail_data['room_number']
                print(f"    部屋番号を更新: {detail_data['room_number']}")
            
            # バルコニー面積を更新
            if detail_data.get('balcony_area') and not listing.master_property.balcony_area:
                listing.master_property.balcony_area = detail_data['balcony_area']
                print(f"    バルコニー面積を更新: {detail_data['balcony_area']}㎡")
            
            # 掲載情報を更新
            if detail_data.get('description'):
                listing.description = detail_data['description']
            
            if detail_data.get('station_info'):
                listing.station_info = detail_data['station_info']
            
            if detail_data.get('management_fee'):
                listing.management_fee = detail_data['management_fee']
                print(f"    管理費を更新: {detail_data['management_fee']}円")
            
            if detail_data.get('repair_fund'):
                listing.repair_fund = detail_data['repair_fund']
                print(f"    修繕積立金を更新: {detail_data['repair_fund']}円")
            
            # 不動産会社情報を更新
            if detail_data.get('agency_name'):
                listing.agency_name = detail_data['agency_name']
                print(f"    不動産会社を更新: {detail_data['agency_name']}")
            
            if detail_data.get('agency_tel'):
                listing.agency_tel = detail_data['agency_tel']
                print(f"    不動産会社電話番号を更新: {detail_data['agency_tel']}")
            
            # 備考を更新
            if detail_data.get('remarks'):
                listing.remarks = detail_data['remarks']
                print(f"    備考を更新")
            
            # 画像を追加
            if detail_data.get('image_urls'):
                self.add_property_images(listing, detail_data['image_urls'])
            elif detail_data.get('image_url'):
                self.add_property_images(listing, [detail_data['image_url']])
            
            # 建物情報を更新
            building = listing.master_property.building
            if detail_data.get('total_floors') and not building.total_floors:
                building.total_floors = detail_data['total_floors']
                print(f"    総階数を更新: {detail_data['total_floors']}階")
            
            if detail_data.get('basement_floors') is not None and not building.basement_floors:
                building.basement_floors = detail_data['basement_floors']
                if detail_data['basement_floors'] > 0:
                    print(f"    地下階数を更新: {detail_data['basement_floors']}階")
            
            if detail_data.get('structure') and not building.structure:
                building.structure = detail_data['structure']
                print(f"    構造を更新: {detail_data['structure']}")
            
            if detail_data.get('land_rights') and not building.land_rights:
                building.land_rights = detail_data['land_rights']
                print(f"    権利形態を更新: {detail_data['land_rights']}")
            
            if detail_data.get('parking_info') and not building.parking_info:
                building.parking_info = detail_data['parking_info']
                print(f"    駐車場情報を更新: {detail_data['parking_info']}")
            
            if detail_data.get('built_year') and not building.built_year:
                building.built_year = detail_data['built_year']
                print(f"    築年を更新: {detail_data['built_year']}年")
            
            # 詳細情報を保存
            for key in ['age', 'floor', 'total_floors']:
                if key in detail_data:
                    detail_info[key] = detail_data[key]
            
            listing.detail_info = detail_info
            listing.detail_fetched_at = datetime.now()
            listing.has_update_mark = False  # 更新マークをクリア
            
            self.session.commit()
            return True
            
        except Exception as e:
            print(f"    詳細ページ取得エラー: {e}")
            return False