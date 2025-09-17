"""
データ正規化フレームワーク
スクレイパーから取得したデータをデータベースに保存する前に正規化・検証するためのユーティリティ

このモジュールは以下の機能を提供します：
1. 型変換とバリデーション
2. 文字列からの各種データ抽出（価格、面積、階数など）
3. 駅情報のフォーマット
4. 日付の正規化
5. エラーハンドリング
"""

import re
from typing import Optional, Union, List, Tuple, Dict, Any
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


class DataNormalizer:
    """データ正規化のメインクラス"""
    
    # 妥当性チェックの定数
    MIN_PRICE = 100  # 最小価格: 100万円
    MAX_PRICE = 1000000  # 最大価格: 100億円（1000000万円）
    MIN_AREA = 10.0  # 最小面積: 10㎡
    MAX_AREA = 1000.0  # 最大面積: 1000㎡（高級ペントハウス等に対応）
    
    def __init__(self):
        """初期化"""
        # 路線名のパターン（駅情報フォーマット用）
        self.railway_patterns = [
            '東京メトロ', '都営', 'ＪＲ', 'JR', '京王', '小田急', '東急', '京急', 
            '京成', '新交通', '東武', '西武', '相鉄', 'りんかい線', 'つくばエクスプレス',
            '横浜市営', '東葉高速', '北総', '埼玉高速', '多摩都市モノレール'
        ]
        
        # 方角の正規化マッピング
        self.direction_mapping = {
            '南東': '南東', 'SE': '南東', '南東向き': '南東',
            '南西': '南西', 'SW': '南西', '南西向き': '南西',
            '北東': '北東', 'NE': '北東', '北東向き': '北東',
            '北西': '北西', 'NW': '北西', '北西向き': '北西',
            '南': '南', 'S': '南', '南向き': '南',
            '北': '北', 'N': '北', '北向き': '北',
            '東': '東', 'E': '東', '東向き': '東',
            '西': '西', 'W': '西', '西向き': '西',
        }
        
        # 構造種別の正規化マッピング
        self.structure_mapping = {
            'RC': 'RC', 'RC造': 'RC', '鉄筋コンクリート': 'RC', '鉄筋コンクリート造': 'RC',
            'SRC': 'SRC', 'SRC造': 'SRC', '鉄骨鉄筋コンクリート': 'SRC', '鉄骨鉄筋コンクリート造': 'SRC',
            'S': 'S造', 'S造': 'S造', '鉄骨': 'S造', '鉄骨造': 'S造',
            '木造': '木造', 'W': '木造', 'W造': '木造',
            '軽量鉄骨': '軽量鉄骨', '軽量鉄骨造': '軽量鉄骨',
            'ALC': 'ALC', 'ALC造': 'ALC',
        }

    # ========== 価格関連 ==========
    
    def extract_price(self, text: str) -> Optional[int]:
        """
        文字列から価格を抽出（万円単位）
        
        Args:
            text: 価格を含む文字列（例: "5,480万円", "1億2000万円", "2億円"）
            
        Returns:
            万円単位の価格（int）またはNone
            
        Examples:
            >>> normalizer.extract_price("5,480万円")
            5480
            >>> normalizer.extract_price("1億2000万円")
            12000
            >>> normalizer.extract_price("2億円")
            20000
            >>> normalizer.extract_price("５，４８０万円")  # 全角数字
            5480
        """
        if not text:
            return None
        
        # 全角数字を半角に変換
        text = text.translate(str.maketrans('０１２３４５６７８９，', '0123456789,'))
        
        # 不要な空白を正規化
        text = re.sub(r'\s+', ' ', text)
        
        # 億万円パターン（例: "1億4500万円"、"1億 4,500万円"）
        oku_man_match = re.search(r'(\d+)\s*億\s*(\d+(?:,\d{3})*)\s*万\s*円', text)
        if oku_man_match:
            oku = int(oku_man_match.group(1))
            man = int(oku_man_match.group(2).replace(',', ''))
            return oku * 10000 + man
        
        # 億円パターン（例: "2億円"、"3億円"）
        oku_only_match = re.search(r'(\d+)\s*億\s*円', text)
        if oku_only_match:
            oku = int(oku_only_match.group(1))
            return oku * 10000
        
        # 億のみパターン（例: "2億"）- ノムコムなどで使用
        oku_only_match2 = re.search(r'(\d+)\s*億(?!円|万)', text)
        if oku_only_match2:
            oku = int(oku_only_match2.group(1))
            return oku * 10000
        
        # 万円パターン（例: "5,480万円", "5,480 万円", "￥5,480万"）
        man_match = re.search(r'([\d,]+)\s*万\s*円?', text)
        if man_match:
            return int(man_match.group(1).replace(',', ''))
        
        return None

    def extract_monthly_fee(self, text: str) -> Optional[int]:
        """
        文字列から月額費用を抽出（円単位）
        
        Args:
            text: 費用を含む文字列（例: "12,000円", "管理費：8,500円/月", "9,580（円/月）", "2万4100円"）
            
        Returns:
            円単位の費用（int）またはNone
        """
        if not text:
            return None
            
        # 全角括弧を半角に変換
        text = text.replace('（', '(').replace('）', ')')
        
        # 全角数字を半角に変換
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        # 万円パターン（例: "2万4100円", "3万円"）
        man_yen_match = re.search(r'(\d+)\s*万\s*(\d*)\s*円', text)
        if man_yen_match:
            man = int(man_yen_match.group(1))
            yen = int(man_yen_match.group(2)) if man_yen_match.group(2) else 0
            return man * 10000 + yen
        
        # 円パターン（括弧内の「円」も含む）
        # パターン1: "12,000円"
        # パターン2: "12,000(円/月)"
        # パターン3: "12,000 (円/月)"
        fee_match = re.search(r'([\d,]+)\s*[（(]?円', text)
        if fee_match:
            return int(fee_match.group(1).replace(',', ''))
        
        return None

    # ========== 面積関連 ==========
    
    def extract_area(self, text: str) -> Optional[float]:
        """
        文字列から面積を抽出（㎡単位）
        
        Args:
            text: 面積を含む文字列（例: "81.3㎡", "85.5m2", "専有面積：70.2m²"）
            
        Returns:
            ㎡単位の面積（float）またはNone
            
        Examples:
            >>> normalizer.extract_area("81.3㎡")
            81.3
            >>> normalizer.extract_area("専有面積：70.2m²")
            70.2
        """
        if not text:
            return None
            
        # 様々な㎡表記に対応
        area_match = re.search(r'([\d.]+)\s*(?:㎡|m²|m2|平米|平方メートル)', text)
        if area_match:
            try:
                return float(area_match.group(1))
            except ValueError:
                return None
        
        return None

    # ========== 階数関連 ==========
    
    def extract_floor_number(self, text: str) -> Optional[int]:
        """
        文字列から階数を抽出
        
        Args:
            text: 階数を含む文字列（例: "4階", "所在階：12階", "4階/SRC9階建"）
            
        Returns:
            階数（int）またはNone
            
        Examples:
            >>> normalizer.extract_floor_number("4階")
            4
            >>> normalizer.extract_floor_number("4階/SRC9階建")
            4
        """
        if not text:
            return None
            
        # 複合パターン（例: "4階/SRC9階建"）
        compound_match = re.search(r'^(\d+)階/', text)
        if compound_match:
            return int(compound_match.group(1))
        
        # 単純なパターン（例: "4階", "12階部分"）
        simple_match = re.search(r'(\d+)階', text)
        if simple_match:
            return int(simple_match.group(1))
        
        return None

    def extract_total_floors(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        文字列から総階数と地下階数を抽出
        
        Args:
            text: 建物情報を含む文字列（例: "地上12階建", "RC21階地下1階建", "SRC42階建"）
            
        Returns:
            (総階数, 地下階数)のタプル
            
        Examples:
            >>> normalizer.extract_total_floors("地上12階建")
            (12, 0)
            >>> normalizer.extract_total_floors("RC21階地下1階建")
            (21, 1)
            >>> normalizer.extract_total_floors("42階建")
            (42, 0)
            >>> normalizer.extract_total_floors("14階地下2階建て")
            (14, 2)
            >>> normalizer.extract_total_floors("鉄筋コンクリート造 地上29階 地下2階建")
            (29, 2)
        """
        if not text:
            return None, None
            
        total_floors = None
        basement_floors = 0
        
        # 地下階数を抽出
        basement_match = re.search(r'地下(\d+)階', text)
        if basement_match:
            basement_floors = int(basement_match.group(1))
        
        # 総階数を抽出（複数のパターンに対応）
        # パターン1: "地上\d+階"
        ground_match = re.search(r'地上(\d+)階', text)
        if ground_match:
            total_floors = int(ground_match.group(1))
        else:
            # パターン2: 構造+階数+建 (例: "RC21階地下1階建")
            struct_match = re.search(r'(?:RC|SRC|S造|木造|鉄骨鉄筋コンクリート造|鉄筋コンクリート造|鉄骨造)\s*(\d+)階', text)
            if struct_match:
                total_floors = int(struct_match.group(1))
            else:
                # パターン3: 単純な階数+建 (例: "14階建", "14階地下2階建て")
                simple_match = re.search(r'(\d+)階(?:地下\d+階)?(?:建|建て)', text)
                if simple_match:
                    total_floors = int(simple_match.group(1))
                else:
                    # パターン4: 単独の階数 (例: "42階")
                    floor_only_match = re.search(r'(\d+)階(?!部|分)', text)
                    if floor_only_match:
                        # "地下"が前にある場合はスキップ
                        if not re.search(r'地下\s*' + floor_only_match.group(1) + r'階', text):
                            total_floors = int(floor_only_match.group(1))
        
        return total_floors, basement_floors

    # ========== 築年関連 ==========
    
    def extract_built_year(self, text: str) -> Optional[int]:
        """
        文字列から築年を抽出
        
        Args:
            text: 築年情報を含む文字列（例: "2020年築", "築年月：2015年3月", "平成27年築", "1971/04"）
            
        Returns:
            西暦年（int）またはNone
            
        Examples:
            >>> normalizer.extract_built_year("2020年築")
            2020
            >>> normalizer.extract_built_year("築年月：2015年3月")
            2015
            >>> normalizer.extract_built_year("1971/04")
            1971
        """
        if not text:
            return None
            
        # 西暦年パターン（「2020年」形式）
        year_match = re.search(r'(19\d{2}|20\d{2})年', text)
        if year_match:
            return int(year_match.group(1))
        
        # スラッシュ形式（「1971/04」「2020/12」形式）
        slash_match = re.search(r'(19\d{2}|20\d{2})/\d{1,2}', text)
        if slash_match:
            return int(slash_match.group(1))
        
        # 年がないパターン（「1971」「2020」のみ）
        year_only_match = re.search(r'^(19\d{2}|20\d{2})$', text.strip())
        if year_only_match:
            return int(year_only_match.group(1))
        
        # 和暦変換（必要に応じて実装）
        # TODO: 和暦対応
        
        return None

    def calculate_age_from_built_year(self, built_year: int) -> int:
        """築年から築年数を計算"""
        current_year = datetime.now().year
        return current_year - built_year

    # ========== 間取り関連 ==========
    
    def normalize_layout(self, text: str) -> Optional[str]:
        """
        間取り表記を正規化
        
        Args:
            text: 間取りを含む文字列（例: "2LDK", "３ＬＤＫ", "2SLDK", "ワンルーム"）
            
        Returns:
            正規化された間取り（例: "2LDK"）またはNone
            
        Examples:
            >>> normalizer.normalize_layout("３ＬＤＫ")
            "3LDK"
            >>> normalizer.normalize_layout("ワンルーム")
            "1R"
        """
        if not text:
            return None
        
        # Unicode正規化（NFKC）で全角文字を半角に変換
        # これにより、全角数字・英字・記号がすべて半角に変換される
        import unicodedata
        text = unicodedata.normalize('NFKC', text)
        
        # 念のため、Unicode正規化で変換されなかった文字があれば手動変換
        # （通常はNFKCで十分だが、一部の特殊文字に対応）
        # 全角数字を半角に変換
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        # 全角英字を半角に変換
        text = text.translate(str.maketrans('ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ', 
                                          'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
        text = text.translate(str.maketrans('ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ', 
                                          'abcdefghijklmnopqrstuvwxyz'))
        
        # 小文字を大文字に
        text = text.upper()
        
        # ワンルーム表記の正規化
        if 'ワンルーム' in text or '1ルーム' in text:
            return '1R'
        
        # スタジオ表記
        if 'スタジオ' in text or 'STUDIO' in text:
            return 'STUDIO'
        
        # 特殊な間取りパターン（LDK+S、SLDK+S、LDK+納戸、LDK+サービスルームなど）
        # 「LDK＋サービスルーム（納戸）」「LDK＋納戸」「1LDK＋納戸」のようなパターンを処理
        # サービスルーム、納戸、WICなどはすべてSとして扱う
        service_room_pattern = r'(\d*)([SLDK]+)[＋+](?:サービスルーム|SERVICE\s*ROOM|S\.R\.|SR|納戸|N|WIC|ウォークインクローゼット)'
        service_match = re.search(service_room_pattern, text, re.IGNORECASE)
        if service_match:
            num = service_match.group(1)
            main_rooms = service_match.group(2)
            # サービスルーム系はSとして扱う
            if num:
                return f"{num}{main_rooms}+S"
            else:
                # 数字がない場合（LDK＋サービスルームなど）
                # LDKの前に数字を探す
                prefix_match = re.search(r'(\d+)\s*' + re.escape(main_rooms), text)
                if prefix_match:
                    return f"{prefix_match.group(1)}{main_rooms}+S"
                else:
                    # それでも数字が見つからない場合は1を仮定
                    return f"1{main_rooms}+S"
        
        # 通常の+パターン（1LDK+S、2SLDK+Sなど）
        special_layout_match = re.search(r'(\d+)([SLDK]+)[＋+]([SLDK]+)', text)
        if special_layout_match:
            num = special_layout_match.group(1)
            main_rooms = special_layout_match.group(2)
            additional_rooms = special_layout_match.group(3)
            # 1LDK+S形式で返す
            return f"{num}{main_rooms}+{additional_rooms}"
        
        # 数字なしの+パターン（LDK+S、DK+Sなど）
        # ワンルームマンションの特殊な間取りとして1を付ける
        # 注釈（※など）がある場合も考慮
        no_num_layout_match = re.search(r'^([SLDK]+)[＋+]([SLDK]+)', text)
        if no_num_layout_match:
            main_rooms = no_num_layout_match.group(1)
            additional_rooms = no_num_layout_match.group(2)
            # 数字がない場合は1を仮定
            return f"1{main_rooms}+{additional_rooms}"
        
        # 一般的な間取りパターン
        layout_match = re.search(r'([1-9]\d*)\s*([SLDK]+)', text)
        if layout_match:
            num = layout_match.group(1)
            rooms = layout_match.group(2)
            # S/L/D/Kの順序を正規化
            normalized_rooms = ''
            if 'S' in rooms:
                normalized_rooms += 'S'
            if 'L' in rooms:
                normalized_rooms += 'L'
            if 'D' in rooms:
                normalized_rooms += 'D'
            if 'K' in rooms:
                normalized_rooms += 'K'
            return f"{num}{normalized_rooms}"
        
        # 数字なしのLDKパターン（LDK、DKなど）
        # ワンルームマンションの特殊な間取りとして1を付ける
        # 注釈（※など）がある場合も考慮
        no_num_simple_match = re.search(r'^([SLDK]+)(?:\s|$|※)', text)
        if no_num_simple_match:
            rooms = no_num_simple_match.group(1)
            # S/L/D/Kの順序を正規化
            normalized_rooms = ''
            if 'S' in rooms:
                normalized_rooms += 'S'
            if 'L' in rooms:
                normalized_rooms += 'L'
            if 'D' in rooms:
                normalized_rooms += 'D'
            if 'K' in rooms:
                normalized_rooms += 'K'
            # 数字がない場合は1を仮定
            return f"1{normalized_rooms}"
        
        # Rタイプ（例: "1R", "2R"）
        r_match = re.search(r'([1-9]\d*)\s*R', text)
        if r_match:
            return f"{r_match.group(1)}R"
        
        return None

    # ========== 方角関連 ==========
    
    def normalize_direction(self, text: str) -> Optional[str]:
        """
        方角表記を正規化
        
        Args:
            text: 方角を含む文字列（例: "南向き", "南西", "SW", "バルコニー：南東向き"）
            
        Returns:
            正規化された方角（例: "南", "南東"）またはNone
        """
        if not text:
            return None
            
        # テキストを大文字に変換（英語表記対応）
        text_upper = text.upper()
        
        # マッピングから正規化
        for key, value in self.direction_mapping.items():
            if key.upper() in text_upper:
                return value
        
        return None

    # ========== 構造関連 ==========
    
    def normalize_structure(self, text: str) -> Optional[str]:
        """
        建物構造を正規化
        
        Args:
            text: 構造を含む文字列（例: "RC造", "鉄筋コンクリート", "SRC"）
            
        Returns:
            正規化された構造（例: "RC", "SRC"）またはNone
        """
        if not text:
            return None
            
        # 長い文字列から順にチェック（部分一致を防ぐため）
        # 鉄骨鉄筋コンクリートを鉄筋コンクリートより先にチェック
        check_order = [
            ('鉄骨鉄筋コンクリート造', 'SRC'),
            ('鉄骨鉄筋コンクリート', 'SRC'),
            ('鉄筋コンクリート造', 'RC'),
            ('鉄筋コンクリート', 'RC'),
            ('SRC造', 'SRC'),
            ('SRC', 'SRC'),
            ('RC造', 'RC'),
            ('RC', 'RC'),
            ('軽量鉄骨造', '軽量鉄骨'),
            ('軽量鉄骨', '軽量鉄骨'),
            ('鉄骨造', 'S造'),
            ('鉄骨', 'S造'),
            ('S造', 'S造'),
            ('S', 'S造'),
            ('木造', '木造'),
            ('W造', '木造'),
            ('W', '木造'),
            ('ALC造', 'ALC'),
            ('ALC', 'ALC'),
        ]
        
        for key, value in check_order:
            if key in text:
                return value
        
        return None

    # ========== 住所関連 ==========
    
    def clean_address(self, text: str, soup_element=None) -> str:
        """
        住所文字列から不要な部分を除去し、住所の本質的な部分のみを抽出
        
        Args:
            text: 住所文字列
            soup_element: BeautifulSoupの要素（リンクを削除する場合）
            
        Returns:
            クリーンな住所文字列
            
        Examples:
            >>> normalizer.clean_address("東京都港区南麻布5丁目周辺地図を見る")
            "東京都港区南麻布5丁目"
            >>> normalizer.clean_address("東京都港区芝浦4丁目地図を見る")
            "東京都港区芝浦4丁目"
        """
        if soup_element is not None:
            # BeautifulSoupの要素からaタグを削除
            for link in soup_element.find_all('a'):
                link.extract()
            text = soup_element.get_text(strip=True)
        
        if not text:
            return ""
        
        # HTMLタグを削除（念のため）
        text = re.sub(r'<[^>]+>', '', text)
        
        # 住所の終端パターンを定義（ホワイトリスト方式）
        # 住所は通常、以下のパターンで終わる：
        # - ●丁目●番●号
        # - ●丁目●-●-●
        # - ●丁目●-●
        # - ●丁目●番地
        # - ●丁目●番
        # - ●丁目
        # - ●番地
        # - ●番●号
        # - （町名のみ）
        
        # 最も詳細な住所パターンから順に検索
        address_patterns = [
            # 丁目-番-号形式（例：5丁目1-2-3、５丁目１－２－３）
            r'(.*?[0-9０-９]+丁目[0-9０-９]+[-－][0-9０-９]+[-－][0-9０-９]+)',
            # 丁目-番形式（例：5丁目1-2）
            r'(.*?[0-9０-９]+丁目[0-9０-９]+[-－][0-9０-９]+)',
            # 丁目番号形式（例：5丁目1番2号）
            r'(.*?[0-9０-９]+丁目[0-9０-９]+番[0-9０-９]+号)',
            # 丁目番地形式（例：5丁目123番地）
            r'(.*?[0-9０-９]+丁目[0-9０-９]+番地)',
            # 丁目番形式（例：5丁目1番）
            r'(.*?[0-9０-９]+丁目[0-9０-９]+番)',
            # 丁目のみ（例：5丁目、南麻布5丁目）
            r'(.*?[0-9０-９]+丁目)',
            # 番地形式（例：123番地）
            r'(.*?[0-9０-９]+番地)',
            # 番号形式（例：1番2号）
            r'(.*?[0-9０-９]+番[0-9０-９]+号)',
            # ハイフン区切り（丁目なし）（例：港区芝浦4-16-1）
            r'(.*?(?:区|市|町|村)[^0-9０-９]*[0-9０-９]+[-－][0-9０-９]+[-－][0-9０-９]+)',
            r'(.*?(?:区|市|町|村)[^0-9０-９]*[0-9０-９]+[-－][0-9０-９]+)',
        ]
        
        # パターンにマッチする最初のものを使用
        for pattern in address_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        # パターンにマッチしない場合、区市町村までを抽出
        # 例：「東京都港区南麻布」
        # 「周辺」を除外対象に追加
        basic_pattern = r'^(.*?(?:都|道|府|県).*?(?:区|市|町|村)[^地図\[【\(周辺]*)'
        match = re.search(basic_pattern, text)
        if match:
            # 末尾の不要な文字を削除
            result = match.group(1).rstrip('、。・周辺')
            # 「周辺」で終わる場合は削除
            if result.endswith('周辺'):
                result = result[:-2]
            return result.strip()
        
        # それでもマッチしない場合は、明らかに住所でない部分を削除
        # 「地図」「MAP」などのキーワード以降を削除
        unwanted_keywords = ['地図', 'MAP', 'マップ', '周辺', '詳細', '※', '＊', '[', '【', '(']
        for keyword in unwanted_keywords:
            if keyword in text:
                text = text.split(keyword)[0]
        
        return text.strip()



    def contains_address_pattern(self, text: str) -> bool:
        """テキストに住所パターンが含まれているかを判定
        
        Args:
            text: 検証するテキスト
            
        Returns:
            bool: 住所パターンが含まれている場合True
        """
        if not text:
            return False
            
        # 都道府県パターン
        prefecture_pattern = r'(?:東京都|北海道|(?:京都|大阪)府|(?:青森|岩手|宮城|秋田|山形|福島|茨城|栃木|群馬|埼玉|千葉|神奈川|新潟|富山|石川|福井|山梨|長野|岐阜|静岡|愛知|三重|滋賀|兵庫|奈良|和歌山|鳥取|島根|岡山|広島|山口|徳島|香川|愛媛|高知|福岡|佐賀|長崎|熊本|大分|宮崎|鹿児島|沖縄)県)'
        
        # 市区町村パターン
        city_pattern = r'[市区町村]'
        
        # 番地パターン
        address_number_pattern = r'\d+丁目|\d+番|\d+号|\d+-\d+'
        
        # いずれかのパターンが含まれているかチェック
        patterns = [prefecture_pattern, city_pattern, address_number_pattern]
        return any(re.search(pattern, text) for pattern in patterns)

    # ========== 駅情報関連 ==========
    
    def format_station_info(self, text: str) -> str:
        """
        駅情報を見やすくフォーマット
        
        Args:
            text: 駅情報を含む文字列
            
        Returns:
            改行で区切られた駅情報
            
        Example:
            >>> normalizer.format_station_info("東京メトロ銀座線銀座駅徒歩5分都営浅草線東銀座駅徒歩3分")
            "東京メトロ銀座線銀座駅徒歩5分\\n都営浅草線東銀座駅徒歩3分"
        """
        if not text:
            return ""
        
        # HTMLタグだけは削除（表示を妨げるため）
        text = re.sub(r'<[^>]+>', '', text)
        
        # 「、」で区切られている場合は改行に変換
        text = text.replace('、', '\n')
        
        # 路線名の前で改行を入れる
        railway_patterns_regex = (
            r'(?=東京メトロ|都営|ＪＲ|JR|京王|小田急|東急|京急|京成|'
            r'新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス|'
            r'横浜市営|東葉高速|北総|埼玉高速|多摩都市モノレール)'
        )
        text = re.sub(railway_patterns_regex, '\n', text)
        
        # 各行を処理して駅情報の本質的な部分のみを抽出
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            # 空行や短い行をスキップ
            if not line or len(line) < 3:
                continue
            
            # 駅情報の終端パターンを探して、それ以降を削除
            # バス利用の場合は「バス●分バス停名歩●分」のパターンも処理
            # まず、バス+徒歩の複合パターンを処理
            bus_walk_pattern = r'(.*?バス\d+分.*?(?:徒歩|歩|停歩)\d+分)'
            bus_walk_match = re.search(bus_walk_pattern, line)
            if bus_walk_match:
                # バス+徒歩パターンの場合は、その部分を抽出
                line = bus_walk_match.group(1)
            else:
                # 単独の終端パターンを探す
                # パターン: 徒歩●分、歩●分、バス●分、車●分、停歩●分
                patterns = [
                    r'(.*?(?:徒歩|歩)\d+分)',
                    r'(.*?バス\d+分)',
                    r'(.*?車\d+分)',
                    r'(.*?停歩\d+分)',
                ]
                
                # 各パターンを検索し、最初にマッチしたものを使用
                for pattern in patterns:
                    match = re.search(pattern, line)
                    if match:
                        line = match.group(1)
                        break
                
                # 終端パターンが見つからない場合はそのまま使用（駅名のみなど）
            
            # 駅情報として有効な行かチェック（路線名、駅名、徒歩などのキーワードを含む）
            if any(keyword in line for keyword in ['駅', '線', '徒歩', '歩', '分', 'バス', '車', '停']):
                cleaned_lines.append(line)
            # 路線名パターンにマッチする行も有効
            elif re.search(r'(東京メトロ|都営|ＪＲ|JR|京王|小田急|東急|京急|京成|新交通|東武|西武|相鉄|りんかい線|つくばエクスプレス)', line):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    # ========== 日付関連 ==========
    
    def parse_date(self, text: str) -> Optional[datetime]:
        """
        文字列から日付を抽出してdatetimeオブジェクトに変換
        
        Args:
            text: 日付を含む文字列（例: "2024年1月15日", "2024/01/15", "2024-01-15"）
            
        Returns:
            datetimeオブジェクトまたはNone
        """
        if not text:
            return None
            
        # 年月日パターン
        date_match = re.search(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?', text)
        if date_match:
            try:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                return datetime(year, month, day)
            except ValueError:
                return None
        
        return None

    # ========== バリデーション ==========
    
    def validate_price(self, price: Optional[int]) -> bool:
        """価格の妥当性を検証（100万円以上、100億円以下）"""
        if price is None:
            return False
        return self.MIN_PRICE <= price <= self.MAX_PRICE

    def validate_area(self, area: Optional[float]) -> bool:
        """面積の妥当性を検証（10㎡以上、1000㎡以下）"""
        if area is None:
            return False
        return self.MIN_AREA <= area <= self.MAX_AREA

    def validate_floor_number(self, floor: Optional[int], total_floors: Optional[int] = None) -> bool:
        """階数の妥当性を検証"""
        if floor is None:
            return False
        if floor < 1:
            return False
        if total_floors is not None and floor > total_floors:
            return False
        return True

    def validate_built_year(self, year: Optional[int]) -> bool:
        """築年の妥当性を検証（新築物件対応で現在年+5年まで許可）"""
        if year is None:
            return False
        current_year = datetime.now().year
        # 新築物件対応で現在年+5年まで許可
        return 1900 <= year <= current_year + 5

    # ========== 型変換ヘルパー ==========
    
    @staticmethod
    def normalize_integer(value: Union[str, int, None], field_name: str = "") -> Optional[int]:
        """
        値を整数に正規化
        
        Args:
            value: 変換する値（文字列、整数、None）
            field_name: フィールド名（デバッグ用）
            
        Returns:
            整数値またはNone
        """
        if value is None:
            return None
            
        if isinstance(value, int):
            return value
            
        if isinstance(value, str):
            # 数値部分を抽出
            match = re.search(r'\d+', value)
            if match:
                try:
                    return int(match.group(0))
                except ValueError:
                    return None
        
        return None

    # ========== 総合的なデータ正規化 ==========
    
    def normalize_property_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        スクレイパーから取得した生データを正規化
        
        Args:
            raw_data: スクレイパーが取得した生データ
            
        Returns:
            正規化されたデータ（データベース保存用）
        """
        normalized = {}
        
        # 価格
        if 'price' in raw_data:
            if isinstance(raw_data['price'], str):
                normalized['price'] = self.extract_price(raw_data['price'])
            else:
                normalized['price'] = raw_data['price']
        
        # 管理費
        if 'management_fee' in raw_data:
            if isinstance(raw_data['management_fee'], str):
                normalized['management_fee'] = self.extract_monthly_fee(raw_data['management_fee'])
            else:
                normalized['management_fee'] = raw_data['management_fee']
        
        # 修繕積立金
        if 'repair_fund' in raw_data:
            if isinstance(raw_data['repair_fund'], str):
                normalized['repair_fund'] = self.extract_monthly_fee(raw_data['repair_fund'])
            else:
                normalized['repair_fund'] = raw_data['repair_fund']
        
        # 面積
        if 'area' in raw_data:
            if isinstance(raw_data['area'], str):
                normalized['area'] = self.extract_area(raw_data['area'])
            else:
                normalized['area'] = raw_data['area']
        
        # バルコニー面積
        if 'balcony_area' in raw_data:
            if isinstance(raw_data['balcony_area'], str):
                normalized['balcony_area'] = self.extract_area(raw_data['balcony_area'])
            else:
                normalized['balcony_area'] = raw_data['balcony_area']
        
        # 階数
        if 'floor_number' in raw_data:
            if isinstance(raw_data['floor_number'], str):
                normalized['floor_number'] = self.extract_floor_number(raw_data['floor_number'])
            else:
                normalized['floor_number'] = raw_data['floor_number']
        
        # 総階数
        if 'total_floors' in raw_data:
            if isinstance(raw_data['total_floors'], str):
                total_floors, basement_floors = self.extract_total_floors(raw_data['total_floors'])
                normalized['total_floors'] = total_floors
                normalized['basement_floors'] = basement_floors
            else:
                normalized['total_floors'] = raw_data['total_floors']
                normalized['basement_floors'] = raw_data.get('basement_floors', 0)
        
        # 築年
        if 'built_year' in raw_data:
            if isinstance(raw_data['built_year'], str):
                normalized['built_year'] = self.extract_built_year(raw_data['built_year'])
            else:
                normalized['built_year'] = raw_data['built_year']
        
        # 間取り
        if 'layout' in raw_data:
            normalized['layout'] = self.normalize_layout(raw_data['layout'])
        
        # 方角
        if 'direction' in raw_data:
            normalized['direction'] = self.normalize_direction(raw_data['direction'])
        
        # 構造
        if 'structure' in raw_data:
            normalized['structure'] = self.normalize_structure(raw_data['structure'])
        
        # 駅情報
        if 'station_info' in raw_data:
            normalized['station_info'] = self.format_station_info(raw_data['station_info'])
        
        # 日付フィールド
        date_fields = ['published_at', 'first_published_at', 'price_updated_at', 'last_confirmed_at']
        for field in date_fields:
            if field in raw_data:
                if isinstance(raw_data[field], str):
                    normalized[field] = self.parse_date(raw_data[field])
                else:
                    normalized[field] = raw_data[field]
        
        # その他のフィールドはそのままコピー
        for key in raw_data:
            if key not in normalized:
                normalized[key] = raw_data[key]
        
        return normalized

    def get_validation_errors(self, data: Dict[str, Any]) -> List[str]:
        """
        データの検証を行い、エラーメッセージのリストを返す
        
        Args:
            data: 検証するデータ
            
        Returns:
            エラーメッセージのリスト（エラーがない場合は空リスト）
        """
        errors = []
        
        # 価格の検証
        if 'price' in data and not self.validate_price(data['price']):
            errors.append(f"価格が妥当でありません: {data['price']}万円")
        
        # 面積の検証
        if 'area' in data and not self.validate_area(data['area']):
            errors.append(f"専有面積が妥当でありません: {data['area']}㎡")
        
        # 階数の検証
        if 'floor_number' in data:
            total_floors = data.get('total_floors')
            if not self.validate_floor_number(data['floor_number'], total_floors):
                errors.append(f"階数が妥当でありません: {data['floor_number']}階")
        
        # 築年の検証
        if 'built_year' in data and not self.validate_built_year(data['built_year']):
            errors.append(f"築年が妥当でありません: {data['built_year']}年")
        
        return errors


# シングルトンインスタンス
_normalizer = DataNormalizer()


# 便利な関数（直接インポートして使用可能）
def extract_price(text: str) -> Optional[int]:
    """文字列から価格を抽出（万円単位）"""
    return _normalizer.extract_price(text)


def extract_area(text: str) -> Optional[float]:
    """文字列から面積を抽出（㎡単位）"""
    return _normalizer.extract_area(text)


def extract_floor_number(text: str) -> Optional[int]:
    """文字列から階数を抽出"""
    return _normalizer.extract_floor_number(text)


def extract_total_floors(text: str) -> Tuple[Optional[int], Optional[int]]:
    """文字列から総階数と地下階数を抽出"""
    return _normalizer.extract_total_floors(text)


# normalize_building_name関数は
# backend.app.utils.building_name_normalizer.normalize_building_nameに移動しました
# そちらを使用してください


# canonicalize_building_name関数は
# backend.app.utils.building_name_normalizer.canonicalize_building_nameに移動しました


def normalize_layout(text: str) -> Optional[str]:
    """間取り表記を正規化"""
    return _normalizer.normalize_layout(text)


def normalize_direction(text: str) -> Optional[str]:
    """方角表記を正規化"""
    return _normalizer.normalize_direction(text)


def normalize_structure(text: str) -> Optional[str]:
    """建物構造を正規化"""
    return _normalizer.normalize_structure(text)


def format_station_info(text: str) -> str:
    """駅情報を見やすくフォーマット"""
    return _normalizer.format_station_info(text)


def clean_address(text: str, soup_element=None) -> str:
    """住所文字列から不要なリンクテキストを除去"""
    return _normalizer.clean_address(text, soup_element)


def normalize_property_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """スクレイパーから取得した生データを正規化"""
    return _normalizer.normalize_property_data(raw_data)


def validate_property_data(data: Dict[str, Any]) -> List[str]:
    """データの検証を行い、エラーメッセージのリストを返す"""
    return _normalizer.get_validation_errors(data)


def normalize_integer(value: Union[str, int, None], field_name: str = "") -> Optional[int]:
    """値を整数に正規化"""
    return DataNormalizer.normalize_integer(value, field_name)


def extract_monthly_fee(text: str) -> Optional[int]:
    """文字列から月額費用を抽出（円単位）"""
    return _normalizer.extract_monthly_fee(text)


def extract_built_year(text: str) -> Optional[int]:
    """文字列から築年を抽出"""
    return _normalizer.extract_built_year(text)


def parse_date(text: str) -> Optional[datetime]:
    """文字列から日付を抽出してdatetimeオブジェクトに変換"""
    return _normalizer.parse_date(text)


def validate_price(price: Optional[int]) -> bool:
    """価格の妥当性を検証（100万円以上、100億円以下）"""
    return _normalizer.validate_price(price)


def validate_area(area: Optional[float]) -> bool:
    """面積の妥当性を検証（10㎡以上、1000㎡以下）"""
    return _normalizer.validate_area(area)


def validate_floor_number(floor: Optional[int], total_floors: Optional[int] = None) -> bool:
    """階数の妥当性を検証"""
    return _normalizer.validate_floor_number(floor, total_floors)

def validate_built_year(year: Optional[int]) -> bool:
    """築年の妥当性を検証（1900年以降、現在年+5年以内）"""
    if year is None:
        return False
    from datetime import datetime
    current_year = datetime.now().year
    # 1900年から現在年+5年までの範囲を許可（新築物件対応）
    return 1900 <= year <= current_year + 5


# 使用例
if __name__ == "__main__":
    # テスト用のコード
    normalizer = DataNormalizer()
    
    # 価格抽出のテスト
    print("=== 価格抽出テスト ===")
    test_prices = [
        "5,480万円",
        "1億2000万円",
        "2億円",
        "販売価格：3,980万円（税込）",
    ]
    for text in test_prices:
        price = normalizer.extract_price(text)
        print(f"{text} -> {price}万円")
    
    # 面積抽出のテスト
    print("\n=== 面積抽出テスト ===")
    test_areas = [
        "81.3㎡",
        "専有面積：70.2m²",
        "バルコニー面積：12.5m2",
    ]
    for text in test_areas:
        area = normalizer.extract_area(text)
        print(f"{text} -> {area}㎡")
    
    # 階数抽出のテスト
    print("\n=== 階数抽出テスト ===")
    test_floors = [
        "4階",
        "所在階：12階",
        "4階/SRC9階建",
        "地上42階地下2階建",
    ]
    for text in test_floors:
        floor = normalizer.extract_floor_number(text)
        total, basement = normalizer.extract_total_floors(text)
        print(f"{text} -> 階数: {floor}, 総階数: {total}, 地下: {basement}")
    
    # 間取り正規化のテスト
    print("\n=== 間取り正規化テスト ===")
    test_layouts = [
        "２ＬＤＫ",
        "3SLDK",
        "ワンルーム",
        "1R",
        "STUDIO",
    ]
    for text in test_layouts:
        layout = normalizer.normalize_layout(text)
        print(f"{text} -> {layout}")