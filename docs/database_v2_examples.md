# データベース設計v2 動作例

## 1. 同一物件の複数掲載パターン

### ケース1: 同じ物件が複数のサイトに掲載
```
建物: ブリリアタワー東京
部屋: 1205号室

掲載情報:
1. SUUMO - 不動産会社A - 8,500万円
2. AtHome - 不動産会社B - 8,480万円
3. HOMES - 不動産会社A - 8,500万円
```

データ構造:
```sql
-- buildings テーブル
id: 1, normalized_name: "ブリリアタワー東京"

-- master_properties テーブル
id: 100, building_id: 1, room_number: "1205", area: 85.5

-- property_listings テーブル
id: 1001, master_property_id: 100, source_site: "SUUMO", agency_name: "不動産会社A", current_price: 8500
id: 1002, master_property_id: 100, source_site: "AtHome", agency_name: "不動産会社B", current_price: 8480
id: 1003, master_property_id: 100, source_site: "HOMES", agency_name: "不動産会社A", current_price: 8500
```

### ケース2: 同一サイト内での複数業者掲載
```
建物: パークコート青山
部屋: 801号室

SUUMO内の掲載:
1. 三井不動産リアルティ - 12,800万円
2. 東急リバブル - 12,900万円
3. 野村不動産アーバンネット - 12,750万円
```

データ構造:
```sql
-- property_listings テーブル（同じmaster_property_id、同じsource_site）
id: 2001, master_property_id: 200, source_site: "SUUMO", agency_name: "三井不動産リアルティ", current_price: 12800
id: 2002, master_property_id: 200, source_site: "SUUMO", agency_name: "東急リバブル", current_price: 12900
id: 2003, master_property_id: 200, source_site: "SUUMO", agency_name: "野村不動産アーバンネット", current_price: 12750
```

## 2. 建物名の標準化例

### 入力される様々な表記
```
1. "ザ・パークハウス　南青山"
2. "THE PARKHOUSE 南青山"
3. "ﾊﾟｰｸﾊｳｽ南青山"
4. "パークハウス南青山（賃貸可）"
```

### 標準化処理
```sql
-- buildings テーブル
id: 10, normalized_name: "パークハウス南青山"

-- building_aliases テーブル
building_id: 10, alias_name: "ザ・パークハウス　南青山", source: "SUUMO"
building_id: 10, alias_name: "THE PARKHOUSE 南青山", source: "AtHome"
building_id: 10, alias_name: "ﾊﾟｰｸﾊｳｽ南青山", source: "HOMES"
```

## 3. 価格履歴の管理

### 掲載別の価格変動追跡
```
物件: ブリリアタワー東京 1205号室
掲載: SUUMO - 不動産会社A

価格履歴:
2024-01-01: 8,800万円
2024-03-15: 8,600万円（値下げ）
2024-06-01: 8,500万円（再値下げ）
```

データ構造:
```sql
-- listing_price_history テーブル
property_listing_id: 1001, price: 8800, recorded_at: '2024-01-01'
property_listing_id: 1001, price: 8600, recorded_at: '2024-03-15'
property_listing_id: 1001, price: 8500, recorded_at: '2024-06-01'
```

## 4. API レスポンス例

### 物件一覧（重複排除済み）
```json
{
  "properties": [
    {
      "id": 100,
      "building": {
        "normalized_name": "ブリリアタワー東京",
        "address": "東京都中央区勝どき"
      },
      "room_number": "1205",
      "area": 85.5,
      "layout": "3LDK",
      "min_price": 8480,  // 全掲載の最安値
      "max_price": 8500,  // 全掲載の最高値
      "listing_count": 3,  // 掲載数
      "source_sites": ["SUUMO", "AtHome", "HOMES"]
    }
  ]
}
```

### 物件詳細（全掲載情報）
```json
{
  "master_property": {
    "id": 100,
    "building": { ... },
    "room_number": "1205",
    "area": 85.5
  },
  "listings": [
    {
      "id": 1001,
      "source_site": "SUUMO",
      "agency_name": "不動産会社A",
      "current_price": 8500,
      "url": "https://suumo.jp/..."
    },
    {
      "id": 1002,
      "source_site": "AtHome",
      "agency_name": "不動産会社B",
      "current_price": 8480,
      "url": "https://athome.co.jp/..."
    }
  ],
  "price_histories_by_listing": {
    "1001": [
      {"price": 8500, "recorded_at": "2024-06-01"},
      {"price": 8600, "recorded_at": "2024-03-15"},
      {"price": 8800, "recorded_at": "2024-01-01"}
    ],
    "1002": [
      {"price": 8480, "recorded_at": "2024-05-20"}
    ]
  }
}
```

## 5. メリット

1. **重複の完全排除**: 同一物件は必ず1つのmaster_propertyとして管理
2. **詳細な価格追跡**: 各掲載・各業者ごとの価格変動を個別に記録
3. **柔軟な検索**: 最安値・最高値での絞り込みが可能
4. **建物名の統一**: 表記ゆれを吸収し、検索精度が向上
5. **スケーラビリティ**: 新しい不動産サイトの追加が容易