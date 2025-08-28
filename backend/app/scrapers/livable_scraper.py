"""
東急リバブルスクレイパー
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup, Tag
import traceback

from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from .data_normalizer import DataNormalizer
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)


class LivableScraper(BaseScraper):
    """東急リバブルのスクレイパー"""
    
    BASE_URL = "https://www.livable.co.jp"
    
    # 定数の定義
    PRICE_MISMATCH_RETRY_DAYS = 7  # 価格不一致時の再試行日数
    PRICE_MISMATCH_THRESHOLD = 0.1  # 価格不一致の閾値（10%）
    DEFAULT_AGENCY_NAME = "東急リバブル"
    
    # デバッグ対象の物件ID
    DEBUG_PROPERTY_IDS = ['C13252J13', 'C13249B30']
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False):
        super().__init__(SourceSite.LIVABLE, force_detail_fetch, max_properties, ignore_error_history)
        # 東急リバブルも一覧ページと詳細ページで建物名の表記が異なることがあるため、部分一致を許可
        self.allow_partial_building_name_match = True
        self.building_name_match_threshold = 0.6  # 東急リバブルは詳細ページの建物名が長い傾向があるため閾値を下げる
    
    def get_optional_required_fields(self) -> List[str]:
        """Livableではlayoutは必須ではない（稀に取得できないため）
        
        Returns:
            List[str]: オプショナルな必須フィールドのリスト（空リスト）
        """
        return []  # layoutを必須から除外

    
    def get_partial_required_fields(self) -> Dict[str, Dict[str, Any]]:
        """Livableの部分的必須フィールドの設定
        
        layoutはほとんどの場合取得できるが、一部の物件で取得できない。
        30%以上の欠損率の場合にエラーとする。
        
        Returns:
            Dict[str, Dict[str, Any]]: 部分的必須フィールドの設定
        """
        return {
            'layout': {
                'max_missing_rate': 0.3,  # 30%までの欠損を許容
                'min_sample_size': 10,     # 10件以上のサンプルで評価
                'empty_values': ['-', '－', '']  # 空とみなす値
            }
        }
    
    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str, 
                                   allow_partial_match: bool = False, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """東急リバブル特有の建物名マッチングロジック
        
        東急リバブルでは詳細ページの建物名が一覧ページよりも詳細な場合が多い
        例：
        - 一覧「ＴＨＥ　ＲＯＰＰＯＮＧＩ　ＴＯＫＹＯ」 → 詳細「ＴＨＥ ＲＯＰＰＯＮＧＩ ＴＯＫＹＯ ＣＬＵＢ ＲＥＳＩＤＥＮＣＥ」
        - 一覧「三田ガーデンヒルズ」 → 詳細「三田ガーデンヒルズノースヒル」
        """
        # 基底クラスのメソッドを呼び出す
        is_verified, verified_name = super().verify_building_names_match(
            detail_building_name, building_name_from_list, allow_partial_match, threshold
        )
        
        # 基底クラスで一致しなかった場合、追加のチェックを行う
        if not is_verified and allow_partial_match:
            # 正規化
            normalized_list = self.normalize_building_name(building_name_from_list)
            normalized_detail = self.normalize_building_name(detail_building_name)
            
            # 一覧の建物名が詳細の建物名の先頭部分と一致するかチェック
            if normalized_detail.startswith(normalized_list):
                self.logger.info(
                    f"建物名が一致（前方一致）: 一覧「{building_name_from_list}」は詳細「{detail_building_name}」の先頭部分"
                )
                return True, detail_building_name
            
            # スペースを除去してもう一度チェック
            list_no_space = normalized_list.replace(' ', '').replace('　', '')
            detail_no_space = normalized_detail.replace(' ', '').replace('　', '')
            
            if detail_no_space.startswith(list_no_space):
                self.logger.info(
                    f"建物名が一致（前方一致・スペース除去後）: 一覧「{building_name_from_list}」は詳細「{detail_building_name}」の先頭部分"
                )
                return True, detail_building_name
        
        return is_verified, verified_name
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """東急リバブルのsite_property_idの妥当性を検証
        
        東急リバブルの物件IDは英数字で構成される（例：C13252J13）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # 東急リバブル固有の検証：英数字のみで構成されているか
        if not site_property_id.isalnum():
            self.logger.error(
                f"[LIVABLE] site_property_idは英数字で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜15文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[LIVABLE] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行
            
        # 'unknown'などの不正な値を拒否
        if site_property_id.lower() in ['unknown', 'detail', 'mansion']:
            self.logger.error(
                f"[LIVABLE] site_property_idが不正な値です: '{site_property_id}' URL={url}"
            )
            return False
            
        return True
    
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        # 共通の詳細チェック処理を使用
        result = self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self._save_property_after_detail
        )
        
        return result
    
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """東急リバブルの検索URLを生成"""
        from .area_config import get_area_code
        
        # エリアコードを取得
        area_code = get_area_code(area)
        
        # 東急リバブルのURL形式（修正版）
        base_url = f"{self.BASE_URL}/kounyu/mansion/tokyo/a{area_code}/"
        
        if page > 1:
            return f"{base_url}?page={page}"
        else:
            return base_url
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧からURLと基本情報を抽出"""
        properties = []
        
        # 物件リストアイテムを取得
        property_items = self._find_property_items(soup)
        
        for i, item in enumerate(property_items):
            property_data = self._parse_property_item(item, i)
            if property_data:
                properties.append(property_data)
        
        # デバッグ: 物件IDの重複チェック
        self._check_duplicate_property_ids(properties)
        
        return properties
    
    def _find_property_items(self, soup: BeautifulSoup) -> List[Tag]:
        """物件リストアイテムを検索"""
        property_items = soup.select('.o-product-list__item')
        
        if not property_items:
            # 別のセレクタを試す
            property_items = soup.select('.o-map-search__property-item')
        
        return property_items
    
    def _parse_property_item(self, item: Tag, index: int) -> Optional[Dict[str, Any]]:
        """物件アイテムをパース"""
        property_data = {}
        
        # 物件詳細へのリンク
        link = self._extract_property_link(item)
        if link:
            href = link.get('href', '')
            property_data['url'] = urljoin(self.BASE_URL, href)
            
            # site_property_idを抽出
            site_property_id = self.extract_property_id(href)
            if not site_property_id:
                self.logger.error(f"[LIVABLE] 物件をスキップします（site_property_id取得失敗）: {property_data['url']}")
                return None
                
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, property_data['url']):
                self.logger.error(f"[LIVABLE] 不正なsite_property_idを検出しました: '{site_property_id}'")
                return None
                
            property_data['site_property_id'] = site_property_id
            
            # デバッグ: 特定物件のリンク情報
            if site_property_id in self.DEBUG_PROPERTY_IDS:
                self.logger.info(f"DEBUG: 一覧ページItem#{index} - ID: {site_property_id}, URL: {property_data['url']}")
        
        
        # 価格を取得
        self._extract_list_price(item, property_data)
        
        # 建物名を取得（一覧ページから）
        building_name = None
        
        # 方法1: リンクのテキストから抽出
        link = item.select_one('a.o-product-list__link')
        if link:
            link_text = link.get_text(' ', strip=True)
            # パターン: 数字/数字の後、物件タイプの前
            match = re.search(r'\d+/\d+<?>\s*(.*?)(?:\s*（間取り）)?\s*(?:中古マンション|新築マンション)', link_text)
            if match:
                building_name = match.group(1).strip()
        
        # 方法2: 画像のalt属性から取得
        if not building_name:
            img = item.select_one('img[alt]')
            if img:
                alt = img.get('alt', '').strip()
                # alt属性から建物名を抽出（「(外観)」「（間取り）」などを除去）
                if alt and '外観' not in alt and '間取り' not in alt:
                    building_name = alt
                elif alt:
                    # （外観）、（間取り）などのカッコ付きテキストを除去
                    building_name = re.sub(r'[（(][^）)]*[）)]', '', alt).strip()
        
        if building_name:
            property_data['building_name_from_list'] = building_name
            property_data['building_name'] = building_name  # 必須フィールドとして設定
        
        # 一覧ページでの必須フィールドを検証（基底クラスの共通メソッドを使用）
        if self.validate_list_page_fields(property_data):
            return property_data
        else:
            return None
    
    def _extract_property_link(self, item: Tag) -> Optional[Tag]:
        """物件リンクを抽出"""
        link = item.select_one('a.o-product-list__link, a.o-map-search__property-link')
        if not link:
            link = item.select_one('a[href*="/kounyu/"]')
        return link
    
    def _extract_list_price(self, item: Tag, property_data: Dict[str, Any]):
        """一覧ページから価格を抽出"""
        price_elem = item.select_one('.o-product-list__info-body--price')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            property_data['price'] = extract_price(price_text)
            
            # デバッグ: 特定物件の価格取得
            if property_data.get('site_property_id') in self.DEBUG_PROPERTY_IDS:
                self.logger.info(f"DEBUG: 一覧ページ価格取得 - ID: {property_data['site_property_id']}, "
                               f"price_text: '{price_text}', extracted: {property_data['price']}万円")
                # 価格要素の親要素も確認
                self._verify_price_parent(price_elem, property_data)
        else:
            # 価格要素が見つからない場合のデバッグ
            if property_data.get('site_property_id') in self.DEBUG_PROPERTY_IDS:
                self.logger.info(f"DEBUG: 一覧ページ価格要素なし - ID: {property_data['site_property_id']}")
    
    def _verify_price_parent(self, price_elem: Tag, property_data: Dict[str, Any]):
        """価格要素の親物件を検証"""
        parent = price_elem.find_parent(class_='o-product-list__item')
        if parent:
            parent_link = parent.select_one('a[href*="/mansion/"], a[href*="/grantact/"]')
            if parent_link:
                parent_id = self.extract_property_id(parent_link.get('href', ''))
                if parent_id != property_data['site_property_id']:
                    self.logger.warning(f"価格要素の親物件IDが異なる: 期待={property_data['site_property_id']}, 実際={parent_id}")
    
    def _check_duplicate_property_ids(self, properties: List[Dict[str, Any]]):
        """物件IDの重複をチェック"""
        property_ids = [p.get('site_property_id') for p in properties if p.get('site_property_id')]
        id_counts = {}
        for pid in property_ids:
            id_counts[pid] = id_counts.get(pid, 0) + 1
        
        duplicates = {pid: count for pid, count in id_counts.items() if count > 1}
        if duplicates:
            self.logger.warning(f"一覧ページで重複物件ID検出: {duplicates}")
        
        # 特定物件の出現状況
        for target_id in self.DEBUG_PROPERTY_IDS:
            if target_id in property_ids:
                count = id_counts.get(target_id, 0)
                self.logger.info(f"DEBUG: 物件ID {target_id} の出現回数: {count}")
    
    def extract_property_id(self, url: str) -> Optional[str]:
        """URLから物件IDを抽出
        
        Returns:
            str: 物件ID（抽出に失敗した場合はNone）
        """
        # パターン1: /mansion/XXXXXXXX/
        match = re.search(r'/mansion/([A-Z0-9]+)/?', url)
        if match:
            return match.group(1)
        
        # パターン2: /grantact/detail/XXXXXXXX
        match = re.search(r'/grantact/detail/([A-Z0-9]+)', url)
        if match:
            return match.group(1)
            
        # 抽出に失敗
        self.logger.error(f"[LIVABLE] URLから物件IDを抽出できませんでした: {url}")
        return None
    
    def _save_property_after_detail(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """詳細データ取得後の保存処理（内部メソッド）"""
        return self.save_property_common(property_data, existing_listing)
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存（共通ロジックを使用）"""
        return self.save_property_common(property_data, existing_listing)
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            # アクセス間隔を保つ
            time.sleep(self.delay)
            
            # 詳細ページを取得
            self.logger.info(f"詳細ページを取得中: {url}")
            soup = self.fetch_page(url)
            if not soup:
                self.logger.error(f"詳細ページの取得に失敗 - ページのフェッチができませんでした: {url}")
                # fetch_pageでのエラー情報を確認
                fetch_error = getattr(self, '_last_fetch_error', None)
                if fetch_error and fetch_error.get('type') == '404':
                    # URLからsite_property_idを抽出して404エラー情報に含める
                    extracted_id = self.extract_property_id(url)
                    # 404エラーの場合は特別なエラー情報を設定
                    self._last_detail_error = {
                        'type': '404_error',
                        'error_type': '404 Not Found',
                        'error_message': '物件ページが見つかりません（削除済みまたは無効なURL）',
                        'building_name': '',
                        'price': '',
                        'site_property_id': extracted_id or ''
                    }
                return None
            
            # URLパターンによってHTML構造を判定
            is_grantact = '/grantact/detail/' in url or 'gt-www.livable.co.jp' in url
            
            # HTML構造の検証
            if not self._validate_html_structure(soup, is_grantact, url):
                return None
            
            # site_property_idを抽出
            site_property_id = self.extract_property_id(url)
            if not site_property_id:
                self.logger.error(f"[LIVABLE] 詳細ページでsite_property_idを取得できませんでした: {url}")
                return None
                
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, url):
                self.logger.error(f"[LIVABLE] 詳細ページで不正なsite_property_idを検出しました: '{site_property_id}'")
                return None
                
            property_data = {
                'url': url,
                'site_property_id': site_property_id,
                '_page_text': soup.get_text()  # 建物名一致確認用
            }
            
            detail_info = {}
            
            # grantactパターンの場合は別の解析処理
            if is_grantact:
                return self._parse_grantact_detail(soup, property_data, detail_info)
            
            # 通常パターンの解析
            return self._parse_normal_detail(soup, property_data, detail_info, url)
            
        except Exception as e:
            self.log_detailed_error("詳細ページ解析エラー", url, e)
            # エラー情報を保存して、Noneを返す（基底クラスでエラーハンドリングされる）
            self._last_detail_error = {
                'type': 'exception',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'building_name': property_data.get('building_name', ''),
                'price': property_data.get('price', ''),
                'site_property_id': property_data.get('site_property_id', '')
            }
            return None
    
    def _validate_html_structure(self, soup: BeautifulSoup, is_grantact: bool, url: str) -> bool:
        """HTML構造を検証"""
        if is_grantact:
            # grantactパターンの場合はテーブル構造を確認
            tables = soup.find_all('table')
            if len(tables) < 1:
                self.logger.warning(f"grantactページでテーブルが不足: {len(tables)}個 - {url}")
                # HTMLの内容を一部ログに出力して構造を確認
                html_preview = str(soup)[:500]
                self.logger.debug(f"HTML構造プレビュー: {html_preview}")
                return False
        else:
            # 通常パターンの場合は既存のセレクタを確認
            required_elements = [
                '.p-detail__content',
                '.o-detail-header', 
                '.m-status-table',
                'h1',
                'h2'
            ]
            
            found = False
            for selector in required_elements:
                elem = soup.select_one(selector)
                if elem:
                    found = True
                    break
            
            if not found:
                self.logger.warning(f"必要な要素が見つかりません: {url}")
                return False
        
        return True
    
    def _parse_normal_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any], 
                           detail_info: Dict[str, Any], url: str) -> Dict[str, Any]:
        """通常パターンの詳細ページを解析"""
        # タイトル・建物名を取得
        self._extract_title_and_building_name(soup, property_data)
        
        # 住所を取得
        self._extract_address(soup, property_data)
        
        # 価格を取得
        if not self._extract_detail_price(soup, property_data, url):
            self.record_field_extraction_error('price', url, log_error=True)
        
        # 物件詳細情報を抽出
        self._extract_property_details(soup, property_data, detail_info)
        
        # 不動産会社情報を取得
        self._extract_agency_info(soup, property_data)
        
        
        # 建物名が取得できなかった場合の警告
        if not property_data.get('building_name'):
            self.logger.warning(f"建物名を取得できませんでした: {url}")
            self.record_field_extraction_error('building_name', url, log_error=True)
        
        # 詳細情報を保存
        property_data['detail_info'] = detail_info
        
        # detail_infoの重要な情報をproperty_dataにコピー
        self._copy_detail_info_to_property_data(detail_info, property_data)
        
        # 詳細ページでの必須フィールドを検証
        if not self.validate_detail_page_fields(property_data, url):
            return self.log_validation_error_and_return_none(property_data, url)
        
        return property_data
    
    def _extract_title_and_building_name(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """タイトルと建物名を抽出"""
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
    
    def _extract_address(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """住所を抽出"""
        address_from_datalayer = None
        address_from_html = None
        
        # 1. HTMLのテーブルから住所を取得（最も完全な情報が期待できる）
        # dl.m-status-table要素から住所を探す
        dl_elements = soup.select('dl.m-status-table')
        for dl in dl_elements:
            dt_elements = dl.select('dt.m-status-table__headline')
            dd_elements = dl.select('dd.m-status-table__body')
            
            for dt, dd in zip(dt_elements, dd_elements):
                dt_text = dt.get_text(strip=True)
                if '所在地' in dt_text or '住所' in dt_text:
                    address_text = dd.get_text(strip=True)
                    if address_text and address_text != '-':
                        address_from_html = address_text
                        self.logger.debug(f"HTMLテーブルから住所を取得: {address_from_html}")
                        break
            if address_from_html:
                break
        
        # 2. JavaScriptから住所を取得（フォールバック用）
        # dataLayerから住所を抽出
        script_texts = soup.find_all('script', string=lambda text: text and 'dataLayer.push' in text if text else False)
        self.logger.debug(f"dataLayerを含むscriptタグ数: {len(script_texts)}")
        for script in script_texts:
            script_content = script.string
            # "address":"東京都港区白金２丁目1-8" のパターンを探す
            address_match = re.search(r'"address"\s*:\s*"([^"]+)"', script_content)
            if address_match:
                address_from_datalayer = address_match.group(1)
                self.logger.debug(f"dataLayerから住所を取得: {address_from_datalayer}")
                break
        
        # gmapParmsからも試す（dataLayerにない場合）
        if not address_from_datalayer:
            script_texts = soup.find_all('script', string=lambda text: text and 'gmapParms' in text if text else False)
            self.logger.debug(f"gmapParmsを含むscriptタグ数: {len(script_texts)}")
            for script in script_texts:
                script_content = script.string
                # address: '東京都港区白金２丁目1-8' のパターンを探す
                address_match = re.search(r"address\s*:\s*['\"]([^'\"]+)['\"]", script_content)
                if address_match:
                    address_from_datalayer = address_match.group(1)
                    self.logger.debug(f"gmapParmsから住所を取得: {address_from_datalayer}")
                    break
        
        # 3. 最適な住所を選択（より完全な住所を優先）
        if address_from_html and address_from_datalayer:
            # 両方ある場合は、より長い（完全な）方を選択
            if len(address_from_html) >= len(address_from_datalayer):
                property_data['address'] = address_from_html
                self.logger.info(f"HTMLテーブルの住所を採用（より完全）: {property_data['address']}")
            else:
                property_data['address'] = address_from_datalayer
                self.logger.info(f"dataLayerの住所を採用（より完全）: {property_data['address']}")
        elif address_from_html:
            property_data['address'] = address_from_html
            self.logger.info(f"HTMLテーブルから住所を取得: {property_data['address']}")
        elif address_from_datalayer:
            property_data['address'] = address_from_datalayer
            self.logger.info(f"dataLayerから住所を取得: {property_data['address']}")
        else:
            # 最終手段: metaタグから取得
            meta_address = soup.find('meta', {'name': 'address'})
            if meta_address and meta_address.get('content'):
                property_data['address'] = meta_address.get('content')
                self.logger.info(f"metaタグから住所を取得: {property_data['address']}")
            else:
                self.logger.warning(f"住所を取得できませんでした")
    
    def _extract_detail_price(self, soup: BeautifulSoup, property_data: Dict[str, Any], url: str) -> bool:
        """詳細ページから価格を抽出"""
        # パターン1: 価格専用のセレクタ
        price_elem = soup.select_one('.a-price__number, .o-detail-header__price-wrapper')
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price = extract_price(price_text)
            if price:
                property_data['price'] = price
                return True
            else:
                self.logger.warning(f"価格抽出失敗 - パターン1: '{price_text}' from {url}")
        
        # パターン2: テーブルから価格を探す
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
                            return True
        
        self.logger.warning(f"価格情報を取得できませんでした: {url}")
        return False
    
    def _extract_property_details(self, soup: BeautifulSoup, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """物件詳細情報を抽出"""
        # JavaScriptのdataLayerから情報を取得（新しいページ構造）
        script_tags = soup.find_all('script')
        for script in script_tags:
            script_text = script.get_text()
            if 'dataLayer' in script_text and 'tlab.property' in script_text:
                # 間取り情報を取得
                layout_match = re.search(r'"tlab\.property\.layout"\s*:\s*"([^"]+)"', script_text)
                if layout_match:
                    layout = layout_match.group(1)
                    # 全角文字を半角に変換
                    layout = layout.replace('ＬＤＫ', 'LDK').replace('Ｓ', 'S').replace('＋', '+')
                    property_data['layout'] = layout
                    self.logger.info(f"dataLayerから間取りを取得: {layout}")
                
                # その他の情報も取得
                area_match = re.search(r'"tlab\.property\.monopoly_area"\s*:\s*"([^"]+)"', script_text)
                if area_match:
                    area = extract_area(area_match.group(1))
                    if area:
                        property_data['area'] = area
        
        # m-status-tableクラスのテーブルから情報を取得（dl/dd構造にも対応）
        status_tables = soup.select('.m-status-table')
        
        for table in status_tables:
            # dl/dd構造の場合
            if table.name == 'dl':
                dt_elements = table.select('dt.m-status-table__headline')
                dd_elements = table.select('dd.m-status-table__body')
                
                for dt, dd in zip(dt_elements, dd_elements):
                    label = dt.get_text(strip=True)
                    
                    # 交通情報の場合は特別処理
                    if '交通' in label or '最寄' in label or '駅' in label:
                        # 交通情報を正しく抽出（リンクテキストと通常テキストを結合）
                        station_parts = []
                        for elem in dd.descendants:
                            if isinstance(elem, str) and elem.strip():
                                station_parts.append(elem.strip())
                        value = ' '.join(station_parts)
                    else:
                        # 他の情報はリンク要素を除外してテキストを取得
                        dd_copy = dd.__copy__()  # ddを変更しないためコピーを作成
                        for link in dd_copy.find_all('a'):
                            link.extract()
                        value = dd_copy.get_text(strip=True)
                    
                    self._extract_property_info(label, value, property_data, detail_info)
            else:
                # table構造の場合（従来の処理）
                rows = table.select('tr, .m-status-table__item')
                for row in rows:
                    label_elem = row.select_one('.m-status-table__headline, th')
                    value_elem = row.select_one('.m-status-table__body, td')
                    
                    if label_elem and value_elem:
                        label = label_elem.get_text(strip=True)
                        
                        # 交通情報の場合は特別処理
                        if '交通' in label or '最寄' in label or '駅' in label:
                            # 交通情報を正しく抽出（リンクテキストと通常テキストを結合）
                            station_parts = []
                            for elem in value_elem.descendants:
                                if isinstance(elem, str) and elem.strip():
                                    station_parts.append(elem.strip())
                            value = ' '.join(station_parts)
                        else:
                            # 他の情報はリンク要素を除外してテキストを取得
                            value_elem_copy = value_elem.__copy__()
                            for link in value_elem_copy.find_all('a'):
                                link.extract()
                            value = value_elem_copy.get_text(strip=True)
                        
                        self._extract_property_info(label, value, property_data, detail_info)
        
        # 通常のテーブルとdl要素もチェック（フォールバック）
        self._extract_from_regular_tables(soup, property_data, detail_info)
    
    def _extract_from_regular_tables(self, soup: BeautifulSoup, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """通常のテーブルとdl要素から情報を抽出"""
        info_elements = soup.select('table:not(.m-status-table), dl')
        
        for elem in info_elements:
            if elem.name == 'table':
                rows = elem.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value_cell = cells[1]
                        
                        # 交通情報の場合は特別処理
                        if '交通' in label or '最寄' in label or '駅' in label:
                            # 交通情報を正しく抽出（リンクテキストと通常テキストを結合）
                            station_parts = []
                            for elem in value_cell.descendants:
                                if isinstance(elem, str) and elem.strip():
                                    station_parts.append(elem.strip())
                            value = ' '.join(station_parts)
                        else:
                            # 他の情報はリンク要素を除外してテキストを取得
                            value_cell_copy = value_cell.__copy__()
                            for link in value_cell_copy.find_all('a'):
                                link.extract()
                            value = value_cell_copy.get_text(strip=True)
                        
                        self._extract_property_info(label, value, property_data, detail_info)
            
            elif elem.name == 'dl':
                dt_elements = elem.find_all('dt')
                dd_elements = elem.find_all('dd')
                for i, dt in enumerate(dt_elements):
                    if i < len(dd_elements):
                        label = dt.get_text(strip=True)
                        value_elem = dd_elements[i]
                        
                        # 交通情報の場合は特別処理
                        if '交通' in label or '最寄' in label or '駅' in label:
                            # 交通情報を正しく抽出（リンクテキストと通常テキストを結合）
                            station_parts = []
                            for elem in value_elem.descendants:
                                if isinstance(elem, str) and elem.strip():
                                    station_parts.append(elem.strip())
                            value = ' '.join(station_parts)
                        else:
                            # 他の情報はリンク要素を除外してテキストを取得
                            value_elem_copy = value_elem.__copy__()
                            for link in value_elem_copy.find_all('a'):
                                link.extract()
                            value = value_elem_copy.get_text(strip=True)
                        
                        self._extract_property_info(label, value, property_data, detail_info)
    
    def _extract_agency_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """不動産会社情報を抽出"""
        agency_elem = soup.select_one('.agency-name, .company-name, [class*="agency"]')
        if agency_elem:
            property_data['agency_name'] = agency_elem.get_text(strip=True)
        
        # 電話番号を取得
        tel_match = re.search(r'0\d{1,4}-\d{1,4}-\d{4}', soup.get_text())
        if tel_match:
            property_data['agency_tel'] = tel_match.group(0)
    
    
    def _copy_detail_info_to_property_data(self, detail_info: Dict[str, Any], property_data: Dict[str, Any]):
        """detail_infoの重要な情報をproperty_dataにコピー"""
        fields_to_copy = [
            'total_floors', 'basement_floors', 'total_units',
            'structure', 'land_rights', 'parking_info'
        ]
        
        for field in fields_to_copy:
            if field in detail_info:
                # 文字列の場合は数値を抽出
                if field == 'total_floors' and isinstance(detail_info[field], str):
                    total_floors, _ = extract_total_floors(detail_info[field])
                    if total_floors is not None:
                        property_data[field] = total_floors
                else:
                    property_data[field] = detail_info[field]
    
    def _extract_property_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """ラベルと値から物件情報を抽出"""
        import re  # メソッドの最初でインポート
        # 建物名/物件名
        if '物件名' in label or '建物名' in label:
            property_data['building_name'] = value
        
        # 所在地/住所
        elif '所在地' in label or '住所' in label:
            if value and value.strip() and value != '-':
                # すでに住所が設定されている場合は、より完全な住所のみで上書き
                current_address = property_data.get('address', '')
                if not current_address or len(value) > len(current_address):
                    property_data['address'] = value
        
        # 階数（所在階）
        elif ('階数' in label or '所在階' in label) and '総階数' not in label:
            self._extract_floor_info(label, value, property_data, detail_info)
        
        # 総階数
        elif '総階数' in label or '建物階数' in label:
            self._extract_total_floors_info(value, detail_info)
        
        # 構造
        elif '構造' in label:
            self._extract_structure_info(value, detail_info)
        
        # 専有面積
        elif ('専有面積' in label or '面積' in label) and 'バルコニー' not in label and '敷地' not in label:
            area_value = extract_area(value)
            if area_value:
                property_data['area'] = area_value
        
        # バルコニー面積
        elif 'バルコニー' in label:
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 間取り
        elif '間取り' in label or '間取' in label:
            # 連続する空白を1つのスペースに変換してから正規化
            cleaned_value = re.sub(r'\s+', ' ', value.strip())
            layout = normalize_layout(cleaned_value)
            if layout:
                property_data['layout'] = layout
                if cleaned_value != value:
                    self.logger.info(f"間取りを取得（空白を正規化）: {value} → {layout}")
                else:
                    self.logger.info(f"間取りを取得: {value} → {layout}")
            else:
                self.logger.warning(f"間取りの正規化に失敗: {value}")
        
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
                # 月情報も取得
                # スラッシュ形式（「1971/04」）に対応
                slash_match = re.search(r'(\d{4})/(\d{1,2})', value)
                if slash_match:
                    property_data['built_month'] = int(slash_match.group(2))
                else:
                    # 通常の月パターン（「3月」）
                    month_match = re.search(r'(\d{1,2})月', value)
                    if month_match:
                        property_data['built_month'] = int(month_match.group(1))
        
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
        
        # その他の詳細情報
        self._extract_additional_info(label, value, property_data, detail_info)
    
    def _extract_floor_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """階数情報を抽出"""
        floor_number = extract_floor_number(value)
        if floor_number is not None:
            property_data['floor_number'] = floor_number
        
        # "8階／地上12階"のような形式から総階数も抽出
        if '地上' in value or '地下' in value:
            total_floors, basement_floors = extract_total_floors(value)
            if total_floors is not None:
                detail_info['total_floors'] = total_floors
            if basement_floors is not None and basement_floors > 0:
                detail_info['basement_floors'] = basement_floors
    
    def _extract_total_floors_info(self, value: str, detail_info: Dict[str, Any]):
        """総階数情報を抽出"""
        # 総階数から数値を抽出
        total_floors_match = re.search(r'(\d+)階', value)
        if total_floors_match:
            detail_info['total_floors'] = int(total_floors_match.group(1))
    
    def _extract_structure_info(self, value: str, detail_info: Dict[str, Any]):
        """構造情報を抽出"""
        detail_info['structure'] = value
        # 構造フィールドから総階数と地下階数を抽出
        if '階建' in value or '階' in value:
            total_floors, basement_floors = extract_total_floors(value)
            if total_floors is not None and 'total_floors' not in detail_info:
                detail_info['total_floors'] = total_floors
            if basement_floors is not None and basement_floors > 0:
                detail_info['basement_floors'] = basement_floors
    
    def _extract_additional_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """その他の詳細情報を抽出"""
        # 土地権利
        if '土地権利' in label or '権利形態' in label:
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
            self._extract_grantact_building_name(soup, property_data)
            
            # JavaScriptから住所を取得
            self._extract_grantact_address(soup, property_data)
            
            # 必須フィールドの確認とフォールバック
            self._validate_grantact_required_fields(soup, property_data)
            
            # 不動産会社情報
            property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
            
            # 詳細情報を保存
            property_data['detail_info'] = detail_info
            
            # detail_infoの重要な情報をproperty_dataにコピー
            self._copy_detail_info_to_property_data(detail_info, property_data)
            
            # 詳細ページでの必須フィールドを検証
            if not self.validate_detail_page_fields(property_data, property_data.get('url', '')):
                return self.log_validation_error_and_return_none(property_data, property_data.get('url', ''), "詳細ページ検証エラー(grantact)")
            
            return property_data
            
        except Exception as e:
            self.logger.error(f"grantact詳細ページ解析エラー: {property_data['url']} - {str(e)}")
            self.logger.debug(f"トレースバック: {traceback.format_exc()}")
            # エラー情報を保存して、Noneを返す（基底クラスでエラーハンドリングされる）
            self._last_detail_error = {
                'type': 'exception',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'building_name': property_data.get('building_name', ''),
                'price': property_data.get('price', ''),
                'site_property_id': property_data.get('site_property_id', '')
            }
            return None
    
    def _extract_grantact_building_name(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページから建物名を抽出"""
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # "パークコート赤坂ザ・タワー｜東急リバブル" のような形式から建物名を抽出
            title_match = re.search(r'^(.+?)(?:｜|│)', title_text)
            if title_match:
                property_data['title'] = title_match.group(1).strip()
                property_data['building_name'] = property_data['title']
    
    def _extract_grantact_address(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページから住所を抽出"""
        if not property_data.get('address'):
            # dataLayerから住所を抽出
            script_texts = soup.find_all('script', string=lambda text: text and 'dataLayer.push' in text if text else False)
            for script in script_texts:
                script_content = script.string
                address_match = re.search(r'"address"\s*:\s*"([^"]+)"', script_content)
                if address_match:
                    property_data['address'] = address_match.group(1)
                    break
            
            # gmapParmsからも試す
            if not property_data.get('address'):
                script_texts = soup.find_all('script', string=lambda text: text and 'gmapParms' in text if text else False)
                for script in script_texts:
                    script_content = script.string
                    address_match = re.search(r"address\s*:\s*['\"]([^'\"]+)['\"]", script_content)
                    if address_match:
                        property_data['address'] = address_match.group(1)
                        break
    
    def _validate_grantact_required_fields(self, soup: BeautifulSoup, property_data: Dict[str, Any]):
        """grantactページの必須フィールドを検証"""
        # 建物名がない場合はh1タグからも試す
        if not property_data.get('building_name'):
            h1 = soup.find('h1')
            if h1:
                property_data['building_name'] = h1.get_text(strip=True)
        
        # 価格が取得できなかった場合の警告
        if not property_data.get('price'):
            self.logger.warning(f"[grantact] 価格情報を取得できませんでした: {property_data['url']}")
            self.record_field_extraction_error('price', property_data['url'], log_error=True)
        
        # 建物名が取得できなかった場合の警告
        if not property_data.get('building_name'):
            self.logger.warning(f"[grantact] 建物名を取得できませんでした: {property_data['url']}")
            self.record_field_extraction_error('building_name', property_data['url'], log_error=True)
    
    def _extract_grantact_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """grantactページから情報を抽出"""
        # マンション名/建物名
        if 'マンション名' in label:
            property_data['building_name'] = value
        
        # 所在地
        elif '所在地' in label:
            if value and value.strip() and value != '-':
                # すでに住所が設定されている場合は、より完全な住所のみで上書き
                current_address = property_data.get('address', '')
                if not current_address or len(value) > len(current_address):
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
                # デバッグ: 特定物件の価格
                if property_data.get('site_property_id') in self.DEBUG_PROPERTY_IDS:
                    self.logger.info(f"DEBUG: grantact詳細価格 - ID: {property_data['site_property_id']}, "
                                   f"label: '{label}', value: '{value}', extracted: {price}")
        
        # 間取り
        elif label == '間取':
            # 連続する空白を1つのスペースに変換してから正規化
            import re
            cleaned_value = re.sub(r'\s+', ' ', value.strip())
            layout = normalize_layout(cleaned_value)
            if layout:
                property_data['layout'] = layout
                if cleaned_value != value:
                    self.logger.info(f"[grantact] 間取りを取得（空白を正規化）: {value} → {layout}")
                else:
                    self.logger.info(f"[grantact] 間取りを取得: {value} → {layout}")
            else:
                self.logger.warning(f"[grantact] 間取りの正規化に失敗: {value}")
                # 正規化に失敗した場合は、少なくとも空白を正規化した値を使用
                property_data['layout'] = cleaned_value[:20]  # varchar(20)制限のため
        
        # 専有面積
        elif '専有面積' in label:
            area = extract_area(value)
            if area:
                property_data['area'] = area
        
        # バルコニー面積
        elif 'バルコニー面積' in label:
            balcony_area = extract_area(value)
            if balcony_area:
                property_data['balcony_area'] = balcony_area
        
        # 所在階
        elif label == '所在階' or '所在階' in label:
            floor_number = extract_floor_number(value)
            if floor_number is not None:
                property_data['floor_number'] = floor_number
        
        # 建物階数
        elif '建物階数' in label:
            total_floors, basement_floors = extract_total_floors(value)
            if total_floors is not None:
                detail_info['total_floors'] = total_floors
            if basement_floors is not None and basement_floors > 0:
                detail_info['basement_floors'] = basement_floors
        
        # その他の情報
        self._extract_grantact_additional_info(label, value, property_data, detail_info)
    
    def _extract_grantact_additional_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
        """grantactページから追加情報を抽出"""
        # 総戸数
        if '総戸数' in label:
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
                # 月情報も取得
                # スラッシュ形式（「1971/04」）に対応
                slash_match = re.search(r'(\d{4})/(\d{1,2})', value)
                if slash_match:
                    property_data['built_month'] = int(slash_match.group(2))
                else:
                    # 通常の月パターン（「3月」）
                    month_match = re.search(r'(\d{1,2})月', value)
                    if month_match:
                        property_data['built_month'] = int(month_match.group(1))
        
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