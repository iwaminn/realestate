#!/usr/bin/env python3
"""
漢数字・ローマ数字変換のテスト
"""

import sys
sys.path.insert(0, '/home/ubuntu/realestate/backend')

from app.utils.building_normalizer import BuildingNameNormalizer

def test_number_conversion():
    normalizer = BuildingNameNormalizer()
    
    test_cases = [
        # 漢数字のテスト
        ("白金ザ・スカイ第一棟", "白金ザスカイ第1棟"),
        ("二号館", "2号館"),
        ("第三期マンション", "第3期マンション"),
        ("十五階建て", "15階建て"),
        ("第十二棟", "第12棟"),
        ("二十三番館", "23番館"),
        
        # ローマ数字のテスト
        ("タワーⅡ", "タワー2"),
        ("第Ⅲ期", "第3期"),
        ("マンションⅣ", "マンション4"),
        ("タワーIII", "タワー3"),
        
        # 混合ケース
        ("第一タワーⅡ", "第1タワー2"),
        ("白金第三期 E棟", "白金第3期 E棟"),
        
        # 既存の正規化も含むテスト
        ("白金ザ・スカイＥ棟", "白金ザスカイE棟"),
        ("白金ザ・スカイ　西棟", "白金ザスカイ 西棟"),
    ]
    
    print("建物名正規化テスト（漢数字・ローマ数字変換）")
    print("=" * 60)
    
    success_count = 0
    for input_name, expected in test_cases:
        result = normalizer.normalize(input_name)
        is_ok = result == expected
        success_count += is_ok
        
        status = "✅" if is_ok else "❌"
        print(f"{status} {input_name}")
        print(f"   期待値: {expected}")
        print(f"   結果:   {result}")
        if not is_ok:
            print(f"   差異: '{result}' != '{expected}'")
        print()
    
    print(f"結果: {success_count}/{len(test_cases)} 成功")
    
    # 追加の確認
    print("\n追加テスト:")
    additional_tests = [
        "第一ビル",
        "二十階建て",
        "タワーⅩⅡ",
        "第十五号室",
    ]
    
    for name in additional_tests:
        result = normalizer.normalize(name)
        print(f"  {name} → {result}")

if __name__ == "__main__":
    test_number_conversion()