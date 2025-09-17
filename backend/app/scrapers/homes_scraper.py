"""
LIFULL HOME'Sスクレイパー（リファクタリング版）
homes.co.jpから中古マンション情報を取得
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup
from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import HomesParser
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from .data_normalizer import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors,
    validate_area  # 共通のvalidate_area関数を使用（1000㎡まで対応）
)


class HomesScraper(BaseScraper):
    """LIFULL HOME'Sのスクレイパー"""
    
    BASE_URL = "https://www.homes.co.jp"
    SOURCE_SITE = SourceSite.HOMES
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(self.SOURCE_SITE, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = HomesParser(logger=self.logger)
        # HOMESは一覧ページと詳細ページで建物名の表記が異なることがあるため、部分一致を許可
        self.allow_partial_building_name_match = True
        # MULTI_SOURCEモードを使用（詳細ページの複数箇所から建物名を取得して検証）
        from ..scrapers.base_scraper import BuildingNameVerificationMode
        self.building_name_verification_mode = BuildingNameVerificationMode.MULTI_SOURCE
        self._setup_headers()
    
    def get_optional_required_fields(self) -> List[str]:
        """HOMESではlayoutは必須ではない（稀に取得できないため）
        
        Returns:
            List[str]: オプショナルな必須フィールドのリスト（空リスト）
        """
        return []  # layoutを必須から除外

    
    def get_partial_required_fields(self) -> Dict[str, Dict[str, Any]]:
        """HOMESの部分的必須フィールドの設定
        
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
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """LIFULL HOME'Sのsite_property_idの妥当性を検証
        
        LIFULL HOME'Sの物件IDは以下の形式：
        - 数字のみ（例：1234567890）
        - b-で始まる英数字（例：b-35005010002458）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # LIFULL HOME'S固有の検証
        # パターン1: 数字のみ
        if site_property_id.isdigit():
            # 通常は7〜12桁程度
            if len(site_property_id) < 7 or len(site_property_id) > 15:
                self.logger.warning(
                    f"[HOMES] site_property_idの桁数が異常です（通常7-15桁）: '{site_property_id}' "
                    f"(桁数: {len(site_property_id)}) URL={url}"
                )
            return True
            
        # パターン2: b-で始まる英数字
        if site_property_id.startswith('b-'):
            remaining = site_property_id[2:]
            if remaining and remaining.replace('-', '').isalnum():
                return True
            else:
                self.logger.error(
                    f"[HOMES] b-形式のsite_property_idが不正です: '{site_property_id}' URL={url}"
                )
                return False
                
        # どちらのパターンにも合致しない
        self.logger.error(
            f"[HOMES] site_property_idの形式が不正です（数字のみ、またはb-で始まる英数字である必要があります）: '{site_property_id}' URL={url}"
        )
        return False
    
    def _setup_headers(self):
        """HTTPヘッダーの設定"""
        self.http_client.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """ページを取得してBeautifulSoupオブジェクトを返す"""
        try:
            time.sleep(3)  # より長い遅延を設定
            
            # リファラーを設定
            if '/list/' in url:
                self.http_client.session.headers['Referer'] = 'https://www.homes.co.jp/'
            else:
                self.http_client.session.headers['Referer'] = 'https://www.homes.co.jp/mansion/chuko/tokyo/list/'
            
            response = self.http_client.session.get(url, timeout=30, allow_redirects=True)
            
            # 405エラーの特別処理
            if response.status_code == 405:
                self.logger.error(f"405 Method Not Allowed for {url}")
                self.logger.info("Trying with modified headers...")
                self.http_client.session.headers['Sec-Fetch-Site'] = 'same-origin'
                self.http_client.session.headers['Sec-Fetch-Mode'] = 'cors'
                time.sleep(5)
                response = self.http_client.session.get(url, timeout=30)
            
            response.raise_for_status()
            
            if len(response.content) < 1000:
                self.logger.warning(f"Response seems too small ({len(response.content)} bytes) for {url}")
            
            return BeautifulSoup(response.content, 'html.parser')
            
        except Exception as e:
            # 404エラーの場合も警告として記録（URL構造が変わった可能性もある）
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                self.logger.warning(f"[HOMES] ページが見つかりません（404）: {url} - 最終ページを超えたか、URL構造が変更された可能性があります")
            else:
                self.logger.error(f"Failed to fetch {url}: {type(e).__name__}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.debug(f"Response headers: {dict(e.response.headers)}")
            return None
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """HOME'Sの検索URLを生成"""
        from .area_config import get_area_code, get_homes_city_code
        area_code = get_area_code(area)
        city_code = get_homes_city_code(area_code)
        # ページ1の場合はページパラメータを付けない（HOMESの仕様）
        if page == 1:
            return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/"
        else:
            return f"{self.BASE_URL}/mansion/chuko/tokyo/{city_code}/list/?page={page}"
    
    def _extract_price(self, soup: BeautifulSoup, page_text: str) -> Optional[int]:
        """価格情報を抽出"""
        # セレクタのリスト
        price_selectors = [
            'b.text-brand', 'b[class*="text-brand"]', '.priceLabel', '.price',
            '[class*="price"]', 'span[class*="price"]', 'div[class*="price"]',
            'p[class*="price"]', '.bukkenPrice', '.detailPrice', '[class*="amount"]'
        ]
        
        # セレクタで価格を探す
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem and '万円' in elem.get_text():
                price = extract_price(elem.get_text(strip=True))
                if price:
                    self.logger.info(f"[HOMES] Price found with selector: {selector} - {price}万円")
                    return price
        
        # b要素とstrong要素を確認
        for tag in ['b', 'strong']:
            for elem in soup.select(tag):
                if '万円' in elem.get_text():
                    price = extract_price(elem.get_text(strip=True))
                    if price:
                        self.logger.info(f"[HOMES] Price found in {tag} tag: {price}万円")
                        return price
        
        # ページ全体から価格を探す
        self.logger.warning("[HOMES] Price not found with selectors, searching in full text...")
        price_matches = re.findall(r'[\d,]+(?:億[\d,]*)?万円', page_text)
        
        for price_text in price_matches[:5]:
            price = extract_price(price_text)
            if price and price >= 100:  # 100万円以上なら妥当な価格
                self.logger.info(f"[HOMES] Selected price from text: {price}万円")
                return price
        
        self.logger.error("[HOMES] No price pattern found")
        return None
    
    def _extract_room_number(self, soup: BeautifulSoup) -> Optional[str]:
        """部屋番号を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
        
        Returns:
            部屋番号（存在しない場合はNone）
        """
        room_number = None
        
        # h1タグから部屋番号を抽出
        _, h1_room = self._extract_building_name_from_h1(soup)
        if h1_room:
            room_number = h1_room
            self.logger.debug(f"[HOMES] h1タグから部屋番号を取得: {room_number}")
        
        # 他のソースからも部屋番号を探すことができる
        # 例: 物件概要テーブルの「部屋番号」「号室」など
        
        return room_number
    
    def get_building_names_from_detail(self, detail_data: Dict[str, Any]) -> List[str]:
        """詳細ページから複数の建物名を取得（MULTI_SOURCEモード用）
        
        _building_names_candidatesから建物名候補を取得して返す。
        
        Args:
            detail_data: 詳細ページから取得したデータ
            
        Returns:
            建物名のリスト（最大2つ）
        """
        # 詳細データに保存された建物名候補を取得
        candidates = detail_data.get('_building_names_candidates', [])
        
        # 重複を除去（完全一致のみ）
        unique_names = []
        seen = set()
        
        for name in candidates:
            if name and name not in seen:
                unique_names.append(name)
                seen.add(name)
                if len(unique_names) >= 2:  # 最大2つまで
                    break
        
        # 候補がない場合は、通常のbuilding_nameを使用
        if not unique_names and detail_data.get('building_name'):
            unique_names = [detail_data['building_name']]
        
        return unique_names
    
    def _extract_building_name_from_breadcrumb(self, soup: BeautifulSoup) -> Optional[str]:
        """パンくずリストから建物名を取得"""
        # LIFULL HOME'Sのパンくずリスト：複数のパターンに対応
        # 1. breadcrumb-listタグ
        # 2. p.mod-breadcrumbs
        # 3. [class*="breadcrumb"]
        breadcrumb_tag = soup.find('breadcrumb-list')
        if breadcrumb_tag:
            breadcrumb_list = breadcrumb_tag.select('ol > li')
        else:
            # p.mod-breadcrumbsパターンを試す
            breadcrumb_tag = soup.select_one('p.mod-breadcrumbs, [class*="breadcrumb"]')
            if breadcrumb_tag:
                breadcrumb_list = breadcrumb_tag.select('li')
            else:
                # フォールバック：最初のol要素（hide-scrollbarクラス）
                breadcrumb_list = soup.select('ol.hide-scrollbar > li')
        
        if breadcrumb_list:
            # 最後のli要素を取得
            last_li = breadcrumb_list[-1]
            
            # li内のテキストを取得（a要素がある場合はその中のテキスト）
            last_elem = last_li.select_one('a')
            if last_elem:
                last_text = last_elem.get_text(strip=True)
            else:
                last_text = last_li.get_text(strip=True)
            
            self.logger.debug(f"[HOMES] breadcrumb-list > ol > li の最後の要素: {last_text}")
            
            # 建物名として妥当かチェック
            if self._is_valid_building_name(last_text):
                building_name = re.sub(r'^(中古マンション|マンション)', '', last_text).strip()
                
                # 階数情報と部屋番号を除去
                # 例: 「グランドパレス田町 4階/413」→「グランドパレス田町」
                # 例: 「デュオ・スカーラ西麻布タワーWEST 12階」→「デュオ・スカーラ西麻布タワーWEST」
                building_name = re.sub(r'\s+\d+階(?:/\d+[A-Z]?)?$', '', building_name)
                
                self.logger.info(f"[HOMES] パンくずリストから建物名を取得: {building_name}")
                return building_name
            else:
                self.logger.debug(f"[HOMES] パンくずの最後の要素が建物名として無効: {last_text}")
        else:
            self.logger.debug("[HOMES] パンくずリスト（breadcrumb-list > ol > liまたはol.hide-scrollbar > li）が見つかりませんでした")
        
        return None
    
    def _is_valid_building_name(self, text: str) -> bool:
        """建物名として妥当かチェック"""
        if not text:
            return False
            
        # 駅情報のパターンを除外（最優先）
        # 「駅」「徒歩」「分」を含む文字列は建物名ではない
        station_patterns = [
            '駅', '徒歩', '分歩', 'バス',
            '線', 'ライン', 'Line'
        ]
        if any(pattern in text for pattern in station_patterns):
            self.logger.debug(f"[HOMES] 駅情報のため建物名として無効: {text}")
            return False
            
        # 不要な文字列を除外
        skip_patterns = [
            'ホーム', 'HOME', 'トップ', 'TOP',
            '中古マンション一覧', '中古マンション', 'マンション一覧',
            '物件一覧', '一覧', '検索結果',
            'LIFULL', 'ライフル', 'ホームズ', 'HOMES',
            '>' # パンくずの区切り文字
        ]
        if any(skip in text for skip in skip_patterns):
            return False
            
        # 「〇〇区」「〇〇市」などの地名でない場合
        if re.search(r'(東京都|都|道|府|県|市|区|町|村)$', text):
            return False
            
        # 数字のみでない場合
        if text.isdigit():
            return False
            
        # 極端に短い（2文字以下）または長い（50文字以上）場合は除外
        if len(text) <= 2 or len(text) >= 50:
            return False
            
        return True
    
    def _extract_building_name_from_detail_table(self, soup: BeautifulSoup) -> Optional[str]:
        """物件概要テーブルから建物名を取得"""
        detail_tables = soup.select('table.detailTable, table.mod-detailTable, table[class*="detail"]')
        for table in detail_tables:
            rows = table.select('tr')
            for row in rows:
                th = row.select_one('th')
                td = row.select_one('td')
                if th and td:
                    header = th.get_text(strip=True)
                    if '物件名' in header or 'マンション名' in header or '建物名' in header:
                        building_name = td.get_text(strip=True)
                        # 「中古マンション」などのプレフィックスを削除
                        building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
                        return building_name
        return None
    
    def _extract_building_name_from_h1(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        """h1タグから建物名と部屋番号を取得
        
        LIFULL HOME'Sの実際の構造（複数パターン対応）:
        1. bukkenNameクラスがある場合（新フォーマット）
        2. break-wordsクラスがある場合（別の新フォーマット）
        3. span要素の位置で判断（旧フォーマット）
        """
        building_name = None
        room_number = None
        
        # h1タグから情報を取得（Header__logoクラスを除外）
        h1_elem = soup.find('h1', class_=lambda x: x and 'Header__logo' not in x)
        if h1_elem:
            # パターン1: bukkenNameクラスを探す（最も正確）
            bukken_name_elem = h1_elem.select_one('.bukkenName')
            if bukken_name_elem:
                building_name = bukken_name_elem.get_text(strip=True)
                self.logger.debug(f"[HOMES] bukkenNameクラスから建物名を取得: {building_name}")
                
                # bukkenRoomクラスから部屋番号を取得
                bukken_room_elem = h1_elem.select_one('.bukkenRoom')
                if bukken_room_elem:
                    room_text = bukken_room_elem.get_text(strip=True)
                    match = re.search(r'/(\d{3,4}[A-Z]?)(?:\s|$)', room_text)
                    if match:
                        room_number = match.group(1)
            
            # パターン2: break-wordsクラスを探す（代官山アドレスのような新フォーマット）
            elif h1_elem.select_one('.break-words'):
                break_words_elem = h1_elem.select_one('.break-words')
                text = break_words_elem.get_text(strip=True)
                # 「代官山アドレス 18階」のような形式から建物名を抽出
                if '階' in text:
                    # 最後の階数部分を除去
                    parts = text.rsplit(' ', 1)
                    if len(parts) > 1 and '階' in parts[-1]:
                        building_name = parts[0]
                    else:
                        building_name = text
                else:
                    building_name = text
                self.logger.debug(f"[HOMES] break-wordsクラスから建物名を取得: {building_name}")
            
            # パターン3: 従来の方法（span要素の位置で判断）
            else:
                spans = h1_elem.select('span')
                if len(spans) >= 4:
                    # 3番目のspan要素に建物名がある
                    building_name_text = spans[2].get_text(strip=True)
                    
                    # 階数情報を除去
                    if ' ' in building_name_text:
                        parts = building_name_text.split(' ')
                        # 最後の部分が階数情報の場合は除去
                        if parts[-1] and ('階' in parts[-1] or '/' in parts[-1]):
                            building_name = ' '.join(parts[:-1])
                            # 部屋番号を抽出
                            match = re.search(r'/(\d{3,4}[A-Z]?)(?:\s|$)', parts[-1])
                            if match:
                                room_number = match.group(1)
                        else:
                            building_name = building_name_text
                    else:
                        building_name = building_name_text
                
                    # 部屋番号も抽出（階数情報の後ろにある可能性）
                    if not room_number and ' ' in building_name_text and '/' in building_name_text:
                        match = re.search(r'/(\d{3,4}[A-Z]?)(?:\s|$)', building_name_text)
                        if match:
                            room_number = match.group(1)
                else:
                    # span要素が少ない場合の処理
                    h1_text = h1_elem.get_text(strip=True)
                    # 駅名情報のパターンを含む場合はスキップ
                    if not any(pattern in h1_text for pattern in ['徒歩', '駅', '（', '区）', '市）', '線']):
                        if '中古マンション' in h1_text:
                            h1_text = h1_text.replace('中古マンション', '').strip()
                        parts = h1_text.split('/')
                        if parts:
                            building_name = parts[0].strip()
        
        # 最終的なクリーンアップ
        if building_name:
            building_name = re.sub(r'^(中古マンション|マンション)', '', building_name).strip()
        
        return building_name, room_number
    
    
    def _extract_property_details_from_dl(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """データリスト（dl/dt/dd）から情報を抽出"""
        details = {}
        
        # 既存のパターン（これまで正常に動作していた処理）
        for dl in soup.select('.detailInfo dl, .mod-detailInfo dl, [class*="detail"] dl'):
            dt = dl.select_one('dt')
            dd = dl.select_one('dd')
            
            if not dt or not dd:
                continue
            
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            self._process_detail_field(label, value, details, element=dd)
        
        # dl要素の別パターン（これまでの処理）
        for dl in soup.select('dl'):
            dt_elements = dl.select('dt')
            dd_elements = dl.select('dd')
            for i, dt in enumerate(dt_elements):
                if i < len(dd_elements):
                    label = dt.get_text(strip=True)
                    value = dd_elements[i].get_text(strip=True)
                    self._process_detail_field(label, value, details)
        
        # 新しいパターン（m-status-table）を追加（今回のページ対応）
        # この処理は上記で取得できなかった場合のフォールバックとして機能
        for dl in soup.select('dl.m-status-table'):
            # m-status-table__headline と m-status-table__body のペアを処理
            headlines = dl.select('dt.m-status-table__headline')
            bodies = dl.select('dd.m-status-table__body')
            
            for i, headline in enumerate(headlines):
                if i < len(bodies):
                    label = headline.get_text(strip=True)
                    value = bodies[i].get_text(strip=True)
                    # 既に取得済みのフィールドはスキップ
                    if '専有面積' in label and 'area' not in details:
                        self._process_detail_field(label, value, details)
                    else:
                        self._process_detail_field(label, value, details)
        
        return details
    
    def _extract_property_details_from_table(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """テーブルから情報を抽出"""
        details = {}
        
        for table in soup.select('table'):
            for row in table.select('tr'):
                cells = row.select('th, td')
                # 複数のth/tdペアがある場合に対応
                i = 0
                while i < len(cells) - 1:
                    # th, tdのペアを処理
                    if cells[i].name == 'th' and cells[i + 1].name == 'td':
                        label = cells[i].get_text(strip=True)
                        value = cells[i + 1].get_text(strip=True)
                        self._process_detail_field(label, value, details)
                        i += 2
                    else:
                        i += 1
        
        return details
    
    def _process_detail_field(self, label: str, value: str, details: Dict[str, Any], element=None):
        """フィールドを処理してdetailsに格納"""
        # デバッグ: 面積関連のフィールドをログに記録
        if '面積' in label:
            self.logger.debug(f"[HOMES] 面積フィールド検出 - label: '{label}', value: '{value}'")
        
        if '所在地' in label or '住所' in label:
            if element:
                # HTML要素から住所を抽出（リンクやタグを適切に処理）
                address = self.extract_address_from_element(element)
            else:
                # フォールバック: テキストから住所をクリーニング
                address = self.clean_address(value)
            details['address'] = address
        elif '間取り' in label:
            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
            if layout_match:
                details['layout'] = layout_match.group(1)
            else:
                layout = normalize_layout(value.split('/')[0].strip())
                if layout:
                    details['layout'] = layout
        elif '専有面積' in label:
            # 専有面積を数値として抽出
            area = extract_area(value)
            if area and validate_area(area):  # data_normalizerの共通検証を使用
                details['area'] = area
        elif '築年月' in label:
            built_year = extract_built_year(value)
            if built_year:
                details['built_year'] = built_year
                details['age'] = datetime.now().year - built_year
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    details['built_month'] = int(month_match.group(1))
        elif '所在階' in label and '階数' in label:
            floor_match = re.search(r'(\d+)階\s*/\s*(\d+)階建', value)
            if floor_match:
                details['floor_number'] = int(floor_match.group(1))
                details['total_floors'] = int(floor_match.group(2))
                _, basement_floors = extract_total_floors(value)
                if basement_floors is not None and basement_floors > 0:
                    details['basement_floors'] = basement_floors
        elif '階' in label and '建' not in label:
            details['floor'] = value
            floor_match = re.search(r'(\d+)階/(\d+)階建', value)
            if floor_match:
                details['floor_number'] = extract_floor_number(floor_match.group(1))
                details['total_floors'] = normalize_integer(floor_match.group(2))
                _, basement_floors = extract_total_floors(value)
                if basement_floors is not None and basement_floors > 0:
                    details['basement_floors'] = basement_floors
            else:
                floor_match = re.search(r'(\d+)階', value)
                if floor_match:
                    details['floor_number'] = int(floor_match.group(1))
        elif '交通' in label or '最寄' in label or '駅' in label:
            from .data_normalizer import format_station_info
            details['station_info'] = format_station_info(value)
        elif '向き' in label or '方角' in label or 'バルコニー' in label or '採光' in label:
            direction = normalize_direction(value)
            if direction:
                details['direction'] = direction
        elif '総戸数' in label or '総区画数' in label:
            # 総戸数を抽出（例：「150戸」→ 150）
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                details['total_units'] = int(units_match.group(1))
                self.logger.info(f"[HOMES] 総戸数: {details['total_units']}戸")
        elif '管理費' in label:
            # "管理費等"も含めて処理する
            management_fee = extract_monthly_fee(value)
            if management_fee:
                details['management_fee'] = management_fee
        elif '修繕積立金' in label:
            repair_fund = extract_monthly_fee(value)
            if repair_fund:
                details['repair_fund'] = repair_fund
        elif '部屋番号' in label or '号室' in label:
            details['room_number'] = value
        elif '権利' in label and ('土地' in label or '敷地' in label):
            details['land_rights'] = value
        elif '駐車' in label:
            details['parking_info'] = value
        elif '主要採光面' in label:
            direction = normalize_direction(value)
            if direction:
                details['direction'] = direction
        elif 'バルコニー面積' in label or ('バルコニー' in label and '面積' in value):
            area = extract_area(value)
            if area:
                details['balcony_area'] = area
        elif '備考' in label:
            details['remarks'] = value
        elif '情報公開日' in label:
            published_date = self._extract_date(value)
            if published_date:
                details['first_published_at'] = published_date
        elif '情報提供日' in label or '情報更新日' in label or '登録日' in label:
            published_date = self._extract_date(value)
            if published_date:
                details['published_at'] = published_date
    
    def _extract_date(self, text: str) -> Optional[datetime]:
        """日付を抽出"""
        date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', text)
        if date_match:
            year = int(date_match.group(1))
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            return datetime(year, month, day)
        return None
    
    def _extract_area_from_page(self, soup: BeautifulSoup, page_text: str) -> Optional[float]:
        """ページ全体から専有面積情報を探す（フォールバック処理）
        
        通常のdl/tableから取得できなかった場合に、
        特にm-status-tableクラスなどの新しい構造から専有面積を取得する
        """
        import re
        
        # 1. floorplanセクションから専有面積を探す（新パターン）
        floorplan_section = soup.find('section', id='floorplan')
        if floorplan_section:
            # span要素で「専有面積」を探す
            area_label = floorplan_section.find('span', string=re.compile('専有面積'))
            if area_label:
                # 次のspan要素を取得
                next_span = area_label.find_next_sibling('span')
                if next_span:
                    area_text = next_span.get_text(strip=True)
                    # 「311.64㎡(壁心)」のような形式から数値を抽出
                    area = extract_area(area_text)
                    if area and validate_area(area):  # data_normalizerの共通検証を使用
                        self.logger.info(f"[HOMES] floorplanセクションから専有面積{area}㎡を取得")
                        return area
        
        # 2. 専有面積のみを探す（他の面積情報は使用しない）
        # m-status-table形式の要素を優先的に探す
        status_tables = soup.select('dl.m-status-table')
        for dl in status_tables:
            # m-status-table__headline と m-status-table__body のペアを探す
            headlines = dl.select('dt.m-status-table__headline')
            bodies = dl.select('dd.m-status-table__body')
            
            for i, headline in enumerate(headlines):
                if i < len(bodies):
                    label = headline.get_text(strip=True)
                    if '専有面積' in label:
                        value = bodies[i].get_text(strip=True)
                        area = extract_area(value)
                        if area and validate_area(area):  # data_normalizerの共通検証を使用
                            self.logger.info(f"[HOMES] フォールバック: m-status-tableから専有面積{area}㎡を取得")
                            return area
        
        # その他の要素から専有面積を探す
        # 専有面積と明記されているもののみを対象とする
        search_selectors = [
            'span:contains("専有面積")',
            'p:contains("専有面積")',
            'div:contains("専有面積")',
            '[class*="area"]:contains("専有")',
        ]
        
        for selector in search_selectors:
            # BeautifulSoupはcontains擬似セレクタをサポートしないため、別の方法を使用
            elements = soup.find_all(text=re.compile('専有面積'))
            for text_node in elements:
                parent = text_node.parent
                if parent:
                    full_text = parent.get_text(strip=True)
                    # 専有面積の値を抽出
                    match = re.search(r'専有面積[：:\s]*(\d+(?:\.\d+)?)\s*(?:㎡|m²|平米)', full_text)
                    if match:
                        area_value = float(match.group(1))
                        if validate_area(area_value):  # data_normalizerの共通検証を使用
                            self.logger.info(f"[HOMES] フォールバック: テキストから専有面積{area_value}㎡を取得")
                            return area_value
        
        return None
    
    def _extract_date_from_page(self, soup: BeautifulSoup, page_text: str) -> Optional[datetime]:
        """ページ全体から情報公開日を取得"""
        # class属性から探す
        date_elements = soup.select('[class*="date"], [class*="update"], [class*="公開"], [class*="info"]')
        for elem in date_elements:
            text = elem.get_text(strip=True)
            if '情報公開日' in text or '掲載日' in text or '登録日' in text:
                date = self._extract_date(text)
                if date:
                    return date
        
        # ページ全体から探す
        date_pattern = re.search(r'情報公開日[：:]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', page_text)
        if date_pattern:
            return self._extract_date(date_pattern.group(0))
        
        return None
    
    def _extract_agency_info(self, soup: BeautifulSoup, page_text: str) -> Tuple[Optional[str], Optional[str]]:
        """不動産会社情報を取得"""
        agency_name = None
        agency_tel = None
        
        # 会社情報セクションから探す
        company_sections = soup.select('.companyInfo, .company-info, [class*="company"]')
        for section in company_sections:
            for table in section.select('table'):
                for row in table.select('tr'):
                    cells = row.select('th, td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        if '会社名' in label or '社名' in label:
                            agency_name = value
                        elif 'TEL' in label or '電話' in label:
                            tel_match = re.search(r'[\d\-\(\)]+', value)
                            if tel_match:
                                agency_tel = tel_match.group(0).replace('(', '').replace(')', '-')
        
        # ページ全体から探す
        if not agency_name:
            company_pattern = re.search(r'(?:会社名|取扱会社|情報提供元)[：:]\s*([^\n]+)', page_text)
            if company_pattern:
                company_name = company_pattern.group(1).strip().split('　')[0].split(' ')[0]
                if len(company_name) > 2 and ('株式会社' in company_name or '有限会社' in company_name):
                    agency_name = company_name
        
        # 問合せ先から探す
        if not agency_name:
            inquiry_pattern = re.search(r'問合せ先[：:]\s*([^\n]+)', page_text)
            if inquiry_pattern:
                company_text = inquiry_pattern.group(1).strip()
                company_match = re.search(r'((?:株式会社|有限会社)?[^\s　]+(?:株式会社|有限会社)?)', company_text)
                if company_match:
                    agency_name = re.sub(r'(会社情報|ポイント|〜).*$', '', company_match.group(1)).strip()
        
        # 電話番号を探す
        if not agency_tel:
            tel_pattern = re.search(r'(?:TEL|電話|問合せ)[：:]\s*([\d\-\(\)]+)', page_text)
            if tel_pattern:
                agency_tel = tel_pattern.group(1).replace('(', '').replace(')', '-')
        
        return agency_name, agency_tel
    
    
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
            
            # パーサーで取得できなかったデータを独自処理で補完
            # HOMESパーサーが取得できない場合の補完処理
            if 'area' not in detail_data or 'layout' not in detail_data:
                self._extract_detail_from_soup(soup, detail_data)
            
            # site_property_idの抽出と検証
            if "site_property_id" not in detail_data and url:
                import re
                site_id_match = re.search(r'/mansion/b-(\d+)/', url)
                if site_id_match:
                    detail_data["site_property_id"] = site_id_match.group(1)
        
        return detail_data

    def _extract_detail_from_soup(self, soup: BeautifulSoup, detail_data: Dict[str, Any]) -> None:
        """
        パーサーで取得できなかったデータを独自処理で補完
        
        Args:
            soup: BeautifulSoupオブジェクト
            detail_data: 物件データ辞書
        """
        # テーブルから情報を抽出
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    label = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    
                    # 間取り
                    if '間取り' in label and 'layout' not in detail_data:
                        layout = normalize_layout(value)
                        if layout:
                            detail_data['layout'] = layout
                            print(f"    間取り: {detail_data['layout']}")
                    
                    # 専有面積
                    elif '専有面積' in label and 'area' not in detail_data:
                        area = extract_area(value)
                        if area:
                            detail_data['area'] = area
                            print(f"    専有面積: {detail_data['area']}㎡")
                    
                    # 所在階
                    elif '所在階' in label and 'floor_number' not in detail_data:
                        floor_number = extract_floor_number(value)
                        if floor_number is not None:
                            detail_data['floor_number'] = floor_number
                            print(f"    所在階: {detail_data['floor_number']}階")
                    
                    # 向き
                    elif '向き' in label and 'direction' not in detail_data:
                        direction = normalize_direction(value)
                        if direction:
                            detail_data['direction'] = direction
                            print(f"    向き: {detail_data['direction']}")
                    
                    # 築年月
                    elif '築年月' in label:
                        built_year = extract_built_year(value)
                        if built_year and 'built_year' not in detail_data:
                            detail_data['built_year'] = built_year
                            print(f"    築年月: {detail_data['built_year']}年")

    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def is_last_page(self, soup: BeautifulSoup) -> bool:
        """
        現在のページが最終ページかどうかを判定
        
        Returns:
            最終ページの場合True
        """
        try:
            # LIFULL HOME'Sの最終ページ判定（2025年8月改訂）
            # 最終ページの特徴：
            # 1. li.nextPage要素が存在しない
            # 2. または、li.nextPage要素はあるがその中にaタグがない
            
            # 方法1: li.nextPage要素の存在と状態を確認（最も確実な方法）
            next_page_li = soup.select_one('li.nextPage')
            if not next_page_li:
                # li.nextPage要素が存在しない = 最終ページ
                self.logger.info("[HOMES] li.nextPage要素が存在しないため最終ページと判定")
                return True
            
            # li.nextPageは存在するが、その中のaタグを確認
            next_link = next_page_li.select_one('a')
            if not next_link:
                # li.nextPageはあるがaタグがない = 最終ページ
                self.logger.info("[HOMES] li.nextPageはあるがaタグがないため最終ページと判定")
                return True
            
            # 方法2: 物件数が0の場合も最終ページと判定（念のため）
            building_blocks = soup.select('.mod-mergeBuilding--sale')
            if len(building_blocks) == 0:
                self.logger.info("[HOMES] 物件リストが空のため最終ページと判定")
                return True
            
            # 方法3: 物件数が30件未満の場合も最終ページの可能性が高い
            # （通常は1ページ30件表示）
            if 0 < len(building_blocks) < 30:
                self.logger.info(f"[HOMES] 物件数が{len(building_blocks)}件（30件未満）のため最終ページの可能性")
                # この場合もli.nextPageの状態を優先的に判定
                return not next_page_li or not next_link
            
            # すべての条件に該当しない場合は最終ページではない
            return False
            
        except Exception as e:
            self.logger.warning(f"[HOMES] ページ終端判定でエラー: {e}")
            return False
    
    def get_max_page_from_list(self, soup: BeautifulSoup) -> Optional[int]:
        """
        一覧ページから最大ページ数を取得
        
        Returns:
            最大ページ数、取得できない場合はNone
        """
        try:
            # ページネーションから最大ページ数を取得
            page_links = soup.select('.pagination a, .pager a, .pageNation a')
            max_page = 1
            
            for link in page_links:
                text = link.get_text(strip=True)
                if text.isdigit():
                    page_num = int(text)
                    if page_num > max_page:
                        max_page = page_num
            
            if max_page > 1:
                self.logger.info(f"[HOMES] 最大ページ数を検出: {max_page}")
                return max_page
                
            # 結果件数から計算する方法
            result_count_elem = soup.select_one('.result-count, .hit-count, .count')
            if result_count_elem:
                import re
                text = result_count_elem.get_text()
                match = re.search(r'(\d+)件', text)
                if match:
                    total_count = int(match.group(1))
                    # HOMESは通常1ページ30件程度
                    items_per_page = 30
                    max_page = (total_count + items_per_page - 1) // items_per_page
                    self.logger.info(f"[HOMES] 件数から最大ページ数を推定: {max_page} (総件数: {total_count})")
                    return max_page
            
            return None
            
        except Exception as e:
            self.logger.warning(f"[HOMES] 最大ページ数取得でエラー: {e}")
            return None
    
    def _parse_property_row(self, row) -> Optional[Dict[str, Any]]:
        """物件行をパース"""
        property_link = row.select_one('a[href*="/mansion/b-"]')
        if not property_link:
            return None
        
        href = property_link.get('href', '')
        if '/mansion/b-' not in href:
            return None
        
        full_url = urljoin(self.BASE_URL, href)
        property_data = {
            'url': full_url
        }
        
        # 価格情報を取得
        tds = row.select('td')
        if len(tds) > 2:
            price_text = tds[2].get_text(strip=True)
            price = extract_price(price_text)
            if price:
                property_data['price'] = price
                self.logger.info(f"[HOMES] Found price: {price}万円 for {href}")
        
        # 物件IDを抽出
        if not self._extract_site_property_id(href, property_data):
            self.logger.error(f"[HOMES] 物件行をスキップします（site_property_id取得失敗）: {href}")
            return None
        
        # 一覧ページから建物名を取得（bukkenNameクラスから）
        parent_block = row.find_parent(class_='mod-mergeBuilding--sale')
        if parent_block:
            # まずbukkenNameクラスを探す
            bukken_name_elem = parent_block.select_one('.bukkenName')
            if bukken_name_elem:
                building_name_from_list = bukken_name_elem.get_text(strip=True)
                property_data['building_name_from_list'] = building_name_from_list
                property_data['building_name'] = building_name_from_list  # 必須フィールドとして設定
                self.logger.debug(f"[HOMES] 一覧ページから建物名を取得（bukkenName）: {building_name_from_list}")
            else:
                # bukkenNameが見つからない場合は従来の方法（h3タグ）を試す
                building_link = parent_block.select_one('h3 a, .heading a')
                if building_link:
                    link_text = building_link.get_text(strip=True)
                    # "中古マンション"で始まる場合はそれを削除
                    if link_text.startswith('中古マンション'):
                        building_name_from_list = link_text[7:].strip()  # "中古マンション"は7文字
                        property_data['building_name_from_list'] = building_name_from_list
                        property_data['building_name'] = building_name_from_list  # 必須フィールドとして設定
                        self.logger.debug(f"[HOMES] 一覧ページから建物名を取得（h3）: {building_name_from_list}")
                    else:
                        # それ以外の場合は建物名として使用しない（駅名などの可能性があるため）
                        self.logger.warning(f"[HOMES] h3タグから建物名を抽出できません: {link_text}")
        
        return property_data
    
    def _extract_site_property_id(self, href: str, property_data: Dict[str, Any]) -> bool:
        """URLから物件IDを抽出
        
        Returns:
            bool: 抽出に成功した場合True
        """
        id_match = (re.search(r'/mansion/([0-9]+)/', href) or 
                   re.search(r'/mansion/b-([^/]+)/', href) or 
                   re.search(r'/detail-([0-9]+)/', href))
        if id_match:
            site_property_id = id_match.group(1)
            
            # site_property_idの妥当性を検証
            if not self.validate_site_property_id(site_property_id, href):
                self.logger.error(f"[HOMES] 不正なsite_property_idを検出しました: '{site_property_id}'")
                return False
                
            property_data['site_property_id'] = site_property_id
            self.logger.info(f"[HOMES] Extracted site_property_id: {site_property_id}")
            return True
        else:
            self.logger.error(f"[HOMES] サイト物件IDを抽出できません: URL={href}")
            return False
    
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存"""
        self.process_property_data(property_data, existing_listing)
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理"""
        url = property_data.get('url', '')
        if '/mansion/b-' in url and not re.search(r'/\d{3,4}[A-Z]?/$', url):
            self.logger.info(f"[HOMES] Processing building URL (will redirect to property): {url}")
        
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property_common
        )
    
    
