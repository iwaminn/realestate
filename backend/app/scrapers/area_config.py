"""
エリア設定の共通定義ファイル
各スクレイパーで使用するエリアコードのマッピング
"""

# 東京都の区コードマッピング
TOKYO_AREA_CODES = {
    # 日本語名
    "千代田区": "13101",
    "中央区": "13102",
    "港区": "13103",
    "新宿区": "13104",
    "文京区": "13105",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108",
    "品川区": "13109",
    "目黒区": "13110",
    "大田区": "13111",
    "世田谷区": "13112",
    "渋谷区": "13113",
    "中野区": "13114",
    "杉並区": "13115",
    "豊島区": "13116",
    "北区": "13117",
    "荒川区": "13118",
    "板橋区": "13119",
    "練馬区": "13120",
    "足立区": "13121",
    "葛飾区": "13122",
    "江戸川区": "13123",
    
    # 英語名（ローマ字）
    "chiyoda": "13101",
    "chuo": "13102",
    "minato": "13103",
    "shinjuku": "13104",
    "bunkyo": "13105",
    "taito": "13106",
    "sumida": "13107",
    "koto": "13108",
    "shinagawa": "13109",
    "meguro": "13110",
    "ota": "13111",
    "setagaya": "13112",
    "shibuya": "13113",
    "nakano": "13114",
    "suginami": "13115",
    "toshima": "13116",
    "kita": "13117",
    "arakawa": "13118",
    "itabashi": "13119",
    "nerima": "13120",
    "adachi": "13121",
    "katsushika": "13122",
    "edogawa": "13123"
}

# LIFULL HOME'S用のエリアマッピング
HOMES_AREA_MAPPING = {
    "13101": "chiyoda-city",
    "13102": "chuo-city",
    "13103": "minato-city",
    "13104": "shinjuku-city",
    "13105": "bunkyo-city",
    "13106": "taito-city",
    "13107": "sumida-city",
    "13108": "koto-city",
    "13109": "shinagawa-city",
    "13110": "meguro-city",
    "13111": "ota-city",
    "13112": "setagaya-city",
    "13113": "shibuya-city",
    "13114": "nakano-city",
    "13115": "suginami-city",
    "13116": "toshima-city",
    "13117": "kita-city",
    "13118": "arakawa-city",
    "13119": "itabashi-city",
    "13120": "nerima-city",
    "13121": "adachi-city",
    "13122": "katsushika-city",
    "13123": "edogawa-city"
}


def get_area_code(area_name: str) -> str:
    """
    エリア名から区コードを取得
    
    Args:
        area_name: エリア名（日本語、英語、または区コード）
        
    Returns:
        区コード（5桁の文字列）
    """
    # すでに区コードの場合はそのまま返す
    if area_name.isdigit() and len(area_name) == 5:
        return area_name
    
    # マッピングから検索（大文字小文字を区別しない）
    area_lower = area_name.lower()
    return TOKYO_AREA_CODES.get(area_name, TOKYO_AREA_CODES.get(area_lower, "13103"))  # デフォルトは港区

def get_homes_city_code(area_code: str) -> str:
    """
    区コードからLIFULL HOME'S用のcityコードを取得
    
    Args:
        area_code: 5桁の区コード
        
    Returns:
        LIFULL HOME'S用のcityコード（例: "minato-city"）
    """
    return HOMES_AREA_MAPPING.get(area_code, "minato-city")

