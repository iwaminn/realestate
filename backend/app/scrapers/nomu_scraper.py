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

from .base_scraper import BaseScraper
from ..models import PropertyListing


class NomuScraper(BaseScraper):
    """ノムコムのスクレイパー"""
    
    BASE_URL = "https://www.nomu.com"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__("NOMU", force_detail_fetch, max_properties)
    
    def get_search_url(self, area_code: str, page: int = 1) -> str:
        """検索URLを生成"""
        # ノムコムの検索URLフォーマット
        # https://www.nomu.com/mansion/area_tokyo/13103/?page=2
        
        # ページ番号は2から開始（1ページ目はパラメータなし）
        if page == 1:
            return f"{self.BASE_URL}/mansion/area_tokyo/{area_code}/"
        else:
            return f"{self.BASE_URL}/mansion/area_tokyo/{area_code}/?page={page}"
    
    def scrape_area(self, area_code: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        if self.force_detail_fetch:
            print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
        
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            # 検索URLを生成
            search_url = self.get_search_url(area_code, page)
            print(f"URL: {search_url}")
            soup = self.fetch_page(search_url)
            
            if not soup:
                print(f"ページ {page} の取得に失敗しました")
                break
            
            # 物件情報を一覧から直接抽出
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
        print(f"\n合計 {len(all_properties)} 件の物件を保存します...")
        
        saved_count = 0
        skipped_count = 0
        
        for i, property_data in enumerate(all_properties, 1):
            print(f"[{i}/{len(all_properties)}] {property_data.get('building_name', 'Unknown')}")
            
            # 建物名と価格の検証
            if not self.validate_property_data(property_data):
                print(f"  → データ検証失敗、スキップ")
                skipped_count += 1
                continue
            
            try:
                self.save_property(property_data)
                saved_count += 1
                
            except Exception as e:
                print(f"  → エラー: {e}")
                skipped_count += 1
                continue
        
        # 変更をコミット
        self.session.commit()
        
        print(f"\n完了: {saved_count} 件保存、{skipped_count} 件スキップ")
    
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
                property_data['title'] = link.get_text(strip=True)
                property_data['building_name'] = self.extract_building_name(property_data['title'])
                property_data['url'] = urljoin(self.BASE_URL, link['href'])
        
        # テーブルから情報を抽出
        table = card.find("table")
        if table:
            # 価格（item_3 セル）
            price_cell = table.find("td", class_="item_td item_3")
            if price_cell:
                price_elem = price_cell.find("p", class_="item_price")
                if price_elem:
                    # span要素から価格を組み立てる
                    spans = price_elem.find_all("span")
                    price_parts = []
                    for span in spans:
                        if span.get("class") and "num" in span.get("class"):
                            price_parts.append(span.get_text(strip=True))
                        elif span.get("class") and "unit" in span.get("class"):
                            unit = span.get_text(strip=True)
                            if unit == "億":
                                price_parts.append("億")
                    
                    # 価格文字列を構築
                    price_text = "".join(price_parts)
                    
                    # 億がある場合
                    if "億" in price_text:
                        parts = price_text.split("億")
                        oku = int(parts[0].replace(',', ''))
                        man = int(parts[1].replace(',', '')) if parts[1] else 0
                        property_data['price'] = oku * 10000 + man
                    else:
                        # 万円のみ
                        property_data['price'] = int(price_text.replace(',', ''))
            
            # 面積・間取り・方角（item_4 セル）
            detail_cell = table.find("td", class_="item_td item_4")
            if detail_cell:
                p_tags = detail_cell.find_all("p")
                
                # 1番目のp: 面積
                if len(p_tags) > 0:
                    area_text = p_tags[0].get_text(strip=True)
                    area_match = re.search(r'(\d+\.?\d*)', area_text)
                    if area_match:
                        property_data['area'] = float(area_match.group(1))
                
                # 2番目のp: 間取り
                if len(p_tags) > 1:
                    property_data['layout'] = p_tags[1].get_text(strip=True)
                
                # 3番目のp: 方角（存在する場合）
                if len(p_tags) > 2:
                    direction_text = p_tags[2].get_text(strip=True)
                    if direction_text in ['北東', '南東', '北西', '南西', '北', '南', '東', '西']:
                        property_data['direction'] = direction_text
            
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
                built_pattern = r'(\d{4})年(\d+)月'
                built_match = re.search(built_pattern, info_text)
                if built_match:
                    property_data['built_year'] = int(built_match.group(1))
            
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
    
    def extract_building_name(self, title: str) -> str:
        """タイトルから建物名を抽出"""
        # 部屋番号や階数を除去
        building_name = re.sub(r'\s*\d+階.*$', '', title)
        building_name = re.sub(r'\s*[A-Z]?\d+号室.*$', '', building_name)
        
        # 不要な記号を除去
        building_name = building_name.strip()
        
        return building_name
    
    def normalize_address(self, address: str) -> str:
        """住所を正規化"""
        # 不要な空白を除去
        address = re.sub(r'\s+', '', address)
        
        # 東京都を追加（なければ）
        if not address.startswith('東京都'):
            address = '東京都' + address
        
        return address
    
    def save_property(self, property_data: Dict[str, Any]):
        """物件情報を保存"""
        # 建物を取得または作成
        building, room_number = self.get_or_create_building(
            building_name=property_data['building_name'],
            address=property_data.get('address')
        )
        
        if not building:
            print(f"  → 建物の作成に失敗しました")
            return
        
        # マスター物件を取得または作成
        master_property = self.get_or_create_master_property(
            building=building,
            room_number=room_number,
            floor_number=property_data.get('floor_number'),
            area=property_data.get('area'),
            layout=property_data.get('layout'),
            direction=property_data.get('direction'),
            url=property_data['url']
        )
        
        # 掲載情報を作成または更新
        listing = self.create_or_update_listing(
            master_property=master_property,
            url=property_data['url'],
            title=property_data.get('title', property_data['building_name']),
            price=property_data['price'],
            agency_name=property_data.get('agency_name', '野村不動産アーバンネット'),
            site_property_id=property_data.get('site_property_id'),
            description=property_data.get('description'),
            station_info=property_data.get('station_info'),
            features=property_data.get('features'),
            management_fee=property_data.get('management_fee'),
            repair_fund=property_data.get('repair_fund'),
            # 掲載サイトごとの物件属性
            listing_floor_number=property_data.get('floor_number'),
            listing_area=property_data.get('area'),
            listing_layout=property_data.get('layout'),
            listing_direction=property_data.get('direction'),
            listing_total_floors=property_data.get('total_floors'),
            listing_balcony_area=property_data.get('balcony_area'),
            listing_address=property_data.get('address')
        )
        
        # 詳細ページの取得が必要かチェック
        if self.needs_detail_fetch(listing):
            print(f"  → 詳細ページを取得します")
            self.fetch_and_update_detail(listing)
        else:
            print(f"  → 詳細ページは最近取得済みのためスキップ")
    
    def fetch_and_update_detail(self, listing: PropertyListing) -> bool:
        """詳細ページを取得して情報を更新"""
        try:
            time.sleep(self.delay)  # 遅延
            
            soup = self.fetch_page(listing.url)
            if not soup:
                return False
            
            # 詳細情報を解析
            detail_data = self.parse_property_detail(soup)
            if not detail_data:
                return False
            
            # 詳細情報で既存の情報を更新
            if detail_data.get('management_fee'):
                listing.management_fee = detail_data['management_fee']
            if detail_data.get('repair_fund'):
                listing.repair_fund = detail_data['repair_fund']
            if detail_data.get('description'):
                listing.description = detail_data['description']
            if detail_data.get('features'):
                listing.features = detail_data['features']
            if detail_data.get('agency_tel'):
                listing.agency_tel = detail_data['agency_tel']
            if detail_data.get('remarks'):
                listing.remarks = detail_data['remarks']
            
            # バルコニー面積があれば更新
            if detail_data.get('balcony_area') and listing.master_property:
                listing.master_property.balcony_area = detail_data['balcony_area']
            
            # 詳細取得日時を更新
            listing.detail_fetched_at = datetime.now()
            listing.has_update_mark = False  # 更新マークをクリア
            
            # 多数決による物件情報更新
            if listing.master_property:
                self.update_master_property_by_majority(listing.master_property)
            
            # 建物情報の更新
            if listing.master_property and listing.master_property.building:
                building = listing.master_property.building
                if detail_data.get('built_year') and not building.built_year:
                    building.built_year = detail_data['built_year']
                if detail_data.get('total_floors') and not building.total_floors:
                    building.total_floors = detail_data['total_floors']
                if detail_data.get('structure') and not building.structure:
                    building.structure = detail_data['structure']
                # 住所が空の場合は更新
                if detail_data.get('address') and not building.address:
                    building.address = detail_data['address']
                    print(f"    → 建物の住所を更新: {building.address}")
            
            self.session.commit()
            print(f"    → 詳細情報を更新しました")
            return True
            
        except Exception as e:
            print(f"    → 詳細ページ取得エラー: {e}")
            return False
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析"""
        detail_data = {}
        
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
                        # 通常の管理費パターン
                        fee_match = re.search(r'(?:管理費\s*)?([\d,]+)円', fee_text)
                        if fee_match:
                            detail_data['management_fee'] = int(fee_match.group(1).replace(',', ''))
                        else:
                            # 特殊パターン（PM棟管理費など）
                            special_fee_match = re.search(r'PM棟管理費\s*([\d,]+)円', fee_text)
                            if special_fee_match:
                                detail_data['management_fee'] = int(special_fee_match.group(1).replace(',', ''))
                    
                    # 修繕積立金を探す
                    if '修繕積立金' in cells[i].get_text():
                        fund_text = cells[i + 1].get_text(strip=True)
                        # 通常の修繕積立金パターン
                        fund_match = re.search(r'(?:修繕積立金\s*)?([\d,]+)円', fund_text)
                        if fund_match:
                            detail_data['repair_fund'] = int(fund_match.group(1).replace(',', ''))
                        else:
                            # 特殊パターン（PM棟修繕積立金など）
                            special_fund_match = re.search(r'PM棟修繕積立金\s*([\d,]+)円', fund_text)
                            if special_fund_match:
                                detail_data['repair_fund'] = int(special_fund_match.group(1).replace(',', ''))
        
        # バルコニー面積
        balcony_elem = soup.find(text=re.compile(r'バルコニー')) or \
                      soup.find("th", text=re.compile(r'バルコニー'))
        if balcony_elem:
            balcony_value = balcony_elem.find_next("td") if balcony_elem.name == "th" else balcony_elem.parent
            if balcony_value:
                balcony_text = balcony_value.get_text(strip=True)
                balcony_match = re.search(r'([\d.]+)㎡', balcony_text)
                if balcony_match:
                    detail_data['balcony_area'] = float(balcony_match.group(1))
        
        # 築年
        built_elem = soup.find(text=re.compile(r'築年月')) or \
                    soup.find("th", text="築年月")
        if built_elem:
            built_value = built_elem.find_next("td") if built_elem.name == "th" else built_elem.parent
            if built_value:
                built_text = built_value.get_text(strip=True)
                built_match = re.search(r'(\d{4})年', built_text)
                if built_match:
                    detail_data['built_year'] = int(built_match.group(1))
        
        # 総階数
        floors_elem = soup.find("th", string=re.compile(r'総階数|建物階数|階数'))
        if floors_elem:
            floors_value = floors_elem.find_next("td") if floors_elem.name == "th" else floors_elem.parent
            if floors_value:
                floors_text = floors_value.get_text(strip=True)
                # 地下階を含むパターンにも対応（例: "14階地下2階建て"）
                floors_match = re.search(r'(\d+)階', floors_text)
                if floors_match:
                    detail_data['total_floors'] = int(floors_match.group(1))
        
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
                            # 構造フィールドから総階数も抽出（例: "RC造14階地下2階建て"）
                            if not detail_data.get('total_floors'):
                                floors_in_structure = re.search(r'(\d+)階(?:地下\d+階)?建', structure_text)
                                if floors_in_structure:
                                    detail_data['total_floors'] = int(floors_in_structure.group(1))
                            
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