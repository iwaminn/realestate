"""
建物名正規化の共通モジュール
base_scraper.pyから正規化ロジックを抽出して共通化
"""

import re
import jaconv


"""
建物名の正規化のための汎用関数群

このファイルは建物名の正規化のための標準的な関数を提供します。
スクレイパー、API、その他のユーティリティで広く使用されています。

主な関数:
- normalize_building_name: 表示用の建物名正規化（中点は保持）
- canonicalize_building_name: 検索用の建物名正規化（中点を削除）
- extract_room_number: 建物名から部屋番号を抽出
"""

def normalize_building_name_with_ad_removal(building_name: str) -> str:
    """
    建物名を正規化する（広告文削除付き）
    
    スクレイピング時など、広告文が含まれている可能性がある場合に使用
    
    Args:
        building_name: 正規化する建物名（広告文が含まれる可能性あり）
        
    Returns:
        広告文を削除して正規化された建物名
    """
    if not building_name:
        return ""
    
    # まず広告文を削除（棟名や番号は保持）
    from ..scrapers.base_scraper import extract_building_name_from_ad_text
    cleaned_name = extract_building_name_from_ad_text(building_name)
    
    # その後、通常の正規化を適用
    return normalize_building_name(cleaned_name)


def normalize_building_name(building_name: str) -> str:
    """
    建物名を正規化する共通メソッド
    
    Args:
        building_name: 正規化する建物名
        
    Returns:
        正規化された建物名
    """
    if not building_name:
        return ""
        
    # 1. 全角英数字と記号を半角に変換
    normalized = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
    
    # 2. ローマ数字の正規化を先に実行（フィルタリング前に変換）
    # 全角ローマ数字を半角に変換
    roman_map = {
        'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V',
        'Ⅵ': 'VI', 'Ⅶ': 'VII', 'Ⅷ': 'VIII', 'Ⅸ': 'IX', 'Ⅹ': 'X',
        'Ⅺ': 'XI', 'Ⅻ': 'XII',
        # 小文字版も追加
        'ⅰ': 'I', 'ⅱ': 'II', 'ⅲ': 'III', 'ⅳ': 'IV', 'ⅴ': 'V',
        'ⅵ': 'VI', 'ⅶ': 'VII', 'ⅷ': 'VIII', 'ⅸ': 'IX', 'ⅹ': 'X',
        'ⅺ': 'XI', 'ⅻ': 'XII'
    }
    for full_width, half_width in roman_map.items():
        normalized = normalized.replace(full_width, half_width)
    
    # 3. 記号類の処理
    # 意味のある記号（・、&、-、~）は保持、装飾記号はスペースに変換
    
    # 各種ダッシュをハイフンに統一
    for dash_char in ['\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015']:
        normalized = normalized.replace(dash_char, '-')
    
    # 波ダッシュをチルダに統一
    normalized = normalized.replace('\u301c', '~').replace('\uff5e', '~')
    
    # 装飾記号をスペースに変換（●■★◆▲◇□◎○△▽♪など）
    # 保持する記号: 英数字、日本語、・（中点）、&、-、~、括弧、スペース
    import string
    allowed_chars = set(string.ascii_letters + string.digits + '・&-~()[] 　々')  # 々を追加
    # 日本語文字の範囲を追加（ひらがな、カタカナ、漢字）
    result = []
    for char in normalized:
        if char in allowed_chars:
            result.append(char)
        elif '\u3000' <= char <= '\u9fff':  # 日本語文字の範囲（U+3000から開始して々を含む）
            result.append(char)
        elif '\uff00' <= char <= '\uffef':  # 全角記号の一部（全角英数字など）
            result.append(char)
        else:
            # その他の記号はスペースに変換
            result.append(' ')
    normalized = ''.join(result)
    
    # 4. 単位の正規化（㎡とm2を統一）
    normalized = normalized.replace('㎡', 'm2').replace('m²', 'm2')
    
    # 5. 英字を大文字に統一（表記ゆれ吸収のため）
    # 日本語（ひらがな・カタカナ・漢字）は影響を受けない
    normalized = normalized.upper()
    
    # 6. スペースの正規化
    # 全角スペースも半角スペースに変換
    normalized = normalized.replace('　', ' ')
    # 連続するスペースを1つの半角スペースに統一
    import re
    normalized = re.sub(r'\s+', ' ', normalized)
    # 前後の空白を除去
    normalized = normalized.strip()
    
    return normalized


