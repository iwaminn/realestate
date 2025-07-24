# データ正規化ガイド

本プロジェクトでは、スクレイパーから取得したデータの型安全性と一貫性を保証するため、データ正規化フレームワークを提供しています。

## 概要

`backend/app/scrapers/data_normalizer.py` は、不動産情報の様々なフォーマットを統一的に処理し、データベースに保存する前に適切な型に変換するユーティリティです。

## 重要性

SQLAlchemyは厳格な型チェックを行うため、以下のような問題を防ぐ必要があります：
- 整数型フィールドに文字列を渡すエラー
- 面積や価格の単位の不一致
- 日付フォーマットの不統一
- 方角や間取りの表記ゆれ

## 使用方法

### 1. スクレイパーでのインポート

```python
from . import (
    extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date,
    normalize_integer
)
```

### 2. 価格の抽出

```python
# 様々な価格フォーマットから万円単位の整数値を抽出
price = extract_price("5,480万円")  # -> 5480
price = extract_price("1億2000万円")  # -> 12000
price = extract_price("2億円")  # -> 20000
```

### 3. 面積の抽出

```python
# 様々な面積表記から㎡単位の浮動小数点数を抽出
area = extract_area("81.3㎡")  # -> 81.3
area = extract_area("専有面積：70.2m²")  # -> 70.2
balcony_area = extract_area("バルコニー：12.5m2")  # -> 12.5
```

### 4. 階数の抽出

```python
# 階数情報の抽出
floor = extract_floor_number("4階")  # -> 4
floor = extract_floor_number("4階/SRC9階建")  # -> 4

# 総階数と地下階数の抽出
total, basement = extract_total_floors("地上20階地下1階建")  # -> (20, 1)
```

### 5. 整数値の正規化

```python
# 文字列から整数値を安全に抽出
listing_total_floors = normalize_integer("地上12階建", "listing_total_floors")  # -> 12
total_units = normalize_integer("総戸数：150戸")  # -> 150
```

### 6. 月額費用の抽出

```python
# 管理費・修繕積立金などの抽出（円単位）
management_fee = extract_monthly_fee("12,000円")  # -> 12000
repair_fund = extract_monthly_fee("修繕積立金：8,500円/月")  # -> 8500
```

### 7. 間取りの正規化

```python
# 全角・半角の統一、表記ゆれの吸収
layout = normalize_layout("３ＬＤＫ")  # -> "3LDK"
layout = normalize_layout("ワンルーム")  # -> "1R"
```

### 8. 方角の正規化

```python
# 方角表記の統一
direction = normalize_direction("南向き")  # -> "南"
direction = normalize_direction("SW")  # -> "南西"
direction = normalize_direction("バルコニー：南東向き")  # -> "南東"
```

### 9. 駅情報のフォーマット

```python
# 路線ごとに改行して見やすく整形
station_info = format_station_info("東京メトロ銀座線銀座駅徒歩5分都営浅草線東銀座駅徒歩3分")
# -> "東京メトロ銀座線銀座駅徒歩5分\n都営浅草線東銀座駅徒歩3分"
```

### 10. 築年の抽出

```python
# 築年情報から西暦年を抽出
built_year = extract_built_year("2020年築")  # -> 2020
built_year = extract_built_year("築年月：2015年3月")  # -> 2015
```

### 11. 日付の解析

```python
# 文字列から datetime オブジェクトを生成
published_at = parse_date("2024年1月15日")  # -> datetime(2024, 1, 15)
published_at = parse_date("2024/01/15")  # -> datetime(2024, 1, 15)
```

## 実装例（東急リバブルスクレイパー）

```python
def _extract_property_info(self, label: str, value: str, property_data: Dict[str, Any], detail_info: Dict[str, Any]):
    """ラベルと値から物件情報を抽出"""
    
    # 階数（所在階）
    if '階数' in label or '所在階' in label and '総階数' not in label:
        floor_number = extract_floor_number(value)
        if floor_number is not None:
            property_data['floor_number'] = floor_number
    
    # 専有面積
    elif ('専有面積' in label or '面積' in label) and 'バルコニー' not in label:
        area_value = extract_area(value)
        if area_value:
            property_data['area'] = area_value
    
    # 間取り
    elif '間取り' in label:
        layout = normalize_layout(value)
        if layout:
            property_data['layout'] = layout
    
    # 管理費
    elif '管理費' in label:
        management_fee = extract_monthly_fee(value)
        if management_fee:
            property_data['management_fee'] = management_fee
```

## データベース保存前の整数型正規化

SQLAlchemyの整数型フィールドに文字列を渡さないよう、必ず正規化を行います：

```python
# 建物情報の総階数を正規化
building_total_floors = normalize_integer(
    detail_info.get('total_floors'),
    field_name='total_floors'
)

# 掲載情報の総階数を正規化
listing_total_floors = normalize_integer(
    property_data.get('detail_info', {}).get('total_floors'),
    field_name='listing_total_floors'
)
```

## データ検証

```python
from backend.app.scrapers import validate_property_data

# 正規化後のデータを検証
errors = validate_property_data(property_data)
if errors:
    for error in errors:
        print(f"検証エラー: {error}")
```

### 検証ルール
- 価格: 100万円以上、10億円以下
- 専有面積: 10㎡以上、500㎡以下
- 階数: 1階以上、総階数以下
- 築年: 1900年以上、現在年以下

## ベストプラクティス

1. **早期正規化**: HTMLから抽出した直後にデータを正規化する
2. **型の一貫性**: 同じフィールドは常に同じ型で保存する
3. **Noneの扱い**: 抽出に失敗した場合はNoneを返す（例外を投げない）
4. **デバッグ情報**: field_nameパラメータを使用してエラーの特定を容易にする
5. **検証の実施**: データベース保存前に必ず検証を実行する

## トラブルシューティング

### TypeError: ('Argument must be int, not type %s' % type(arg))
整数型フィールドに文字列を渡している。`normalize_integer()` を使用して正規化する。

### ValueError: could not convert string to float
浮動小数点型フィールドに不正な文字列を渡している。`extract_area()` を使用して正規化する。

### 面積が小さすぎる値になる
単位の誤認識の可能性。`extract_area()` は自動的に㎡単位に変換します。

## 新しいスクレイパーの実装時の注意

1. 必ずdata_normalizerの関数を使用する
2. 生の正規表現ではなく、提供された抽出関数を使用する
3. 整数型フィールドは必ず `normalize_integer()` を通す
4. データ検証を実装し、不正なデータの保存を防ぐ