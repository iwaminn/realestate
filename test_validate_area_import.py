"""validate_area関数のインポートテスト"""
import sys
sys.path.append('/home/ubuntu/realestate')

# homes_scraper.pyがdata_normalizerから正しくインポートしているか確認
from backend.app.scrapers import homes_scraper
from backend.app.scrapers import data_normalizer

# 関数が同一かチェック
if hasattr(homes_scraper, 'validate_area'):
    print("❌ homes_scraper.pyにローカルのvalidate_area関数がまだ存在します")
else:
    print("✓ homes_scraper.pyのローカルvalidate_area関数は削除されました")

# HomesScraper内でvalidate_areaが使用されているか確認
import inspect
source = inspect.getsource(homes_scraper.HomesScraper)
if 'validate_area' in source:
    print("✓ HomesScraperクラス内でvalidate_area関数が使用されています")
    
    # 実際に動作確認
    test_areas = [300, 500, 700, 1000, 1001]
    print("\n実際の動作確認:")
    for area in test_areas:
        result = data_normalizer.validate_area(area)
        print(f"  {area:4}㎡: {'有効' if result else '無効'}")
else:
    print("⚠ HomesScraperクラス内でvalidate_area関数が見つかりません")
