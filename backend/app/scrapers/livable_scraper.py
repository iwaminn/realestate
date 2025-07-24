"""
東急リバブルスクレイパー
"""

import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from ..models import PropertyListing
from .data_normalizer import DataNormalizer
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date
)


class LivableScraper(BaseScraper):
    """東急リバブルのスクレイパー"""
    
    BASE_URL = "https://www.livable.co.jp"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__("東急リバブル", force_detail_fetch, max_properties)
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        # 共通ロジックを使用
        return self.common_scrape_area_logic(area, max_pages)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self._save_property_after_detail
        )
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """東急リバブルの検索URLを生成"""
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 東急リバブルのURL形式
        # /kounyu/chuko-mansion/tokyo/a{area_code}/
        # ページネーション: ?page={page}
        base_url = f"{self.BASE_URL}/kounyu/chuko-mansion/tokyo/a{area_code}/"
        
        if page > 1:
            return f"{base_url}?page={page}"
        else:
            return base_url
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと基本情報を抽出"""
        properties = []
        
        # 物件リストアイテムを取得
        property_items = soup.select('.o-product-list__item')
        
        if not property_items:
            # 別のセレクタを試す
            property_items = soup.select('.o-map-search__property-item')
        
        for i, item in enumerate(property_items):
            property_data = {}
            
            # 物件詳細へのリンク
            link = item.select_one('a.o-product-list__link, a.o-map-search__property-link')
            if not link:
                link = item.select_one('a[href*="/kounyu/"]')
            
            if link:
                href = link.get('href', '')
                # 相対URLの場合は絶対URLに変換
                property_data['url'] = urljoin(self.BASE_URL, href)
                # URLから物件IDを抽出
                property_data['site_property_id'] = self.extract_property_id(href)
            
            # 新着・更新マークを検出
            new_tag = item.select_one('.a-tag--new-date')
            property_data['has_update_mark'] = bool(new_tag)
            
            # 建物名を取得
            headline = item.select_one('.o-product-list__headline')
            if headline:
                property_data['building_name'] = headline.get_text(strip=True)
            
            # 価格を取得
            price_elem = item.select_one('.o-product-list__info-body--price')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # DataNormalizerを使用して価格を解析
                property_data['price'] = extract_price(price_text)
            
            # URLが取得できた物件を追加
            if property_data.get('url'):
                # 建物名がない場合は仮の名前を設定
                if not property_data.get('building_name'):
                    property_data['building_name'] = f"物件_{property_data.get('site_property_id', 'unknown')}"
                properties.append(property_data)
        
        return properties
    
    def extract_property_id(self, url: str) -> str:
        """URLから物件IDを抽出"""
        # パターン1: /mansion/XXXXXXXX/
        match = re.search(r'/mansion/([A-Z0-9]+)/?', url)
        if match:
            return match.group(1)
        # パターン2: 最後の部分を取得（フォールバック）
        parts = url.rstrip('/').split('/')
        return parts[-1] if parts else 'unknown'
    
    def _save_property_after_detail(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """詳細データ取得後の保存処理（内部メソッド）"""
        # save_propertyメソッドを呼び出す
        self.save_property(property_data, existing_listing)
        return True
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（旧メソッド - 互換性のため残す）"""
        try:
            print(f"  URL: {property_data.get('url', 'URLなし')}")
            
            # 詳細データ取得後の完全な検証
            if not self.enhanced_validate_property_data(property_data):
                validation_errors = []
                if not property_data.get('building_name'):
                    validation_errors.append('建物名が不足')
                if not property_data.get('price'):
                    validation_errors.append('価格が不足')
                
                self.record_error(
                    error_type='validation',
                    url=property_data.get('url'),
                    building_name=property_data.get('building_name'),
                    property_data=property_data,
                    phase='enhanced_validation'
                )
                
                if validation_errors:
                    self.error_logger.log_validation_error(
                        property_data=property_data,
                        validation_errors=validation_errors,
                        field_names=list(property_data.keys())
                    )
                return
            
            # 価格が存在しない場合は保存しない
            if not property_data.get('price'):
                print(f"  → 価格情報なし、スキップ")
                self.record_price_missing()
                return
            
            # 建物を取得または作成
            # 詳細情報を取得
            detail_info = property_data.get('detail_info', {})
            
            # DataNormalizerを使用してtotal_floorsを正規化
            building_total_floors = normalize_integer(
                detail_info.get('total_floors'),
                field_name='total_floors'
            )
            
            # 建物を取得または作成
            building, extracted_room_number = self.get_or_create_building(
                building_name=property_data['building_name'],
                address=property_data.get('address'),
                built_year=property_data.get('built_year'),
                total_floors=building_total_floors,
                basement_floors=detail_info.get('basement_floors'),
                total_units=detail_info.get('total_units'),
                structure=detail_info.get('structure'),
                land_rights=detail_info.get('land_rights'),
                parking_info=detail_info.get('parking_info')
            )
            
            if not building:
                print(f"  → 建物情報が不足")
                self.record_building_info_missing()
                return
            
            # 部屋番号の決定（詳細ページから取得したものを優先）
            room_number = property_data.get('room_number') or extracted_room_number
            
            # マスター物件を取得または作成
            master_property = self.get_or_create_master_property(
                building=building,
                room_number=room_number,
                floor_number=property_data.get('floor_number'),
                area=property_data.get('area'),
                layout=property_data.get('layout'),
                direction=property_data.get('direction'),
                url=property_data['url'],
                current_price=property_data['price']
            )
            
            # 新規作成かどうかを事前に判定
            is_new_listing = existing_listing is None
            
            # DataNormalizerを使用してlisting_total_floorsを正規化
            listing_total_floors = normalize_integer(
                property_data.get('detail_info', {}).get('total_floors'),
                field_name='listing_total_floors'
            )
            
            # 掲載情報を作成または更新（カウントは自動で行わない）
            listing = self.create_or_update_listing(
                master_property=master_property,
                url=property_data['url'],
                title=property_data.get('title', property_data['building_name']),
                price=property_data['price'],
                agency_name=property_data.get('agency_name', '東急リバブル'),
                site_property_id=property_data.get('site_property_id'),
                description=property_data.get('description'),
                station_info=property_data.get('station_info'),
                features=property_data.get('features'),
                management_fee=property_data.get('management_fee'),
                repair_fund=property_data.get('repair_fund'),
                published_at=property_data.get('published_at'),
                first_published_at=property_data.get('first_published_at'),
                # 掲載サイトごとの物件属性
                listing_floor_number=property_data.get('floor_number'),
                listing_area=property_data.get('area'),
                listing_layout=property_data.get('layout'),
                listing_direction=property_data.get('direction'),
                listing_total_floors=listing_total_floors,
                listing_balcony_area=property_data.get('balcony_area'),
                listing_address=property_data.get('address'),
                record_stats=False  # 手動でカウントするため自動カウントは無効化
            )
            
            # agency_telは別途保存が必要な場合は、listingのカスタムフィールドに保存
            if property_data.get('agency_tel'):
                listing.detail_info = listing.detail_info or {}
                listing.detail_info['agency_tel'] = property_data['agency_tel']
            
            # 一覧ページのデータで更新
            self.update_listing_from_list(listing, property_data)
            
            # 画像を追加
            if property_data.get('image_urls'):
                self.add_property_images(listing, property_data['image_urls'])
            
            # 詳細情報を保存
            listing.detail_info = property_data.get('detail_info', {})
            listing.detail_fetched_at = datetime.now()
            
            # 多数決による物件情報更新
            self.update_master_property_by_majority(master_property)
            
            # 新規/更新の記録（詳細取得が成功した場合のみ）
            if is_new_listing:
                self.record_listing_created()
            else:
                self.record_listing_updated()
            
            print(f"  → 保存完了")
            self.record_success()
            
        except Exception as e:
            print(f"  → エラー: {e}")
            import traceback
            traceback.print_exc()
            
            # SQLAlchemyのセッションエラーの場合はロールバック
            if hasattr(self, '_session') and self._session:
                try:
                    self._session.rollback()
                except:
                    pass
            
            self.record_error(
                error_type='saving',
                url=property_data.get('url'),
                building_name=property_data.get('building_name'),
                property_data=property_data,
                error=e,
                phase='save_property'
            )
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            # アクセス間隔を保つ
            time.sleep(self.delay)
            
            # 詳細ページを取得
            soup = self.fetch_page(url)
            if not soup:
                self.record_error('detail_page')
                return None
            
            # URLパターンによってHTML構造を判定
            is_grantact = '/grantact/detail/' in url
            
            if is_grantact:
                # grantactパターンの場合はテーブル構造を確認
                tables = soup.find_all('table')
                if len(tables) < 2:
                    print(f"  → grantactページでテーブルが不足: {len(tables)}個")
                    self.record_error('parsing')
                    return None
            else:
                # 通常パターンの場合は既存のセレクタを確認
                required_selectors = {
                    '物件情報': '.p-detail__content, .o-detail-header, .m-status-table',
                    'タイトル': '.o-detail-header__headline, h1, h2',
                }
                
                if not self.validate_html_structure(soup, required_selectors):
                    self.record_error('parsing')
                    return None
            
            property_data = {
                'url': url,
                'site_property_id': self.extract_property_id(url)
            }
            
            detail_info = {}
            
            # grantactパターンの場合は別の解析処理
            if is_grantact:
                return self._parse_grantact_detail(soup, property_data, detail_info)
            
            # タイトルを取得（建物名として使用）
            # まずはタイトルタグから取得を試みる
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                # "南青ハイツ(C48257022)｜マンション購入｜東急リバブル" のような形式から建物名を抽出
                title_match = re.search(r'^(.+?)(?:\(|｜)', title_text)
                if title_match:
                    property_data['title'] = title_match.group(1).strip()
                    # 建物名がまだない場合は、タイトルから取得した名前を使用
                    if 'building_name' not in property_data:
                        property_data['building_name'] = property_data['title']
                else:
                    property_data['title'] = title_text
            else:
                # フォールバック：ヘッドライン要素から取得
                title_elem = soup.select_one('.o-detail-header__headline, h1, h2')
                if title_elem:
                    property_data['title'] = title_elem.get_text(strip=True)
            
            # 価格を取得（複数のセレクタを試す）
            price_found = False
            
            # パターン1: 価格専用のセレクタ
            price_elem = soup.select_one('.a-price__number, .o-detail-header__price-wrapper')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = extract_price(price_text)
                if price:
                    property_data['price'] = price
                    price_found = True
            
            # パターン2: テーブルから価格を探す
            if not price_found:
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            label = th.get_text(strip=True)
                            value = td.get_text(strip=True)
                            if '価格' in label and '万円' in value:
                                price_match = re.search(r'([\d,]+)万円', value)
                                if price_match:
                                    property_data['price'] = int(price_match.group(1).replace(',', ''))
                                    price_found = True
                                    break
            
            # 物件詳細情報を抽出
            # m-status-tableクラスのテーブルから情報を取得
            status_tables = soup.select('.m-status-table')
            
            for table in status_tables:
                rows = table.select('tr, .m-status-table__item')
                for row in rows:
                    # 東急リバブルの構造に対応
                    label_elem = row.select_one('.m-status-table__headline, th')
                    value_elem = row.select_one('.m-status-table__body, td')
                    
                    if label_elem and value_elem:
                        label = label_elem.get_text(strip=True)
                        value = value_elem.get_text(strip=True)
                        self._extract_property_info(label, value, property_data, detail_info)
            
            # 通常のテーブルとdl要素もチェック（フォールバック）
            info_elements = soup.select('table:not(.m-status-table), dl')
            
            for elem in info_elements:
                if elem.name == 'table':
                    rows = elem.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['th', 'td'])
                        if len(cells) >= 2:
                            label = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            self._extract_property_info(label, value, property_data, detail_info)
                
                elif elem.name == 'dl':
                    dt_elements = elem.find_all('dt')
                    dd_elements = elem.find_all('dd')
                    for i, dt in enumerate(dt_elements):
                        if i < len(dd_elements):
                            label = dt.get_text(strip=True)
                            value = dd_elements[i].get_text(strip=True)
                            self._extract_property_info(label, value, property_data, detail_info)
            
            # 不動産会社情報を取得
            agency_elem = soup.select_one('.agency-name, .company-name, [class*="agency"]')
            if agency_elem:
                property_data['agency_name'] = agency_elem.get_text(strip=True)
            
            # 電話番号を取得
            tel_match = re.search(r'0\d{1,4}-\d{1,4}-\d{4}', soup.get_text())
            if tel_match:
                property_data['agency_tel'] = tel_match.group(0)
            
            # 画像URLを取得
            image_urls = []
            image_elements = soup.select('img.property-image, .gallery img, .slider img')
            for img in image_elements[:10]:  # 最大10枚
                img_url = img.get('src') or img.get('data-src')
                if img_url:
                    # 相対URLを絶対URLに変換
                    img_url = urljoin(url, img_url)
                    if img_url not in image_urls:
                        image_urls.append(img_url)
            
            if image_urls:
                property_data['image_urls'] = image_urls
            
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
            
            return property_data
            
        except Exception as e:
            print(f"  → 詳細ページ解析エラー: {e}")
            self.record_error(
                error_type='parsing',
                url=url,
                error=e,
                phase='parse_detail'
            )
            return None
    
    def _extract_property_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """ラベルと値から物件情報を抽出"""
        
        # デバッグ出力
        print(f"    [DEBUG] ラベル: '{label}' -> 値: '{value}'")
        
        # 建物名/物件名
        if '物件名' in label or '建物名' in label:
            property_data['building_name'] = value
        
        # 所在地/住所
        elif '所在地' in label or '住所' in label:
            property_data['address'] = value
        
        # 階数（所在階）
        elif '階数' in label or '所在階' in label and '総階数' not in label:
            floor_number = extract_floor_number(value)
            if floor_number is not None:
                property_data['floor_number'] = floor_number
        
        # 総階数
        elif '総階数' in label or '建物階数' in label:
            # 総階数は文字列として保存（"14階地下1階建"のような形式に対応）
            detail_info['total_floors'] = value
        
        # 構造
        elif '構造' in label:
            detail_info['structure'] = value
            # 総階数がまだ設定されていない場合、構造から抽出
            if 'total_floors' not in detail_info:
                # "14階地下1階建"のような形式を保持
                if '階建' in value:
                    detail_info['total_floors'] = value
            # 地下階数も抽出
            basement_match = re.search(r'地下(\d+)階', value)
            if basement_match:
                detail_info['basement_floors'] = int(basement_match.group(1))
        
        # 専有面積（バルコニー面積を除外）
        elif ('専有面積' in label or '面積' in label) and 'バルコニー' not in label and '敷地' not in label:
            # DataNormalizerを使用して面積を抽出
            area_value = extract_area(value)
            if area_value:
                property_data['area'] = area_value
                print(f"    [DEBUG] 専有面積: {area_value}㎡")
        
        # バルコニー面積
        elif 'バルコニー' in label:
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 間取り
        elif '間取り' in label:
            layout = normalize_layout(value)
            if layout:
                property_data['layout'] = layout
        
        # 向き/方角
        elif '向き' in label or '方角' in label or '採光' in label:
            direction = normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                property_data['built_year'] = built_year
        
        # 総戸数
        elif '総戸数' in label:
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                detail_info['total_units'] = int(units_match.group(1))
        
        # 管理費
        elif '管理費' in label:
            management_fee = extract_monthly_fee(value)
            if management_fee:
                property_data['management_fee'] = management_fee
        
        # 修繕積立金
        elif '修繕積立金' in label or '修繕費' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                property_data['repair_fund'] = repair_fund
        
        # 交通/最寄り駅
        elif '交通' in label or '最寄' in label or '駅' in label:
            station_info = format_station_info(value)
            property_data['station_info'] = station_info
        
        # 土地権利
        elif '土地権利' in label or '権利形態' in label:
            detail_info['land_rights'] = value
        
        # 駐車場
        elif '駐車場' in label:
            detail_info['parking_info'] = value
        
        # 備考/特記事項
        elif '備考' in label or '特記' in label:
            property_data['remarks'] = value
        
        # 引渡し時期
        elif '引渡' in label:
            detail_info['delivery_date'] = value
        
        # 現況
        elif '現況' in label:
            detail_info['current_status'] = value
        
        # 情報提供日/情報公開日
        elif '情報提供日' in label or '情報公開日' in label or '登録日' in label:
            published_date = parse_date(value)
            if published_date:
                property_data['published_at'] = published_date
    
    def _parse_grantact_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any], detail_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """grantactパターンの詳細ページを解析"""
        try:
            # テーブルから情報を抽出
            tables = soup.find_all('table')
            
            # 各テーブルを解析
            for table in tables:
                for row in table.find_all('tr'):
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        self._extract_grantact_info(label, value, property_data, detail_info)
            
            # タイトルから建物名を取得
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                # "パークコート赤坂ザ・タワー｜東急リバブル" のような形式から建物名を抽出
                title_match = re.search(r'^(.+?)(?:｜|│)', title_text)
                if title_match:
                    property_data['title'] = title_match.group(1).strip()
                    property_data['building_name'] = property_data['title']
            
            # 必須フィールドの確認
            if not property_data.get('building_name'):
                # h1タグからも試す
                h1 = soup.find('h1')
                if h1:
                    property_data['building_name'] = h1.get_text(strip=True)
            
            # 不動産会社情報
            property_data['agency_name'] = '東急リバブル'
            
            # 詳細情報を保存
            property_data['detail_info'] = detail_info
            
            # detail_infoの重要な情報をproperty_dataにも含める
            if 'total_floors' in detail_info:
                property_data['total_floors'] = detail_info['total_floors']
            if 'basement_floors' in detail_info:
                property_data['basement_floors'] = detail_info['basement_floors']
            if 'total_units' in detail_info:
                property_data['total_units'] = detail_info['total_units']
            
            return property_data
            
        except Exception as e:
            print(f"  → grantact詳細ページ解析エラー: {e}")
            self.record_error(
                error_type='parsing',
                url=property_data.get('url'),
                error=e,
                phase='parse_grantact_detail'
            )
            return None
    
    def _extract_grantact_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """grantactページから情報を抽出"""
        
        # デバッグ出力
        print(f"    [DEBUG-GRANTACT] ラベル: '{label}' -> 値: '{value}'")
        
        # マンション名/建物名
        if 'マンション名' in label:
            property_data['building_name'] = value
        
        # 所在地
        elif '所在地' in label:
            property_data['address'] = value
        
        # 交通
        elif '交通' in label or '駅徒歩' in label:
            station_info = format_station_info(value)
            property_data['station_info'] = station_info
        
        # 価格
        elif label == '価格' and '万円' in value:
            price = extract_price(value)
            if price:
                property_data['price'] = price
        
        # 間取り
        elif label == '間取':
            property_data['layout'] = value
        
        # 専有面積
        elif '専有面積' in label:
            area = extract_area(value)
            if area:
                property_data['area'] = area
                print(f"    [DEBUG-GRANTACT] 専有面積: {area}㎡")
        
        # バルコニー面積
        elif 'バルコニー面積' in label:
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 建物階数
        elif '建物階数' in label:
            detail_info['total_floors'] = value
            # 地下階数も抽出
            basement_match = re.search(r'地下(\d+)階', value)
            if basement_match:
                detail_info['basement_floors'] = int(basement_match.group(1))
        
        # 総戸数
        elif '総戸数' in label:
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                detail_info['total_units'] = int(units_match.group(1))
        
        # 土地権利
        elif '土地権利' in label:
            detail_info['land_rights'] = value
        
        # 管理会社
        elif '管理会社' in label:
            detail_info['management_company'] = value
        
        # 向き
        elif label == '向き':
            direction = normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 階数（所在階）
        elif label == '階' or label == '階数':
            floor_number = extract_floor_number(value)
            if floor_number is not None:
                property_data['floor_number'] = floor_number
        
        # 築年月
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                property_data['built_year'] = built_year
        
        # 管理費
        elif '管理費' in label and '修繕' not in label:
            management_fee = extract_monthly_fee(value)
            if management_fee:
                property_data['management_fee'] = management_fee
        
        # 修繕積立金
        elif '修繕積立金' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                property_data['repair_fund'] = repair_fund