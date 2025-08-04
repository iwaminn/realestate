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
            # 丁目-番地-号パターン
            (r'(\d+)\s*丁目\s*(\d+)\s*番地?\s*(\d+)\s*号?', r'\1-\2-\3'),
            (r'(\d+)\s*丁目\s*(\d+)\s*番地?', r'\1-\2'),
            (r'(\d+)\s*丁目', r'\1'),
            
            # 番地・号パターン（丁目なし）
            (r'(\d+)\s*番地?\s*(\d+)\s*号?', r'\1-\2'),
            (r'(\d+)\s*番地?', r'\1'),
            
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
        
        # 単純な置換
        for old, new in self.number_map.items():
            normalized = normalized.replace(old, new)
        
        # 「十」を含む漢数字の処理
        # 例: 「二十三」→「23」、「十五」→「15」
        def convert_japanese_number(match):
            num_str = match.group(0)
            total = 0
            
            # 十の位
            if '十' in num_str:
                parts = num_str.split('十')
                if parts[0] and parts[0] in self.number_map:
                    total += int(self.number_map[parts[0]]) * 10
                elif parts[0] == '':
                    total += 10
                else:
                    return num_str  # 変換できない場合は元の文字列を返す
                
                if len(parts) > 1 and parts[1] and parts[1] in self.number_map:
                    total += int(self.number_map[parts[1]])
            else:
                # 十を含まない場合はそのまま
                return num_str
            
            return str(total)
        
        # 漢数字のパターンをマッチして変換
        normalized = re.sub(r'[一二三四五六七八九]?十[一二三四五六七八九]?', convert_japanese_number, normalized)
        
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
        
        # 番地情報を抽出
        block_match = re.search(r'(\d+(?:-\d+)*)', remaining)
        if block_match:
            components['block'] = block_match.group(1)
            # 番地より前の部分を地域名として保存
            components['area'] = remaining[:block_match.start()].strip()
            # 番地より後の部分を建物名として保存
            components['building'] = remaining[block_match.end():].strip()
        else:
            # 番地がない場合は全体を地域名として保存
            components['area'] = remaining.strip()
        
        return components
    
    def normalize(self, address: str) -> str:
        """住所を正規化"""
        if not address:
            return ""
        
        # Unicode正規化
        normalized = unicodedata.normalize('NFKC', address)
        
        # 数字を正規化
        normalized = self.normalize_numbers(normalized)
        
        # 余分なスペースを削除
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 丁目・番地・号を正規化
        normalized = self.normalize_block_number(normalized)
        
        # 句読点を削除
        normalized = re.sub(r'[、。，．]', '', normalized)
        
        # カッコ内の情報を削除（建物名など）
        normalized = re.sub(r'[（(][^）)]*[）)]', '', normalized).strip()
        
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