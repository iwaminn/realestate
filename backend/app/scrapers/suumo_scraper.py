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

from .base_scraper import BaseScraper
from ..models import PropertyListing


class SuumoScraper(BaseScraper):
    """SUUMOのスクレイパー（v3 - 一覧ページベース）"""
    
    BASE_URL = "https://suumo.jp"
    
    def __init__(self, force_detail_fetch=False, max_properties=None):
        super().__init__("SUUMO", force_detail_fetch, max_properties)
    
    def scrape_area(self, area: str, max_pages: int = 5):
        """エリアの物件をスクレイピング"""
        if self.force_detail_fetch:
            print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
        
        all_properties = []
        
        for page in range(1, max_pages + 1):
            print(f"ページ {page} を取得中...")
            
            # 検索URLを生成
            search_url = self.get_search_url(area, page)
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
            if len(properties) == 100:
                print("  → 100件取得（最大表示件数）")
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
            
            # スキップ機能を削除 - 常に最新情報を取得
            
            # 建物名のみ検証（価格は詳細ページから取得するため）
            if not property_data.get('building_name'):
                print(f"  → 建物名が不足、スキップ")
                skipped_count += 1
                continue
            
            try:
                self.save_property(property_data)
                saved_count += 1
                
            except Exception as e:
                print(f"  → エラー: {e}")
                skipped_count += 1
                continue
        
        # 非アクティブな掲載をマーク
        # 注意: 部分的なスクレイピングの場合は、その部分のみをチェックすべきではない
        # 全体をスクレイピングした場合のみ実行する
        if max_pages >= 30:  # 全体スクレイピングの閾値（適宜調整）
            all_urls = [p['url'] for p in all_properties if 'url' in p]
            self.mark_inactive_listings(all_urls)
        else:
            print(f"部分スクレイピング（{max_pages}ページ）のため、非アクティブマーキングをスキップ")
        
        # 変更をコミット
        self.session.commit()
        print(f"\nスクレイピング完了: {saved_count} 件保存、{skipped_count} 件スキップ")
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """SUUMOの検索URLを生成（100件/ページ）"""
        # SUUMOのURLパラメータ
        # ar=030: 関東地方
        # bs=011: 中古マンション
        # sc=13103: 港区（エリアコード）
        # ta=13: 東京都
        # po=0: デフォルトソート
        # pj=1: ページ番号
        # pc=100: 1ページあたり100件表示
        
        area_codes = {
            "港区": "13103",
            "minato": "13103",
            "渋谷区": "13113",
            "shibuya": "13113",
            "新宿区": "13104",
            "shinjuku": "13104",
            "千代田区": "13101",
            "chiyoda": "13101",
            "中央区": "13102",
            "chuo": "13102",
            "品川区": "13109",
            "shinagawa": "13109",
            "目黒区": "13110",
            "meguro": "13110",
            "世田谷区": "13112",
            "setagaya": "13112"
        }
        
        # エリアコードを取得（見つからない場合はそのまま使用）
        area_code = area_codes.get(area.lower(), area_codes.get(area, area))
        
        # 新形式のURL（100件/ページ）
        # pageパラメータを追加して正しくページネーションが動作するように修正
        return f"{self.BASE_URL}/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=011&sc={area_code}&ta=13&po=0&pj={page}&pc=100&page={page}"
    
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
            
            # 物件詳細へのリンク（新旧両方のパターンに対応）
            link = unit.select_one('a[href*="/ms/chuko/"][href*="/nc_"]')
            if not link:
                # 新形式のリンクパターン
                link = unit.select_one('a[href*="/chuko/"][href*="nc"]')
            if not link:
                # さらに別のパターン
                link = unit.select_one('.js-property_link, .property_link')
            
            if link:
                property_data['url'] = urljoin(self.BASE_URL, link.get('href'))
                property_data['site_property_id'] = self.extract_property_id(property_data['url'])
            
            # 新着・更新マークを検出（詳細ページ取得の判定用）
            is_new = bool(unit.select_one('.property_unit-newmark, .icon_new, [class*="new"]'))
            is_updated = bool(unit.select_one('.property_unit-update, .icon_update, [class*="update"]'))
            property_data['has_update_mark'] = is_new or is_updated
            
            # 建物名を取得（物件名フィールドから - 一時的な識別用）
            building_name = None
            
            # .dottable-lineから物件名を取得
            dottable_lines = unit.select('.dottable-line')
            for line in dottable_lines:
                dt_elem = line.select_one('dt')
                dd_elem = line.select_one('dd')
                if dt_elem and dd_elem:
                    label = dt_elem.get_text(strip=True)
                    value = dd_elem.get_text(strip=True)
                    
                    if '物件名' in label:
                        building_name = value
                        break
            
            # 注意: .cassette-titleや.property_unit-titleは広告文なので使用しない
            # 物件名フィールドが見つからない場合は建物名なしとする
            
            if building_name:
                property_data['building_name'] = building_name
            
            # URLと建物名が取得できた物件のみ追加（他の情報は詳細ページから取得）
            if property_data.get('url') and property_data.get('building_name'):
                properties.append(property_data)
        
        return properties
    
    def extract_property_id(self, url: str) -> str:
        """URLから物件IDを抽出"""
        match = re.search(r'/nc_(\d+)/', url)
        return match.group(1) if match else url.split('/')[-1]
    
    def save_property(self, property_data: Dict[str, Any]):
        """物件情報を保存（スマートスクレイピング対応）"""
        try:
            print(f"  URL: {property_data.get('url', 'URLなし')}")
            
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
                    self.session.commit()
                    return
            
            # 詳細ページから全ての情報を取得
            detail_data = self.parse_property_detail(property_data['url'])
            if not detail_data:
                print(f"  → 詳細ページの取得に失敗しました")
                return
            
            # 詳細データで property_data を更新
            property_data.update(detail_data)
            
            # 価格が取得できているか確認
            if not property_data.get('price'):
                print(f"  → 価格情報が取得できませんでした")
                return
            
            print(f"  価格: {property_data.get('price')}万円")
            print(f"  間取り: {property_data.get('layout', '不明')}")
            print(f"  面積: {property_data.get('area', '不明')}㎡")
            print(f"  階数: {property_data.get('floor_number', '不明')}階")
            
            # 建物を取得または作成
            building, extracted_room_number = self.get_or_create_building(
                property_data.get('building_name', ''),
                property_data.get('address', ''),
                built_year=property_data.get('built_year'),
                total_floors=detail_data.get('detail_info', {}).get('total_floors') if detail_data else None,
                basement_floors=detail_data.get('detail_info', {}).get('basement_floors') if detail_data else None,
                total_units=detail_data.get('detail_info', {}).get('total_units') if detail_data else None,
                structure=detail_data.get('detail_info', {}).get('structure') if detail_data else None,
                land_rights=detail_data.get('detail_info', {}).get('land_rights') if detail_data else None,
                parking_info=detail_data.get('detail_info', {}).get('parking_info') if detail_data else None
            )
            
            if not building:
                print(f"  → 建物情報が不足")
                return
            
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
                site_property_id=property_data.get('site_property_id', ''),
                description=property_data.get('description'),
                station_info=property_data.get('station_info'),
                management_fee=property_data.get('management_fee'),
                repair_fund=property_data.get('repair_fund'),
                published_at=property_data.get('published_at'),
                first_published_at=property_data.get('first_published_at'),
                # 掲載サイトごとの物件属性
                listing_floor_number=property_data.get('floor_number'),
                listing_area=property_data.get('area'),
                listing_layout=property_data.get('layout'),
                listing_direction=property_data.get('direction'),
                listing_total_floors=property_data.get('total_floors'),
                listing_balcony_area=property_data.get('balcony_area'),
                listing_address=property_data.get('address')
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
            listing.detail_info = property_data.get('detail_info', {})
            listing.detail_fetched_at = datetime.now()
            
            # 多数決による物件情報更新
            self.update_master_property_by_majority(master_property)
            
            print(f"  → 保存完了")
            
        except Exception as e:
            print(f"  → エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細を解析"""
        try:
            # 詳細ページを取得
            soup = self.fetch_page(url)
            if not soup:
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
                            # 億単位の価格に対応
                            # パターン1: "1億4500万円"
                            oku_man_match = re.search(r'(\d+)億(\d+(?:,\d{3})*)万円', value)
                            if oku_man_match:
                                oku = int(oku_man_match.group(1))
                                man = int(oku_man_match.group(2).replace(',', ''))
                                property_data['price'] = oku * 10000 + man
                                print(f"    価格: {oku}億{man}万円 ({property_data['price']}万円)")
                                price_found = True
                                break
                            
                            # パターン2: "2億円"（万円部分なし）
                            oku_only_match = re.search(r'(\d+)億円', value)
                            if oku_only_match:
                                oku = int(oku_only_match.group(1))
                                property_data['price'] = oku * 10000
                                print(f"    価格: {oku}億円 ({property_data['price']}万円)")
                                price_found = True
                                break
                            
                            # パターン3: 億がない通常の価格
                            man_match = re.search(r'([\d,]+)万円', value)
                            if man_match:
                                property_data['price'] = int(man_match.group(1).replace(',', ''))
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
                            # 「4階」のようなパターンから所在階を抽出
                            floor_match = re.search(r'(\d+)階', value)
                            if floor_match:
                                property_data['floor_number'] = int(floor_match.group(1))
                                print(f"    所在階: {property_data['floor_number']}階")
                        
                        # 向き（単独のフィールド）
                        elif label == '向き' or (label.endswith('ヒント') and '向き' in label):
                            # 「南西」「南」などの方位を取得
                            direction_value = value.strip()
                            if direction_value and direction_value not in ['-', '－', '']:
                                property_data['direction'] = direction_value
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
                            print(f"    [DEBUG] 所在階/構造・階建フィールド発見: {label} = {value}")
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
                            
                            # 総階数を抽出 - より詳細なパターンマッチング
                            # 「RC21階地下1階建」のように建物種別の後に階数が来るパターンに対応
                            total_floors_match = re.search(r'(?:RC|SRC|S造|木造|鉄骨)?(\d+)階(?:地下\d+階)?建', value)
                            if total_floors_match:
                                detail_info['total_floors'] = int(total_floors_match.group(1))
                                print(f"    総階数: {detail_info['total_floors']}階")
                            
                            # 地下階数を抽出
                            basement_match = re.search(r'地下(\d+)階', value)
                            if basement_match:
                                detail_info['basement_floors'] = int(basement_match.group(1))
                            else:
                                detail_info['basement_floors'] = 0
                            
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
                            print(f"    [DEBUG] 構造・階建フィールド発見（別形式）: {label} = {value}")
                            # 「SRC14階地下1階建」のようなパターンに対応
                            # スラッシュで分割してからパターンマッチ
                            parts = value.split('/')
                            structure_part = parts[-1] if len(parts) > 1 else value
                            
                            # 地下を含む完全な階数表記を解析
                            # 例: "14階地下1階建", "42階建", "5階地下2階建"
                            # より詳細なパターンマッチング
                            floors_match = re.search(r'(?:RC|SRC|S造|木造|鉄骨)?(\d+)階(?:地下(\d+)階)?建', structure_part)
                            if floors_match:
                                detail_info['total_floors'] = int(floors_match.group(1))
                                if floors_match.group(2):
                                    detail_info['basement_floors'] = int(floors_match.group(2))
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
                            print(f"    物件名: {property_data['building_name']}")
                        
                        # 部屋番号を取得
                        if '部屋番号' in label or '号室' in label:
                            property_data['room_number'] = value
                            print(f"    部屋番号: {property_data['room_number']}")
                        
                        # バルコニー面積
                        if 'バルコニー' in label or 'バルコニー' in value or ('その他面積' in label):
                            print(f"    [DEBUG] バルコニー関連フィールド発見: {label} = {value}")
                            # パターン1: バルコニー面積：9.15m2
                            area_match = re.search(r'バルコニー面積[：:]\s*([\d.]+)', value)
                            if not area_match:
                                # パターン2: バルコニー：9.15m2
                                area_match = re.search(r'バルコニー[：:]\s*([\d.]+)', value)
                            if not area_match:
                                # パターン3: 数値 + m2
                                area_match = re.search(r'([\d.]+)\s*m[²2]', value)
                            if area_match:
                                balcony_area = float(area_match.group(1))
                                print(f"    [DEBUG] バルコニー面積を抽出: {balcony_area}㎡")
                                property_data['balcony_area'] = balcony_area
                                print(f"    バルコニー面積: {balcony_area}㎡")
                        
                        # 価格（テーブルからも取得を試みる）
                        if '価格' in label and ('万円' in value or '億円' in value) and 'price' not in property_data:
                            # 億単位の価格に対応
                            # パターン1: "1億4500万円"
                            oku_man_match = re.search(r'(\d+)億(\d+(?:,\d{3})*)万円', value)
                            if oku_man_match:
                                oku = int(oku_man_match.group(1))
                                man = int(oku_man_match.group(2).replace(',', ''))
                                property_data['price'] = oku * 10000 + man
                                print(f"    価格（テーブルから）: {oku}億{man}万円 ({property_data['price']}万円)")
                            # パターン2: "2億円"
                            elif re.search(r'(\d+)億円', value):
                                oku_only_match = re.search(r'(\d+)億円', value)
                                oku = int(oku_only_match.group(1))
                                property_data['price'] = oku * 10000
                                print(f"    価格（テーブルから）: {oku}億円 ({property_data['price']}万円)")
                            # パターン3: 通常の価格
                            else:
                                price_match = re.search(r'([\d,]+)万円', value)
                                if price_match:
                                    property_data['price'] = int(price_match.group(1).replace(',', ''))
                                    print(f"    価格（テーブルから）: {property_data['price']}万円")
                        
                        # 間取り
                        elif '間取り' in label:
                            layout_match = re.search(r'([1-9]\d*[SLDK]+)', value)
                            if layout_match:
                                property_data['layout'] = layout_match.group(1)
                        
                        # 専有面積
                        elif '専有面積' in label:
                            area_match = re.search(r'([\d.]+)', value)
                            if area_match:
                                property_data['area'] = float(area_match.group(1))
                        
                        # 築年月から築年を取得
                        elif '築年月' in label:
                            year_match = re.search(r'(\d{4})年', value)
                            if year_match:
                                property_data['built_year'] = int(year_match.group(1))
                        
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
                                wan_match = re.search(r'(\d+)万([\d,]+)円', value)
                                if wan_match:
                                    man = int(wan_match.group(1)) * 10000
                                    yen = int(wan_match.group(2).replace(',', ''))
                                    property_data['repair_fund'] = man + yen
                                    print(f"    修繕積立金: {property_data['repair_fund']}円（{wan_match.group(1)}万{wan_match.group(2)}円）")
                                else:
                                    # 通常の円パターン
                                    fund_match = re.search(r'([\d,]+)円', value)
                                    if fund_match:
                                        property_data['repair_fund'] = int(fund_match.group(1).replace(',', ''))
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
            
            # タイトルと説明文
            title_elem = soup.select_one('h1, .property-title')
            if title_elem:
                property_data['title'] = title_elem.get_text(strip=True)
            
            # 価格が取得できていない場合は、ページ全体から探す
            if 'price' not in property_data:
                page_text = soup.get_text()
                # 億単位の価格を優先的に探す
                # パターン1: "1億4500万円"
                oku_man_match = re.search(r'(\d+)億(\d+(?:,\d{3})*)万円', page_text)
                if oku_man_match:
                    oku = int(oku_man_match.group(1))
                    man = int(oku_man_match.group(2).replace(',', ''))
                    property_data['price'] = oku * 10000 + man
                    print(f"    価格（ページ全体から）: {oku}億{man}万円 ({property_data['price']}万円)")
                else:
                    # パターン2: "2億円"
                    oku_only_match = re.search(r'(\d+)億円', page_text)
                    if oku_only_match:
                        oku = int(oku_only_match.group(1))
                        property_data['price'] = oku * 10000
                        print(f"    価格（ページ全体から）: {oku}億円 ({property_data['price']}万円)")
                    else:
                        # パターン3: 通常の価格
                        price_match = re.search(r'([\d,]+)万円', page_text)
                        if price_match:
                            property_data['price'] = int(price_match.group(1).replace(',', ''))
                            print(f"    価格（ページ全体から）: {property_data['price']}万円")
            
            # 必須フィールドのチェック
            if 'price' in property_data:
                return property_data
            else:
                self.logger.warning(f"Price not found for {url}")
                return None
            
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
            
        except Exception as e:
            print(f"    詳細ページ取得エラー: {e}")
            return False