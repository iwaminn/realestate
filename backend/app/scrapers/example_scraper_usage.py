"""
データ正規化フレームワークの使用例
新しいスクレイパーを実装する際の参考にしてください
"""

from typing import Dict, Any, Optional
from .data_normalizer import (
    DataNormalizer,
    extract_price,
    extract_area,
    extract_floor_number,
    normalize_layout,
    normalize_direction,
    format_station_info,
    normalize_property_data,
    validate_property_data
)


def example_basic_usage():
    """基本的な使い方の例"""
    
    # 個別の関数を使用する場合
    price_text = "販売価格：5,480万円"
    price = extract_price(price_text)
    print(f"抽出された価格: {price}万円")
    
    area_text = "専有面積：75.3㎡"
    area = extract_area(area_text)
    print(f"抽出された面積: {area}㎡")
    
    floor_text = "所在階：12階/20階建"
    floor = extract_floor_number(floor_text)
    print(f"抽出された階数: {floor}階")


def example_scraper_integration():
    """スクレイパーでの統合例"""
    
    # スクレイパーが取得した生データ（例）
    raw_property_data = {
        'url': 'https://example.com/property/123',
        'title': '○○マンション 12階',
        'price': '5,480万円',  # 文字列
        'management_fee': '12,000円/月',  # 文字列
        'repair_fund': '8,500円',  # 文字列
        'area': '専有面積：75.3㎡',  # 文字列
        'balcony_area': 'バルコニー：10.5m²',  # 文字列
        'floor_number': '12階/20階建',  # 文字列
        'total_floors': '地上20階地下1階建',  # 文字列
        'layout': '３ＬＤＫ',  # 全角
        'direction': 'バルコニー：南東向き',  # 方角情報を含む
        'station_info': '東京メトロ銀座線銀座駅徒歩5分都営浅草線東銀座駅徒歩3分',
        'built_year': '築年月：2015年3月',  # 文字列
        'building_name': '○○マンション',
        'room_number': '1203',
        'address': '東京都港区○○1-2-3',
    }
    
    # データを正規化
    normalized_data = normalize_property_data(raw_property_data)
    
    print("\n=== 正規化されたデータ ===")
    print(f"価格: {normalized_data.get('price')}万円")
    print(f"管理費: {normalized_data.get('management_fee')}円")
    print(f"修繕積立金: {normalized_data.get('repair_fund')}円")
    print(f"専有面積: {normalized_data.get('area')}㎡")
    print(f"バルコニー面積: {normalized_data.get('balcony_area')}㎡")
    print(f"階数: {normalized_data.get('floor_number')}階")
    print(f"総階数: {normalized_data.get('total_floors')}階（地下{normalized_data.get('basement_floors', 0)}階）")
    print(f"間取り: {normalized_data.get('layout')}")
    print(f"方角: {normalized_data.get('direction')}")
    print(f"築年: {normalized_data.get('built_year')}年")
    print(f"駅情報:\n{normalized_data.get('station_info')}")
    
    # データの検証
    errors = validate_property_data(normalized_data)
    if errors:
        print("\n=== 検証エラー ===")
        for error in errors:
            print(f"- {error}")
    else:
        print("\n✓ データ検証OK")


def example_custom_normalization():
    """カスタム正規化の例"""
    
    # DataNormalizerインスタンスを作成
    normalizer = DataNormalizer()
    
    # 複雑なケースの処理
    complex_price = "物件価格：1億4,500万円（税込）"
    price = normalizer.extract_price(complex_price)
    print(f"\n複雑な価格パターン: {complex_price} -> {price}万円")
    
    # 総階数と地下階数を同時に取得
    building_info = "RC造42階地下3階建"
    total_floors, basement_floors = normalizer.extract_total_floors(building_info)
    print(f"建物情報: {building_info} -> 地上{total_floors}階、地下{basement_floors}階")
    
    # 駅情報のフォーマット
    station_text = "東京メトロ銀座線銀座駅徒歩5分、都営浅草線東銀座駅徒歩3分、JR山手線有楽町駅徒歩8分"
    formatted_stations = normalizer.format_station_info(station_text)
    print(f"\n駅情報のフォーマット:")
    print(formatted_stations)


def example_in_scraper_class():
    """スクレイパークラスでの使用例"""
    
    class ExampleScraper:
        def __init__(self):
            self.normalizer = DataNormalizer()
        
        def parse_property_detail(self, html_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            """物件詳細ページの解析"""
            
            property_data = {}
            
            # HTMLから取得したデータ（例）
            price_element = html_data.get('price_text', '')
            area_element = html_data.get('area_text', '')
            floor_element = html_data.get('floor_text', '')
            
            # 個別に正規化
            property_data['price'] = self.normalizer.extract_price(price_element)
            property_data['area'] = self.normalizer.extract_area(area_element)
            property_data['floor_number'] = self.normalizer.extract_floor_number(floor_element)
            
            # または、まとめて正規化
            raw_data = {
                'price': price_element,
                'area': area_element,
                'floor_number': floor_element,
                # ... その他のフィールド
            }
            property_data = self.normalizer.normalize_property_data(raw_data)
            
            # 検証
            errors = self.normalizer.get_validation_errors(property_data)
            if errors:
                print(f"警告: データ検証エラー - {', '.join(errors)}")
                # エラーがあっても処理を続ける場合
                # return None  # または、エラーがある場合はNoneを返す
            
            return property_data
    
    # 使用例
    scraper = ExampleScraper()
    test_data = {
        'price_text': '3,980万円',
        'area_text': '65.5㎡',
        'floor_text': '8階'
    }
    result = scraper.parse_property_detail(test_data)
    print(f"\nスクレイパークラスでの使用例: {result}")


def example_error_handling():
    """エラーハンドリングの例"""
    
    normalizer = DataNormalizer()
    
    # 不正なデータの例
    invalid_data = {
        'price': 50,  # 100万円未満
        'area': 5.0,  # 10㎡未満
        'floor_number': 50,
        'total_floors': 30,  # 階数 > 総階数
        'built_year': 2050,  # 未来の年
    }
    
    errors = normalizer.get_validation_errors(invalid_data)
    print("\n=== 不正なデータの検証結果 ===")
    for error in errors:
        print(f"❌ {error}")


if __name__ == "__main__":
    print("=== データ正規化フレームワークの使用例 ===\n")
    
    example_basic_usage()
    print("\n" + "="*50)
    
    example_scraper_integration()
    print("\n" + "="*50)
    
    example_custom_normalization()
    print("\n" + "="*50)
    
    example_in_scraper_class()
    print("\n" + "="*50)
    
    example_error_handling()