#!/usr/bin/env python3
"""
物件ハッシュを再計算して確認
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
from app.scrapers.base_scraper import BaseScraper

def recalculate_hash():
    """ID 827と829のハッシュを再計算"""
    scraper = BaseScraper("TEST")
    
    # 両方とも同じデータ
    building_id = 361
    room_number = None
    floor_number = 38
    area = 71.81
    layout = "2LDK"
    direction = "北"
    
    # 新しいロジックでハッシュを計算
    hash1 = scraper.generate_property_hash(building_id, room_number, floor_number, area, layout, direction)
    print(f"新ロジックでのハッシュ: {hash1}")
    
    # 旧ロジック（方角を含まない）でハッシュを計算
    floor_str = f"F{floor_number}"
    area_str = f"A{area:.1f}"
    data_old = f"{building_id}:{floor_str}_{area_str}"
    hash_old = hashlib.md5(data_old.encode()).hexdigest()
    print(f"旧ロジックでのハッシュ: {hash_old}")
    print(f"旧ロジックデータ: {data_old}")
    
    # 実際のハッシュと比較
    print("\n実際のハッシュ:")
    print(f"ID 827: 87b50e11d1a44f2de3b3d594696db738")
    print(f"ID 829: 55796564c52eb17f56f9383ccb904c2e")
    
    # 異なるハッシュになる原因を調査
    # ID 827のハッシュがどのように生成されたか調査
    print("\nID 827のハッシュを探索:")
    
    # 異なる組み合わせを試す
    # 1. 階数が異なる？
    for floor in [36, 37, 38, 39]:
        data_test = f"{building_id}:F{floor}_A71.8"
        hash_test = hashlib.md5(data_test.encode()).hexdigest()
        if hash_test == "87b50e11d1a44f2de3b3d594696db738":
            print(f"階数 {floor} でID 827のハッシュと一致！")
    
    # 2. URLが含まれている？
    test_url = "https://suumo.jp/ms/chuko/tokyo/sc_minato/nc_77844335/"
    data_with_url = f"{building_id}:F38_A71.8_{test_url}"
    hash_with_url = hashlib.md5(data_with_url.encode()).hexdigest()
    print(f"\nURLを含むハッシュ: {hash_with_url}")
    
    # 3. 方角が含まれている？（古い実装で）
    data_with_dir = f"{building_id}:F38_A71.8_北"
    hash_with_dir = hashlib.md5(data_with_dir.encode()).hexdigest()
    print(f"方角を含むハッシュ: {hash_with_dir}")

if __name__ == "__main__":
    recalculate_hash()