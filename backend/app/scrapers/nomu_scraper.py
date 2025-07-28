"""
ノムコムスクレイパー
野村不動産アーバンネット（nomu.com）からの物件情報取得
"""

import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, quote
from datetime import datetime
from bs4 import BeautifulSoup

from .constants import SourceSite
from .base_scraper import BaseScraper
from ..models import PropertyListing
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date
)


class NomuScraper(BaseScraper):
    """ノムコムのスクレイパー"""
    
    BASE_URL = "https://www.nomu.com"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__(SourceSite.NOMU, force_detail_fetch, max_properties)
    
    def get_search_url(self, area_code: str, page: int = 1) -> str:
        """検索URLを生成"""
        # ノムコムはGETパラメータでページングを行う
        base_url = f"{self.BASE_URL}/mansion/area_tokyo/{area_code}/"
        if page > 1:
            return f"{base_url}?pager_page={page}"
        return base_url
    
    
    def scrape_area(self, area_code: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        # 共通ロジックを使用（価格変更ベースのスマートスクレイピングを含む）
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
                print(f"物件カード解析エラー: {e}")
                continue
        
        return properties
    
    def parse_property_card(self, card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件カードから情報を抽出"""
        property_data = {}
        
        # タイトル/建物名とURL
        title_elem = card.find("div", class_="item_title")
        if title_elem:
            link = title_elem.find("a")
            if link:
                building_name = link.get_text(strip=True)
                property_data['title'] = building_name
                property_data['building_name'] = building_name  # save_property用に追加
                property_data['url'] = urljoin(self.BASE_URL, link['href'])
                
                # URLから物件IDを抽出（例: /chukomap/xxxxxxxx.html）
                id_match = re.search(r'/chukomap/([^/]+)\.html', link['href'])
                if id_match:
                    property_data['site_property_id'] = id_match.group(1)
        
        # テーブルから情報を抽出
        table = card.find("table")
        if table:
            # 価格（item_3 セル）
            price_cell = table.find("td", class_="item_td item_3")
            if price_cell:
                price_elem = price_cell.find("p", class_="item_price")
                if price_elem:
                    # まず全体のテキストを取得してみる
                    full_price_text = price_elem.get_text(strip=True)
                    
                    # span要素から価格を組み立てる
                    spans = price_elem.find_all("span")
                    price_parts = []
                    for span in spans:
                        span_text = span.get_text(strip=True)
                        if span_text:  # 空でないテキストのみ追加
                            # クラスリストを取得
                            class_list = span.get("class", [])
                            class_str = " ".join(class_list) if isinstance(class_list, list) else str(class_list)
                            
                            # numクラスまたは数字を含む場合
                            if "num" in class_str or re.search(r'\d', span_text):
                                price_parts.append(span_text)
                            # unitクラスまたは「億」「万円」を含む場合
                            elif "unit" in class_str or "yen" in class_str or span_text in ["億", "万円", "万"]:
                                price_parts.append(span_text)
                    
                    # 価格文字列を構築
                    if price_parts:
                        price_text = "".join(price_parts)
                    else:
                        # span要素から組み立てられない場合は全体テキストを使用
                        price_text = full_price_text
                    
                    # 万円を追加（extract_priceが処理するため）
                    # ただし、すでに「円」で終わっている場合や「億」のみの場合は追加しない
                    if price_text and not price_text.endswith("円") and "万" not in price_text:
                        # 「億」で終わっている場合はそのまま
                        if not price_text.endswith("億"):
                            price_text += "万円"
                    
                    # データ正規化フレームワークを使用して価格を抽出
                    price = extract_price(price_text)
                    if price:
                        property_data['price'] = price
                    else:
                        # 価格抽出に失敗した場合、デバッグ情報を出力
                        print(f"価格抽出失敗: full_text='{full_price_text}', constructed='{price_text}', parts={price_parts}")
            
            # 面積・間取り・方角（item_4 セル）
            detail_cell = table.find("td", class_="item_td item_4")
            if detail_cell:
                p_tags = detail_cell.find_all("p")
                
                # 1番目のp: 面積
                if len(p_tags) > 0:
                    area_text = p_tags[0].get_text(strip=True)
                    # データ正規化フレームワークを使用して面積を抽出
                    area = extract_area(area_text)
                    if area:
                        property_data['area'] = area
                
                # 2番目のp: 間取り
                if len(p_tags) > 1:
                    # データ正規化フレームワークを使用して間取りを正規化
                    layout = normalize_layout(p_tags[1].get_text(strip=True))
                    if layout:
                        property_data['layout'] = layout
                
                # 3番目のp: 方角（存在する場合）
                if len(p_tags) > 2:
                    direction_text = p_tags[2].get_text(strip=True)
                    # データ正規化フレームワークを使用して方角を正規化
                    direction = normalize_direction(direction_text)
                    if direction:
                        property_data['direction'] = direction
            
            # 階数・築年（item_5 セル）
            info_cell = table.find("td", class_="item_td item_5")
            if info_cell:
                info_text = info_cell.get_text()
                
                # 階数 (例: "7階 / 29階建")
                floor_pattern = r'(\d+)階\s*/\s*(\d+)階建'
                floor_match = re.search(floor_pattern, info_text)
                if floor_match:
                    property_data['floor_number'] = int(floor_match.group(1))
                    property_data['total_floors'] = int(floor_match.group(2))
                
                # 築年（年月から抽出）
                # データ正規化フレームワークを使用して築年を抽出
                built_year = extract_built_year(info_text)
                if built_year:
                    property_data['built_year'] = built_year
            
            # 住所（区名を含む部分を抽出）
            cells = table.find_all("td")
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                if "区" in cell_text and "東京" not in cell_text and len(cell_text) < 50:
                    # 駅情報を除外
                    if "駅" not in cell_text:
                        property_data['address'] = "東京都" + cell_text
                    # 駅情報
                    elif "駅" in cell_text:
                        property_data['station_info'] = cell_text
        
        # 仲介業者名（ノムコムは野村不動産アーバンネット）
        property_data['agency_name'] = "野村不動産アーバンネット"
        
        return property_data if property_data.get('url') else None
    
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
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self._parse_property_detail_from_url,
            save_property_func=self.save_property
        )
    
    def _parse_property_detail_from_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URLから詳細ページを取得して解析"""
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        detail_data = self.parse_property_detail(soup)
        if detail_data:
            detail_data['url'] = url
        return detail_data
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None) -> bool:
        """物件情報を保存"""
        # 共通の保存処理を使用
        return self.save_property_common(property_data, existing_listing)
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析"""
        detail_data = {}
        
        # 建物名を取得
        h1_elem = soup.find("h1", class_="item_title")
        if h1_elem:
            building_name = h1_elem.get_text(strip=True)
            if building_name:
                detail_data['building_name'] = building_name
        
        # 住所を取得
        address_th = soup.find("th", text="所在地")
        if address_th:
            address_td = address_th.find_next("td")
            if address_td:
                # リンクテキストと通常テキストを結合
                address_parts = []
                for elem in address_td.descendants:
                    if elem.name is None and elem.strip():
                        address_parts.append(elem.strip())
                address_text = ' '.join(address_parts)
                # 不要な文字を削除
                address_text = re.sub(r'\s+', ' ', address_text)
                address_text = re.sub(r'周辺地図を見る', '', address_text).strip()
                
                # 個人情報保護の説明文は除外
                if address_text and not address_text.startswith('物件の所在地'):
                    detail_data['address'] = address_text
        
        # 管理費と修繕積立金を含むテーブルを探す
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                # 管理費を探す
                for i in range(len(cells) - 1):
                    if '管理費' in cells[i].get_text():
                        fee_text = cells[i + 1].get_text(strip=True)
                        # データ正規化フレームワークを使用して月額費用を抽出
                        management_fee = extract_monthly_fee(fee_text)
                        if management_fee:
                            detail_data['management_fee'] = management_fee
                    
                    # 修繕積立金を探す
                    if '修繕積立金' in cells[i].get_text():
                        fund_text = cells[i + 1].get_text(strip=True)
                        # データ正規化フレームワークを使用して月額費用を抽出
                        repair_fund = extract_monthly_fee(fund_text)
                        if repair_fund:
                            detail_data['repair_fund'] = repair_fund
        
        # バルコニー面積
        balcony_elem = soup.find(text=re.compile(r'バルコニー')) or \
                      soup.find("th", text=re.compile(r'バルコニー'))
        if balcony_elem:
            balcony_value = balcony_elem.find_next("td") if balcony_elem.name == "th" else balcony_elem.parent
            if balcony_value:
                balcony_text = balcony_value.get_text(strip=True)
                # データ正規化フレームワークを使用して面積を抽出
                balcony_area = extract_area(balcony_text)
                if balcony_area:
                    detail_data['balcony_area'] = balcony_area
        
        # 築年
        built_elem = soup.find(text=re.compile(r'築年月')) or \
                    soup.find("th", text="築年月")
        if built_elem:
            built_value = built_elem.find_next("td") if built_elem.name == "th" else built_elem.parent
            if built_value:
                built_text = built_value.get_text(strip=True)
                # データ正規化フレームワークを使用して築年を抽出
                built_year = extract_built_year(built_text)
                if built_year:
                    detail_data['built_year'] = built_year
        
        # 総階数
        floors_elem = soup.find("th", string=re.compile(r'総階数|建物階数|階数'))
        if floors_elem:
            floors_value = floors_elem.find_next("td") if floors_elem.name == "th" else floors_elem.parent
            if floors_value:
                floors_text = floors_value.get_text(strip=True)
                # データ正規化フレームワークを使用
                from . import extract_total_floors
                total_floors, basement_floors = extract_total_floors(floors_text)
                if total_floors is not None:
                    detail_data['total_floors'] = total_floors
                if basement_floors is not None and basement_floors > 0:
                    detail_data['basement_floors'] = basement_floors
        
        # 構造（item_tableクラスのテーブルも含めて探す）
        structure_found = False
        for table in soup.find_all('table'):
            if structure_found:
                break
            for row in table.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                for i in range(len(cells) - 1):
                    if cells[i].get_text(strip=True) == '構造':
                        structure_text = cells[i + 1].get_text(strip=True)
                        
                        # 実際の構造情報（RC造、SRC造など）が含まれている場合のみ処理
                        if re.search(r'(RC造|SRC造|S造|木造|鉄骨造|鉄筋コンクリート造|鉄骨鉄筋コンクリート造)', structure_text):
                            # 構造フィールドから総階数と地下階数も抽出
                            from . import extract_total_floors
                            total_floors, basement_floors = extract_total_floors(structure_text)
                            if total_floors is not None and not detail_data.get('total_floors'):
                                detail_data['total_floors'] = total_floors
                            if basement_floors is not None and basement_floors > 0 and not detail_data.get('basement_floors'):
                                detail_data['basement_floors'] = basement_floors
                            
                            # 構造情報のみを抽出（RC造、SRC造など）
                            structure_match = re.search(r'(RC造|SRC造|S造|木造|鉄骨造|鉄筋コンクリート造|鉄骨鉄筋コンクリート造)', structure_text)
                            if structure_match:
                                detail_data['structure'] = structure_match.group(1)
                            
                            structure_found = True
                            break
        
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
        
        # 問い合わせ電話番号
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
        
        return detail_data