def convert_japanese_numbers_to_arabic(text: str) -> str:
    """漢数字を算用数字に変換（検索用）
    
    Args:
        text: 変換対象のテキスト
    
    Returns:
        漢数字を算用数字に変換したテキスト
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
    
    result = text
    
    # パターン1: 第X棟、X号館などの単純な置換
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
                    rest = num_str[1:]
                    if rest in basic_map:
                        converted = '1' + basic_map[rest]
                    else:
                        converted = num_str
                elif num_str.endswith('十'):
                    first = num_str[:-1]
                    if first in basic_map:
                        converted = basic_map[first] + '0'
                    else:
                        converted = num_str
                elif len(num_str) == 3 and num_str[1] == '十':
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


def convert_roman_numerals_to_arabic(text: str) -> str:
    """ローマ数字を算用数字に変換（検索用）
    
    Args:
        text: 変換対象のテキスト
    
    Returns:
        ローマ数字を算用数字に変換したテキスト
    """
    if not text:
        return text
    
    # 全角ローマ数字の変換マップ
    roman_map = {
        # 大文字
        'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4', 'Ⅴ': '5',
        'Ⅵ': '6', 'Ⅶ': '7', 'Ⅷ': '8', 'Ⅸ': '9', 'Ⅹ': '10',
        'Ⅺ': '11', 'Ⅻ': '12',
        # 小文字
        'ⅰ': '1', 'ⅱ': '2', 'ⅲ': '3', 'ⅳ': '4', 'ⅴ': '5',
        'ⅵ': '6', 'ⅶ': '7', 'ⅷ': '8', 'ⅸ': '9', 'ⅹ': '10',
        'ⅺ': '11', 'ⅻ': '12'
    }
    
    result = text
    
    # 全角ローマ数字を変換
    for roman, num in roman_map.items():
        result = result.replace(roman, num)
    
    # 半角ローマ数字パターン（汎用的な変換）
    import re
    
    def replace_roman(match):
        """ローマ数字を算用数字に変換する関数"""
        roman = match.group(1).upper() if match.lastindex else match.group(0).upper()  # グループ1があれば使用、なければグループ0
        
        # ローマ数字と算用数字の対応表（1-30まで対応）
        roman_to_arabic = {
            'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
            'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
            'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
            'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20,
            'XXI': 21, 'XXII': 22, 'XXIII': 23, 'XXIV': 24, 'XXV': 25,
            'XXVI': 26, 'XXVII': 27, 'XXVIII': 28, 'XXIX': 29, 'XXX': 30
        }
        
        # 大文字に統一して検索
        if roman in roman_to_arabic:
            return str(roman_to_arabic[roman])
        
        # 見つからない場合はそのまま返す
        return match.group(0)
    
    # 半角ローマ数字のパターン（より汎用的）
    # 前後が英字でない場合にマッチ（日本語文字や数字、記号の前後はOK）
    # (?<![A-Za-z]) : 前に英字がない
    # (roman_numeral) : ローマ数字をキャプチャグループ1として取得
    # (?![A-Za-z]) : 後に英字がない
    roman_pattern = r'(?<![A-Za-z])((?:XXX|XX[IXV]|XX|X[IXV]|IX|IV|V?I{1,3}|X{1,2}))(?![A-Za-z])'
    
    # ローマ数字を変換（大文字小文字を問わない）
    result = re.sub(roman_pattern, replace_roman, result, flags=re.IGNORECASE)
    
    return result


def canonicalize_building_name(building_name: str) -> str:
    """
    建物名を正規化して検索用キーを生成
    
    処理内容：
    1. normalize_building_nameで基本的な正規化
    2. 漢数字を算用数字に変換
    3. ローマ数字を算用数字に変換
    4. ひらがなをカタカナに変換
    5. 英数字と日本語文字以外を削除（中点・も削除）
    6. 小文字化
    
    注意：棟表記（東棟、西棟など）は除去しません。
    異なる棟は別々の建物として扱われます。
    
    Args:
        building_name: 正規化する建物名
        
    Returns:
        検索用に完全に正規化された建物名
    """
    if not building_name:
        return ""
    
    # まず標準的な正規化を適用
    normalized = normalize_building_name(building_name)
    
    # 漢数字を算用数字に変換（検索精度向上）
    normalized = convert_japanese_numbers_to_arabic(normalized)
    
    # ローマ数字を算用数字に変換（検索精度向上）
    normalized = convert_roman_numerals_to_arabic(normalized)
    
    # ひらがなをカタカナに変換
    canonical = ''
    for char in normalized:
        # ひらがなの範囲（U+3040〜U+309F）をカタカナ（U+30A0〜U+30FF）に変換
        if '\u3040' <= char <= '\u309f':
            canonical += chr(ord(char) + 0x60)
        else:
            canonical += char
    
    # 英数字と日本語文字以外をすべて削除
    import string
    result = []
    for char in canonical:
        if char in string.ascii_letters + string.digits:
            result.append(char)
        # 中点（・）は除外して、日本語文字のみを残す
        elif char == '・':
            continue  # 中点は削除
        elif char == '々':  # 繰り返し記号は保持
            result.append(char)
        elif '\u3000' <= char <= '\u9fff':  # 日本語文字の範囲（U+3000から開始）
            result.append(char)
        # それ以外の文字（記号、スペース等）は削除
    
    # 小文字化
    return ''.join(result).lower()


def extract_room_number(building_name: str) -> tuple[str, str]:
    """
    建物名から部屋番号を抽出する
    
    Args:
        building_name: 部屋番号を含む可能性のある建物名
        
    Returns:
        (部屋番号を除いた建物名, 抽出された部屋番号)
    """
    if not building_name:
        return "", None
    
    # 部屋番号のパターン（末尾の数字）
    # 例: "パークハウス101" -> ("パークハウス", "101")
    # 例: "東京タワー 2003号" -> ("東京タワー", "2003")
    
    # パターン1: 末尾の3-4桁の数字（号や号室を含む）
    pattern1 = re.compile(r'(.+?)\s*(\d{3,4})\s*(?:号|号室)?$')
    match = pattern1.match(building_name)
    if match:
        return match.group(1).strip(), match.group(2)
    
    # パターン2: 末尾に「○階」がある場合（これは部屋番号ではない）
    if re.search(r'\d+階$', building_name):
        return building_name, None
    
    # パターン3: 建物名の後に明確に区切られた数字
    # 例: "ビル名 101"
    pattern3 = re.compile(r'(.+?)\s+(\d{3,4})$')
    match = pattern3.match(building_name)
    if match:
        clean_name = match.group(1).strip()
        # 建物名っぽい場合のみ分離
        if len(clean_name) >= 2:  # 最低2文字以上
            return clean_name, match.group(2)
    
    return building_name, None