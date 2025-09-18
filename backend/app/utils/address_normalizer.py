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
            r'\d+丁目\d+番地?\d*号?',       # N丁目N番地N号、N丁目N番N号、N丁目N番地、N丁目N番
            r'\d+丁目\d+-\d+',             # N丁目N-N
            r'\d+丁目\d+',                 # N丁目N
            r'\d+-\d+-\d+',                # N-N-N
            r'\d+-\d+',                    # N-N
            r'\d+丁目',                    # N丁目のみ
            r'\d+番地?\d*号?',             # N番地N号、N番N号、N番地、N番
            r'\d+',                        # 数字のみ
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
    
    def find_address_end_position(self, address: str) -> Optional[int]:
        """
        住所の有効な終端位置を検出する共通メソッド
        
        Args:
            address: 住所文字列
            
        Returns:
            住所の終端位置（インデックス）、見つからない場合はNone
        """
        # パターン1: ○丁目○番地○号 / ○丁目○番○号 / ○丁目○-○-○
        pattern1 = re.compile(
            r'[０-９0-9一二三四五六七八九十百千万〇○]+'  # 数字1
            r'丁目'  # 丁目
            r'[\s]*'  # 空白（あってもなくても）
            r'[０-９0-9一二三四五六七八九十百千万〇○]+'  # 数字2
            r'(?:番地?|[-－−])'  # 番地/番/ハイフン
            r'[\s]*'  # 空白
            r'(?:[０-９0-9一二三四五六七八九十百千万〇○]+)?'  # 数字3（オプション）
            r'(?:号|[-－−])?'  # 号/ハイフン（オプション）
        )
        match = pattern1.search(address)
        if match:
            return match.end()
        
        # パターン2: ○丁目○ （丁目の後に数字のみ）
        pattern2 = re.compile(
            r'[０-９0-9一二三四五六七八九十百千万〇○]+'  # 数字1
            r'丁目'  # 丁目
            r'[\s]*'  # 空白
            r'[０-９0-9一二三四五六七八九十百千万〇○]+'  # 数字2
            r'(?![番号丁])'  # 番・号・丁が続かない
        )
        match = pattern2.search(address)
        if match:
            return match.end()
        
        # パターン3: 単独の○丁目
        pattern3 = re.compile(
            r'[０-９0-9一二三四五六七八九十百千万〇○]+'  # 数字
            r'丁目'  # 丁目
            r'(?![\s]*[０-９0-9一二三四五六七八九十百千万〇○])'  # 後に数字が続かない
        )
        match = pattern3.search(address)
        if match:
            return match.end()
        
        # パターン4: ハイフン区切りの番地（丁目なし）
        # 例：「千駄ヶ谷4-20-3」「日本橋3-5-1」「三番町26-1」
        pattern4 = re.compile(
            r'(?<=[ぁ-んァ-ヶー一-龯])'  # 前に日本語文字
            r'[０-９0-9]+'  # 数字1
            r'[-－−]'  # ハイフン
            r'[０-９0-9]+'  # 数字2
            r'(?:[-－−][０-９0-9]+)?'  # 数字3（オプション）
        )
        match = pattern4.search(address)
        if match:
            return match.end()
        
        return None

    def remove_ui_elements(self, address: str) -> str:
        """
        住所文字列からUI要素（地図リンクなど）を削除
        
        住所として有効な終端パターンの後にUI関連のキーワードが来た場合、
        それ以降を削除する
        """
        if not address:
            return ""
        
        # HTMLタグを削除（念のため）
        address = re.sub(r'<[^>]+>', '', address)
        
        # 共通メソッドを使用して住所の終端位置を検出
        end_pos = self.find_address_end_position(address)
        if end_pos is not None:
            return address[:end_pos].strip()
        
        # パターンにマッチしない場合、区市町村までを抽出
        # 「周辺」を除外対象に追加
        basic_pattern = r'^(.*?(?:都|道|府|県).*?(?:区|市|町|村)[^地図\[【\(周辺]*)'
        match = re.search(basic_pattern, address)
        if match:
            # 末尾の不要な文字を削除
            result = match.group(1).rstrip('、。・周辺')
            # 「周辺」で終わる場合は削除
            if result.endswith('周辺'):
                result = result[:-2]
            return result.strip()
        
        # それでもマッチしない場合は、明らかに住所でない部分を削除
        # 「地図」「MAP」などのキーワード以降を削除
        unwanted_keywords = ['地図', 'MAP', 'Map', 'map', 'マップ', '周辺', '詳細', 'もっと見る', 'アクセス', '※', '＊', '[', '【', '(', '→']
        for keyword in unwanted_keywords:
            if keyword in address:
                address = address.split(keyword)[0]
        
        return address.strip()

    def contains_address_pattern(self, text: str) -> bool:
        """
        テキストに住所パターンが含まれているかを判定
        
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

    def normalize(self, address: str) -> str:
        """住所を正規化"""
        if not address:
            return ""
        
        # UI要素を削除
        address = self.remove_ui_elements(address)
        
        # Unicode正規化
        normalized = unicodedata.normalize('NFKC', address)
        
        # 余分なスペースを削除
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 句読点を削除
        normalized = re.sub(r'[、。，．]', '', normalized)
        
        # カッコ内の情報を削除（建物名など）
        normalized = re.sub(r'[（(][^）)]*[）)]', '', normalized).strip()
        
        # 番地の数字を正規化する関数
        def normalize_number(num_str):
            """数字文字列を半角数字に変換"""
            # 漢数字の「十」「百」「千」を含む場合
            if any(char in num_str for char in ['十', '百', '千', '万']):
                return self.normalize_numbers(num_str)
            else:
                # 全角数字・簡単な漢数字を変換
                result = num_str
                for old, new in self.number_map.items():
                    if old not in ['十', '百', '千', '万']:
                        result = result.replace(old, new)
                return result
        
        # 住所番地の厳密なパターン
        # パターン1: ○丁目○番地○号 / ○丁目○番○号 / ○丁目○-○-○
        pattern1 = re.compile(
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)'  # 数字1
            r'(丁目)'  # 丁目
            r'[\s]*'  # 空白（あってもなくても）
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)'  # 数字2
            r'(番地?|[-－−])'  # 番地/番/ハイフン
            r'[\s]*'  # 空白
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)?'  # 数字3（オプション）
            r'(号|[-－−])?'  # 号/ハイフン（オプション）
        )
        
        def replace_pattern1(match):
            """○丁目○番○号パターンを正規化"""
            groups = match.groups()
            result = normalize_number(groups[0])  # 丁目の数字
            result += '-'
            result += normalize_number(groups[2])  # 番/番地の数字
            if groups[4]:  # 号の数字があれば
                result += '-' + normalize_number(groups[4])
            return result
        
        # パターン2: ○丁目○ （丁目の後に数字のみ）
        pattern2 = re.compile(
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)'  # 数字1
            r'(丁目)'  # 丁目
            r'[\s]*'  # 空白
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)'  # 数字2
            r'(?![番号丁])'  # 番・号・丁が続かない
        )
        
        def replace_pattern2(match):
            """○丁目○パターンを正規化"""
            groups = match.groups()
            result = normalize_number(groups[0])  # 丁目の数字
            result += '-'
            result += normalize_number(groups[2])  # 番地の数字
            return result
        
        # パターン3: 単独の○丁目
        pattern3 = re.compile(
            r'([０-９0-9一二三四五六七八九十百千万〇○]+)'  # 数字
            r'(丁目)'  # 丁目
            r'(?![\s]*[０-９0-9一二三四五六七八九十百千万〇○])'  # 後に数字が続かない
        )
        
        def replace_pattern3(match):
            """単独の○丁目を正規化"""
            return normalize_number(match.group(1))
        
        # パターン4: ハイフン区切りの番地（丁目なし）
        # 例：「千駄ヶ谷4-20-3」「日本橋3-5-1」
        # ただし、前に地名（漢字・ひらがな・カタカナ）があることが条件
        pattern4 = re.compile(
            r'(?<=[ぁ-んァ-ヶー一-龯])'  # 前に日本語文字
            r'([０-９0-9]+)'  # 数字1
            r'[-－−]'  # ハイフン
            r'([０-９0-9]+)'  # 数字2
            r'(?:[-－−]([０-９0-9]+))?'  # 数字3（オプション）
        )
        
        def replace_pattern4(match):
            """ハイフン区切り番地を正規化"""
            groups = match.groups()
            result = groups[0].translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            result += '-'
            result += groups[1].translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            if groups[2]:
                result += '-' + groups[2].translate(str.maketrans('０１２３４５６７８９', '0123456789'))
            return result
        
        # パターンを順番に適用（より具体的なパターンから）
        normalized = pattern1.sub(replace_pattern1, normalized)
        normalized = pattern2.sub(replace_pattern2, normalized)
        normalized = pattern3.sub(replace_pattern3, normalized)
        normalized = pattern4.sub(replace_pattern4, normalized)
        
        # 全角数字の単純な変換（番地以外の部分）
        # 町名の後の単独の数字（番地の可能性）
        normalized = re.sub(
            r'(?<=[町村通り条])([０-９]+)(?=[-－−]|$)',
            lambda m: m.group(1).translate(str.maketrans('０１２３４５６７８９', '0123456789')),
            normalized
        )
        
        # ハイフンの統一
        normalized = re.sub(r'[－−]', '-', normalized)
        
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
    
    def get_address_detail_level(self, address: str) -> int:
        """
        住所の詳細度レベルを取得する
        
        Args:
            address: 住所文字列
            
        Returns:
            詳細度レベル（0-4）
            0: 都道府県のみ
            1: 市区町村まで
            2: 町名まで
            3: 丁目まで
            4: 番地・号まで
        """
        if not address:
            return 0
        
        components = self.extract_components(address)
        
        # 番地・号がある場合
        if components.get('block'):
            block = components['block']
            # 「N丁目」のみの場合は丁目レベル
            if re.match(r'^\d+丁目$', block):
                return 3
            # 「N丁目N-N」「N丁目N番地N号」などは番地・号レベル
            elif '丁目' in block and (re.search(r'丁目\d+', block) or '番地' in block or '号' in block):
                return 4
            # ハイフンが2つ以上ある（号まである）
            elif block.count('-') >= 2:
                return 4
            # ハイフンが1つある（番地まで）
            elif '-' in block:
                return 4
            # 3桁以上の数字（番地の可能性が高い）
            elif block.isdigit() and len(block) >= 3:
                return 4
            # 1桁または2桁の数字（元の住所で「丁目」があったか判断が必要）
            elif block.isdigit():
                # 町名の後に1桁の数字だけの場合は丁目の可能性が高い
                if len(block) == 1:
                    return 3  # 丁目
                elif len(block) == 2:
                    # 2桁は微妙（丁目または番地）
                    # 前後の文脈で判断するのが難しいので、丁目と仮定
                    return 3
                else:
                    return 4
            else:
                # その他（通常ありえない）
                return 3
        
        # 町名まで
        if components.get('area'):
            # 「○丁目」パターンのチェック
            if re.search(r'\d+丁目', components['area']):
                return 3
            return 2
        
        # 市区町村まで
        if components.get('city') or components.get('ward'):
            return 1
        
        # 都道府県のみ
        if components.get('prefecture'):
            return 0
        
        return 0
    
    def get_address_prefix(self, address: str, level: int = 2) -> str:
        """
        指定したレベルまでの住所前方部分を取得する
        
        Args:
            address: 住所文字列
            level: 取得するレベル（0-4）
            
        Returns:
            指定レベルまでの住所文字列
        """
        components = self.extract_components(address)
        
        parts = []
        
        # レベル0: 都道府県のみ
        if level >= 0 and components.get('prefecture'):
            parts.append(components['prefecture'])
        
        # レベル1: 市区町村まで
        if level >= 1:
            if components.get('city'):
                parts.append(components['city'])
            if components.get('ward'):
                parts.append(components['ward'])
        
        # レベル2: 町名まで
        if level >= 2 and components.get('area'):
            parts.append(components['area'])
        
        # レベル3以上: 丁目・番地
        if level >= 3 and components.get('block'):
            block = components['block']
            if level == 3:
                # 丁目レベルまで
                # 「1-8」「1-9-8」のような場合、最初の数字部分（丁目）だけ取得
                if '-' in block:
                    # ハイフン区切りの最初の部分が丁目
                    first_part = block.split('-')[0]
                    parts.append(first_part)
                elif re.match(r'^\d+丁目', block):
                    # 「N丁目」部分だけ抽出
                    match = re.match(r'^(\d+丁目)', block)
                    if match:
                        parts.append(match.group(1))
                elif block.isdigit() and len(block) <= 2:
                    # 数字のみで2桁以下は丁目として扱う
                    parts.append(block)
                # それ以外（番地など）は含めない
            else:
                # レベル4: 番地・号まですべて含める
                # 「1丁目8番地」→「1丁目8番地」（そのまま）
                # 「1丁目9番地8号」→「1丁目9番地8号」（そのまま）
                parts.append(block)
        
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