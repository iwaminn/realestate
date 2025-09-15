"""
検索用ユーティリティ関数
"""
import re
from typing import List


def split_search_terms(text: str) -> List[str]:
    """
    検索語を適切に分割する
    
    「白金ザスカイ」→ ['白金', 'ザスカイ']
    「白金ザ・スカイ」→ ['白金', 'ザ', 'スカイ']
    「パークコート麻布十番」→ ['パークコート', '麻布', '十番']
    """
    if not text:
        return []
    
    # まず記号で分割
    # ・、･、−、－、スペースで分割
    parts = re.split(r'[・･\-－\s]+', text)
    
    result = []
    for part in parts:
        if not part:
            continue
            
        # カタカナと漢字の境界で分割
        # 例：「白金ザスカイ」→「白金」「ザスカイ」
        segments = re.findall(r'[一-龥]+|[ァ-ヴー]+|[ぁ-ん]+|[a-zA-Z0-9]+', part)
        
        if len(segments) > 1:
            # 複数のセグメントがある場合
            # カタカナの助詞（ザ、ノ、ガなど）は次の語と結合するか単独にする
            i = 0
            while i < len(segments):
                segment = segments[i]
                
                # カタカナの助詞的な短い語
                if re.match(r'^[ザノガデヲニハヘトモ]$', segment):
                    if i + 1 < len(segments):
                        # 次の語がカタカナなら結合
                        if re.match(r'^[ァ-ヴー]+$', segments[i + 1]):
                            result.append(segment + segments[i + 1])
                            i += 2
                            continue
                    # 単独で追加
                    result.append(segment)
                else:
                    result.append(segment)
                i += 1
        else:
            # 単一セグメントの場合はそのまま
            result.append(part)
    
    return result


def generate_search_patterns(text: str) -> List[str]:
    """
    検索パターンを生成する
    
    「白金ザスカイ」の場合：
    - そのまま: 「白金ザスカイ」
    - 分割: 「白金」「ザスカイ」
    - カタカナ分離: 「白金」「ザ」「スカイ」
    """
    if not text:
        return []
    
    from .building_name_normalizer import normalize_building_name
    
    patterns = set()
    
    # 1. 元のテキストをそのまま
    patterns.add(text)
    
    # 2. 正規化したテキスト
    normalized = normalize_building_name(text)
    patterns.add(normalized)
    
    # 3. 正規化後をスペースで分割
    for term in normalized.split():
        if term:
            patterns.add(term)
    
    # 4. 賢い分割
    smart_terms = split_search_terms(text)
    for term in smart_terms:
        if term:
            patterns.add(term)
    
    # 5. スペース・記号を完全に除去したパターン
    no_space = re.sub(r'[・･\-－\s]+', '', text)
    if no_space:
        patterns.add(no_space)
    
    return list(patterns)