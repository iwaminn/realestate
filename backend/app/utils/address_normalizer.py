"""
住所正規化ユーティリティ

住所の表記ゆれを吸収し、同一住所を正確に判定するためのツール
"""

import re
from typing import Dict, Optional, Tuple, List
import unicodedata


class AddressNormalizer:
    """住所正規化クラス"""
    
    def __init__(self):
        # 数字の正規化辞書
        self.number_map = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
            '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
            '〇': '0', '○': '0'
        }
        
        # 丁目・番地・号の表記パターン
        self.block_patterns = [
            # 丁目-番地-号パターン（最も詳細なパターンから処理）
            (r'(\d+)\s*丁目\s*(\d+)\s*番地?\s*(\d+)\s*号?', r'\1-\2-\3'),
            (r'(\d+)\s*丁目\s*(\d+)\s*番地?', r'\1-\2'),
            (r'(\d+)\s*丁目\s*(\d+)\s*[-－−]\s*(\d+)', r'\1-\2-\3'),  # 7丁目1-19のパターン
            (r'(\d+)\s*丁目\s*(\d+)\s*号', r'\1-\2'),  # 7丁目119号のパターン
            (r'(\d+)\s*丁目\s*(\d+)(?![番号])', r'\1-\2'),  # 7丁目119のパターン（番・号が続かない）
            (r'(\d+)\s*丁目(?!\d)', r'\1'),  # 丁目のみ（後ろに数字が続かない場合）
            
            # 番地・号パターン（丁目なし）
            (r'(\d+)\s*番地?\s*(\d+)\s*号?', r'\1-\2'),
            (r'(\d+)\s*番地?(?!\d)', r'\1'),  # 番地のみ（後ろに数字が続かない場合）
            
            # ハイフン区切りパターン（そのまま）
            (r'(\d+)\s*[-－−]\s*(\d+)\s*[-－−]\s*(\d+)', r'\1-\2-\3'),
            (r'(\d+)\s*[-－−]\s*(\d+)', r'\1-\2'),
        ]
        
        # 住所の構成要素パターン
        self.address_components = {
            'prefecture': r'(東京都|北海道|(?:京都|大阪)府|(?:神奈川|埼玉|千葉|愛知|兵庫|福岡)県|(?:\S+?)県)',
            'city': r'(\S+?[市])',
            'ward': r'(\S+?[区])',
            'town': r'(\S+?[町村])',
            'area': r'([^0-9０-９一二三四五六七八九十〇○]+)',  # 地域名（数字以外）
        }
    
    def normalize_numbers(self, text: str) -> str:
        """全角数字・漢数字を半角数字に変換"""
        normalized = text
        
        # 複雑な漢数字を処理する関数
        def convert_complex_japanese_number(text):
            """千・百・十を含む漢数字を変換"""
            # 基本的な数値マップ
            basic_nums = {
                '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '〇': 0, '○': 0
            }
            
            # 位の値
            positions = {'千': 1000, '百': 100, '十': 10}
            
            # 数値に変換
            result = 0
            current_num = 0
            
            i = 0
            while i < len(text):
                char = text[i]
                
                if char in basic_nums:
                    current_num = basic_nums[char]
                elif char in positions:
                    if current_num == 0:
                        # 「百」「千」の前に数字がない場合は1とする
                        current_num = 1
                    result += current_num * positions[char]
                    current_num = 0
                else:
                    # 変換できない文字が含まれる場合は元の文字列を返す
                    return text
                
                i += 1
            
            # 最後の数字を追加
            result += current_num
            
            return str(result)
        
        # 千・百・十を含む漢数字のパターン
        # 例：「二千三百四十五」「百十九」「千二百」
        pattern = r'[一二三四五六七八九千百十〇○]+'
        
        def replace_func(match):
            matched_text = match.group(0)
            # 千・百・十のいずれかを含む場合のみ変換
            if any(pos in matched_text for pos in ['千', '百', '十']):
                return convert_complex_japanese_number(matched_text)
            else:
                # 単純な数字の場合はそのまま返す
                return matched_text
        
        normalized = re.sub(pattern, replace_func, normalized)
        
        # その後、残った単純な数字を置換
        for old, new in self.number_map.items():
            if old not in ['千', '百', '十']:  # 千・百・十は上で処理済み
                normalized = normalized.replace(old, new)
        
        return normalized
    
    def normalize_block_number(self, text: str) -> str:
        """丁目・番地・号の表記を統一"""
        normalized = text
        
        # 各パターンを適用
        for pattern, replacement in self.block_patterns:
            normalized = re.sub(pattern, replacement, normalized)
        
        # 余分なスペースを削除
        normalized = re.sub(r'\s+', '', normalized)
        
        # ハイフンの統一
        normalized = re.sub(r'[－−]', '-', normalized)
        
        return normalized
    
    def extract_components(self, address: str) -> Dict[str, str]:
        """住所を構成要素に分解"""
        components = {
            'prefecture': '',
            'city': '',
            'ward': '',
            'town': '',
            'area': '',
            'block': '',
            'building': ''
        }
        
        remaining = address
        
        # 都道府県
        pref_match = re.search(self.address_components['prefecture'], remaining)
        if pref_match:
            components['prefecture'] = pref_match.group(1)
            remaining = remaining[pref_match.end():]
        
        # 市
        city_match = re.search(self.address_components['city'], remaining)
        if city_match:
            components['city'] = city_match.group(1)
            remaining = remaining[city_match.end():]
        
        # 区
        ward_match = re.search(self.address_components['ward'], remaining)
        if ward_match:
            components['ward'] = ward_match.group(1)
            remaining = remaining[ward_match.end():]
        
        # 町村
        town_match = re.search(self.address_components['town'], remaining)
        if town_match:
            components['town'] = town_match.group(1)
            remaining = remaining[town_match.end():]
        
        # 番地情報を抽出（より正確なパターン）
        # 丁目を含むパターンを優先
        block_patterns = [
            r'(\d+)丁目(\d+)(?:-(\d+))?',  # N丁目N-N または N丁目N
            r'(\d+)-(\d+)-(\d+)',           # N-N-N
            r'(\d+)-(\d+)',                 # N-N
            r'(\d+)丁目',                   # N丁目のみ
            r'(\d+)',                       # 数字のみ
        ]
        
        matched = False
        for pattern in block_patterns:
            match = re.search(pattern, remaining)
            if match:
                # マッチした部分全体を番地として保存
                components['block'] = match.group(0)
                # 番地より前の部分を地域名として保存
                components['area'] = remaining[:match.start()].strip()
                # 番地より後の部分を建物名として保存
                components['building'] = remaining[match.end():].strip()
                matched = True
                break
        
        if not matched:
            # 番地がない場合は全体を地域名として保存
            components['area'] = remaining.strip()
        
        return components
    
    def normalize(self, address: str) -> str:
        """住所を正規化"""
        if not address:
            return ""
        
        # Unicode正規化
        normalized = unicodedata.normalize('NFKC', address)
        
        # 余分なスペースを削除
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 句読点を削除
        normalized = re.sub(r'[、。，．]', '', normalized)
        
        # カッコ内の情報を削除（建物名など）
        normalized = re.sub(r'[（(][^）)]*[）)]', '', normalized).strip()
        
        # 丁目・番地・号の部分のみ数字を正規化
        # まず、丁目・番地・号のパターンを特定
        def normalize_chome_numbers(match):
            """丁目・番地・号の数字のみを正規化"""
            text = match.group(0)
            num_part = match.group(1)
            suffix = match.group(2) if len(match.groups()) > 1 else ''
            
            # 漢数字の「十」を含む場合の特別処理
            if '十' in num_part:
                num_part = self.normalize_numbers(num_part)
            else:
                # 単純な数字変換
                for old, new in self.number_map.items():
                    if old != '十':  # 十は特別処理
                        num_part = num_part.replace(old, new)
            
            return num_part + suffix
        
        # 丁目・番地・号のパターンにマッチする部分のみ数字を変換
        patterns = [
            r'([０-９0-9一二三四五六七八九千百十〇○]+)(丁目)',
            r'([０-９0-9一二三四五六七八九千百十〇○]+)(番地?)',
            r'([０-９0-9一二三四五六七八九千百十〇○]+)(号)',
        ]
        
        for pattern in patterns:
            normalized = re.sub(pattern, normalize_chome_numbers, normalized)
        
        # 丁目・番地・号を正規化（統一形式に変換）
        normalized = self.normalize_block_number(normalized)
        
        return normalized
    
    def normalize_for_comparison(self, address: str) -> str:
        """比較用に住所を正規化（建物名を除去）"""
        normalized = self.normalize(address)
        
        # 構成要素に分解
        components = self.extract_components(normalized)
        
        # 建物名を除いて再構成
        parts = []
        for key in ['prefecture', 'city', 'ward', 'town', 'area', 'block']:
            if components[key]:
                parts.append(components[key])
        
        return ''.join(parts)
    
    def is_same_block(self, addr1: str, addr2: str) -> bool:
        """同じ番地かどうかを判定"""
        norm1 = self.normalize_for_comparison(addr1)
        norm2 = self.normalize_for_comparison(addr2)
        
        return norm1 == norm2
    
    def extract_block_numbers(self, address: str) -> List[int]:
        """住所から番地番号を抽出"""
        normalized = self.normalize(address)
        
        # 番地部分を抽出
        block_match = re.search(r'(\d+(?:-\d+)*)', normalized)
        if block_match:
            block_str = block_match.group(1)
            # ハイフンで分割して数値のリストに変換
            return [int(num) for num in block_str.split('-')]
        
        return []
    
    def calculate_similarity(self, addr1: str, addr2: str) -> float:
        """住所の類似度を計算（0.0〜1.0）"""
        comp1 = self.extract_components(self.normalize(addr1))
        comp2 = self.extract_components(self.normalize(addr2))
        
        # 各要素の重み
        weights = {
            'prefecture': 0.1,
            'city': 0.15,
            'ward': 0.15,
            'town': 0.1,
            'area': 0.2,
            'block': 0.3
        }
        
        total_score = 0.0
        
        for key, weight in weights.items():
            if comp1[key] == comp2[key] and comp1[key]:
                total_score += weight
            elif key == 'block' and comp1[key] and comp2[key]:
                # 番地の部分一致を考慮
                nums1 = self.extract_block_numbers(comp1[key])
                nums2 = self.extract_block_numbers(comp2[key])
                
                if nums1 and nums2:
                    # 最初の番号（丁目）が一致すれば部分点
                    if nums1[0] == nums2[0]:
                        total_score += weight * 0.5
                        
                        # 2番目の番号（番地）も一致すれば追加点
                        if len(nums1) > 1 and len(nums2) > 1 and nums1[1] == nums2[1]:
                            total_score += weight * 0.3
        
        return total_score
    
    def is_same_chome(self, addr1: str, addr2: str) -> bool:
        """同じ丁目かどうかを判定"""
        nums1 = self.extract_block_numbers(addr1)
        nums2 = self.extract_block_numbers(addr2)
        
        if nums1 and nums2:
            return nums1[0] == nums2[0]
        
        return False
    
    def get_canonical_address(self, address: str) -> str:
        """正規化された住所を取得（API用）"""
        normalized = self.normalize_for_comparison(address)
        components = self.extract_components(normalized)
        
        # より読みやすい形式で再構成
        parts = []
        
        # 都道府県〜町村まで
        for key in ['prefecture', 'city', 'ward', 'town']:
            if components[key]:
                parts.append(components[key])
        
        # 地域名
        if components['area']:
            parts.append(components['area'])
        
        # 番地（ハイフン区切り）
        if components['block']:
            parts.append(components['block'])
        
        return ''.join(parts)


# 使用例
if __name__ == "__main__":
    normalizer = AddressNormalizer()
    
    # テストケース
    test_cases = [
        ("東京都港区芝浦１丁目３番地５号", "東京都港区芝浦1-3-5"),
        ("東京都港区芝浦一丁目三番地五号", "東京都港区芝浦1-3-5"),
        ("東京都港区芝浦１丁目３番５号", "東京都港区芝浦1-3-5"),
        ("東京都港区芝浦１－３－５", "東京都港区芝浦1-3-5"),
        ("東京都港区芝浦2丁目3番地", "東京都港区芝浦3丁目2番地"),  # 異なる住所
    ]
    
    print("住所正規化テスト:")
    for addr1, addr2 in test_cases:
        norm1 = normalizer.normalize_for_comparison(addr1)
        norm2 = normalizer.normalize_for_comparison(addr2)
        is_same = normalizer.is_same_block(addr1, addr2)
        similarity = normalizer.calculate_similarity(addr1, addr2)
        
        print(f"\n'{addr1}'")
        print(f"  正規化: {norm1}")
        print(f"'{addr2}'")
        print(f"  正規化: {norm2}")
        print(f"  同一判定: {is_same}")
        print(f"  類似度: {similarity:.2f}")