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
        english_to_japanese = {
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
        
        # 1. 全角英数字を半角に変換
        name = jaconv.z2h(name, kana=False, ascii=True, digit=True)
        
        # 2. カタカナの正規化（半角カナを全角に）
        name = jaconv.h2z(name, kana=True, ascii=False, digit=False)
        
        # 2.5. 英字の大文字統一（建物名では通常大文字が使われる）
        # ただし、棟表記（E棟、W棟など）は後で処理するので、ここでは建物名部分のみ
        # 例: "n's" → "N'S", "N´s" → "N'S"
        name = self.normalize_english_case(name)
        
        # 3. スペースの正規化
        name = re.sub(r'[\s　]+', ' ', name).strip()
        
        # 4. 特殊文字の正規化
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
        
        # 5. 不要なパターンを削除
        for pattern in self.REMOVE_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
        # 6. 建物タイプの正規化
        for variant, standard in self.BUILDING_TYPE_MAP.items():
            if variant in name:
                name = name.replace(variant, standard)
        
        # 7. 棟表記の正規化
        name = self.normalize_building_unit(name)
        
        # 8. 中黒（・）の有無を統一（重要な建物名の区切りでない場合は削除）
        # 例: "白金ザ・スカイ" → "白金ザスカイ"
        # ただし、明確に別の単語を区切る場合は保持
        # カタカナ同士の間の中黒は削除
        name = re.sub(r'([ァ-ヴー])・([ァ-ヴー])', r'\1\2', name)
        # 「ザ・」「ラ・」「レ・」などの定冠詞後の中黒は削除
        name = re.sub(r'(ザ|ラ|レ|ル|ロ)・', r'\1', name)
        
        # 9. よく使われる英語建物名をカタカナに変換
        # 大文字小文字の違いを吸収するため
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
            name = name.replace(eng, katakana)
        
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
        """2つの建物名の類似度を計算（構造化アプローチ）"""
        # 正規化
        norm1 = self.normalize(name1)
        norm2 = self.normalize(name2)
        
        # 完全一致の場合
        if norm1 == norm2:
            return 1.0
        
        # 構成要素を抽出
        comp1 = self.extract_building_components(norm1)
        comp2 = self.extract_building_components(norm2)
        
        # 地域名が異なる場合は低い類似度
        if comp1['area'] and comp2['area'] and comp1['area'] != comp2['area']:
            return SequenceMatcher(None, norm1, norm2).ratio() * 0.5
        
        # メイン名称の類似度（最重要）
        main_sim = SequenceMatcher(None, comp1['main'], comp2['main']).ratio()
        
        # 建物タイプの一致度
        type_sim = 1.0 if comp1['type'] == comp2['type'] else 0.0
        
        # 棟情報の扱い
        unit_penalty = 0
        if comp1['unit'] and comp2['unit']:
            if comp1['unit'] != comp2['unit']:
                # 棟が明示的に異なる場合は別建物として扱う
                return 0.3  # 低い類似度を返す
        elif comp1['unit'] or comp2['unit']:
            # 片方だけ棟情報がある場合は、同一建物の可能性もあるので軽いペナルティ
            unit_penalty = 0.2
        
        # 重み付け計算
        weighted_sim = (
            main_sim * 0.7 +      # メイン名称が最重要
            type_sim * 0.2 +      # 建物タイプ
            0.1                   # ベースボーナス
        ) - unit_penalty
        
        # 文字列全体の類似度も考慮（安全網として）
        overall_sim = SequenceMatcher(None, norm1, norm2).ratio()
        
        # より保守的な値を採用
        return min(max(weighted_sim, overall_sim * 0.8), 1.0)
    
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