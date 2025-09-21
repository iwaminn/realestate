"""
LIFULL HOME'S専用HTMLパーサー

LIFULL HOME'S（www.homes.co.jp）のHTML構造に特化したパーサー
"""
import re
import logging
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup, Tag

from .base_parser import BaseHtmlParser
from ..data_normalizer import extract_monthly_fee


class HomesParser(BaseHtmlParser):
    """LIFULL HOME'S専用パーサー"""
    
    # LIFULL HOME'Sのデフォルト設定
    DEFAULT_AGENCY_NAME = None  # LIFULL HOME'Sは不動産会社ではないため、デフォルト値は設定しない
    BASE_URL = "https://www.homes.co.jp"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        super().__init__(logger)
        self.logger = logger or logging.getLogger(__name__)

    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        物件一覧をパース
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            物件情報のリスト
        """
        properties = []
        
        self.logger.info("[HOMES] Parsing property list page")
        
        # 建物ブロックを探す
        building_blocks = soup.select('.mod-mergeBuilding--sale')
        self.logger.info(f"[HOMES] Found {len(building_blocks)} building blocks")
        
        for block in building_blocks:
            building_link = block.select_one('h3 a, .heading a')
            if not building_link:
                continue
            
            # 複数物件に対応
            price_rows = block.select('tr.raSpecRow')
            
            if not price_rows:
                # raSpecRowがない場合も建物URLを物件URLとして扱う
                href = building_link.get('href', '')
                if '/mansion/b-' in href:
                    from urllib.parse import urljoin
                    full_url = urljoin(self.BASE_URL, href)
                    property_data = {
                        'url': full_url
                    }
                    # URLからIDを抽出
                    import re
                    id_match = re.search(r'/b-(\d+)', href)
                    if id_match:
                        property_data['site_property_id'] = id_match.group(1)
                        # 価格を必須フィールドとして追加（ダミー値）
                        property_data['price'] = 0  # 詳細ページで取得
                        properties.append(property_data)
                    else:
                        self.logger.error(f"[HOMES] 物件をスキップします（site_property_id取得失敗）: {full_url}")
            else:
                # 各物件行を処理
                for row in price_rows:
                    property_data = self._parse_property_row(row)
                    if property_data:
                        properties.append(property_data)
        
        return properties

    
    def _parse_property_row(self, row: Tag) -> Optional[Dict[str, Any]]:
        """物件行から情報を抽出"""
        property_data = {}
        
        # td要素を取得
        tds = row.find_all('td')
        if len(tds) < 5:
            return None
        
        # 物件詳細へのリンク（最初のtdにある）
        link_elem = tds[0].find('a')
        if link_elem:
            href = link_elem.get('href', '')
            if href:
                from urllib.parse import urljoin
                property_data['url'] = urljoin(self.BASE_URL, href)
                # URLからIDを抽出
                import re
                # 新しいURLパターン /mansion/b-XXXXX/
                id_match = re.search(r'/mansion/b-(\d+)', href)
                if not id_match:
                    # 旧パターン /mansion/XXXXX/
                    id_match = re.search(r'/mansion/(\d+)', href)
                if id_match:
                    property_data['site_property_id'] = id_match.group(1)
        
        # 価格（3番目のtd）
        if len(tds) > 2:
            price_text = self.extract_text(tds[2])
            price = self.parse_price(price_text)
            if price:
                property_data['price'] = price
        
        # 間取り（4番目のtd）
        if len(tds) > 3:
            layout_text = self.extract_text(tds[3])
            layout = self.normalize_layout(layout_text)
            if layout:
                property_data['layout'] = layout
        
        # 面積（5番目のtd）
        if len(tds) > 4:
            area_text = self.extract_text(tds[4])
            area = self.parse_area(area_text)
            if area:
                property_data['area'] = area
        
        # 階数（2番目のtdに含まれている可能性があるが、詳細ページで取得する）
        # ここでは一覧ページの必須フィールドのみ
        
        # 必須フィールドのチェック（URLとsite_property_idのみ必須）
        if property_data.get('url') and property_data.get('site_property_id'):
            return property_data
        
        return None
    
    def _parse_property_card(self, card: Tag) -> Optional[Dict[str, Any]]:
        """
        物件カードから情報を抽出
        
        Args:
            card: 物件カード要素
            
        Returns:
            物件データ
        """
        property_data = {}
        
        # タイトル/建物名とURL
        title_elem = card.find("h2", class_="object-name") or card.find("a", class_="property-name")
        if title_elem:
            if title_elem.name == 'a':
                property_data['building_name'] = self.extract_text(title_elem)
                href = title_elem.get('href')
            else:
                link = title_elem.find('a')
                if link:
                    property_data['building_name'] = self.extract_text(link)
                    href = link.get('href')
                else:
                    property_data['building_name'] = self.extract_text(title_elem)
                    # h2の親要素からリンクを探す
                    parent_link = card.find('a', href=re.compile(r'/chintai/'))
                    href = parent_link.get('href') if parent_link else None
            
            if href:
                property_data['url'] = self.normalize_url(href, self.BASE_URL)
                # URLからIDを抽出（例: /chintai/123456/）
                site_id_match = re.search(r'/chintai/(\d+)', href)
                if site_id_match:
                    property_data['site_property_id'] = site_id_match.group(1)
        
        # 価格
        price_elem = card.find("span", class_="price") or card.find("span", class_="priceLabel")
        if price_elem:
            price = self.parse_price(self.extract_text(price_elem))
            if price:
                property_data['price'] = price
        
        # 詳細情報を抽出
        self._extract_card_details(card, property_data)
        
        # 仲介業者名を取得
        self._extract_agency_from_card(card, property_data)
        
        # 必須フィールドの検証
        if self._validate_card_data(property_data):
            return property_data
        else:
            return None
    
    def _extract_card_details(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードから詳細情報を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        # 詳細テーブルを探す
        detail_table = card.find("table", class_="object-data")
        if detail_table:
            table_data = self.extract_table_data(detail_table)
            for key, value in table_data.items():
                self._process_detail_item(key, value, property_data)
        
        # dl要素から情報を抽出
        dl_elements = card.select("dl.detail-info")
        for dl in dl_elements:
            dt = dl.find('dt')
            dd = dl.find('dd')
            if dt and dd:
                key = self.extract_text(dt)
                value = self.extract_text(dd)
                if key and value:
                    self._process_detail_item(key, value, property_data)
    
    def _extract_agency_from_card(self, card: Tag, property_data: Dict[str, Any]) -> None:
        """
        カードから不動産会社名を抽出
        
        Args:
            card: カード要素
            property_data: データ格納先
        """
        agency_elem = card.find("div", class_="company-name") or card.find("span", class_="agency")
        if agency_elem:
            property_data['agency_name'] = self.extract_text(agency_elem)
        else:
            pass  # 不動産会社が取得できない場合は空のままにする
    
    def parse_property_detail(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        物件詳細をパース

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            物件詳細情報
            
        Raises:
            ValueError: HTML構造が期待と異なる場合
        """
        property_data = {}

        try:
            # id="about"の中の物件概要から情報を取得
            about_section = soup.find(id='about')
            if about_section:
                # 物件概要テーブルを探す
                tables = about_section.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        th = row.find('th')
                        td = row.find('td')
                        if th and td:
                            key = self.extract_text(th)
                            value = self.extract_text(td)
                            if key and value:
                                self._process_detail_item(key, value, property_data)
                
                # テーブルの後の情報公開日等を取得
                # 「情報公開日：2025/06/15」のような形式で表示されている
                for p_tag in about_section.find_all('p'):
                    text = self.extract_text(p_tag)
                    if text and '情報公開日' in text:
                        # 「情報公開日：2025/06/15」から日付部分を抽出
                        import re
                        date_match = re.search(r'情報公開日[：:]\s*(\d{4}/\d{2}/\d{2})', text)
                        if date_match:
                            date_str = date_match.group(1)
                            published_at = self.parse_date(date_str)
                            if published_at:
                                property_data['published_at'] = published_at
            else:
                # about sectionが見つからない場合は警告
                self.logger.warning("[HOMES] id='about'セクションが見つかりません")

            # 建物名を取得
            try:
                self._extract_building_name_from_detail(soup, property_data)
            except ValueError as e:
                # 建物名の取得でHTML構造エラーが発生した場合
                self.logger.error(f"[HOMES] 建物名の抽出でエラー: {e}")
                # 建物名が取得できない場合は、パース全体を失敗とする
                raise ValueError(f"必須フィールド（建物名）の取得に失敗: {e}")
                
        except Exception as e:
            # 予期しないエラーをキャッチしてログに記録
            self.logger.error(f"[HOMES] 詳細ページのパースでエラー: {e}", exc_info=True)
            # エラーでも部分的なデータを返す（スクレイパー側で判断）
            property_data['_parse_error'] = str(e)

        return property_data
    
    def _process_detail_item(self, key: str, value: str, property_data: Dict[str, Any]) -> None:
        """
        詳細アイテムを処理
        
        Args:
            key: キー
            value: 値
            property_data: データ格納先
        """
        if not value:
            return
        
        # 価格（賃料）
        if '価格' in key or '賃料' in key:
            price = self.parse_price(value)
            if price:
                property_data['price'] = price
        
        # 間取り
        elif '間取' in key:
            # 正規表現で間取りを抽出（例: "3LDK / 85.5㎡" -> "3LDK"）
            layout_match = re.search(r'^([1-9]\d*[SLDK]+)', value)
            if layout_match:
                property_data['layout'] = layout_match.group(1)
            else:
                # フォールバック: normalize_layoutを使用
                from ..data_normalizer import normalize_layout
                layout = normalize_layout(value.split('/')[0].strip())
                if layout:
                    property_data['layout'] = layout
        
        # 専有面積
        elif '専有面積' in key or ('面積' in key and 'バルコニー' not in key and '建築' not in key and '敷地' not in key):
            from ..data_normalizer import extract_area, validate_area
            area = extract_area(value)
            if area and validate_area(area):
                property_data['area'] = area
        
        # バルコニー面積
        elif 'バルコニー' in key:
            from ..data_normalizer import extract_area
            balcony_area = extract_area(value)
            # バルコニー面積は0㎡以上、100㎡以下であれば有効
            if balcony_area is not None and 0 <= balcony_area <= 100:
                property_data['balcony_area'] = balcony_area
        
        # 階数情報
        elif '階' in key:
            # 所在階の抽出
            floor = self.parse_floor(value)
            if floor:
                property_data['floor_number'] = floor

            # 総階数の抽出
            total_floors = self.parse_total_floors(value)
            if total_floors:
                property_data['total_floors'] = total_floors

            # 地下階数の抽出
            basement_floors = self.parse_basement_floors(value)
            if basement_floors:
                property_data['basement_floors'] = basement_floors
        
        # 方角（主要採光面も含む）
        elif '向き' in key or '方位' in key or '方角' in key or '採光' in key:
            direction = self.normalize_direction(value)
            if direction:
                property_data['direction'] = direction
        
        # 築年月
        elif '築年月' in key or '竣工' in key:
            built_info = self.parse_built_date(value)
            if built_info['built_year']:
                property_data['built_year'] = built_info['built_year']
            if built_info['built_month']:
                property_data['built_month'] = built_info['built_month']
        
        # 所在地
        elif '所在地' in key or '住所' in key:
            address = self.normalize_address(value)
            if address:
                property_data['address'] = address
        
        # 交通
        elif '交通' in key or '最寄' in key or '駅' in key:
            station = self.parse_station_info(value)
            if station:
                property_data['station_info'] = station
        
        # 管理費
        elif '管理費' in key:
            fee = extract_monthly_fee(value)
            if fee:
                property_data['management_fee'] = fee
        
        # 修繕積立金
        elif '修繕積立' in key:
            fund = extract_monthly_fee(value)
            if fund:
                property_data['repair_fund'] = fund
        
        # 総戸数
        elif '総戸数' in key or '総区画数' in key:
            units = self.parse_total_units(value)
            if units:
                property_data['total_units'] = units

        # 部屋番号
        elif '部屋番号' in key or '号室' in key:
            room = self.extract_text(value)
            if room and room != '-':
                property_data['room_number'] = room
                # first_published_atはbase_scraperで自動的に設定される
    
    def _extract_building_name_from_detail(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        詳細ページから建物名を抽出
        
        HOMES詳細ページの期待される構造:
        h1タグ: 3つのspan要素
          - 1番目: "中古マンション"
          - 2番目: 建物名（階数情報を含む場合がある）
          - 3番目: 間取りと価格
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
            
        Raises:
            ValueError: HTML構造が期待と異なる場合
        """
        h1_building_name = None
        room_number = None
        
        # h1タグから建物名を取得（必須）
        h1_tags = soup.find_all('h1')
        h1_found = False
        
        for h1_elem in h1_tags:
            # ヘッダーのロゴh1をスキップ
            if h1_elem.get('class') and 'Header__logo' in ' '.join(h1_elem.get('class', [])):
                continue
            
            h1_found = True
            
            # h1内のspan要素を取得（直下の子要素のみ）
            span_elements = h1_elem.find_all('span', recursive=False)
            
            # 新しいHTML構造に対応
            # 3つのspan要素を期待しているが、最初のspanが入れ子構造の場合もある
            if len(span_elements) != 3:
                error_msg = f"h1タグ内のspan要素数が期待値(3)と異なります: {len(span_elements)}個"
                self.logger.error(f"[HOMES] {error_msg}")
                
                # デバッグ情報
                for i, span in enumerate(span_elements):
                    self.logger.debug(f"  span[{i}]: {self.extract_text(span)[:50]}")
                
                raise ValueError(error_msg)
            
            # 1番目のspan: "中古マンション"、"マンション未入居"、または単に"マンション"であることを確認
            # 新しい構造では最初のspanが入れ子になっている場合がある
            first_span_text = self.extract_text(span_elements[0])
            # 「マンション」という文字列が含まれていればOKとする（より柔軟な判定）
            if "マンション" not in first_span_text:
                error_msg = f"h1の1番目のspan要素が期待値と異なります: '{first_span_text}' (期待値: 'マンション'を含む)"
                self.logger.error(f"[HOMES] {error_msg}")
                raise ValueError(error_msg)
            
            # 2番目のspan: 建物名（階数情報を含む場合がある）
            second_span_text = self.extract_text(span_elements[1])
            if not second_span_text:
                error_msg = "h1の2番目のspan要素（建物名）が空です"
                self.logger.error(f"[HOMES] {error_msg}")
                raise ValueError(error_msg)
            
            # 3番目のspan: 間取りと価格（検証）
            third_span_text = self.extract_text(span_elements[2])
            if not third_span_text or ('万円' not in third_span_text):
                error_msg = f"h1の3番目のspan要素が期待される形式（間取り/価格）ではありません: '{third_span_text}'"
                self.logger.error(f"[HOMES] {error_msg}")
                raise ValueError(error_msg)
            
            # 2番目のspanから建物名を抽出（階数情報を除去）
            h1_building_name = second_span_text
            
            # 階数情報を除去（例: "麻布プレイス 5階" → "麻布プレイス"）
            if '階' in h1_building_name:
                # スペースで分割して階数部分を除去
                parts = h1_building_name.rsplit(' ', 1)
                if len(parts) > 1 and '階' in parts[-1]:
                    h1_building_name = parts[0]
                else:
                    # 階数が含まれているが分割できない場合
                    h1_building_name = re.sub(r'\s*\d+[-〜～]?\d*階.*$', '', h1_building_name)
            
            self.logger.info(f"[HOMES] h1タグから建物名を取得: {h1_building_name}")
            break
        
        if not h1_found:
            error_msg = "物件詳細のh1タグが見つかりません"
            self.logger.error(f"[HOMES] {error_msg}")
            raise ValueError(error_msg)
        
        if not h1_building_name:
            error_msg = "h1タグから建物名を取得できませんでした"
            self.logger.error(f"[HOMES] {error_msg}")
            raise ValueError(error_msg)
        
        # 結果を保存
        # タイトルフィールドにも設定（表示用）
        property_data['title'] = h1_building_name
        
        # 部屋番号と階数を除去してbuilding_nameに設定
        cleaned_name = re.sub(r'\s*\d+号室.*$', '', h1_building_name)
        cleaned_name = re.sub(r'\s*\d+[-〜～]?\d*階.*$', '', cleaned_name)
        cleaned_name = cleaned_name.strip()
        
        # 建物名が空でないことを確認
        if cleaned_name:
            property_data['building_name'] = cleaned_name
            
            # 部屋番号も保存（取得できている場合）
            if room_number:
                property_data['room_number'] = room_number
            
            # 建物名候補リストも作成（MULTI_SOURCE用）
            property_data['_building_names_candidates'] = [cleaned_name]
        else:
            # クリーニング後の建物名が無効
            raise ValueError(f"建物名のクリーニング後に無効な値になりました: '{cleaned_name}'")
    
    
    
    



    def _extract_agency_info(self, soup: BeautifulSoup, property_data: Dict[str, Any]) -> None:
        """
        不動産会社情報を抽出
        
        Args:
            soup: BeautifulSoupオブジェクト
            property_data: データ格納先
        """
        # 会社情報を探す
        company_elem = self.safe_select_one(soup, "div.companyInfo, div.realtor")
        if company_elem:
            company_text = company_elem.get_text(' ', strip=True)
            
            # 会社名を抽出
            company_name_elem = company_elem.find("h3") or company_elem.find("div", class_="companyName")
            if company_name_elem:
                property_data['agency_name'] = self.extract_text(company_name_elem)
            
            # 電話番号を抽出
            tel_match = re.search(r'(?:TEL|電話)[:：\s]*([0-9\-]+)', company_text)
            if tel_match:
                property_data['agency_tel'] = tel_match.group(1)
        
        # デフォルト値
        if 'agency_name' not in property_data:
            pass  # 不動産会社が取得できない場合は空のままにする
    
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

    def get_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        次ページのURLを取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            current_url: 現在のURL
            
        Returns:
            次ページのURL（なければNone）
        """
        # ページネーションを探す
        next_link = self.safe_select_one(soup, "a.next, li.next a, a[rel='next']")
        
        if next_link and next_link.get('href'):
            next_url = self.normalize_url(next_link['href'], self.BASE_URL)
            if next_url and next_url != current_url:
                return next_url
        
        return None
    
    def _validate_card_data(self, data: Dict[str, Any]) -> bool:
        """
        カードデータの妥当性を検証
        
        Args:
            data: 物件データ
            
        Returns:
            妥当性フラグ
        """
        # 必須フィールド
        required = ['building_name', 'price', 'url']
        for field in required:
            if field not in data or not data[field]:
                self.logger.debug(f"必須フィールド '{field}' が欠落")
                return False
        
        # 価格の妥当性
        if data.get('price'):
            price = data['price']
            if price < 100 or price > 500000:  # 100万円〜50億円
                self.logger.debug(f"価格が範囲外: {price}万円")
                return False
        
        return True