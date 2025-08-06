"""検索文字列正規化ユーティリティ"""

import re
import unicodedata


def normalize_search_text(text: str) -> str:
    """
    検索文字列を正規化する
    - 全角英数字を半角に変換
    - カタカナを全角に統一
    - 大文字を小文字に変換
    - 不要な空白を削除
    """
    if not text:
        return ""
    
    # NFKCで正規化（全角英数字を半角に、半角カナを全角に）
    text = unicodedata.normalize('NFKC', text)
    
    # 英字を小文字に統一
    text = text.lower()
    
    # 連続する空白を単一の空白に
    text = re.sub(r'\s+', ' ', text)
    
    # 前後の空白を削除
    text = text.strip()
    
    return text


def create_search_patterns(search: str) -> list[str]:
    """
    検索パターンのバリエーションを生成
    """
    patterns = []
    
    # 正規化したパターン（半角小文字）
    normalized = normalize_search_text(search)
    patterns.append(normalized)
    
    # 元の検索文字列（正規化前）
    if search != normalized:
        patterns.append(search)
    
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
    for char in search.upper():
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
    hyphen_normalized = re.sub(r'[ー－−–—‐]', '-', normalized)
    if hyphen_normalized != normalized and hyphen_normalized not in patterns:
        patterns.append(hyphen_normalized)
    
    # ハイフンを除去
    no_hyphen = re.sub(r'[ー－−–—‐-]', '', normalized)
    if no_hyphen != normalized and no_hyphen not in patterns:
        patterns.append(no_hyphen)
    
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