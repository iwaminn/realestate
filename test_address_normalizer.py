#!/usr/bin/env python3
"""
AddressNormalizerのfind_address_end_positionメソッドのテスト
"""

import sys
sys.path.append('/home/ubuntu/realestate/backend')

from app.utils.address_normalizer import AddressNormalizer

def test_find_address_end_position():
    normalizer = AddressNormalizer()

    # テストケース
    test_cases = [
        # (入力住所, 期待される終端位置の後の文字列)
        ("東京都港区芝浦4-16-1地図を見る", "地図を見る"),
        ("千代田区三番町26-1周辺地図", "周辺地図"),
        ("港区南麻布5丁目詳細を見る", "詳細を見る"),
        ("渋谷区恵比寿3丁目10番地MAP", "MAP"),
        ("新宿区西新宿2丁目8番1号もっと見る", "もっと見る"),
        ("品川区大崎1-11-1アクセス", "アクセス"),
        ("中央区日本橋3-5-1[詳細]", "[詳細]"),
        ("千代田区一番町12-3※地図", "※地図"),
        ("港区六本木6丁目10番1号", ""),  # UI要素なし
        ("世田谷区三軒茶屋2-11-23", ""),  # UI要素なし
    ]

    print("=" * 70)
    print("find_address_end_position メソッドのテスト")
    print("=" * 70)

    for address, expected_remainder in test_cases:
        end_pos = normalizer.find_address_end_position(address)

        if end_pos is not None:
            extracted = address[:end_pos]
            remainder = address[end_pos:].strip()
        else:
            extracted = "パターンにマッチしませんでした"
            remainder = address

        # 結果の表示
        print(f"\n入力: {address}")
        print(f"  終端位置: {end_pos}")
        print(f"  抽出住所: {extracted}")
        print(f"  残り部分: {remainder}")
        print(f"  期待残り: {expected_remainder}")
        print(f"  判定: {'✓ OK' if remainder == expected_remainder else '✗ NG'}")

def test_remove_ui_elements():
    normalizer = AddressNormalizer()

    test_cases = [
        ("東京都港区芝浦4-16-1地図を見る", "東京都港区芝浦4-16-1"),
        ("千代田区三番町26-1周辺地図", "千代田区三番町26-1"),
        ("港区南麻布5丁目詳細を見る", "港区南麻布5丁目"),
        ("渋谷区恵比寿3丁目10番地MAP", "渋谷区恵比寿3丁目10番地"),
        ("新宿区西新宿2丁目8番1号もっと見る", "新宿区西新宿2丁目8番1号"),
        ("品川区大崎1-11-1アクセス", "品川区大崎1-11-1"),
        ("中央区日本橋3-5-1[詳細]", "中央区日本橋3-5-1"),
        ("千代田区一番町12-3※地図", "千代田区一番町12-3"),
        ("港区六本木6丁目10番1号", "港区六本木6丁目10番1号"),
        ("世田谷区三軒茶屋2-11-23", "世田谷区三軒茶屋2-11-23"),
    ]

    print("\n" + "=" * 70)
    print("remove_ui_elements メソッドのテスト")
    print("=" * 70)

    for input_address, expected in test_cases:
        result = normalizer.remove_ui_elements(input_address)
        is_ok = result == expected

        print(f"\n入力: {input_address}")
        print(f"  期待: {expected}")
        print(f"  結果: {result}")
        print(f"  判定: {'✓ OK' if is_ok else '✗ NG'}")

if __name__ == "__main__":
    test_find_address_end_position()
    test_remove_ui_elements()