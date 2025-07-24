# データ正規化フレームワーク

スクレイパーで取得したデータをデータベースに保存する前に正規化・検証するためのフレームワークです。

## 概要

`data_normalizer.py` は、不動産情報の様々なフォーマットを統一的に処理するためのユーティリティを提供します。

## 主な機能

### 1. 価格抽出
```python
from backend.app.scrapers import extract_price

# 様々な価格フォーマットに対応
price1 = extract_price("5,480万円")           # -> 5480
price2 = extract_price("1億2000万円")         # -> 12000
price3 = extract_price("2億円")               # -> 20000
price4 = extract_price("価格：3,980万円（税込）") # -> 3980
```

### 2. 面積抽出
```python
from backend.app.scrapers import extract_area

# 様々な面積表記に対応
area1 = extract_area("81.3㎡")               # -> 81.3
area2 = extract_area("専有面積：70.2m²")      # -> 70.2
area3 = extract_area("バルコニー：12.5m2")    # -> 12.5
```

### 3. 階数抽出
```python
from backend.app.scrapers import extract_floor_number, extract_total_floors

# 階数情報の抽出
floor = extract_floor_number("4階/SRC9階建")  # -> 4
total, basement = extract_total_floors("地上20階地下1階建")  # -> (20, 1)
```

### 4. 間取り正規化
```python
from backend.app.scrapers import normalize_layout

# 全角・半角の統一、表記ゆれの吸収
layout1 = normalize_layout("２ＬＤＫ")        # -> "2LDK"
layout2 = normalize_layout("3SLDK")          # -> "3SLDK"
layout3 = normalize_layout("ワンルーム")       # -> "1R"
```

### 5. 方角正規化
```python
from backend.app.scrapers import normalize_direction

# 方角表記の統一
dir1 = normalize_direction("南向き")          # -> "南"
dir2 = normalize_direction("SW")             # -> "南西"
dir3 = normalize_direction("バルコニー：南東向き") # -> "南東"
```

### 6. 駅情報フォーマット
```python
from backend.app.scrapers import format_station_info

# 路線ごとに改行して見やすく整形
station_text = "東京メトロ銀座線銀座駅徒歩5分都営浅草線東銀座駅徒歩3分"
formatted = format_station_info(station_text)
# -> "東京メトロ銀座線銀座駅徒歩5分\n都営浅草線東銀座駅徒歩3分"
```

## スクレイパーでの使用方法

### 方法1: 個別の関数を使用
```python
class MyScraper(BaseScraper):
    def parse_property_detail(self, soup):
        from backend.app.scrapers import extract_price, extract_area
        
        property_data = {}
        
        # 個別に抽出・正規化
        price_elem = soup.select_one('.price')
        if price_elem:
            property_data['price'] = extract_price(price_elem.text)
        
        area_elem = soup.select_one('.area')
        if area_elem:
            property_data['area'] = extract_area(area_elem.text)
        
        return property_data
```

### 方法2: 一括正規化
```python
class MyScraper(BaseScraper):
    def parse_property_detail(self, soup):
        from backend.app.scrapers import normalize_property_data
        
        # 生データを収集
        raw_data = {
            'price': soup.select_one('.price').text,
            'area': soup.select_one('.area').text,
            'floor_number': soup.select_one('.floor').text,
            'layout': soup.select_one('.layout').text,
            # ... その他のフィールド
        }
        
        # 一括で正規化
        property_data = normalize_property_data(raw_data)
        
        return property_data
```

### 方法3: DataNormalizerクラスを直接使用
```python
from backend.app.scrapers import DataNormalizer

class MyScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.normalizer = DataNormalizer()
    
    def parse_property_detail(self, soup):
        # より細かい制御が必要な場合
        price_text = soup.select_one('.price').text
        price = self.normalizer.extract_price(price_text)
        
        # データ検証
        errors = self.normalizer.get_validation_errors({'price': price})
        if errors:
            self.logger.warning(f"データ検証エラー: {errors}")
        
        return {'price': price}
```

## データ検証

```python
from backend.app.scrapers import validate_property_data

property_data = {
    'price': 5480,
    'area': 75.3,
    'floor_number': 12,
    'total_floors': 20,
    'built_year': 2015
}

# 検証実行
errors = validate_property_data(property_data)
if errors:
    for error in errors:
        print(f"エラー: {error}")
else:
    print("データ検証OK")
```

### 検証ルール
- 価格: 100万円以上、10億円以下
- 専有面積: 10㎡以上、500㎡以下
- 階数: 1階以上、総階数以下
- 築年: 1900年以上、現在年以下

## 拡張方法

新しい正規化パターンを追加する場合：

```python
# data_normalizer.py に追加
class DataNormalizer:
    def extract_custom_field(self, text: str) -> Optional[str]:
        """カスタムフィールドの抽出"""
        # 実装
        pass

# エクスポート関数も追加
def extract_custom_field(text: str) -> Optional[str]:
    return _normalizer.extract_custom_field(text)

# __init__.py にもエクスポートを追加
```

## 注意事項

1. **エラーハンドリング**: 抽出に失敗した場合は`None`を返します
2. **型安全性**: 戻り値の型は明確に定義されています
3. **検証**: データの妥当性検証は別途行ってください
4. **拡張性**: 新しいサイトのパターンは随時追加可能です

## テスト

```bash
# 単体テストの実行
python backend/app/scrapers/data_normalizer.py

# 使用例の実行
python -m backend.app.scrapers.example_scraper_usage
```