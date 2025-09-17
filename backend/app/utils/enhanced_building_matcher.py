"""
高度な建物マッチングユーティリティ（統合版）

既存のマッチングユーティリティを統合し、
より高精度な建物重複検出を実現します。
"""

import re
from typing import Dict, Optional, Tuple, List, Any
from difflib import SequenceMatcher
import logging

from .address_normalizer import AddressNormalizer

logger = logging.getLogger(__name__)


class BuildingNameNormalizer:
    """建物名を標準化するクラス（類似性判定用）"""

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
        english_to_japanese = {
            'EAST棟': 'E棟', 'WEST棟': 'W棟', 'NORTH棟': 'N棟', 'SOUTH棟': 'S棟',
            'East棟': 'E棟', 'West棟': 'W棟', 'North棟': 'N棟', 'South棟': 'S棟',
            'ＥＡＳＴ棟': 'E棟', 'ＷＥＳＴ棟': 'W棟', 'ＮＯＲＴＨ棟': 'N棟', 'ＳＯＵＴＨ棟': 'S棟',
            'EAST': 'E棟', 'WEST': 'W棟', 'NORTH': 'N棟', 'SOUTH': 'S棟',
            'East': 'E棟', 'West': 'W棟', 'North': 'N棟', 'South': 'S棟',
        }

        for eng, jpn in english_to_japanese.items():
            name = name.replace(eng, jpn)

        # 棟の表記パターン（棟の意味は保持）
        unit_patterns = {
            # アルファベット棟（全角→半角）
            r'[Ｅ]棟': 'E棟', r'[Ｗ]棟': 'W棟', r'[Ｎ]棟': 'N棟', r'[Ｓ]棟': 'S棟',
            r'[Ａ]棟': 'A棟', r'[Ｂ]棟': 'B棟', r'[Ｃ]棟': 'C棟', r'[Ｄ]棟': 'D棟',
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
        """建物名を類似性判定用に正規化"""
        if not name:
            return ""

        # まず部屋番号を抽出・除去
        name, _ = self.extract_room_number(name)

        # 基本的な正規化処理は normalize_building_name() を使用
        from ..utils.building_name_normalizer import normalize_building_name
        name = normalize_building_name(name)

        # === 以下、類似性判定用の追加処理 ===

        # 1. 漢数字を算用数字に変換（類似性判定のため）
        from ..utils.building_name_normalizer import convert_japanese_numbers_to_arabic
        name = convert_japanese_numbers_to_arabic(name)

        # 2. ローマ数字を算用数字に変換
        from ..utils.building_name_normalizer import convert_roman_numerals_to_arabic
        name = convert_roman_numerals_to_arabic(name)

        # 3. 中点（・）の削除（類似性判定では「白金ザ・スカイ」と「白金ザスカイ」を同一と判定）
        # カタカナ同士の間の中点は削除
        name = re.sub(r'([ァ-ヴー])・([ァ-ヴー])', r'\1\2', name)
        # 「ザ・」「ラ・」「レ・」などの定冠詞後の中点は削除
        name = re.sub(r'(ザ|ラ|レ|ル|ロ)・', r'\1', name)

        # 4. 棟表記の正規化
        name = self.normalize_building_unit(name)

        # 5. カタカナ単語間のスペースを削除（類似性判定用）
        name = re.sub(r'([ァ-ヴー]+)\s+([ァ-ヴー]+)', r'\1\2', name)

        # 6. 特定のカタカナビル名パターンでのスペース削除
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


class EnhancedBuildingMatcher:
    """統合型建物マッチャークラス"""
    
    def __init__(self, aliases_cache=None):
        self.address_normalizer = AddressNormalizer()
        self.building_normalizer = BuildingNameNormalizer()
        
        # デバッグ情報を保存
        self.last_debug_info = {}
        
        # 掲載履歴のキャッシュ（建物ID -> エイリアスリスト）
        self.aliases_cache = aliases_cache or {}

    def _get_building_aliases(self, building: Any, session) -> List[str]:
        """建物の掲載履歴からエイリアス（建物名のバリエーション）を取得
        
        Args:
            building: 建物オブジェクト
            session: データベースセッション
            
        Returns:
            エイリアス建物名のリスト
        """
        # キャッシュから取得を試みる
        if building.id in self.aliases_cache:
            return self.aliases_cache[building.id]
        
        # sessionがNoneの場合は空リストを返す
        if session is None:
            return []
            
        try:
            from ..models import BuildingListingName
            
            # この建物の掲載名をすべて取得
            listing_names = session.query(BuildingListingName).filter(
                BuildingListingName.building_id == building.id
            ).all()
            
            aliases = []
            seen_canonical = set()  # 重複排除用
            
            for listing in listing_names:
                # 正規化された名前（canonical_name）で重複チェック
                if listing.canonical_name not in seen_canonical:
                    seen_canonical.add(listing.canonical_name)
                    # 実際の掲載名（listing_name）をエイリアスとして追加
                    if listing.listing_name and listing.listing_name not in aliases:
                        aliases.append(listing.listing_name)
            
            # キャッシュに保存
            self.aliases_cache[building.id] = aliases
            return aliases
        except Exception as e:
            logger.warning(f"掲載履歴の取得中にエラー: {e}")
            return []

    def calculate_comprehensive_similarity(self, building1: Any, building2: Any, session = None) -> float:
        """総合的な類似度を計算
        
        Args:
            building1: 建物1のオブジェクト（Building model）
            building2: 建物2のオブジェクト（Building model）
            session: データベースセッション（掲載履歴取得用、オプション）
            
        Returns:
            類似度スコア（0.0-1.0）
        """
        # 早期リターン: 明らかに異なる建物の場合
        # 築年が3年以上異なる場合は即座に低スコアを返す
        if building1.built_year and building2.built_year:
            year_diff = abs(building1.built_year - building2.built_year)
            if year_diff > 2:
                return 0.3  # 類似度閾値（0.7）以下を返す
        
        # 総階数の判定を緩和：同じ建物群では棟により階数が大きく異なることがある
        # 階数差だけでは早期リターンしない（築年と建物名で判定）
        
        # デバッグ情報をリセット
        self.last_debug_info = {
            'building1_id': building1.id,
            'building2_id': building2.id,
            'building1_name': building1.normalized_name,
            'building2_name': building2.normalized_name,
            'scores': {}
        }
        
        # 1. 住所の類似度（正規化後）
        addr_score = self._calculate_address_similarity(
            building1.address, building2.address
        )
        self.last_debug_info['scores']['address'] = addr_score
        
        # 2. 建物名の類似度（複数の手法を組み合わせ、掲載履歴も考慮）
        name_score = self._calculate_name_similarity(
            building1.normalized_name, building2.normalized_name,
            building1, building2, session
        )
        self.last_debug_info['scores']['name'] = name_score
        
        # 3. 属性の一致度（築年月、総階数）
        attr_score = self._calculate_attribute_similarity(
            building1, building2
        )
        self.last_debug_info['scores']['attributes'] = attr_score
        
        # 4. 最終スコア計算
        final_score = self._calculate_final_score(
            addr_score, name_score, attr_score
        )
        self.last_debug_info['final_score'] = final_score
        
        return final_score
    
    def _calculate_address_similarity(self, addr1: Optional[str], addr2: Optional[str]) -> float:
        """住所の類似度を計算（正規化後）"""
        if not addr1 or not addr2:
            return 0.0
        
        # 住所を正規化
        norm_addr1 = self.address_normalizer.normalize(addr1)
        norm_addr2 = self.address_normalizer.normalize(addr2)
        
        # デバッグ情報
        self.last_debug_info['normalized_addresses'] = {
            'addr1': norm_addr1,
            'addr2': norm_addr2
        }
        
        # 完全一致の場合
        if norm_addr1 == norm_addr2:
            return 1.0
        
        # 構成要素に分解
        comp1 = self.address_normalizer.extract_components(norm_addr1)
        comp2 = self.address_normalizer.extract_components(norm_addr2)
        
        # デバッグ情報
        self.last_debug_info['address_components'] = {
            'comp1': comp1,
            'comp2': comp2
        }
        
        # 番地レベルまで比較（部分一致を考慮）
        if comp1['block'] and comp2['block']:
            # 番地を数値配列に分解（例：「1-9-18」→[1, 9, 18]）
            nums1 = self.address_normalizer.extract_block_numbers(comp1['block'])
            nums2 = self.address_normalizer.extract_block_numbers(comp2['block'])
            
            if nums1 and nums2:
                # 短い方の長さで比較（部分一致の判定）
                min_len = min(len(nums1), len(nums2))
                
                # 最初の要素（丁目）が異なる場合は明確に別住所
                if nums1[0] != nums2[0]:
                    # 町名までが一致している場合のみ部分点
                    if (comp1['prefecture'] == comp2['prefecture'] and
                        comp1['city'] == comp2['city'] and
                        comp1['area'] == comp2['area']):
                        return 0.3  # 同じ地域だが丁目が違う（別住所の可能性高）
                    else:
                        return 0.1  # 完全に異なる
                
                # 丁目が一致する場合、共通部分をチェック
                matches = sum(1 for i in range(min_len) if nums1[i] == nums2[i])
                
                if matches == min_len:
                    # 片方が他方の部分集合（例：「1-9-18」と「1-9」または「1」）
                    if len(nums1) == len(nums2):
                        return 0.95  # 完全一致
                    else:
                        # 部分一致（片方が省略形の可能性）
                        if min_len == 1:
                            return 0.85  # 丁目のみ一致
                        elif min_len == 2:
                            return 0.90  # 番地まで一致
                        else:
                            return 0.93  # より詳細まで一致
                else:
                    # 途中から異なる（例：「1-9-18」と「1-10-5」）
                    if matches >= 1:
                        # 丁目は一致するが番地以降が異なる
                        return 0.4  # 同じ丁目だが別の番地
                    else:
                        return 0.2  # 異なる住所
            else:
                # 番地が文字列として一致するかチェック
                if comp1['block'] == comp2['block']:
                    return 0.95
                else:
                    return 0.4
        
        # 片方にのみ番地情報がある場合
        if comp1['block'] or comp2['block']:
            # 番地以外の部分が一致するかチェック
            if (comp1['prefecture'] == comp2['prefecture'] and
                comp1['city'] == comp2['city'] and
                comp1['area'] == comp2['area']):
                # 同じ地域で、片方のみ番地情報がある（省略の可能性）
                return 0.75  # 高い類似度だが、完全一致ではない
            else:
                # 地域も異なる
                return 0.3
        
        # 両方とも番地情報がない場合は文字列類似度で判定
        return SequenceMatcher(None, norm_addr1, norm_addr2).ratio()
    
    def _calculate_name_similarity(self, name1: str, name2: str, 
                                    building1: Any = None, building2: Any = None, 
                                    session = None) -> float:
        """建物名の類似度を計算（正規化形式のみ使用・高速版）
        
        Args:
            name1: 建物1の名前
            name2: 建物2の名前  
            building1: 建物1のオブジェクト（掲載履歴取得用、オプション）
            building2: 建物2のオブジェクト（掲載履歴取得用、オプション）
            session: データベースセッション（掲載履歴取得用、オプション）
        """
        if not name1 or not name2:
            return 0.0
        
        # 1. 基本的な正規化
        norm1 = self.building_normalizer.normalize(name1)
        norm2 = self.building_normalizer.normalize(name2)
        
        # 完全一致の場合
        if norm1 == norm2:
            return 1.0
        
        # 2. 正規化された名前のリストを作成（バリエーション生成はしない）
        names1 = [norm1]
        names2 = [norm2]
        
        # 3. 掲載履歴からエイリアスを追加（すべて使用・正規化のみ）
        if building1 and session:
            aliases1 = self._get_building_aliases(building1, session)
            for alias in aliases1:
                normalized_alias = self.building_normalizer.normalize(alias)
                if normalized_alias not in names1:
                    names1.append(normalized_alias)
                
        if building2 and session:
            aliases2 = self._get_building_aliases(building2, session)
            for alias in aliases2:
                normalized_alias = self.building_normalizer.normalize(alias)
                if normalized_alias not in names2:
                    names2.append(normalized_alias)
        
        # デバッグ情報
        self.last_debug_info['name_variations'] = {
            'name1': names1,
            'name2': names2,
            'has_aliases1': building1 is not None and session is not None and len(names1) > 1,
            'has_aliases2': building2 is not None and session is not None and len(names2) > 1
        }
        
        # 4. 全ての組み合わせで最高スコアを採用（組み合わせ数が大幅に削減）
        max_score = 0.0
        best_pair = None
        
        for n1 in names1:
            for n2 in names2:
                # シンプルな類似度計算
                score = self.building_normalizer.calculate_similarity(n1, n2)
                
                if score > max_score:
                    max_score = score
                    best_pair = (n1, n2)
                    
                # 0.95以上で早期終了（完全一致でなくても十分高い）
                if max_score >= 0.95:
                    break
            if max_score >= 0.95:
                break
        
        # デバッグ情報
        if best_pair:
            self.last_debug_info['best_name_match'] = {
                'pair': best_pair,
                'score': max_score
            }
        
        return max_score
    
    
    def _calculate_attribute_similarity(self, building1: Any, building2: Any) -> float:
        """築年月、総階数の一致度を計算"""
        scores = []
        weights = []
        
        # 築年月の一致（厳格な判定 - 同一建物なら一致するはず）
        if building1.built_year and building2.built_year:
            # 築月情報の取得
            month1 = getattr(building1, 'built_month', None)
            month2 = getattr(building2, 'built_month', None)
            
            year_diff = abs(building1.built_year - building2.built_year)
            
            if year_diff == 0:
                # 年が完全一致する場合
                if month1 and month2:
                    # 両方とも月情報がある場合
                    if month1 == month2:
                        scores.append(1.0)  # 年月とも完全一致
                    else:
                        # 月が異なる = 誤表記または別建物の可能性
                        scores.append(0.3)  # 低い類似度
                else:
                    # 片方または両方の月情報がない場合
                    scores.append(0.7)  # 年のみで比較（月情報が不完全）
            elif year_diff == 1:
                # 1年差の場合（誤表記の可能性はあるが低い）
                scores.append(0.2)  # かなり低い類似度
            elif year_diff == 2:
                # 2年差（誤表記の可能性は極めて低い）
                scores.append(0.1)  # 非常に低い類似度
            else:
                # 3年以上の差は別建物
                scores.append(0.0)
            
            weights.append(2.0)  # 築年月は重要度高
        
        # 総階数の一致（段階的な類似度判定、大きな差も許容）
        if building1.total_floors and building2.total_floors:
            floor_diff = abs(building1.total_floors - building2.total_floors)
            
            if floor_diff == 0:
                scores.append(1.0)  # 完全一致
            elif floor_diff == 1:
                scores.append(0.8)  # 1階差は高い類似度
            elif floor_diff <= 5:
                scores.append(0.5)  # 5階以内の差は中程度の類似度
            elif floor_diff <= 10:
                scores.append(0.3)  # 10階以内の差は低い類似度
            elif floor_diff <= 20:
                scores.append(0.2)  # 20階以内の差は非常に低い類似度
            else:
                scores.append(0.1)  # 20階以上の差でも完全に否定はしない
            
            weights.append(0.8)  # 階数の重要度を下げる（同じ建物群で差があるため）
        
        # 構造の一致（もしあれば）
        if (hasattr(building1, 'construction_type') and 
            hasattr(building2, 'construction_type') and
            building1.construction_type and building2.construction_type):
            if building1.construction_type == building2.construction_type:
                scores.append(1.0)
            else:
                scores.append(0.5)  # 異なる構造
            weights.append(0.5)  # 構造は参考程度
        
        # デバッグ情報
        self.last_debug_info['attribute_details'] = {
            'built_year1': building1.built_year,
            'built_year2': building2.built_year,
            'built_month1': getattr(building1, 'built_month', None),
            'built_month2': getattr(building2, 'built_month', None),
            'total_floors1': building1.total_floors,
            'total_floors2': building2.total_floors,
        }
        
        # 重み付き平均を計算
        if weights:
            return sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            return 0.5  # 属性情報がない場合は中立的なスコア
    
    def _calculate_final_score(self, addr_score: float, name_score: float, attr_score: float) -> float:
        """最終的な類似度スコアを計算"""
        
        # ケース1: 住所・属性が高一致
        # → 建物名が異なっても同一建物の可能性が高い（英字/カタカナの違い等）
        if addr_score >= 0.95 and attr_score >= 0.9:
            # 建物名が極端に低い場合でも高スコア
            if name_score < 0.3:
                self.last_debug_info['match_reason'] = '住所と属性が完全一致（建物名は異なる）'
                return 0.92
            else:
                self.last_debug_info['match_reason'] = '住所と属性が完全一致'
                return 0.95
        
        # ケース2: 建物名が高一致で、住所も一致
        if name_score >= 0.85 and addr_score >= 0.8:
            self.last_debug_info['match_reason'] = '建物名と住所が高一致'
            return max(name_score, addr_score)
        
        # ケース3: 建物名は低いが、住所と属性が一致
        # → 英字/カタカナの表記違いの可能性
        if name_score < 0.5 and addr_score >= 0.9 and attr_score >= 0.8:
            self.last_debug_info['match_reason'] = '住所一致・属性一致（建物名の表記違いの可能性）'
            return 0.85
        
        # ケース4: 住所が不明だが、建物名と属性が高一致
        if addr_score == 0.0 and name_score >= 0.9 and attr_score >= 0.8:
            self.last_debug_info['match_reason'] = '建物名と属性が高一致（住所情報なし）'
            return 0.85
        
        # ケース5: 通常の重み付け計算
        # 住所がある場合とない場合で重みを調整
        if addr_score > 0:
            # 住所情報がある場合
            score = (
                name_score * 0.35 +
                addr_score * 0.40 +
                attr_score * 0.25
            )
            self.last_debug_info['match_reason'] = '総合判定（住所情報あり）'
        else:
            # 住所情報がない場合は建物名と属性を重視
            score = (
                name_score * 0.65 +
                attr_score * 0.35
            )
            self.last_debug_info['match_reason'] = '総合判定（住所情報なし）'
        
        return score
    
    def get_debug_info(self) -> Dict[str, Any]:
        """最後の比較のデバッグ情報を取得"""
        return self.last_debug_info.copy()