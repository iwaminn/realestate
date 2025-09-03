"""
建物名標準化ユーティリティ
"""

import re
import unicodedata
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher
import jaconv  # 日本語変換ライブラリ


class BuildingNameNormalizer:
    """建物名を標準化するクラス"""
    
    # 建物タイプの正規化辞書
    BUILDING_TYPE_MAP = {
        'マンション': 'マンション',
        'ビル': 'ビル',
        'ハイツ': 'ハイツ',
        'コーポ': 'コーポ',
        'レジデンス': 'レジデンス',
        'アパート': 'アパート',
        'メゾン': 'メゾン',
        'ハウス': 'ハウス',
        'パレス': 'パレス',
        'コート': 'コート',
        'ヴィラ': 'ヴィラ',
        'プラザ': 'プラザ',
        'タワー': 'タワー',
    }
    
    # 削除する接頭辞・接尾辞
    REMOVE_PATTERNS = [
        r'^ザ\s*[・･]\s*',          # 「ザ・」のみ削除（THEは保持）
        r'\s*\(.*?\)$',             # 括弧内の情報
        r'\s*（.*?）$',             # 全角括弧内の情報
    ]
    
    def __init__(self):
        self.similarity_threshold = 0.85  # 類似度の閾値
    
    def extract_room_number(self, name: str) -> Tuple[str, Optional[str]]:
        """建物名から部屋番号を抽出し、建物名と部屋番号のタプルを返す"""
        if not name:
            return ("", None)
        
        # 部屋番号のパターン（末尾の数字）
        # 例: "白金ザ・スカイE棟 2414" → 建物名: "白金ザ・スカイE棟", 部屋番号: "2414"
        # 例: "パークハウス 301号室" → 建物名: "パークハウス", 部屋番号: "301"
        room_patterns = [
            r'\s+(\d{3,4})$',  # 末尾の3-4桁の数字（スペース区切り）
            r'\s+(\d{3,4})号室?$',  # 末尾の号室表記
            r'\s+(\d{1,2}F?\s*-?\s*\d{1,4})$',  # 階数-部屋番号形式（例: 2F-201, 2-201）
            r'[-]\s*(\d{3,4})$',  # ハイフン区切りの部屋番号
            r'[・]\s*(\d{3,4})$',  # 中点区切りの部屋番号
        ]
        
        for pattern in room_patterns:
            match = re.search(pattern, name)
            if match:
                room_number = match.group(1).replace('F', '').replace('-', '').replace(' ', '')
                building_name = re.sub(pattern, '', name).strip()
                return (building_name, room_number)
        
        return (name, None)
    
    def normalize_building_unit(self, name: str) -> str:
        """建物の棟表記を正規化（全角・半角を統一、スペースを削除）"""
        # まず英語の棟表記を日本語に統一
        # EAST → E棟, WEST → W棟, NORTH → N棟, SOUTH → S棟
        # ただし、既に「棟」が付いている場合（例：ＥＡＳＴ棟）は「棟」を重複させない
        english_to_japanese = {
            'EAST棟': 'E棟',
            'WEST棟': 'W棟',
            'NORTH棟': 'N棟',
            'SOUTH棟': 'S棟',
            'East棟': 'E棟',
            'West棟': 'W棟',
            'North棟': 'N棟',
            'South棟': 'S棟',
            'ＥＡＳＴ棟': 'E棟',
            'ＷＥＳＴ棟': 'W棟',
            'ＮＯＲＴＨ棟': 'N棟',
            'ＳＯＵＴＨ棟': 'S棟',
            'EAST': 'E棟',
            'WEST': 'W棟',
            'NORTH': 'N棟',
            'SOUTH': 'S棟',
            'East': 'E棟',
            'West': 'W棟',
            'North': 'N棟',
            'South': 'S棟',
        }
        
        for eng, jpn in english_to_japanese.items():
            name = name.replace(eng, jpn)
        
        # 棟の表記パターン（棟の意味は保持）
        unit_patterns = {
            # アルファベット棟（全角→半角）
            r'[Ｅ]棟': 'E棟',
            r'[Ｗ]棟': 'W棟',
            r'[Ｎ]棟': 'N棟',
            r'[Ｓ]棟': 'S棟',
            r'[Ａ]棟': 'A棟',
            r'[Ｂ]棟': 'B棟',
            r'[Ｃ]棟': 'C棟',
            r'[Ｄ]棟': 'D棟',
            # スペース付きパターンのスペースを削除
            r'\s+([A-Za-zＡ-Ｚａ-ｚ東西南北])棟': r'\1棟',
        }
        
        # 各パターンを適用
        for pattern, replacement in unit_patterns.items():
            name = re.sub(pattern, replacement, name)
        
        # 棟の前のスペースを削除（半角アルファベット）
        name = re.sub(r'\s+([A-Z])棟', r'\1棟', name)
        
        # 小文字の棟表記も大文字に統一
        name = re.sub(r'([a-z])棟', lambda m: m.group(1).upper() + '棟', name)
        
        return name
    
    def normalize(self, name: str) -> str:
        """建物名を標準化"""
        if not name:
            return ""
        
        # まず部屋番号を抽出・除去
        name, room_number = self.extract_room_number(name)
        
        # 1. 漢数字を算用数字に変換（全角変換の前に実行）
        name = self.convert_japanese_numbers(name)
        
        # 2. ローマ数字を算用数字に変換
        name = self.convert_roman_numerals(name)
        
        # 3. 全角英数字を半角に変換
        name = jaconv.z2h(name, kana=False, ascii=True, digit=True)
        
        # 4. カタカナの正規化（半角カナを全角に）
        name = jaconv.h2z(name, kana=True, ascii=False, digit=False)
        
        # 5. 英字の大文字統一（建物名では通常大文字が使われる）
        # ただし、棟表記（E棟、W棟など）は後で処理するので、ここでは建物名部分のみ
        # 例: "n's" → "N'S", "N´s" → "N'S"
        name = self.normalize_english_case(name)
        
        # 6. スペースの正規化
        name = re.sub(r'[\s　]+', ' ', name).strip()
        
        # 7. 特殊文字の正規化
        replacements = {
            '〜': '～',
            '－': '-',
            '―': '-',
            '‐': '-',
            '･': '・',
            '､': '、',
            '｡': '。',
        }
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        # 8. 不要なパターンを削除
        for pattern in self.REMOVE_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # 9. 建物タイプの正規化
        for variant, standard in self.BUILDING_TYPE_MAP.items():
            if variant in name:
                name = name.replace(variant, standard)
        
        # 10. 棟表記の正規化
        name = self.normalize_building_unit(name)
        
        # 11. 中黒（・）の有無を統一（重要な建物名の区切りでない場合は削除）
        # 例: "白金ザ・スカイ" → "白金ザスカイ"
        # ただし、明確に別の単語を区切る場合は保持
        # カタカナ同士の間の中黒は削除
        name = re.sub(r'([ァ-ヴー])・([ァ-ヴー])', r'\1\2', name)
        # 「ザ・」「ラ・」「レ・」などの定冠詞後の中黒は削除
        name = re.sub(r'(ザ|ラ|レ|ル|ロ)・', r'\1', name)
        
        # 9. よく使われる英語建物名をカタカナに変換
        # 大文字小文字の違いを吸収するため
        # 単語境界を使用して完全一致のみ置換（VILLAGEがヴィラGEにならないように）
        english_to_katakana = {
            'SQUARE': 'スクエア',
            'TOWER': 'タワー',
            'COURT': 'コート',
            'PALACE': 'パレス',
            'HOUSE': 'ハウス',
            'PARK': 'パーク',
            'HILLS': 'ヒルズ',
            'GARDEN': 'ガーデン',
            'TERRACE': 'テラス',
            'RESIDENCE': 'レジデンス',
            'HEIGHTS': 'ハイツ',
            'MANSION': 'マンション',
            'VILLA': 'ヴィラ',
            'PLAZA': 'プラザ',
        }
        
        for eng, katakana in english_to_katakana.items():
            # 単語境界を使用して完全一致のみ置換
            name = re.sub(r'\b' + eng + r'\b', katakana, name)
        
        # 10. カタカナ単語間のスペースを削除（建物名の統一性を保つため）
        # 例: "芝浦アイランド ケープタワー" → "芝浦アイランドケープタワー"
        # ただし、数字や記号が含まれる場合はスペースを保持
        # パターン: カタカナ文字列＋スペース＋カタカナ文字列
        name = re.sub(r'([ァ-ヴー]+)\s+([ァ-ヴー]+)', r'\1\2', name)
        
        # 11. 特定のカタカナビル名パターンでのスペース削除
        # 例: "パーク タワー" → "パークタワー", "リバー サイド" → "リバーサイド"
        common_patterns = [
            (r'パーク\s+タワー', 'パークタワー'),
            (r'タワー\s+レジデンス', 'タワーレジデンス'),
            (r'シティ\s+タワー', 'シティタワー'),
            (r'グランド\s+タワー', 'グランドタワー'),
            (r'ベイ\s+タワー', 'ベイタワー'),
            (r'リバー\s+サイド', 'リバーサイド'),
            (r'ガーデン\s+タワー', 'ガーデンタワー'),
        ]
        for pattern, replacement in common_patterns:
            name = re.sub(pattern, replacement, name)
        
        return name.strip()
    
    def convert_japanese_numbers(self, text: str) -> str:
        """漢数字を算用数字に変換
        
        例：
        - 第一棟 → 第1棟
        - 二号館 → 2号館
        - 十五階建 → 15階建
        """
        if not text:
            return text
        
        # 基本的な漢数字マップ
        basic_map = {
            '〇': '0', '○': '0', '零': '0',
            '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
            '六': '6', '七': '7', '八': '8', '九': '9',
            '壱': '1', '弐': '2', '参': '3',  # 旧字体
        }
        
        # 十の位の処理
        ten_map = {
            '十': '10', '二十': '20', '三十': '30', '四十': '40', '五十': '50',
            '六十': '60', '七十': '70', '八十': '80', '九十': '90',
        }
        
        result = text
        
        # パターン1: 第X棟、X号館などの単純な置換
        # 第一棟 → 第1棟
        for pattern in [r'第([一二三四五六七八九十]+)([棟館号])', 
                       r'([一二三四五六七八九十]+)([棟館号])']:
            def replace_func(match):
                num_str = match.group(1)
                suffix = match.group(2) if len(match.groups()) > 1 else ''
                prefix = '第' if '第' in match.group(0) else ''
                
                # 「十」を含む場合の処理
                if '十' in num_str:
                    if num_str == '十':
                        converted = '10'
                    elif num_str.startswith('十'):
                        # 十X → 1X
                        rest = num_str[1:]
                        if rest in basic_map:
                            converted = '1' + basic_map[rest]
                        else:
                            converted = num_str
                    elif num_str.endswith('十'):
                        # X十 → X0
                        first = num_str[:-1]
                        if first in basic_map:
                            converted = basic_map[first] + '0'
                        else:
                            converted = num_str
                    elif len(num_str) == 3 and num_str[1] == '十':
                        # X十Y → XY
                        first = num_str[0]
                        last = num_str[2]
                        if first in basic_map and last in basic_map:
                            converted = basic_map[first] + basic_map[last]
                        else:
                            converted = num_str
                    else:
                        converted = num_str
                else:
                    # 単純な置換
                    converted = num_str
                    for kanji, num in basic_map.items():
                        converted = converted.replace(kanji, num)
                
                return prefix + converted + suffix
            
            result = re.sub(pattern, replace_func, result)
        
        # パターン2: 残った独立した漢数字を処理
        # 「二十三」のような複合数字を処理
        def convert_compound_number(match):
            text = match.group(0)
            # 十の位と一の位を処理
            if '十' in text:
                parts = text.split('十')
                if len(parts) == 2:
                    tens = basic_map.get(parts[0], parts[0]) if parts[0] else '1'
                    ones = basic_map.get(parts[1], '0') if parts[1] else '0'
                    if tens.isdigit() and ones.isdigit():
                        return str(int(tens) * 10 + int(ones))
                elif text == '十':
                    return '10'
            # 単純な一桁の数字
            return basic_map.get(text, text)
        
        # 漢数字のパターンにマッチする部分を変換
        result = re.sub(r'[一二三四五六七八九十]+', convert_compound_number, result)
        
        return result
    
    def convert_roman_numerals(self, text: str) -> str:
        """ローマ数字を算用数字に変換
        
        例：
        - タワーⅡ → タワー2
        - 第Ⅲ期 → 第3期
        """
        if not text:
            return text
        
        # ローマ数字マップ（大文字と小文字の両方）
        # 複合文字を先に処理するため、長い組み合わせから順に並べる
        roman_patterns = [
            # 2文字の組み合わせ（全角）
            ('ⅩⅡ', '12'),  # Ⅹ + Ⅱ
            ('ⅩⅠ', '11'),  # Ⅹ + Ⅰ
            # 単一文字（全角）
            ('Ⅰ', '1'), ('Ⅱ', '2'), ('Ⅲ', '3'), ('Ⅳ', '4'), ('Ⅴ', '5'),
            ('Ⅵ', '6'), ('Ⅶ', '7'), ('Ⅷ', '8'), ('Ⅸ', '9'), ('Ⅹ', '10'),
            ('Ⅺ', '11'), ('Ⅻ', '12'),
            # 小文字ローマ数字（全角）
            ('ⅰ', '1'), ('ⅱ', '2'), ('ⅲ', '3'), ('ⅳ', '4'), ('ⅴ', '5'),
            ('ⅵ', '6'), ('ⅶ', '7'), ('ⅷ', '8'), ('ⅸ', '9'), ('ⅹ', '10'),
        ]
        
        result = text
        
        # 全角ローマ数字を変換（長い組み合わせから処理）
        for roman, num in roman_patterns:
            result = result.replace(roman, num)
        
        # 半角ローマ数字パターン（慎重に処理）
        # 「タワーIII」「第II期」のようなパターンのみ変換
        patterns = [
            # より複雑な組み合わせから先に処理
            (r'(タワー|Tower|TOWER|棟|期|第)\s*XII\b', r'\g<1>12'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*XI\b', r'\g<1>11'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*IX\b', r'\g<1>9'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*VIII\b', r'\g<1>8'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*VII\b', r'\g<1>7'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*VI\b', r'\g<1>6'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*IV\b', r'\g<1>4'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*V\b', r'\g<1>5'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*III\b', r'\g<1>3'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*II\b', r'\g<1>2'),
            (r'(タワー|Tower|TOWER|棟|期|第)\s*I\b', r'\g<1>1'),
        ]
        
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result
    
    def normalize_english_case(self, name: str) -> str:
        """英字の大文字小文字を統一（建物名では通常大文字を使用）"""
        # 建物名でよく使われる英語表記を大文字に統一
        # ただし、棟表記は別途処理するので除外
        
        # アポストロフィのバリエーションを統一
        name = re.sub(r"[''´`]", "'", name)
        
        # 英単語のパターンを検出して大文字化
        # 以下のパターンは大文字化する：
        # - 単独の英単語（例: tower → TOWER）
        # - アポストロフィ付きの英単語（例: n's → N'S）
        # - ハイフン付きの英単語（例: e-style → E-STYLE）
        
        def upper_match(match):
            word = match.group(0)
            # 棟表記（「棟」が続く場合）は元のまま（後で処理される）
            if match.end() < len(name) and match.end() + 1 < len(name) and name[match.end():match.end()+1] == '棟':
                return word.upper()  # 棟の前の英字も大文字化
            return word.upper()
        
        # 英単語パターン（アポストロフィやハイフンを含む）
        # より広いパターンでマッチング（単一文字も含む）
        name = re.sub(r"[a-zA-Z]+(?:['-]?[a-zA-Z]*)*", upper_match, name)
        
        return name
    
    def extract_building_components(self, name: str) -> Dict[str, str]:
        """建物名から構成要素を抽出"""
        components = {
            'area': '',      # 地域名（例：白金、青山）
            'main': '',      # メイン名称（例：ザスカイ、タワー）
            'type': '',      # 建物タイプ（例：マンション、レジデンス）
            'unit': '',      # 棟情報（例：E棟、西棟）
            'suffix': ''     # その他の修飾語
        }
        
        # 棟情報を抽出（より厳密なパターン）
        unit_patterns = [
            r'([東西南北EWNS]棟)',           # 方角棟
            r'([A-Za-z]棟)',                 # アルファベット棟
            r'(第[一二三四五六七八九十\d]+棟)', # 第X棟
            r'([一二三四五六七八九十\d]+号棟)', # X号棟
            r'(タワー棟|テラス棟)',          # 特殊棟
            r'(ライトウィング|レフトウィング)',  # ウィング系
            r'(\d+番館)',                    # 番館
            r'(棟)$',                        # 末尾の単独「棟」
        ]
        
        for pattern in unit_patterns:
            unit_match = re.search(pattern, name)
            if unit_match:
                components['unit'] = unit_match.group(1)
                name = name.replace(unit_match.group(1), '').strip()
                break
        
        # 建物タイプを抽出
        for building_type in self.BUILDING_TYPE_MAP.values():
            if building_type in name:
                components['type'] = building_type
                name = name.replace(building_type, '').strip()
                break
        
        # 地域名と本体名を分離（最初の漢字/ひらがな部分を地域名と仮定）
        area_match = re.match(r'^([\u4e00-\u9faf\u3040-\u309f]+)', name)
        if area_match:
            components['area'] = area_match.group(1)
            components['main'] = name[len(area_match.group(1)):].strip()
        else:
            components['main'] = name
        
        return components
    
    def calculate_similarity(self, name1: str, name2: str) -> float:
        """2つの建物名の類似度を計算（末尾の識別子を重視した汎用的アプローチ）"""
        # 正規化
        norm1 = self.normalize(name1)
        norm2 = self.normalize(name2)
        
        # 完全一致の場合
        if norm1 == norm2:
            return 1.0
        
        # 建物名を単語単位に分割
        def tokenize(name):
            """建物名を意味のある単位に分割"""
            # スペース、中黒、ハイフンなどで分割
            tokens = re.split(r'[\s　・\-－]+', name)
            # 空の要素を除去
            return [t for t in tokens if t]
        
        tokens1 = tokenize(norm1)
        tokens2 = tokenize(norm2)
        
        # トークンが存在しない場合は基本的な文字列比較
        if not tokens1 or not tokens2:
            return SequenceMatcher(None, norm1, norm2).ratio()
        
        # 共通接頭辞と異なる部分を分析
        def find_common_prefix_and_suffix(t1, t2):
            """共通の接頭辞と、それぞれの異なる部分を見つける"""
            # 共通接頭辞を見つける
            common_prefix = []
            min_len = min(len(t1), len(t2))
            
            for i in range(min_len):
                if t1[i] == t2[i]:
                    common_prefix.append(t1[i])
                else:
                    break
            
            # 残りの部分（識別子部分）
            suffix1 = t1[len(common_prefix):]
            suffix2 = t2[len(common_prefix):]
            
            return common_prefix, suffix1, suffix2
        
        common, suffix1, suffix2 = find_common_prefix_and_suffix(tokens1, tokens2)
        
        # ケース1: 完全に異なる建物名（共通部分がない）
        if not common:
            # 基本的な文字列類似度
            return SequenceMatcher(None, norm1, norm2).ratio()
        
        # ケース2: 共通部分はあるが、末尾（識別子）が異なる
        if suffix1 or suffix2:
            # 共通部分の割合を計算
            total_tokens = max(len(tokens1), len(tokens2))
            common_ratio = len(common) / total_tokens
            
            # 末尾が異なる場合の類似度計算
            # 末尾の違いが重要な識別子である可能性が高いため、大きく減点
            if suffix1 and suffix2:
                # 両方に末尾がある（例：SEA VILLAGE B棟 vs SUN VILLAGE F棟）
                # 末尾の類似度も考慮
                suffix_sim = SequenceMatcher(None, ' '.join(suffix1), ' '.join(suffix2)).ratio()
                # 共通部分が多くても、末尾が異なれば低い類似度
                return min(0.6, common_ratio * 0.5 + suffix_sim * 0.1)
            else:
                # 片方のみ末尾がある（例：HARUMI FLAG vs HARUMI FLAG B棟）
                # これも異なる建物の可能性が高い
                return min(0.65, common_ratio * 0.7)
        
        # ケース3: 末尾まで同じ（トークンが完全一致）
        # この場合は正規化の違いのみ
        return 0.95
        
        # 以下は到達しないが、念のため基本的な類似度を返す
        return SequenceMatcher(None, norm1, norm2).ratio()
    
    def is_same_building(self, name1: str, name2: str, 
                        address1: Optional[str] = None, 
                        address2: Optional[str] = None) -> bool:
        """同じ建物かどうかを判定"""
        # 名前の類似度
        name_similarity = self.calculate_similarity(name1, name2)
        
        # 住所が提供されている場合
        if address1 and address2:
            # 住所の類似度も考慮
            addr_similarity = SequenceMatcher(None, address1, address2).ratio()
            # 名前と住所の重み付け平均
            total_similarity = name_similarity * 0.7 + addr_similarity * 0.3
        else:
            total_similarity = name_similarity
        
        return total_similarity >= self.similarity_threshold
    
    def find_best_name(self, names: List[str]) -> str:
        """複数の表記から最適な標準名を選択"""
        if not names:
            return ""
        
        # 各名前の出現回数をカウント
        name_counts = {}
        for name in names:
            normalized = self.normalize(name)
            name_counts[normalized] = name_counts.get(normalized, 0) + 1
        
        # 最も頻出する正規化名を取得
        most_common_normalized = max(name_counts.items(), key=lambda x: x[1])[0]
        
        # その正規化名に対応する元の名前の中で最も詳細なものを選択
        candidates = [name for name in names if self.normalize(name) == most_common_normalized]
        
        # 最も長い（＝詳細な）名前を選択
        return max(candidates, key=len)
    
    def group_buildings(self, buildings: List[Dict[str, any]]) -> List[List[Dict[str, any]]]:
        """建物リストをグループ化"""
        groups = []
        used = set()
        
        for i, building1 in enumerate(buildings):
            if i in used:
                continue
            
            group = [building1]
            used.add(i)
            
            for j, building2 in enumerate(buildings[i+1:], i+1):
                if j in used:
                    continue
                
                if self.is_same_building(
                    building1.get('name', ''),
                    building2.get('name', ''),
                    building1.get('address'),
                    building2.get('address')
                ):
                    group.append(building2)
                    used.add(j)
            
            groups.append(group)
        
        return groups


# 使用例
if __name__ == "__main__":
    normalizer = BuildingNameNormalizer()
    
    # テストケース
    test_cases = [
        ("ザ・パークハウス　南青山", "THE PARKHOUSE 南青山"),
        ("ﾊﾟｰｸﾊｳｽ南青山", "パークハウス南青山"),
        ("南青山マンション（賃貸）", "南青山マンション"),
        ("プラウド南青山　～PROUD～", "プラウド南青山"),
        ("白金ザ・スカイE棟", "白金ザスカイE棟"),
        ("白金ザ・スカイ EAST", "白金ザスカイE棟"),
        ("白金ザ・スカイＥＡＳＴ棟", "白金ザスカイE棟"),  # 新しいテストケース
        ("白金ザ・スカイEAST棟", "白金ザスカイE棟"),  # 新しいテストケース
        ("イニシア大森町n'sスクエア", "イニシア大森町N´sスクエア"),
        ("イニシア大森町N'sスクエア", "イニシア大森町n´sスクエア"),
    ]
    
    print("建物名の正規化テスト:")
    for name1, name2 in test_cases:
        norm1 = normalizer.normalize(name1)
        norm2 = normalizer.normalize(name2)
        similarity = normalizer.calculate_similarity(name1, name2)
        is_same = normalizer.is_same_building(name1, name2)
        
        print(f"\n'{name1}' → '{norm1}'")
        print(f"'{name2}' → '{norm2}'")
        print(f"類似度: {similarity:.2f}")
        print(f"同一建物判定: {is_same}")