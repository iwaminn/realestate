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
        """
        if not text:
            return None
            
        # 億万円パターン（例: "1億4500万円"）
        oku_man_match = re.search(r'(\d+)億(\d+(?:,\d{3})*)万円', text)
        if oku_man_match:
            oku = int(oku_man_match.group(1))
            man = int(oku_man_match.group(2).replace(',', ''))
            return oku * 10000 + man
        
        # 億円パターン（例: "2億円"）
        oku_only_match = re.search(r'(\d+)億円', text)
        if oku_only_match:
            oku = int(oku_only_match.group(1))
            return oku * 10000
        
        # 万円パターン（例: "5,480万円"）
        man_match = re.search(r'([\d,]+)万円', text)
        if man_match:
            return int(man_match.group(1).replace(',', ''))
        
        return None

    def extract_monthly_fee(self, text: str) -> Optional[int]:
        """
        文字列から月額費用を抽出（円単位）
        
        Args:
            text: 費用を含む文字列（例: "12,000円", "管理費：8,500円/月"）
            
        Returns:
            円単位の費用（int）またはNone
        """
        if not text:
            return None
            
        # 円パターン
        fee_match = re.search(r'([\d,]+)円', text)
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
        """
        if not text:
            return None, None
            
        total_floors = None
        basement_floors = 0
        
        # 地下階数を抽出
        basement_match = re.search(r'地下(\d+)階', text)
        if basement_match:
            basement_floors = int(basement_match.group(1))
        
        # 総階数を抽出（構造種別の後にある場合も考慮）
        total_match = re.search(r'(?:地上)?(?:RC|SRC|S造|木造|鉄骨)?(\d+)階(?:地下\d+階)?建', text)
        if total_match:
            total_floors = int(total_match.group(1))
        
        return total_floors, basement_floors

    # ========== 築年関連 ==========
    
    def extract_built_year(self, text: str) -> Optional[int]:
        """
        文字列から築年を抽出
        
        Args:
            text: 築年情報を含む文字列（例: "2020年築", "築年月：2015年3月", "平成27年築"）
            
        Returns:
            西暦年（int）またはNone
            
        Examples:
            >>> normalizer.extract_built_year("2020年築")
            2020
            >>> normalizer.extract_built_year("築年月：2015年3月")
            2015
        """
        if not text:
            return None
            
        # 西暦年パターン
        year_match = re.search(r'(19\d{2}|20\d{2})年', text)
        if year_match:
            return int(year_match.group(1))
        
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
            
        # 不要な文言を削除
        text = re.sub(r'\[乗り換え案内\]|\[地図\]', '', text)
        
        # 「、」で区切られている場合は改行に変換
        text = text.replace('、', '\n')
        
        # 路線名の前で改行を入れる
        for railway in self.railway_patterns:
            text = re.sub(rf'(?={railway})', '\n', text)
        
        # 連続する改行を1つに
        text = re.sub(r'\n+', '\n', text)
        
        # 前後の空白・改行を削除
        text = text.strip()
        
        return text

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
        """価格の妥当性を検証（100万円以上、10億円以下）"""
        if price is None:
            return False
        return 100 <= price <= 100000

    def validate_area(self, area: Optional[float]) -> bool:
        """面積の妥当性を検証（10㎡以上、500㎡以下）"""
        if area is None:
            return False
        return 10.0 <= area <= 500.0

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
        """築年の妥当性を検証"""
        if year is None:
            return False
        current_year = datetime.now().year
        return 1900 <= year <= current_year

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