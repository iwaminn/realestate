"""検索文字列正規化ユーティリティ"""

import re
import unicodedata
from .building_name_normalizer import normalize_building_name, get_search_key_for_building


def normalize_search_text(text: str) -> str:
    """
    検索文字列を正規化する
    ひらがなをカタカナに変換してから正規化
    """
    if not text:
        return ""
    
    # まず、ひらがなをカタカナに変換
    text_katakana = ''
    for char in text:
        # ひらがなの範囲（U+3040〜U+309F）をカタカナ（U+30A0〜U+30FF）に変換
        if '\u3040' <= char <= '\u309f':
            # ひらがなをカタカナに変換（コードポイントを0x60加算）
            text_katakana += chr(ord(char) + 0x60)
        else:
            text_katakana += char
    
    # その後、共通の正規化関数を使用
    return normalize_building_name(text_katakana)


def create_search_patterns(search: str) -> list[str]:
    """
    検索パターンのバリエーションを生成
    ひらがな・カタカナの変換も含む
    
    例：
    「白金ざ　すかい」→「白金ザスカイ」「白金ザ・スカイ」「白金ザ スカイ」など
    """
    patterns = []
    
    # まず、ひらがなをカタカナに変換
    search_katakana = ''
    for char in search:
        # ひらがなの範囲（U+3040〜U+309F）をカタカナ（U+30A0〜U+30FF）に変換
        if '\u3040' <= char <= '\u309f':
            # ひらがなをカタカナに変換（コードポイントを0x60加算）
            search_katakana += chr(ord(char) + 0x60)
        else:
            search_katakana += char
    
    # 正規化したパターン（半角小文字、ひらがな→カタカナ変換済み）
    normalized = normalize_search_text(search_katakana)
    patterns.append(normalized)
    
    # 元の検索文字列（正規化前）
    if search != normalized:
        patterns.append(search)
    
    # カタカナ変換後が異なる場合も追加
    if search_katakana != search and search_katakana != normalized:
        patterns.append(search_katakana)
    
    # 「ザ」や「ヴ」などの後に中点を追加するパターン
    # 例：「白金ザスカイ」→「白金ザ・スカイ」
    import re
    # カタカナの「ザ」「ダ」「ヴ」などの後にカタカナが続く場合、中点を挿入
    with_nakaten = re.sub(r'([ザダヴ])([ァ-ヶー])', r'\1・\2', normalized)
    if with_nakaten != normalized and with_nakaten not in patterns:
        patterns.append(with_nakaten)
    
    # 全角英字版（データベースに全角で保存されている場合に対応）
    # unicodedata.normalize('NFKC')の逆変換
    fullwidth_upper = ''
    for char in search_katakana.upper():
        if 'A' <= char <= 'Z':
            # 半角英字を全角に変換（A-Z → Ａ-Ｚ）
            fullwidth_upper += chr(ord('Ａ') + ord(char) - ord('A'))
        elif '0' <= char <= '9':
            # 半角数字を全角に変換（0-9 → ０-９）
            fullwidth_upper += chr(ord('０') + ord(char) - ord('0'))
        elif char == ' ':
            # 半角スペースを全角スペースに変換
            fullwidth_upper += '　'
        else:
            fullwidth_upper += char
    
    if fullwidth_upper not in patterns:
        patterns.append(fullwidth_upper)
    
    # 中点（・）を除去
    no_nakaten = normalized.replace('・', '')
    if no_nakaten != normalized and no_nakaten not in patterns:
        patterns.append(no_nakaten)
    
    # スペースを除去
    no_space = normalized.replace(' ', '')
    if no_space != normalized and no_space not in patterns:
        patterns.append(no_space)
    
    # スペースを中点に置換（「白金ザ スカイ」→「白金ザ・スカイ」）
    space_to_nakaten = normalized.replace(' ', '・')
    if space_to_nakaten != normalized and space_to_nakaten not in patterns:
        patterns.append(space_to_nakaten)
    
    # 中点とスペースの両方を除去
    clean = normalized.replace('・', '').replace(' ', '')
    if clean not in patterns:
        patterns.append(clean)
    
    # ハイフンの正規化（全角ハイフン、ダッシュ、マイナスを統一）
    hyphen_normalized = re.sub(r'[ーｰ－—–−]', '-', normalized)
    if hyphen_normalized != normalized and hyphen_normalized not in patterns:
        patterns.append(hyphen_normalized)
    
    # ハイフンを除去
    no_hyphen = re.sub(r'[ーｰ－—–−-]', '', normalized)
    if no_hyphen != normalized and no_hyphen not in patterns:
        patterns.append(no_hyphen)
    
    # canonicalize形式（すべてのスペース・記号を削除、小文字化）も追加
    # これにより「白金ざ　すかい」→「白金ザスカイ」のようなcanonical形式でも検索可能
    from backend.app.scrapers.data_normalizer import canonicalize_building_name
    canonical = canonicalize_building_name(search)
    if canonical not in patterns:
        patterns.append(canonical)
    
    return patterns


def normalize_for_comparison(text: str) -> str:
    """
    比較用に文字列を正規化（より厳密な正規化）
    データベース内のテキストと検索文字列を比較する際に使用
    """
    if not text:
        return ""
    
    # 基本的な正規化
    text = normalize_search_text(text)
    
    # 記号を全て除去（英数字とひらがな・カタカナ・漢字のみ残す）
    text = re.sub(r'[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', text)
    
    return text


def get_search_key_for_comparison(text: str) -> str:
    """
    建物検索用のキーを生成
    building_name_normalizerの共通関数を使用
    """
    if not text:
        return ""
    
    # 共通の検索キー生成関数を使用
    return get_search_key_for_building(text)