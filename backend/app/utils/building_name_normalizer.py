"""
建物名正規化の共通モジュール
base_scraper.pyから正規化ロジックを抽出して共通化
"""

import re
import jaconv


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
    
    # 2. 記号類の処理
    # 意味のある記号（・、&、-、~）は保持、装飾記号はスペースに変換
    
    # 各種ダッシュをハイフンに統一
    for dash_char in ['\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015']:
        normalized = normalized.replace(dash_char, '-')
    
    # 波ダッシュをチルダに統一
    normalized = normalized.replace('\u301c', '~').replace('～', '~')
    
    # 装飾記号をスペースに変換（●■★◆▲◇□◎○△▽♪など）
    # 保持する記号: 英数字、日本語、・（中点）、&、-、~、括弧、スペース
    import string
    allowed_chars = set(string.ascii_letters + string.digits + '・&-~()[] 　')
    # 日本語文字の範囲を追加（ひらがな、カタカナ、漢字）
    result = []
    for char in normalized:
        if char in allowed_chars:
            result.append(char)
        elif '\u3040' <= char <= '\u9fff':  # 日本語文字の範囲
            result.append(char)
        elif '\uff00' <= char <= '\uffef':  # 全角記号の一部（全角英数字など）
            result.append(char)
        else:
            # その他の記号はスペースに変換
            result.append(' ')
    normalized = ''.join(result)
    
    # 3. ローマ数字の正規化（全角ローマ数字を半角に変換）
    roman_map = {
        'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V',
        'Ⅵ': 'VI', 'Ⅶ': 'VII', 'Ⅷ': 'VIII', 'Ⅸ': 'IX', 'Ⅹ': 'X',
        'Ⅺ': 'XI', 'Ⅻ': 'XII'
    }
    for full_width, half_width in roman_map.items():
        normalized = normalized.replace(full_width, half_width)
    
    # 4. 単位の正規化（㎡とm2を統一）
    normalized = normalized.replace('㎡', 'm2').replace('m²', 'm2')
    
    # 5. 英字を大文字に統一（表記ゆれ吸収のため）
    # 日本語（ひらがな・カタカナ・漢字）は影響を受けない
    normalized = normalized.upper()
    
    # 6. スペースの正規化
    # 全角スペースも半角スペースに変換
    normalized = normalized.replace('　', ' ')
    # 連続するスペースを1つの半角スペースに統一
    normalized = re.sub(r'\s+', ' ', normalized)
    # 前後の空白を除去
    normalized = normalized.strip()
    
    return normalized


def get_search_key_for_building(building_name: str) -> str:
    """
    建物検索用のキーを生成（normalize_building_nameをベースに追加処理）
    
    normalize_building_nameの処理に加えて：
    - スペースと記号を完全削除（より緩い一致のため）
    
    注意：棟表記（東棟、西棟など）は除去しません。
    異なる棟は別々の建物として扱われます。
    """
    # まず標準的な正規化を適用
    key = normalize_building_name(building_name)
    
    # 検索用により緩い正規化を追加
    # スペースを完全削除（検索時の利便性のため）
    key = re.sub(r'\s+', '', key)
    
    return key


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