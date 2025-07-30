"""
SUUMOスクレイパー v3
一覧ページから直接情報を収集
"""

import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup

from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date
)


class SuumoScraper(BaseScraper):
    """SUUMOのスクレイパー（v3 - 一覧ページベース）"""
    
    BASE_URL = "https://suumo.jp"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(SourceSite.SUUMO, force_detail_fetch, max_properties)
        # 建物名取得エラーの履歴（メモリ内管理）
        self._building_name_error_cache = {}  # {url: timestamp}
    
    def scrape_area(self, area: str, max_pages: int = None):
        """エリアの物件をスクレイピング
        
        Args:
            area: エリアコード（13101, 13102など）
            max_pages: 最大ページ数（使用しない）
        """
        # 共通ロジックを使用（エリアコードを渡す）
        # 注意: _area_romajiの設定は削除（スレッドセーフでないため）
        return self.common_scrape_area_logic(area)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（SUUMOスクレイパー固有の実装）"""
        try:
            # process_property_with_detail_checkを直接呼び出す
            result = self.process_property_with_detail_check(
                property_data=property_data,
                existing_listing=existing_listing,
                parse_detail_func=self.parse_property_detail,
                save_property_func=self._save_property_after_detail
            )
            # detail_fetchedフラグは既にprocess_property_with_detail_check内で設定されているため、
            # ここでの二重設定は不要（削除）
            return result
        except Exception as e:
            # エラーは呼び出し元で処理されるので、ここでは再スロー
            raise
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """SUUMOの検索URLを生成（100件/ページ）
        
        Args:
            area: エリアコード（common_scrape_area_logicから渡される）
            page: ページ番号
        """
        # SUUMOの中古マンション検索URL
        # 東京都のエリア別URL形式: /ms/chuko/tokyo/sc_[area]/
        # pc=100で100件表示を指定
        
        # エリアコードからローマ字を取得
        if area.isdigit() and len(area) == 5:
            # エリアコードの場合はローマ字に変換
            from ..scrapers.area_config import get_area_romaji_from_code
            area_romaji = get_area_romaji_from_code(area)
        else:
            # すでにローマ字の場合はそのまま使用
            area_romaji = area
        
        # 中古マンション検索用URL
        if page == 1:
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc=100"
        else:
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc=100&page={page}"
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと最小限の情報のみを抽出"""
        properties = []
        
        # SUUMOの物件リストセレクタ（新旧両方のフォーマットに対応）
        property_units = soup.select('.property_unit')
        
        # 新形式のセレクタも試す
        if not property_units:
            property_units = soup.select('.cassette')
        
        for unit in property_units:
            property_data = {}
            
            # 物件詳細へのリンク（タイトルリンクを取得）
            title_link = unit.select_one('.property_unit-title a')
            if title_link:
                property_data['url'] = urljoin(self.BASE_URL, title_link.get('href'))
                property_data['site_property_id'] = self.extract_property_id(property_data['url'])
            
            # 新着・更新マークを検出（詳細ページ取得の判定用）
            is_new = bool(unit.select_one('.property_unit-newmark, .icon_new, [class*="new"]'))
            is_updated = bool(unit.select_one('.property_unit-update, .icon_update, [class*="update"]'))
            property_data['has_update_mark'] = is_new or is_updated
            
            # 価格を取得（一覧ページから）
            price_elem = unit.select_one('.dottable-value')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # データ正規化フレームワークを使用して価格を抽出
                property_data['price'] = extract_price(price_text)
            
            # URLが取得できた物件を追加
            if property_data.get('url'):
                properties.append(property_data)
        
        # SUUMOの100件表示チェック
        if len(properties) == 100:
            print("  → 100件取得（最大表示件数）")
        
        return properties
    
    def extract_property_id(self, url: str) -> str:
        """URLから物件IDを抽出"""
        match = re.search(r'/nc_(\d+)/', url)
        return match.group(1) if match else url.split('/')[-1]
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（スマートスクレイピング対応）"""
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self._save_property_after_detail
        )
    
    def _save_property_after_detail(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """詳細データ取得後の保存処理（内部メソッド）"""
        # 共通の保存処理を使用（例外処理はbase_scraperで行う）
        return self.save_property_common(property_data, existing_listing)
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            # 特定物件のデバッグログ
            if 'nc_76583217' in url:
                self.logger.info(f"[DEBUG] nc_76583217の詳細ページ取得開始: {url}")
            
            # アクセス間隔を保つ
            time.sleep(self.delay)
            
            # 詳細ページを取得
            soup = self.fetch_page(url)
            if not soup:
                # record_errorは呼ばない（base_scraperでカウントされるため）
                return None
                
            # HTML構造の検証
            required_selectors = {
                '物件情報テーブル': 'table',
                'タイトル': 'h1, h2.section_h1-header-title',
            }
            
            if not self.validate_html_structure(soup, required_selectors):
                return None
                
            property_data = {
                'url': url,
                'site_property_id': self.extract_property_id(url)
            }
            
            detail_info = {}
            
            # 価格を最初に取得（複数のセレクタを試す）
            price_found = False
            
            # まずテーブルから価格を探す（最も確実）
            all_tables = soup.find_all('table')
            for table in all_tables:
                if price_found:
                    break
                rows = table.find_all('tr')
                for row in rows:
                    th = row.select_one('th')
                    td = row.select_one('td')
                    if th and td:
                        label = th.get_text(strip=True)
                        value = td.get_text(strip=True)
                        if '価格' in label and ('万円' in value or '億円' in value):
                            # データ正規化フレームワークを使用して価格を抽出
                            price = extract_price(value)
                            if price:
                                property_data['price'] = price
                                print(f"    価格: {property_data['price']}万円")
                                price_found = True
                                break
            
            # 詳細情報を抽出
            # 1. 物件概要テーブル - すべてのテーブルから該当情報を探す
            all_tables = soup.find_all('table')
            for table in all_tables:
                rows = table.find_all('tr')
                for row in rows:
                    # 複数のth/tdペアがある可能性があるため、すべて処理
                    th_elements = row.find_all('th')
                    td_elements = row.find_all('td')
                    
                    for i, th in enumerate(th_elements):
                        if i < len(td_elements):
                            td = td_elements[i]
                            label = th.get_text(strip=True)
                            value = td.get_text(strip=True)
                        
                        # 所在階（単独のフィールド）
                        if label == '所在階' or (label.endswith('ヒント') and '所在階' in label):
                            # データ正規化フレームワークを使用して階数を抽出
                            floor_number = extract_floor_number(value)
                            if floor_number is not None:
                                property_data['floor_number'] = floor_number
                                print(f"    所在階: {property_data['floor_number']}階")
                        
                        # 向き（単独のフィールド）
                        elif label == '向き' or (label.endswith('ヒント') and '向き' in label):
                            # データ正規化フレームワークを使用して方角を正規化
                            direction = normalize_direction(value)
                            if direction:
                                property_data['direction'] = direction
                                print(f"    向き: {property_data['direction']}")
                        
                        # 住所（単独のフィールド）
                        elif label == '住所' or label == '所在地':
                            # td内に複数のp要素がある場合は最初のp要素のテキストを取得
                            first_p = td.find('p')
                            if first_p:
                                property_data['address'] = first_p.get_text(strip=True)
                            else:
                                property_data['address'] = value
                            print(f"    住所: {property_data['address']}")
                        
                        # 所在階/構造・階建（複合フィールド - フォールバック用）
                        elif '所在階' in label and '構造' in label and 'floor_number' not in property_data:
                            # 「4階/SRC9階建一部RC」のようなパターンから所在階と総階数を抽出
                            floor_pattern = re.search(r'^(\d+)階/', value)
                            if floor_pattern:
                                property_data['floor_number'] = int(floor_pattern.group(1))
                                print(f"    所在階: {property_data['floor_number']}階")
                            
                            # 総階数を抽出
                            total_floors_match = re.search(r'(\d+)階建', value)
                            if total_floors_match:
                                detail_info['total_floors'] = int(total_floors_match.group(1))
                                print(f"    総階数: {detail_info['total_floors']}階")
                        
                        # 構造・階建て（単独のフィールド）
                        elif label == '構造・階建て' or (label.endswith('ヒント') and '構造・階建て' in label):
                            # 構造情報を保存（フルテキスト）
                            detail_info['structure_full'] = value
                            print(f"    構造（フル）: {value}")
                            
                            # データ正規化フレームワークを使用して総階数と地下階数を抽出
                            from . import extract_total_floors
                            total_floors, basement_floors = extract_total_floors(value)
                            
                            # 明らかに間違った総階数（1階など）の場合は無視
                            # 「RC1階地下2階建」のようなパターンは総階数が正しく抽出できない
                            if total_floors is not None and total_floors > 1:
                                detail_info['total_floors'] = total_floors
                                print(f"    総階数: {detail_info['total_floors']}階")
                            elif total_floors == 1 and '地下' in value:
                                # 地下があるのに総階数1階は不自然なのでスキップ
                                print(f"    総階数: 不明（構造情報から正確に抽出できません: {value}）")
                            elif total_floors is not None:
                                detail_info['total_floors'] = total_floors
                                print(f"    総階数: {detail_info['total_floors']}階")
                                
                            if basement_floors is not None:
                                detail_info['basement_floors'] = basement_floors
                                if basement_floors > 0:
                                    print(f"    地下階数: {detail_info['basement_floors']}階")
                            
                            # 構造種別を抽出
                            structure_match = re.search(r'(RC|SRC|S造|木造|鉄骨)', value)
                            if structure_match:
                                detail_info['structure'] = structure_match.group(1)
                        
                        # 階数情報を取得（別形式のフィールドから）
                        elif '階' in label and '建物' not in label and '構造' not in label:
                            floor_match = re.search(r'(\d+)階', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                                print(f"    階数: {property_data['floor_number']}階")
                        
                        # 建物の総階数を取得（別形式のフィールドから）
                        elif '構造' in label and '階建' in label and '所在階' not in label and 'total_floors' not in detail_info:
                            # スラッシュで分割してからパターンマッチ
                            parts = value.split('/')
                            structure_part = parts[-1] if len(parts) > 1 else value
                            
                            # データ正規化フレームワークを使用
                            from . import extract_total_floors
                            total_floors, basement_floors = extract_total_floors(structure_part)
                            if total_floors is not None:
                                detail_info['total_floors'] = total_floors
                                if basement_floors is not None and basement_floors > 0:
                                    detail_info['basement_floors'] = basement_floors
                                    print(f"    総階数: {detail_info['total_floors']}階（地下{detail_info['basement_floors']}階）")
                                else:
                                    detail_info['basement_floors'] = 0
                                    print(f"    総階数: {detail_info['total_floors']}階")
                            
                            # 構造も保存（まだ保存されていない場合）
                            if 'structure' not in detail_info:
                                structure_match = re.search(r'(RC|SRC|S造|木造|鉄骨)', structure_part)
                                if structure_match:
                                    detail_info['structure'] = structure_match.group(1)
                        
                        # 総戸数を取得
                        if '総戸数' in label:
                            units_match = re.search(r'(\d+)戸', value)
                            if units_match:
                                detail_info['total_units'] = int(units_match.group(1))
                                print(f"    総戸数: {detail_info['total_units']}戸")
                        
                        # 物件名（建物名）を取得
                        if '物件名' in label:
                            property_data['building_name'] = value
                            property_data['building_name_source'] = 'table'  # 取得元を記録
                            print(f"    物件名: {property_data['building_name']}")
                        
                        # 部屋番号を取得
                        if '部屋番号' in label or '号室' in label:
                            property_data['room_number'] = value
                            print(f"    部屋番号: {property_data['room_number']}")
                        
                        # バルコニー面積
                        if 'バルコニー' in label or 'バルコニー' in value or ('その他面積' in label):
                            # データ正規化フレームワークを使用して面積を抽出
                            balcony_area = extract_area(value)
                            if balcony_area:
                                property_data['balcony_area'] = balcony_area
                                print(f"    バルコニー面積: {balcony_area}㎡")
                        
                        # 価格（テーブルからも取得を試みる）
                        if '価格' in label and ('万円' in value or '億円' in value) and 'price' not in property_data:
                            # データ正規化フレームワークを使用して価格を抽出
                            price = extract_price(value)
                            if price:
                                property_data['price'] = price
                                print(f"    価格（テーブルから）: {property_data['price']}万円")
                        
                        # 間取り
                        elif '間取り' in label:
                            # デバッグ: 特定物件の間取り取得
                            if 'nc_76583217' in url:
                                self.logger.info(f"[DEBUG] nc_76583217 - 間取りフィールド発見: label='{label}', value='{value}'")
                            # データ正規化フレームワークを使用して間取りを正規化
                            layout = normalize_layout(value)
                            if layout:
                                property_data['layout'] = layout
                                if 'nc_76583217' in url:
                                    self.logger.info(f"[DEBUG] nc_76583217 - 間取り設定: {layout}")
                        
                        # 専有面積
                        elif '専有面積' in label:
                            # デバッグ: 特定物件の面積取得
                            if 'nc_76583217' in url:
                                self.logger.info(f"[DEBUG] nc_76583217 - 専有面積フィールド発見: label='{label}', value='{value}'")
                            # データ正規化フレームワークを使用して面積を抽出
                            area = extract_area(value)
                            if area:
                                property_data['area'] = area
                                if 'nc_76583217' in url:
                                    self.logger.info(f"[DEBUG] nc_76583217 - 面積設定: {area}㎡")
                        
                        # 築年月から築年を取得
                        elif '築年月' in label:
                            # データ正規化フレームワークを使用して築年を抽出
                            built_year = extract_built_year(value)
                            if built_year:
                                property_data['built_year'] = built_year
                        
                        # 交通情報を取得
                        elif '交通' in label or 'アクセス' in label:
                            # 不要な文言を削除し、路線ごとに改行を入れる
                            station_info = value.replace('[乗り換え案内]', '')
                            # 各路線の開始位置で改行を入れる
                            station_info = re.sub(
                                r'(?=東京メトロ|都営|ＪＲ|京王|小田急|東急|京急|京成|新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス)',
                                '\n',
                                station_info
                            ).strip()
                            property_data['station_info'] = station_info
                            print(f"    交通: {station_info.replace(chr(10), ' / ')}")  # ログでは改行を / で表示
                        
                        # 敷地の権利形態を取得
                        elif '権利' in label and ('土地' in label or '敷地' in label):
                            detail_info['land_rights'] = value
                            print(f"    権利形態: {value}")
                        
                        # 駐車場情報を取得
                        elif '駐車' in label:
                            detail_info['parking_info'] = value
                            print(f"    駐車場: {value}")
                        
                        # 情報公開日を取得（初めて公開された日）
                        elif '情報公開日' in label or '情報登録日' in label or '登録日' in label:
                            # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                            date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                            if date_match:
                                year = int(date_match.group(1))
                                month = int(date_match.group(2))
                                day = int(date_match.group(3))
                                from datetime import datetime
                                # 情報公開日として保存
                                property_data['first_published_at'] = datetime(year, month, day)
                                # published_atにも設定（後方互換性のため）
                                if 'published_at' not in property_data:
                                    property_data['published_at'] = property_data['first_published_at']
                                print(f"    売出確認日: {property_data['first_published_at'].strftime('%Y-%m-%d')}")
                        
                        # 情報提供日を取得（最新の更新日）
                        elif '情報提供日' in label or '情報更新日' in label:
                            # 日付のパターンをマッチ（YYYY年MM月DD日 or YYYY/MM/DD or YYYY-MM-DD）
                            date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
                            if date_match:
                                year = int(date_match.group(1))
                                month = int(date_match.group(2))
                                day = int(date_match.group(3))
                                from datetime import datetime
                                property_data['published_at'] = datetime(year, month, day)
                                print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
            
            # 2. 設備・仕様情報
            facility_section = soup.select_one('.section-facilities, .property-spec')
            if facility_section:
                facilities = []
                facility_items = facility_section.select('li')
                for item in facility_items:
                    facilities.append(item.get_text(strip=True))
                detail_info['設備'] = facilities
            
            # 3. 不動産会社情報と管理費・修繕積立金
            # テーブルから情報を取得
            for table in all_tables:
                rows = table.find_all('tr')
                for row in rows:
                    # 1つの行に複数のth/tdペアがある可能性があるため、すべてのth要素を取得
                    th_elements = row.find_all('th')
                    td_elements = row.find_all('td')
                    
                    # th/tdペアを処理
                    for i, th in enumerate(th_elements):
                        if i < len(td_elements):
                            td = td_elements[i]
                            label = th.get_text(strip=True)
                            value = td.get_text(strip=True)
                            
                            # 会社概要から不動産会社情報を取得
                            if '会社概要' in label:
                                # 会社名を抽出（例: "(株)LIVEACE" の部分）
                                company_match = re.search(r'((?:株式会社|有限会社|\(株\)|\(有\))[\w\s]+)', value)
                                if company_match:
                                    property_data['agency_name'] = company_match.group(1).strip()
                                    print(f"    不動産会社: {property_data['agency_name']}")
                                
                                # 電話番号も探す（同じテキストから）
                                tel_pattern = re.compile(r'(0\d{1,4}-\d{1,4}-\d{4}|\d{10,11})')
                                tel_match = tel_pattern.search(value)
                                if tel_match:
                                    property_data['agency_tel'] = tel_match.group(0)
                                    print(f"    電話番号: {property_data['agency_tel']}")
                            
                            # 管理費
                            elif '管理費' in label and '修繕' not in label:
                                # 「1万3150円」のような万円パターンに対応
                                wan_match = re.search(r'(\d+)万([\d,]+)円', value)
                                if wan_match:
                                    man = int(wan_match.group(1)) * 10000
                                    yen = int(wan_match.group(2).replace(',', ''))
                                    property_data['management_fee'] = man + yen
                                    print(f"    管理費: {property_data['management_fee']}円（{wan_match.group(1)}万{wan_match.group(2)}円）")
                                else:
                                    # 通常の円パターン
                                    fee_match = re.search(r'([\d,]+)円', value)
                                    if fee_match:
                                        property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                                        print(f"    管理費: {property_data['management_fee']}円")
                            
                            # 修繕積立金
                            elif '修繕' in label:
                                # 「1万5460円」のような万円パターンに対応
                                # データ正規化フレームワークを使用して月額費用を抽出
                                repair_fund = extract_monthly_fee(value)
                                if repair_fund:
                                    property_data['repair_fund'] = repair_fund
                                    print(f"    修繕積立金: {property_data['repair_fund']}円")
                            
                            # 諸費用から管理費を抽出（SUUMOでは管理費が諸費用に含まれることがある）
                            elif '諸費用' in label and 'management_fee' not in property_data:
                                # 管理費のパターンを探す
                                management_patterns = [
                                    r'管理費[：:]?\s*([0-9,]+)円',
                                    r'管理[・･]\s*([0-9,]+)円',
                                    r'([0-9,]+)円[／/]月.*管理'
                                ]
                                for pattern in management_patterns:
                                    fee_match = re.search(pattern, value)
                                    if fee_match:
                                        property_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                                        print(f"    諸費用から管理費を抽出: {property_data['management_fee']}円")
                                        break
            
            # 4. 備考・特記事項
            # パターン1: 物件のセールスポイント・アピール
            remarks_text = ""
            
            # セールスポイントを探す
            sales_points = soup.find_all(['div', 'p'], class_=re.compile(r'sales|point|appeal|feature|comment', re.I))
            for elem in sales_points:
                text = elem.get_text(strip=True)
                if len(text) > 50 and not text.startswith('※'):  # 注意書きは除外
                    remarks_text = text
                    break
            
            # パターン2: 長い説明文
            if not remarks_text:
                for tag in ['p', 'div']:
                    long_texts = soup.find_all(tag)
                    for elem in long_texts:
                        text = elem.get_text(strip=True)
                        # 物件説明っぽい長文を探す
                        if (len(text) > 100 and 
                            any(kw in text for kw in ['立地', '環境', '駅', '徒歩', '生活', '便利']) and
                            not any(ng in text for ng in ['利用規約', 'Copyright', '個人情報', 'お問い合わせ'])):
                            remarks_text = text[:500]  # 最大500文字
                            break
                    if remarks_text:
                        break
            
            # パターン3: 既存のセレクタ
            if not remarks_text:
                remarks_section = soup.select_one('.remarks, .notes, .property-notes, [class*="remarks"]')
                if remarks_section:
                    remarks_text = remarks_section.get_text(strip=True)
            
            if remarks_text:
                property_data['remarks'] = remarks_text
                print(f"    備考を取得")
            
            # 5. 物件画像
            image_urls = []
            image_elements = soup.select('.property-view-photo img, .property-photo img')
            for img in image_elements:
                img_url = img.get('src', '')
                if img_url and not img_url.startswith('data:'):
                    # 相対URLを絶対URLに変換
                    img_url = urljoin(self.BASE_URL, img_url)
                    image_urls.append(img_url)
            
            if image_urls:
                property_data['image_urls'] = image_urls[:10]  # 最大10枚まで
            
            # 詳細情報を保存
            property_data['detail_info'] = detail_info
            
            # detail_infoの重要な情報をproperty_dataにも含める（後方互換性のため）
            if 'total_floors' in detail_info:
                property_data['total_floors'] = detail_info['total_floors']
            if 'basement_floors' in detail_info:
                property_data['basement_floors'] = detail_info['basement_floors']
            if 'total_units' in detail_info:
                property_data['total_units'] = detail_info['total_units']
            if 'structure' in detail_info:
                property_data['structure'] = detail_info['structure']
            if 'land_rights' in detail_info:
                property_data['land_rights'] = detail_info['land_rights']
            if 'parking_info' in detail_info:
                property_data['parking_info'] = detail_info['parking_info']
            
            # タイトルと説明文
            title_elem = soup.select_one('h1, .property-title, h2.section_h1-header-title')
            if title_elem:
                property_data['title'] = title_elem.get_text(strip=True)
                
                # 建物名が取得できていない場合、タイトルから抽出を試みる
                if 'building_name' not in property_data and property_data.get('title'):
                    # タイトルから建物名を抽出する
                    # 例: "パークリュクス御茶ノ水 7階" -> "パークリュクス御茶ノ水"
                    title_text = property_data['title']
                    # 階数情報を除去
                    building_name_match = re.match(r'^([^0-9]+?)(?:\s*\d+階)?(?:\s|$)', title_text)
                    if building_name_match:
                        building_name = building_name_match.group(1).strip()
                        # 一般的な接尾辞を除去
                        for suffix in ['の物件詳細', 'の詳細', '物件詳細', '詳細']:
                            if building_name.endswith(suffix):
                                building_name = building_name[:-len(suffix)].strip()
                        if building_name:
                            # タイトルから取得した場合は警告を出して処理を中断
                            # 初回のみエラーログを出力
                            if not self._has_recent_building_name_error(url):
                                self.logger.error(
                                    f"建物名がテーブルから取得できませんでした。"
                                    f"HTML構造が変更された可能性があります: {url}"
                                )
                                self._record_building_name_error(url)
                                self._scraping_stats['building_name_missing_new'] += 1
                            else:
                                self.logger.debug(f"建物名取得エラー（既知）: {url}")
                                
                            print(f"    [ERROR] 物件名がテーブルから取得できませんでした")
                            print(f"    [INFO] タイトルには「{building_name}」とありますが、信頼性が低いため使用しません")
                            # 統計情報を更新
                            self._scraping_stats['building_name_missing'] += 1
                            # 詳細取得失敗として扱う
                            return None
            
            # 建物名が全く取得できない場合も同様
            if 'building_name' not in property_data:
                # 初回のみエラーログを出力（過去24時間以内に同じURLでエラーが記録されていない場合）
                if not self._has_recent_building_name_error(url):
                    self.logger.error(f"建物名が取得できませんでした。HTML構造の確認が必要です: {url}")
                    self._record_building_name_error(url)
                    self._scraping_stats['building_name_missing_new'] += 1
                else:
                    self.logger.debug(f"建物名取得エラー（既知）: {url}")
                    
                print(f"    [ERROR] 物件名が取得できませんでした")
                # 統計情報を更新
                self._scraping_stats['building_name_missing'] = self._scraping_stats.get('building_name_missing', 0) + 1
                # 詳細取得失敗として扱う
                return None
            
            # 価格が取得できていない場合は、ページ全体から探す
            if 'price' not in property_data:
                page_text = soup.get_text()
                # データ正規化フレームワークを使用して価格を抽出
                price = extract_price(page_text)
                if price:
                    property_data['price'] = price
                    print(f"    価格（ページ全体から）: {property_data['price']}万円")
            
            # 必須フィールドのチェック
            missing_fields = []
            
            # 価格のチェック
            if 'price' not in property_data:
                missing_fields.append('price')
            
            # 専有面積のチェック（新規物件の場合は必須）
            if 'area' not in property_data and not existing_listing:
                missing_fields.append('area')
                
            # 間取りのチェック（新規物件の場合は必須）
            if 'layout' not in property_data and not existing_listing:
                missing_fields.append('layout')
            
            # エラーがある場合の処理
            if missing_fields:
                for field in missing_fields:
                    # 基底クラスのメソッドを使用してエラーを記録
                    self.record_field_extraction_error(field, url)
                
                print(f"    [ERROR] 必須フィールドが取得できませんでした: {', '.join(missing_fields)}")
                return None
            
            # すべての必須フィールドが揃っている場合
            if 'price' in property_data:
                # 建物名取得元の統計を更新
                if property_data.get('building_name_source'):
                    source = property_data['building_name_source']
                    if source == 'table':
                        self._scraping_stats['building_name_from_table'] += 1
                    elif source == 'title':
                        self._scraping_stats['building_name_from_title'] += 1
                    elif source == 'fallback':
                        self._scraping_stats['building_name_from_fallback'] += 1
                    # property_dataから削除（DBに保存する必要はない）
                    del property_data['building_name_source']
                
                # デバッグ: 特定物件の最終データ
                if 'nc_76583217' in url:
                    self.logger.info(f"[DEBUG] nc_76583217 - 最終データ: "
                                   f"price={property_data.get('price')}, "
                                   f"building_name={property_data.get('building_name')}, "
                                   f"area={property_data.get('area')}, "
                                   f"layout={property_data.get('layout')}")
                
                return property_data
            else:
                # 価格が取得できない場合
                # 基底クラスのメソッドを使用してエラーを記録
                self.record_field_extraction_error('price', url)
                
                print(f"    [ERROR] 価格が取得できませんでした")
                return None
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            self.logger.error(f"Error parsing property detail from {url}: {e}")
            return None
    
    def fetch_and_update_detail(self, listing: PropertyListing) -> bool:
        """詳細ページを取得して情報を更新（後方互換性のため残す）"""
        try:
            detail_data = self.parse_property_detail(listing.url)
            if not detail_data:
                return False
            
            # 必要な情報を更新
            if detail_data.get('management_fee') and not listing.management_fee:
                listing.management_fee = detail_data['management_fee']
            
            if detail_data.get('repair_fund') and not listing.repair_fund:
                listing.repair_fund = detail_data['repair_fund']
            
            if detail_data.get('agency_name') and not listing.agency_name:
                listing.agency_name = detail_data['agency_name']
            
            if detail_data.get('agency_tel') and not listing.agency_tel:
                listing.agency_tel = detail_data['agency_tel']
            
            if detail_data.get('remarks') and not listing.remarks:
                listing.remarks = detail_data['remarks']
            
            if detail_data.get('balcony_area') and not listing.master_property.balcony_area:
                listing.master_property.balcony_area = detail_data['balcony_area']
            
            # 建物情報も更新
            building = listing.master_property.building
            detail_info = detail_data.get('detail_info', {})
            
            if detail_info.get('total_floors') and not building.total_floors:
                building.total_floors = detail_info['total_floors']
            
            if detail_info.get('basement_floors') is not None and not building.basement_floors:
                building.basement_floors = detail_info['basement_floors']
            
            if detail_info.get('structure') and not building.structure:
                building.structure = detail_info['structure']
            
            if detail_info.get('land_rights') and not building.land_rights:
                building.land_rights = detail_info['land_rights']
            
            if detail_info.get('parking_info') and not building.parking_info:
                building.parking_info = detail_info['parking_info']
            
            listing.detail_info = detail_info
            listing.detail_fetched_at = datetime.now()
            listing.has_update_mark = False
            
            self.session.commit()
            return True
            
        except (TaskPausedException, TaskCancelledException):
            # タスクの一時停止・キャンセル例外は再スロー
            raise
        except Exception as e:
            print(f"    詳細ページ取得エラー: {e}")
            return False
    
    def _has_recent_building_name_error(self, url: str) -> bool:
        """最近（24時間以内）に建物名取得エラーが記録されているかチェック"""
        if url in self._building_name_error_cache:
            error_time = self._building_name_error_cache[url]
            hours_since_error = (datetime.now() - error_time).total_seconds() / 3600
            # 24時間以内のエラーは既知として扱う
            return hours_since_error < 24
        return False
    
    def should_skip_due_to_building_name_error(self, url: str) -> bool:
        """建物名取得エラーのためスキップすべきかチェック（一覧処理用）"""
        return self._has_recent_building_name_error(url)
    
    def _record_building_name_error(self, url: str):
        """建物名取得エラーを記録"""
        self._building_name_error_cache[url] = datetime.now()
        
        # キャッシュサイズが大きくなりすぎないよう、古いエントリを削除
        if len(self._building_name_error_cache) > 1000:
            # 24時間以上前のエントリを削除
            now = datetime.now()
            old_urls = [
                u for u, t in self._building_name_error_cache.items()
                if (now - t).total_seconds() > 86400  # 24時間
            ]
            for u in old_urls:
                del self._building_name_error_cache[u]
    
    
    def has_critical_errors(self, url: str) -> bool:
        """重要項目でエラーが発生している物件かチェック（後方互換性のため）"""
        # 基底クラスのメソッドを使用
        if self.has_critical_field_errors(url):
            return True
        # 後方互換性のため建物名エラーキャッシュもチェック
        if self._has_recent_building_name_error(url):
            return True
        return False