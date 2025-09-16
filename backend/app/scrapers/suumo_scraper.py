"""
SUUMOスクレイパー v3
一覧ページから直接情報を収集
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup, Tag

from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import SuumoParser
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)


class SuumoScraper(BaseScraper):
    """SUUMOのスクレイパー（v3 - 一覧ページベース）"""
    
    BASE_URL = "https://suumo.jp"
    
    # 定数の定義
    MAX_DISPLAY_ITEMS = 100  # SUUMOの最大表示件数
    MAX_REMARKS_LENGTH = 500  # 備考の最大文字数
    MIN_REMARKS_LENGTH = 50  # 備考の最小文字数
    MIN_LONG_TEXT_LENGTH = 100  # 長文と判定する最小文字数
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(SourceSite.SUUMO, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = SuumoParser(logger=self.logger)
        # 建物名取得エラーの履歴（メモリ内管理）
    
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（SUUMOスクレイパー固有の実装）"""
        try:
            # process_property_with_detail_checkを直接呼び出す
            result = self.process_property_with_detail_check(
                property_data=property_data,
                existing_listing=existing_listing,
                parse_detail_func=self.parse_property_detail,
                save_property_func=self.save_property_common
            )
            return result
        except Exception as e:
            # エラーは呼び出し元で処理されるので、ここでは再スロー
            raise
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """SUUMOの検索URLを生成（100件/ページ）
        
        Args:
            area: エリアコード（scrape_areaから渡される）
            page: ページ番号
        """
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
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc={self.MAX_DISPLAY_ITEMS}"
        else:
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc={self.MAX_DISPLAY_ITEMS}&page={page}"
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def is_last_page(self, soup: BeautifulSoup) -> bool:
        """
        現在のページが最終ページかどうかを判定（SUUMOの実装）
        
        Returns:
            最終ページの場合True
        """
        try:
            # SUUMOのページネーション要素を探す
            # 方法1: 「次へ」リンクの有無で判定
            next_link = soup.select_one('.pagination a[rel="next"], .pagination-parts a:contains("次へ")')
            if next_link is None:
                # 次へリンクがない場合は最終ページ
                return True
            
            # 方法2: ページ番号から判定
            pagination = soup.select_one('.pagination, .pagination-parts')
            if pagination:
                # 現在のページ（activeまたはcurrent）
                current = pagination.select_one('.active, .current, strong')
                if current:
                    # 最後のページ番号を取得
                    page_links = pagination.select('a')
                    if page_links:
                        last_page_text = page_links[-1].get_text(strip=True)
                        if last_page_text == '次へ' and len(page_links) > 1:
                            last_page_text = page_links[-2].get_text(strip=True)
                        
                        try:
                            current_page = int(current.get_text(strip=True))
                            last_page = int(last_page_text)
                            return current_page >= last_page
                        except (ValueError, AttributeError):
                            pass
            
            return False
            
        except Exception as e:
            self.logger.warning(f"[SUUMO] ページ終端判定でエラー: {e}")
            return False
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """SUUMOのsite_property_idの妥当性を検証
        
        SUUMOの物件IDは数字のみで構成される（例：76583217）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # SUUMO固有の検証：数字のみで構成されているか
        if not site_property_id.isdigit():
            self.logger.error(
                f"[SUUMO] site_property_idは数字のみで構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜10桁程度
        if len(site_property_id) < 6 or len(site_property_id) > 10:
            self.logger.warning(
                f"[SUUMO] site_property_idの桁数が異常です（通常6-10桁）: '{site_property_id}' "
                f"(桁数: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行（将来的に桁数が変わる可能性があるため）
            
        return True
    
    def extract_property_id(self, url: str) -> Optional[str]:
        """URLから物件IDを抽出
        
        Returns:
            str: 物件ID（抽出に失敗した場合はNone）
        """
        match = re.search(r'/nc_(\d+)/', url)
        if match:
            return match.group(1)
        else:
            self.logger.error(f"[SUUMO] URLから物件IDを抽出できませんでした: {url}")
            return None
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（スマートスクレイピング対応）"""
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property_common
        )
    
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        # パーサーで基本的な解析を実行
        detail_data = self.parser.parse_property_detail(soup)
        
        # スクレイパー固有の処理
        if detail_data:
            detail_data["url"] = url
            detail_data["_page_text"] = soup.get_text()  # 建物名一致確認用
            
            # site_property_idの抽出と検証（必要に応じて）
            if "site_property_id" not in detail_data and url:
                # URLからsite_property_idを抽出する処理（スクレイパー固有）
                pass
        
        return detail_data

    def _extract_price(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> bool:
        """価格を抽出（複数の方法を試行）"""
        # まずテーブルから価格を探す（最も確実）
        all_tables = soup.find_all('table')
        for table in all_tables:
            rows = table.find_all('tr')
            for row in rows:
                th = row.select_one('th')
                td = row.select_one('td')
                if th and td:
                    label = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    if '価格' in label and ('万円' in value or '億円' in value):
                        price = extract_price(value)
                        if price:
                            property_data['price'] = price
                            print(f"    価格: {property_data['price']}万円")
                            return True
        
        # 価格が取得できていない場合は、ページ全体から探す
        page_text = soup.get_text()
        price = extract_price(page_text)
        if price:
            property_data['price'] = price
            print(f"    価格（ページ全体から）: {property_data['price']}万円")
            return True
        
        return False
    
    def _process_all_tables(self, tables: List[Tag], property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """すべてのテーブルからデータを抽出"""
        for table in tables:
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
                        
                        # 各フィールドの抽出を専用メソッドに委譲
                        self._extract_field_from_table(label, value, td, property_data, detail_info)
    
    def _extract_field_from_table(self, label: str, value: str, td_element: Tag, 
                                 property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """テーブルの1フィールドからデータを抽出"""
        # 所在階
        if label == '所在階' or (label.endswith('ヒント') and '所在階' in label):
            floor_number = extract_floor_number(value)
            if floor_number is not None:
                property_data['floor_number'] = floor_number
                print(f"    所在階: {property_data['floor_number']}階")
        
        # 向き
        elif label == '向き' or (label.endswith('ヒント') and '向き' in label):
            direction = normalize_direction(value)
            if direction:
                property_data['direction'] = direction
                print(f"    向き: {property_data['direction']}")
        
        # 住所
        elif label == '住所' or label == '所在地':
            self._extract_address(td_element, value, property_data)
        
        # 所在階/構造・階建（複合フィールド）
        elif '所在階' in label and '構造' in label and 'floor_number' not in property_data:
            self._extract_floor_and_structure(value, property_data, detail_info)
        
        # 構造・階建て
        elif label == '構造・階建て' or (label.endswith('ヒント') and '構造・階建て' in label):
            self._extract_structure_info(value, detail_info)
        
        # 総戸数
        elif '総戸数' in label:
            self._extract_total_units(value, detail_info)
        
        # 物件名（建物名）
        elif '物件名' in label:
            property_data['building_name'] = value
            property_data['building_name_source'] = 'table'
            print(f"    物件名: {property_data['building_name']}")
        
        # 部屋番号
        elif '部屋番号' in label or '号室' in label:
            property_data['room_number'] = value
            print(f"    部屋番号: {property_data['room_number']}")
        
        # バルコニー面積
        elif 'バルコニー' in label or 'バルコニー' in value or ('その他面積' in label):
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
                print(f"    バルコニー面積: {balcony_area}㎡")
        
        # 間取り
        elif '間取り' in label:
            self._extract_layout(label, value, property_data)
        
        # 専有面積
        elif '専有面積' in label:
            self._extract_area(label, value, property_data)
        
        # 築年月
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                property_data['built_year'] = built_year
                # 月情報も取得
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    property_data['built_month'] = int(month_match.group(1))
        
        # 交通情報
        elif '交通' in label or 'アクセス' in label:
            self._extract_station_info(value, property_data)
        
        # 権利形態
        elif '権利' in label and ('土地' in label or '敷地' in label):
            detail_info['land_rights'] = value
            print(f"    権利形態: {value}")
        
        # 駐車場
        elif '駐車' in label:
            detail_info['parking_info'] = value
            print(f"    駐車場: {value}")
        
        # 情報公開日
        elif '情報公開日' in label or '情報登録日' in label or '登録日' in label:
            self._extract_first_published_date(value, property_data)
        
        # 情報提供日
        elif '情報提供日' in label or '情報更新日' in label:
            self._extract_published_date(value, property_data)
        
        # 管理費
        elif '管理費' in label and '修繕' not in label:
            self._extract_management_fee(value, property_data)
        
        # 修繕積立金
        elif '修繕' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                property_data['repair_fund'] = repair_fund
                print(f"    修繕積立金: {property_data['repair_fund']}円")
        
        # 不動産会社情報
        elif '会社概要' in label:
            self._extract_agency_info(value, property_data)
        
        # 諸費用（管理費の別パターン）
        elif '諸費用' in label and 'management_fee' not in property_data:
            self._extract_management_fee_from_misc(value, property_data)
    
    def _extract_address(self, td_element: Tag, value: str, property_data: Dict[str, Any]):
        """住所を抽出"""
        # td内に複数のp要素がある場合は最初のp要素のテキストを取得
        first_p = td_element.find('p')
        if first_p:
            property_data['address'] = first_p.get_text(strip=True)
        else:
            property_data['address'] = value
        print(f"    住所: {property_data['address']}")
    
    def _extract_floor_and_structure(self, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """所在階/構造・階建の複合フィールドから情報を抽出"""
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
    
    def _extract_structure_info(self, value: str, detail_info: Dict[str, Any]):
        """構造情報を抽出"""
        # 構造情報を保存（フルテキスト）
        detail_info['structure_full'] = value
        print(f"    構造（フル）: {value}")
        
        # 総階数と地下階数を抽出
        total_floors, basement_floors = extract_total_floors(value)
        
        # 明らかに間違った総階数（1階など）の場合は無視
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
    
    def _extract_total_units(self, value: str, detail_info: Dict[str, Any]):
        """総戸数を抽出"""
        units_match = re.search(r'(\d+)戸', value)
        if units_match:
            detail_info['total_units'] = int(units_match.group(1))
            print(f"    総戸数: {detail_info['total_units']}戸")
    
    def _extract_layout(self, label: str, value: str, property_data: Dict[str, Any]):
        """間取りを抽出"""
        
        layout = normalize_layout(value)
        if layout:
            property_data['layout'] = layout

    
    def _extract_area(self, label: str, value: str, property_data: Dict[str, Any]):
        """専有面積を抽出"""

        
        area = extract_area(value)
        if area:
            property_data['area'] = area

    
    def _extract_station_info(self, value: str, property_data: Dict[str, Any]):
        """交通情報を抽出"""
        from .data_normalizer import format_station_info
        station_info = format_station_info(value)
        property_data['station_info'] = station_info
        print(f"    交通: {station_info.replace(chr(10), ' / ')}")  # ログでは改行を / で表示  # ログでは改行を / で表示
    
    def _extract_first_published_date(self, value: str, property_data: Dict[str, Any]):
        """情報公開日を抽出"""
        date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            property_data['first_published_at'] = datetime(year, month, day)
            # published_atにも設定（後方互換性のため）
            if 'published_at' not in property_data:
                property_data['published_at'] = property_data['first_published_at']
            print(f"    売出確認日: {property_data['first_published_at'].strftime('%Y-%m-%d')}")
    
    def _extract_published_date(self, value: str, property_data: Dict[str, Any]):
        """情報提供日を抽出"""
        date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', value)
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            property_data['published_at'] = datetime(year, month, day)
            print(f"    情報提供日: {property_data['published_at'].strftime('%Y-%m-%d')}")
    
    def _extract_management_fee(self, value: str, property_data: Dict[str, Any]):
        """管理費を抽出"""
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
    
    def _extract_agency_info(self, value: str, property_data: Dict[str, Any]):
        """不動産会社情報を抽出"""
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
    
    def _extract_management_fee_from_misc(self, value: str, property_data: Dict[str, Any]):
        """諸費用から管理費を抽出"""
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
    
    def _extract_title_and_building_name(self, soup: BeautifulSoup, property_data: Dict[str, Any], url: str) -> bool:
        """タイトルと建物名を抽出"""
        # タイトルと説明文
        title_elem = soup.select_one('h1, .property-title, h2.section_h1-header-title')
        if title_elem:
            property_data['title'] = title_elem.get_text(strip=True)
            
            # 建物名が取得できていない場合、タイトルから抽出を試みる
            if 'building_name' not in property_data and property_data.get('title'):
                # タイトルから建物名を抽出する
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
                        self.logger.error(
                            f"建物名がテーブルから取得できませんでした。"
                            f"HTML構造が変更された可能性があります: {url}"
                        )
                        self._scraping_stats['building_name_missing_new'] += 1
                            
                        print(f"    [ERROR] 物件名がテーブルから取得できませんでした")
                        print(f"    [INFO] タイトルには「{building_name}」とありますが、信頼性が低いため使用しません")
                        # 統計情報を更新
                        self._scraping_stats['building_name_missing'] += 1
                        # 詳細取得失敗として扱う
                        return False
        
        # 建物名が全く取得できない場合も同様
        if 'building_name' not in property_data:
            self.logger.error(f"建物名が取得できませんでした。HTML構造の確認が必要です: {url}")
            self._scraping_stats['building_name_missing_new'] += 1
                
            print(f"    [ERROR] 物件名が取得できませんでした")
            # 統計情報を更新
            self._scraping_stats['building_name_missing'] = self._scraping_stats.get('building_name_missing', 0) + 1
            # 詳細取得失敗として扱う
            return False
        
        return True
    
    def _extract_facilities(self, soup: BeautifulSoup, detail_info: Dict[str, Any]):
        """設備・仕様情報を抽出"""
        facility_section = soup.select_one('.section-facilities, .property-spec')
        if facility_section:
            facilities = []
            facility_items = facility_section.select('li')
            for item in facility_items:
                facilities.append(item.get_text(strip=True))
            detail_info['設備'] = facilities
    
    def _extract_remarks(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """備考・特記事項を抽出"""
        remarks_text = ""
        
        # セールスポイントを探す
        sales_points = soup.find_all(['div', 'p'], class_=re.compile(r'sales|point|appeal|feature|comment', re.I))
        for elem in sales_points:
            text = elem.get_text(strip=True)
            if len(text) > self.MIN_REMARKS_LENGTH and not text.startswith('※'):  # 注意書きは除外
                remarks_text = text
                break
        
        # パターン2: 長い説明文
        if not remarks_text:
            for tag in ['p', 'div']:
                long_texts = soup.find_all(tag)
                for elem in long_texts:
                    text = elem.get_text(strip=True)
                    # 物件説明っぽい長文を探す
                    if (len(text) > self.MIN_LONG_TEXT_LENGTH and 
                        any(kw in text for kw in ['立地', '環境', '駅', '徒歩', '生活', '便利']) and
                        not any(ng in text for ng in ['利用規約', 'Copyright', '個人情報', 'お問い合わせ'])):
                        remarks_text = text[:self.MAX_REMARKS_LENGTH]
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
    
    
    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str,
                                    allow_partial_match: bool = False, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """建物名の一致確認（SUUMOの省略表示に対応）
        
        SUUMOの仕様：
        - 一覧ページでは長い建物名が「…」付きで省略表示される
        - 省略されている場合：詳細ページの建物名が一覧の建物名で始まるか確認（前方一致）
        - 省略されていない場合：詳細ページの建物名と一覧の建物名が同じか確認（完全一致）
        
        Args:
            detail_building_name: 詳細ページから取得した建物名
            building_name_from_list: 一覧ページから取得した建物名（省略されている可能性あり）
            threshold: 類似度の閾値（0.0-1.0）
            
        Returns:
            (建物名が確認できたか, 詳細ページの完全な建物名またはNone)
        """
        if not building_name_from_list or not detail_building_name:
            return False, None
        
        # 「…」で終わっている場合は省略されている
        is_abbreviated = building_name_from_list.endswith('…') or building_name_from_list.endswith('...')
        
        # 省略されていない場合は基底クラスの正規化処理を使用
        if not is_abbreviated:
            # 基底クラスのメソッドを使用（㎡とm2の正規化も含まれる）
            return super().verify_building_names_match(detail_building_name, building_name_from_list, 
                                                      allow_partial_match=False, threshold=threshold)
        
        if is_abbreviated:
            self.logger.info(f"[SUUMO] 省略された建物名を検出: '{building_name_from_list}'")
            
            # 省略記号を除去
            abbreviated_name = building_name_from_list.rstrip('….')
            
            # 基底クラスの正規化メソッドを使用
            normalized_abbreviated = self.normalize_building_name(abbreviated_name)
            normalized_detail = self.normalize_building_name(detail_building_name)
            
            # ログで確認
            self.logger.info(f"[SUUMO] 建物名比較（省略） - 一覧: '{abbreviated_name}' が 詳細: '{detail_building_name}' に前方一致するか確認")
            
            # 詳細ページの建物名が、省略された建物名で始まるか確認（正規化版で比較）
            if normalized_detail.startswith(normalized_abbreviated):
                self.logger.info(
                    f"[SUUMO] 省略された建物名が前方一致（成功）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
            
            self.logger.debug(
                f"[SUUMO] 正規化後 - 一覧: '{normalized_abbreviated}' が 詳細: '{normalized_detail}' に前方一致するか確認"
            )
            
            # 大文字小文字を無視して比較
            if normalized_detail.lower().startswith(normalized_abbreviated.lower()):
                self.logger.info(
                    f"[SUUMO] 省略された建物名が正規化後に前方一致（成功）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
            
            # 見つからない場合
            self.logger.warning(
                f"[SUUMO] 省略された建物名が一致しません: "
                f"一覧「{building_name_from_list}」が詳細「{detail_building_name}」に前方一致しません"
            )
            return False, None
        else:
            # 省略されていない場合
            self.logger.info(f"[SUUMO] 建物名比較（完全） - 一覧: '{building_name_from_list}' と 詳細: '{detail_building_name}' が完全一致するか確認")
            
            if building_name_from_list == detail_building_name:
                self.logger.info(
                    f"[SUUMO] 建物名が完全一致（成功）: '{building_name_from_list}'"
                )
                return True, detail_building_name
            
            # 正規化して比較
            normalized_list = re.sub(r'[\s　・－―～〜]+', '', building_name_from_list)
            normalized_detail = re.sub(r'[\s　・－―～〜]+', '', detail_building_name)
            
            if normalized_list.lower() == normalized_detail.lower():
                self.logger.info(
                    f"[SUUMO] 建物名が正規化後に完全一致（成功）: '{building_name_from_list}'"
                )
                return True, detail_building_name
            
            # 一致しない場合は基底クラスのメソッドを使用（部分一致などの高度な比較）
            return super().verify_building_names_match(
                detail_building_name, 
                building_name_from_list, 
                allow_partial_match=self.allow_partial_building_name_match,
                threshold=threshold
            )
    
    
    
    def _update_building_name_statistics(self, property_data: Dict[str, Any]):
        """建物名取得元の統計を更新"""
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
    
    
