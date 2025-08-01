"""
建物の住所から適切なエリア（区）を判定するユーティリティ
"""

import re
from typing import Optional, Tuple

# 東京23区のパターン定義
TOKYO_WARD_PATTERNS = {
    "13101": ["千代田区"],
    "13102": ["中央区"],
    "13103": ["港区"],
    "13104": ["新宿区"],
    "13105": ["文京区"],
    "13106": ["台東区"],
    "13107": ["墨田区"],
    "13108": ["江東区"],
    "13109": ["品川区"],
    "13110": ["目黒区"],
    "13111": ["大田区"],
    "13112": ["世田谷区"],
    "13113": ["渋谷区"],
    "13114": ["中野区"],
    "13115": ["杉並区"],
    "13116": ["豊島区"],
    "13117": ["北区"],
    "13118": ["荒川区"],
    "13119": ["板橋区"],
    "13120": ["練馬区"],
    "13121": ["足立区"],
    "13122": ["葛飾区"],
    "13123": ["江戸川区"]
}

def get_area_code_from_address(address: str) -> Optional[str]:
    """
    住所から区コードを取得
    
    Args:
        address: 建物の住所（例: "東京都港区南麻布１-24-11"）
        
    Returns:
        区コード（例: "13103"）、判定できない場合はNone
    """
    if not address:
        return None
    
    # 住所から区名を抽出
    for area_code, ward_names in TOKYO_WARD_PATTERNS.items():
        for ward_name in ward_names:
            if ward_name in address:
                return area_code
    
    return None

def is_address_in_area(address: str, area_code: str) -> bool:
    """
    住所が指定されたエリアに属するかを判定
    
    Args:
        address: 建物の住所
        area_code: エリアコード
        
    Returns:
        住所がエリアに属する場合True
    """
    actual_area_code = get_area_code_from_address(address)
    return actual_area_code == area_code

def compare_area_match(address: str, area_code1: str, area_code2: str) -> Optional[str]:
    """
    住所に対してより適切なエリアコードを判定
    
    Args:
        address: 建物の住所
        area_code1: 比較するエリアコード1
        area_code2: 比較するエリアコード2
        
    Returns:
        より適切なエリアコード、判定できない場合はNone
    """
    actual_area_code = get_area_code_from_address(address)
    
    if not actual_area_code:
        return None
    
    # 実際の区と一致する方を返す
    if actual_area_code == area_code1:
        return area_code1
    elif actual_area_code == area_code2:
        return area_code2
    else:
        # どちらも一致しない場合
        return None

def get_ward_name_from_code(area_code: str) -> Optional[str]:
    """
    区コードから区名を取得
    
    Args:
        area_code: 区コード（例: "13103"）
        
    Returns:
        区名（例: "港区"）、不明な場合はNone
    """
    ward_names = TOKYO_WARD_PATTERNS.get(area_code)
    return ward_names[0] if ward_names else None