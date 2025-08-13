"""
ノムコムスクレイパー
野村不動産アーバンネット（nomu.com）からの物件情報取得
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, quote
from datetime import datetime
from bs4 import BeautifulSoup, Tag

from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from .area_config import get_area_code
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, clean_address,
    extract_total_floors
)


class NomuScraper(BaseScraper):
    """ノムコムのスクレイパー"""
    
    BASE_URL = "https://www.nomu.com"
    
    # 定数の定義
    DEFAULT_AGENCY_NAME = "野村不動産アーバンネット"
    MAX_ADDRESS_LENGTH = 50  # 住所として妥当な最大文字数
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False):
        super().__init__(SourceSite.NOMU, force_detail_fetch, max_properties, ignore_error_history)
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """ノムコムのsite_property_idの妥当性を検証
        
        ノムコムの物件IDは英数字で構成される（例：A12345678）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # ノムコム固有の検証：英数字のみで構成されているか
        if not site_property_id.replace('-', '').replace('_', '').isalnum():
            self.logger.error(
                f"[NOMU] site_property_idは英数字（ハイフン・アンダースコア可）で構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜15文字程度
        if len(site_property_id) < 6 or len(site_property_id) > 20:
            self.logger.warning(
                f"[NOMU] site_property_idの長さが異常です（通常6-20文字）: '{site_property_id}' "
                f"(長さ: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行
            
        return True
    
    def get_search_url(self, area_code: str, page: int = 1) -> str:
        """検索URLを生成"""
        # エリアコード変換（minato -> 13103）
        actual_area_code = get_area_code(area_code)
        base_url = f"{self.BASE_URL}/mansion/area_tokyo/{actual_area_code}/"
        if page > 1:
            return f"{base_url}?pager_page={page}"
        return base_url
    
    def scrape_area(self, area_code: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        return self.common_scrape_area_logic(area_code, max_pages)
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析"""
        properties = []
        
        # ノムコムの物件カードを検索
        property_cards = soup.find_all("div", class_="item_resultsmall")
        
        if not property_cards:
            print("物件カードが見つかりません")
            return properties
        
        for card in property_cards:
            try:
                property_data = self.parse_property_card(card)
                if property_data:
                    properties.append(property_data)
            except Exception as e:
                self.logger.error(f"物件カード解析エラー - {type(e).__name__}: {str(e)}")
                continue
        
        return properties
    
    def parse_property_card(self, card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件カードから情報を抽出"""
        property_data = {}
        
        # タイトル/建物名とURL
        self._extract_title_and_url(card, property_data)
        
        # テーブルから情報を抽出
        table = card.find("table")
        if table:
            self._extract_card_table_info(table, property_data)
        
        # 仲介業者名（ノムコムは野村不動産アーバンネット）
        property_data['agency_name'] = self.DEFAULT_AGENCY_NAME
        
        # 一覧ページでの必須フィールドを検証（基底クラスの共通メソッドを使用）
        if property_data and self.validate_list_page_fields(property_data):
            return property_data
        else:
            return None
    
    def _extract_title_and_url(self, card: Tag, property_data: Dict[str, Any]):
        """タイトルとURLを抽出"""
        title_elem = card.find("div", class_="item_title")
        if title_elem:
            link = title_elem.find("a")
            if link:
                building_name = link.get_text(strip=True)
                property_data['title'] = building_name
                property_data['building_name'] = building_name
                property_data['building_name_from_list'] = building_name  # 建物名一致確認用
                property_data['url'] = urljoin(self.BASE_URL, link['href'])
                
                # URLから物件IDを抽出
                id_match = re.search(r'/mansion/id/([^/]+)/', link['href'])
                if not id_match:
                    self.logger.error(f"[NOMU] URLから物件IDを抽出できませんでした: {link['href']}")
                    property_data.clear()  # 無効なデータをクリア
                    return
                    
                site_property_id = id_match.group(1)
                
                # site_property_idの妥当性を検証
                if not self.validate_site_property_id(site_property_id, property_data['url']):
                    self.logger.error(f"[NOMU] 不正なsite_property_idを検出しました: '{site_property_id}'")
                    property_data.clear()  # 無効なデータをクリア
                    return
                    
                property_data['site_property_id'] = site_property_id
    
    def _extract_card_table_info(self, table: Tag, property_data: Dict[str, Any]):
        """物件カードのテーブルから情報を抽出"""
        # 価格
        self._extract_card_price(table, property_data)
        
        # 面積・間取り・方角
        self._extract_card_details(table, property_data)
        
        # 階数・築年
        self._extract_card_floor_info(table, property_data)
        
        # 住所と駅情報
        self._extract_card_location(table, property_data)
    
    def _extract_card_price(self, table: Tag, property_data: Dict[str, Any]):
        """カードから価格を抽出"""
        price_cell = table.find("td", class_="item_td item_3")
        if price_cell:
            price_elem = price_cell.find("p", class_="item_price")
            if price_elem:
                price_text = self._build_price_text(price_elem)
                price = extract_price(price_text)
                if price:
                    property_data['price'] = price
                else:
                    # デバッグ情報
                    full_price_text = price_elem.get_text(strip=True)
                    print(f"価格抽出失敗: '{full_price_text}' -> '{price_text}'")
    
    def _build_price_text(self, price_elem: Tag) -> str:
        """価格要素から価格文字列を構築"""
        # span要素から価格を組み立てる
        spans = price_elem.find_all("span")
        price_parts = []
        
        for span in spans:
            span_text = span.get_text(strip=True)
            if span_text:
                class_list = span.get("class", [])
                class_str = " ".join(class_list) if isinstance(class_list, list) else str(class_list)
                
                # numクラスまたは数字を含む場合
                if "num" in class_str or re.search(r'\d', span_text):
                    price_parts.append(span_text)
                # unitクラスまたは単位を含む場合
                elif "unit" in class_str or "yen" in class_str or span_text in ["億", "万円", "万"]:
                    price_parts.append(span_text)
        
        if price_parts:
            price_text = "".join(price_parts)
        else:
            # span要素から組み立てられない場合は全体テキストを使用
            price_text = price_elem.get_text(strip=True)
        
        # 万円を追加（必要な場合）
        if price_text and not price_text.endswith("円") and "万" not in price_text:
            if not price_text.endswith("億"):
                price_text += "万円"
        
        return price_text
    
    def _extract_card_details(self, table: Tag, property_data: Dict[str, Any]):
        """カードから面積・間取り・方角を抽出"""
        detail_cell = table.find("td", class_="item_td item_4")
        if detail_cell:
            p_tags = detail_cell.find_all("p")
            
            # 1番目のp: 面積
            if len(p_tags) > 0:
                area_text = p_tags[0].get_text(strip=True)
                area = extract_area(area_text)
                if area:
                    property_data['area'] = area
            
            # 2番目のp: 間取り
            if len(p_tags) > 1:
                layout = normalize_layout(p_tags[1].get_text(strip=True))
                if layout:
                    property_data['layout'] = layout
            
            # 3番目のp: 方角
            if len(p_tags) > 2:
                direction_text = p_tags[2].get_text(strip=True)
                direction = normalize_direction(direction_text)
                if direction:
                    property_data['direction'] = direction
    
    def _extract_card_floor_info(self, table: Tag, property_data: Dict[str, Any]):
        """カードから階数・築年を抽出"""
        info_cell = table.find("td", class_="item_td item_5")
        if info_cell:
            info_text = info_cell.get_text()
            
            # 階数 (例: "7階 / 29階建")
            floor_pattern = r'(\d+)階\s*/\s*(\d+)階建'
            floor_match = re.search(floor_pattern, info_text)
            if floor_match:
                property_data['floor_number'] = int(floor_match.group(1))
                property_data['total_floors'] = int(floor_match.group(2))
            
            # 築年
            built_year = extract_built_year(info_text)
            if built_year:
                property_data['built_year'] = built_year
    
    def _extract_card_location(self, table: Tag, property_data: Dict[str, Any]):
        """カードから住所と駅情報を抽出"""
        cells = table.find_all("td")
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            # 住所情報の判定
            if "区" in cell_text and len(cell_text) < self.MAX_ADDRESS_LENGTH:
                # 駅情報を除外
                if "駅" not in cell_text and "徒歩" not in cell_text:
                    # 東京都が含まれていない場合のみ追加
                    if "東京都" not in cell_text:
                        property_data['address'] = "東京都" + cell_text
                    else:
                        property_data['address'] = cell_text
                # 駅情報
                elif "駅" in cell_text:
                    property_data['station_info'] = format_station_info(cell_text)
    
    def normalize_address(self, address: str) -> str:
        """住所を正規化"""
        # 不要な空白を除去
        address = re.sub(r'\s+', '', address)
        
        # 東京都を追加（なければ）
        if not address.startswith('東京都'):
            address = '東京都' + address
        
        return address
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（共通インターフェース用）"""
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self._parse_property_detail_from_url,
            save_property_func=self.save_property
        )
    
    def _parse_property_detail_from_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URLから詳細ページを取得して解析"""
        detail_data = self.parse_property_detail(url)
        if detail_data:
            detail_data['url'] = url
        return detail_data
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存"""
        return self.save_property_common(property_data, existing_listing)
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        detail_data = {
            'url': url,
            '_page_text': soup.get_text()  # 建物名一致確認用
        }
        
        # URLから物件IDを抽出
        id_match = re.search(r'/mansion/id/([^/]+)/', url)
        if not id_match:
            self.logger.error(f"[NOMU] 詳細ページでURLから物件IDを抽出できませんでした: {url}")
            return None
            
        site_property_id = id_match.group(1)
        
        # site_property_idの妥当性を検証
        if not self.validate_site_property_id(site_property_id, url):
            self.logger.error(f"[NOMU] 詳細ページで不正なsite_property_idを検出しました: '{site_property_id}'")
            return None
            
        detail_data['site_property_id'] = site_property_id
        
        # 建物名を取得
        self._extract_building_name(soup, detail_data)
        
        # 価格を取得
        self._extract_detail_price(soup, detail_data)
        
        # 住所と駅情報を取得
        self._extract_address_and_station(soup, detail_data, url)
        
        # 物件詳細情報を取得
        self._extract_mansion_table_info(soup, detail_data)
        
        # 管理費と修繕積立金を取得
        self._extract_fees(soup, detail_data)
        
        # 面積と間取りを優先的に取得（現在のページ構造対応）
        self._extract_area_and_layout_current_format(soup, detail_data)
        
        # その他の詳細情報を取得
        self._extract_additional_details(soup, detail_data)
        
        # 詳細ページでの必須フィールドを検証
        if not self.validate_detail_page_fields(detail_data, url):
            return self.log_validation_error_and_return_none(detail_data, url)
        
        return detail_data
    
    def _extract_building_name(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """建物名を抽出"""
        # まずclass="item_title"を探す
        h1_elem = soup.find("h1", {"class": "item_title"})
        if not h1_elem:
            # classがないh1タグも試す
            h1_elem = soup.find("h1")
        
        if h1_elem:
            # h1要素のコピーを作成（元のDOMを変更しないため）
            h1_copy = h1_elem.__copy__()
            
            # item_newクラスの要素を探して除外
            item_new_elem = h1_copy.find(class_='item_new')
            if item_new_elem:
                item_new_elem.extract()  # 価格情報を削除
                self.logger.info(f"[ノムコム] item_newクラスを除外して建物名を取得")
            
            # 残ったテキストが建物名
            building_name = h1_copy.get_text(strip=True)
            if building_name:
                detail_data['building_name'] = building_name
                self.logger.info(f"[ノムコム] 建物名を取得: {building_name}")
    
    def _extract_detail_price(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """詳細ページから価格を抽出（複数フォーマット対応）"""
        # 優先1: p.item_priceフォーマット（現在の主要フォーマット）
        item_price_elem = soup.find("p", {"class": "item_price"})
        if item_price_elem:
            # span.numから価格を構築
            price_text = self._build_price_text(item_price_elem)
            price = extract_price(price_text)
            if price:
                detail_data['price'] = price
                return
        
        # 優先2: 旧フォーマット: p.priceTxt
        price_elem = soup.find("p", {"class": "priceTxt"})
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price = extract_price(price_text)
            if price:
                detail_data['price'] = price
                return
        
        # 優先3: テーブル内の価格（_extract_mansion_table_infoで処理される）
        # この段階では価格がまだ取得されていない場合のみ到達
    
    def _extract_address_and_station(self, soup: BeautifulSoup, detail_data: Dict[str, Any], url: str):
        """住所と駅情報を抽出"""
        address_found = False
        
        # 優先1: テーブルから所在地を探す
        address_found = self._extract_address_from_table(soup, detail_data)
        
        # 優先2: p.addressから探す
        if not address_found:
            address_found = self._extract_address_from_p_tag(soup, detail_data)
        
        # 住所が見つからなかった場合のエラーハンドリング
        if not address_found:
            self._handle_missing_address(url, detail_data)
    
    def _extract_address_from_table(self, soup: BeautifulSoup, detail_data: Dict[str, Any]) -> bool:
        """テーブルから住所を抽出"""
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                for i in range(len(cells) - 1):
                    if cells[i].get_text(strip=True) == "所在地":
                        next_cell = cells[i + 1]
                        # p要素を探す
                        p_elem = next_cell.find("p")
                        if p_elem:
                            address_text = p_elem.get_text(strip=True)
                            address_text = clean_address(address_text, p_elem)
                            # 説明文でないことを確認
                            if address_text and "東京都" in address_text and "区" in address_text:
                                detail_data['address'] = address_text
                                return True
                        else:
                            # p要素がない場合は直接テキストを確認
                            cell_text = next_cell.get_text(strip=True)
                            cell_text = clean_address(cell_text)
                            if cell_text and "東京都" in cell_text and "区" in cell_text:
                                detail_data['address'] = cell_text
                                return True
        return False
    
    def _extract_address_from_p_tag(self, soup: BeautifulSoup, detail_data: Dict[str, Any]) -> bool:
        """p.addressタグから住所を抽出"""
        address_elem = soup.find("p", {"class": "address"})
        if address_elem:
            full_text = address_elem.get_text(strip=True)
            # 「｜」で住所と駅情報を分離
            if "｜" in full_text:
                parts = full_text.split("｜")
                address_text = parts[0].strip()
                address_text = clean_address(address_text)
                if address_text:
                    detail_data['address'] = address_text
                    # 駅情報もフォーマットして保存
                    if len(parts) >= 2:
                        station_text = parts[1].strip()
                        if station_text:
                            detail_data['station_info'] = format_station_info(station_text)
                    return True
            else:
                # 「｜」がない場合は全体を住所として扱う
                if full_text:
                    full_text = clean_address(full_text)
                    detail_data['address'] = full_text
                    return True
        return False
    
    def _handle_missing_address(self, url: str, detail_data: Dict[str, Any]):
        """住所が見つからない場合のエラーハンドリング"""
        if url:
            self.record_field_extraction_error('address', url)
            self.logger.error(
                f"住所が取得できません - URL: {url}, "
                f"建物名: {detail_data.get('building_name', '不明')}, "
                f"テーブル内「所在地」検索: 失敗, "
                f"p.address要素検索: 失敗"
            )
            # 管理画面用のエラーログ
            if hasattr(self, '_save_error_log'):
                self._save_error_log({
                    'url': url,
                    'reason': '住所要素が見つかりません（テーブル「所在地」およびp.address両方なし）',
                    'building_name': detail_data.get('building_name', ''),
                    'price': detail_data.get('price', ''),
                    'timestamp': datetime.now().isoformat()
                })
        else:
            self.logger.error("住所が取得できません（URLなし）")
    
    def _extract_built_year_from_various_sources(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """築年月を様々な場所から探す（新築物件などで特殊な配置の場合がある）"""
        import re
        from .data_normalizer import extract_built_year
        
        # すでに築年が取得済みの場合はスキップ
        if detail_data.get('built_year'):
            return
        
        # 方法1: テーブル内のth/tdペアから探す
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    if "築年月" in label:
                        value = cells[1].get_text(strip=True)
                        built_year = extract_built_year(value)
                        if built_year:
                            detail_data['built_year'] = built_year
                            # 月情報も取得
                            month_match = re.search(r'(\d{1,2})月', value)
                            if month_match:
                                detail_data['built_month'] = int(month_match.group(1))
                            self.logger.info(f"[NOMU] 築年月をテーブルから取得: {value}")
                            return
        
        # 方法2: span.item_status_content から探す
        status_items = soup.find_all("li", {"class": "item_status"})
        for item in status_items:
            label_elem = item.find("span", {"class": "item_status_label"})
            content_elem = item.find("span", {"class": "item_status_content"})
            if label_elem and content_elem:
                label = label_elem.get_text(strip=True)
                if "築年月" in label:
                    value = content_elem.get_text(strip=True)
                    built_year = extract_built_year(value)
                    if built_year:
                        detail_data['built_year'] = built_year
                        # 月情報も取得
                        month_match = re.search(r'(\d{1,2})月', value)
                        if month_match:
                            detail_data['built_month'] = int(month_match.group(1))
                        self.logger.info(f"[NOMU] 築年月をitem_statusから取得: {value}")
                        return
        
        # 方法3: ページテキストから直接探す（最終手段）
        page_text = soup.get_text()
        year_month_pattern = r'築年月[：:\s]*(\d{4}年\d{1,2}月)'
        match = re.search(year_month_pattern, page_text)
        if match:
            value = match.group(1)
            built_year = extract_built_year(value)
            if built_year:
                detail_data['built_year'] = built_year
                # 月情報も取得
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    detail_data['built_month'] = int(month_match.group(1))
                self.logger.info(f"[NOMU] 築年月をテキストから取得: {value}")
    
    def _extract_mansion_table_info(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """物件詳細情報を抽出（両フォーマット対応）"""
        
        # まず、築年月を個別に探す（新築物件などで別の場所にある場合がある）
        self._extract_built_year_from_various_sources(soup, detail_data)
        
        # 新フォーマット: item_tableクラス（3番目または4番目のテーブル）
        item_tables = soup.find_all("table", {"class": "item_table"})
        if len(item_tables) >= 3:
            # 4番目のテーブルがある場合はそれを使用、なければ3番目を使用
            main_table = item_tables[3] if len(item_tables) >= 4 else item_tables[2]
            rows = main_table.find_all("tr")
            
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    self._process_mansion_field(label, value, detail_data)
        else:
            # 旧フォーマット: tableMansionクラス
            mansion_table = soup.find("table", {"class": "tableMansion"})
            if mansion_table:
                cells = mansion_table.find_all("td")
                for cell in cells:
                    inner_div = cell.find("div", {"class": "inner"})
                    if inner_div:
                        heading = inner_div.find("div", {"class": "heading"})
                        value_elem = inner_div.find("p")
                        
                        if heading and value_elem:
                            label = heading.get_text(strip=True)
                            value = value_elem.get_text(strip=True)
                            self._process_mansion_field(label, value, detail_data)
            else:
                # 第3のフォーマット: 現在のページ構造（p.item_priceあり）
                # まず優先的にp.item_priceから価格を抽出
                item_price_elem = soup.find("p", {"class": "item_price"})
                if item_price_elem:
                    price_text = self._build_price_text(item_price_elem)
                    price = extract_price(price_text)
                    if price:
                        detail_data['price'] = price
                    else:
                        self.logger.warning(f"[NOMU] p.item_priceから価格を抽出できませんでした: {price_text}")
                
                # p.item_priceがない場合のみリスト形式を試行
                if not detail_data.get('price'):
                    self._extract_list_format_info(soup, detail_data)
                
                if not detail_data.get('price'):
                    self.logger.warning(f"[NOMU] 詳細ページで物件情報テーブルが見つかりません")
    
    def _process_mansion_field(self, label: str, value: str, detail_data: Dict[str, Any]):
        """マンション情報フィールドを処理（ノムコム専用）"""
        if label == "価格":
            price = extract_price(value)
            if price:
                detail_data['price'] = price
        
        elif label == "間取り":
            layout = normalize_layout(value)
            if layout:
                detail_data['layout'] = layout
        
        elif label == "専有面積":
            area = extract_area(value)
            if area:
                detail_data['area'] = area
        
        elif label == "構造":
            # "SRC造29階地下4階建て" のような形式から総階数を抽出
            # 地上階数を優先して抽出（地下階は無視）
            above_ground_match = re.search(r'(\d+)階地下', value)
            if above_ground_match:
                detail_data['total_floors'] = int(above_ground_match.group(1))
            else:
                # 通常の "RC造5階建て" 形式
                total_match = re.search(r'(\d+)階建', value)
                if total_match:
                    detail_data['total_floors'] = int(total_match.group(1))
            
            # 構造情報も保存
            structure_pattern = r'(RC造|SRC造|S造|木造|鉄骨造|鉄筋コンクリート造|鉄骨鉄筋コンクリート造)'
            structure_match = re.search(structure_pattern, value)
            if structure_match:
                detail_data['structure'] = structure_match.group(1)
        
        elif label == "築年月":
            built_year = extract_built_year(value)
            if built_year:
                detail_data['built_year'] = built_year
                # 月情報も取得
                month_match = re.search(r'(\d{1,2})月', value)
                if month_match:
                    detail_data['built_month'] = int(month_match.group(1))
        
        elif label == "管理費":
            management_fee = extract_monthly_fee(value)
            if management_fee:
                detail_data['management_fee'] = management_fee
        
        elif label == "バルコニー面積":
            balcony_area = extract_area(value)
            if balcony_area:
                detail_data['balcony_area'] = balcony_area
        
        elif label == "総戸数":
            # 総戸数を抽出（例："250戸"）
            units_match = re.search(r'(\d+)戸', value)
            if units_match:
                detail_data['total_units'] = int(units_match.group(1))
                self.logger.info(f"[NOMU] 総戸数: {detail_data['total_units']}戸")
        
        elif label == "備　考":
            if value and value != "―":
                detail_data['remarks'] = value
        
        elif label == "交通":
            # 駅情報をフォーマットして保存
            if value:
                detail_data['station_info'] = format_station_info(value)
    
    def _extract_fees(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """管理費と修繕積立金を抽出（ノムコム用）"""
        # ノムコムでは管理費と修繕積立金が同じ行に表示される場合がある
        # 例: 管理費: 48,790円 / 月    修繕積立金: 24,040円 / 月
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                # 4つのセルがある場合（管理費と修繕積立金が同じ行）
                if len(cells) >= 4:
                    if '管理費' in cells[0].get_text() and '修繕' in cells[2].get_text():
                        # 管理費
                        if 'management_fee' not in detail_data:
                            fee_text = cells[1].get_text(strip=True)
                            management_fee = extract_monthly_fee(fee_text)
                            if management_fee:
                                detail_data['management_fee'] = management_fee
                        # 修繕積立金
                        if 'repair_fund' not in detail_data:
                            fund_text = cells[3].get_text(strip=True)
                            repair_fund = extract_monthly_fee(fund_text)
                            if repair_fund:
                                detail_data['repair_fund'] = repair_fund
                
                # 通常のレイアウト（2つのセル）
                for i in range(len(cells) - 1):
                    cell_text = cells[i].get_text(strip=True)
                    if '管理費' in cell_text and 'management_fee' not in detail_data:
                        fee_text = cells[i + 1].get_text(strip=True)
                        management_fee = extract_monthly_fee(fee_text)
                        if management_fee:
                            detail_data['management_fee'] = management_fee
                    elif '修繕積立金' in cell_text and 'repair_fund' not in detail_data:
                        fund_text = cells[i + 1].get_text(strip=True)
                        repair_fund = extract_monthly_fee(fund_text)
                        if repair_fund:
                            detail_data['repair_fund'] = repair_fund
    
    def _extract_list_format_info(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """リスト形式の物件情報を抽出（Rで始まるIDのページ）"""
        # ページ全体のテキストから情報を抽出
        page_text = soup.get_text()
        
        # 価格を抽出（"○億○万円"形式）
        price_patterns = [
            r'(\d+)億(\d+),?(\d+)万円',  # 12億5,000万円
            r'(\d+)億(\d+)万円',          # 1億5000万円
            r'(\d+),?(\d+)万円',          # 5,000万円
            r'(\d+)万円'                  # 5000万円
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                if '億' in pattern:
                    if len(match.groups()) == 3:
                        # 12億5,000万円
                        oku = int(match.group(1))
                        man = int(match.group(2)) * 1000 + int(match.group(3))
                        detail_data['price'] = oku * 10000 + man
                    else:
                        # 1億5000万円
                        oku = int(match.group(1))
                        man = int(match.group(2))
                        detail_data['price'] = oku * 10000 + man
                else:
                    # 万円のみ
                    if len(match.groups()) == 2:
                        man = int(match.group(1)) * 10000 + int(match.group(2))
                    else:
                        man = int(match.group(1))
                    detail_data['price'] = man
                break
        
        # 専有面積を抽出（複数のパターンに対応）
        area_patterns = [
            r'専有面積[：:\s]*(\d+\.?\d*)㎡',
            r'専有面積[：:\s]*(\d+\.?\d*)m²',
            r'専有面積[：:\s]*(\d+\.?\d*)m2',
            r'専有面積\s*(\d+\.?\d*)㎡',
            r'専有面積\s*(\d+\.?\d*)m'
        ]
        
        for pattern in area_patterns:
            area_match = re.search(pattern, page_text)
            if area_match:
                detail_data['area'] = float(area_match.group(1))
                break
        
        # 間取りを抽出
        layout_match = re.search(r'(\d+[LDK]+(?:\+[SW]IC)*)', page_text)
        if layout_match:
            layout = layout_match.group(1)
            detail_data['layout'] = normalize_layout(layout)
        
        # 管理費を抽出
        mgmt_match = re.search(r'管理費[：:]\s*(\d+[,，]?\d*)円', page_text)
        if mgmt_match:
            mgmt_text = mgmt_match.group(1).replace(',', '').replace('，', '')
            detail_data['management_fee'] = int(mgmt_text)
        
        # 修繕積立金を抽出
        repair_match = re.search(r'修繕積立金[：:]\s*(\d+[,，]?\d*)円', page_text)
        if repair_match:
            repair_text = repair_match.group(1).replace(',', '').replace('，', '')
            detail_data['repair_fund'] = int(repair_text)
    
    def _extract_additional_details(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """その他の詳細情報を抽出"""
        # バルコニー面積
        self._extract_balcony_area(soup, detail_data)
        
        # 築年（別の場所から）
        self._extract_built_year_alt(soup, detail_data)
        
        # 総階数（別の場所から）
        self._extract_total_floors_alt(soup, detail_data)
        
        # 構造
        self._extract_structure(soup, detail_data)
        
        # 物件説明・備考
        self._extract_description_and_remarks(soup, detail_data)
        
        # 電話番号
        self._extract_agency_tel(soup, detail_data)
    
    def _extract_balcony_area(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """バルコニー面積を抽出"""
        balcony_elem = soup.find(text=re.compile(r'バルコニー')) or \
                      soup.find("th", text=re.compile(r'バルコニー'))
        if balcony_elem:
            balcony_value = balcony_elem.find_next("td") if balcony_elem.name == "th" else balcony_elem.parent
            if balcony_value:
                balcony_text = balcony_value.get_text(strip=True)
                balcony_area = extract_area(balcony_text)
                if balcony_area:
                    detail_data['balcony_area'] = balcony_area
    
    def _extract_built_year_alt(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """築年を別の場所から抽出"""
        if 'built_year' not in detail_data:
            built_elem = soup.find(text=re.compile(r'築年月')) or \
                        soup.find("th", text="築年月")
            if built_elem:
                built_value = built_elem.find_next("td") if built_elem.name == "th" else built_elem.parent
                if built_value:
                    built_text = built_value.get_text(strip=True)
                    built_year = extract_built_year(built_text)
                    if built_year:
                        detail_data['built_year'] = built_year
    
    def _extract_total_floors_alt(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """総階数を別の場所から抽出"""
        if 'total_floors' not in detail_data:
            floors_elem = soup.find("th", string=re.compile(r'総階数|建物階数|階数'))
            if floors_elem:
                floors_value = floors_elem.find_next("td") if floors_elem.name == "th" else floors_elem.parent
                if floors_value:
                    floors_text = floors_value.get_text(strip=True)
                    total_floors, basement_floors = extract_total_floors(floors_text)
                    if total_floors is not None:
                        detail_data['total_floors'] = total_floors
                    if basement_floors is not None and basement_floors > 0:
                        detail_data['basement_floors'] = basement_floors
    
    def _extract_structure(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """構造情報を抽出"""
        structure_found = False
        for table in soup.find_all('table'):
            if structure_found:
                break
            for row in table.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                for i in range(len(cells) - 1):
                    if cells[i].get_text(strip=True) == '構造':
                        structure_text = cells[i + 1].get_text(strip=True)
                        
                        # 実際の構造情報が含まれている場合のみ処理
                        structure_pattern = r'(RC造|SRC造|S造|木造|鉄骨造|鉄筋コンクリート造|鉄骨鉄筋コンクリート造)'
                        if re.search(structure_pattern, structure_text):
                            # 構造フィールドから総階数と地下階数も抽出
                            total_floors, basement_floors = extract_total_floors(structure_text)
                            if total_floors is not None and not detail_data.get('total_floors'):
                                detail_data['total_floors'] = total_floors
                            if basement_floors is not None and basement_floors > 0 and not detail_data.get('basement_floors'):
                                detail_data['basement_floors'] = basement_floors
                            
                            # 構造情報のみを抽出
                            structure_match = re.search(structure_pattern, structure_text)
                            if structure_match:
                                detail_data['structure'] = structure_match.group(1)
                            
                            structure_found = True
                            break
    
    def _extract_description_and_remarks(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """物件説明と備考を抽出"""
        # 物件説明
        desc_elem = soup.find("div", class_="property-description") or \
                   soup.find("div", class_="description") or \
                   soup.find("section", class_="comment")
        if desc_elem:
            detail_data['description'] = desc_elem.get_text(strip=True)
        
        # 備考
        remarks_elem = soup.find("div", class_="remarks") or \
                      soup.find("section", class_="notes")
        if remarks_elem:
            detail_data['remarks'] = remarks_elem.get_text(strip=True)
    
    def _extract_area_and_layout_current_format(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """現在のページ構造から面積と間取りを抽出（span.item_status_content）"""
        # span.item_status_contentクラスの要素をすべて取得
        status_content_spans = soup.find_all("span", class_="item_status_content")
        
        for span in status_content_spans:
            text = span.get_text(strip=True)
            
            # 面積を抽出（m²、㎡、m2の形式）
            if not detail_data.get('area') and re.search(r'\d+\.?\d*[㎡m²m2]', text):
                area = extract_area(text)
                if area:
                    detail_data['area'] = area
                    self.logger.debug(f"[NOMU] 面積を抽出: {area}㎡ from '{text}'")
            
            # 間取りを抽出（1R、1K、1DK、1LDK等の形式）
            if not detail_data.get('layout') and re.search(r'\d+[RLDK]+', text):
                layout = normalize_layout(text)
                if layout:
                    detail_data['layout'] = layout
                    self.logger.debug(f"[NOMU] 間取りを抽出: {layout} from '{text}'")
    
    def _extract_agency_tel(self, soup: BeautifulSoup, detail_data: Dict[str, Any]):
        """電話番号を抽出"""
        tel_elem = soup.find("a", href=re.compile(r'tel:')) or \
                  soup.find(text=re.compile(r'\d{2,4}-\d{2,4}-\d{3,4}'))
        if tel_elem:
            if hasattr(tel_elem, 'get_text'):
                tel_text = tel_elem.get_text(strip=True)
            else:
                tel_text = str(tel_elem)
            tel_match = re.search(r'(\d{2,4}-\d{2,4}-\d{3,4})', tel_text)
            if tel_match:
                detail_data['agency_tel'] = tel_match.group(1)