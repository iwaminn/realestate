"""大面積物件の処理テスト"""
from backend.app.scrapers.data_normalizer import validate_area

# テスト
test_areas = [
    (5, False),    # 10㎡未満
    (10, True),    # 10㎡（最小値）
    (100, True),   # 通常の物件
    (300, True),   # 300㎡（以前の上限）
    (500, True),   # 500㎡
    (700, True),   # 700㎡
    (1000, True),  # 1000㎡（新しい上限）
    (1001, False), # 1000㎡超
]

print("面積検証テスト結果:")
for area, expected in test_areas:
    result = validate_area(area)
    status = "✓" if result == expected else "✗"
    print(f"  {status} {area:4}㎡: {result} (期待値: {expected})")

# homes_scraper.pyのローカル関数もテスト
from backend.app.scrapers.homes_scraper import validate_area as homes_validate_area

print("\nhomes_scraper.pyの検証関数テスト:")
for area, expected in test_areas:
    result = homes_validate_area(area)
    status = "✓" if result == expected else "✗"
    print(f"  {status} {area:4}㎡: {result} (期待値: {expected})")
