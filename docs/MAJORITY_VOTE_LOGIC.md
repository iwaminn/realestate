# 多数決による物件情報統合ロジック

## 概要

本システムでは、複数の不動産サイトから取得した同一物件の情報を統合する際、多数決ロジックを使用して最も信頼性の高い情報を自動的に選択します。

## 基本原則

1. **多数決の原則**: 最も多くのサイトが同じ値を報告している場合、その値を採用
2. **優先順位の原則**: 同数の場合は、サイトの信頼性に基づく優先順位で決定
3. **補完の原則**: 情報がない項目は、他のサイトの情報で補完

## サイト優先順位

同数票の場合、以下の優先順位で情報源を選択します：

1. **SUUMO** (最優先)
2. **LIFULL HOME'S**
3. **三井のリハウス**
4. **ノムコム**

この優先順位は、各サイトのデータ品質と更新頻度を考慮して設定されています。

## 対象となる情報

### 物件情報（MasterProperty）
- 階数（floor_number）
- 専有面積（area）
- 間取り（layout）
- 方角（direction）
- バルコニー面積（balcony_area）

### 建物情報（Building）
- 総階数（total_floors）- 物件の最大階数から推定
- 住所（address）- 通常は変更されないが、データ品質向上のため

## 実装詳細

### データ構造

各不動産サイトの掲載情報（PropertyListing）に、サイト固有の物件属性を保存：

```sql
-- PropertyListingテーブルの拡張フィールド
listing_floor_number     INTEGER    -- この掲載での階数情報
listing_area            FLOAT      -- この掲載での専有面積
listing_layout          VARCHAR(50) -- この掲載での間取り
listing_direction       VARCHAR(50) -- この掲載での方角
listing_total_floors    INTEGER    -- この掲載での総階数
listing_balcony_area    FLOAT      -- この掲載でのバルコニー面積
listing_address         TEXT       -- この掲載での住所
```

### 多数決アルゴリズム

```python
# 1. 各サイトの値を収集
values = {
    "10階": ["suumo", "homes"],
    "11階": ["nomu"],
    "10F": ["rehouse"]
}

# 2. 正規化（"10階" と "10F" は同じとみなす）
normalized_values = {
    10: ["suumo", "homes", "rehouse"],
    11: ["nomu"]
}

# 3. 最頻値を特定
# 10階: 3票（最多）
# 11階: 1票

# 4. 結果: 10階を採用
```

### 同数の場合の処理

```python
# 例: 2サイトずつが異なる値を報告
values = {
    "南向き": ["homes", "nomu"],
    "南東向き": ["suumo", "rehouse"]
}

# サイト優先順位を適用
# "南東向き"にはsuumo（優先度1）が含まれる
# "南向き"の最高優先度はhomes（優先度2）

# 結果: "南東向き"を採用（SUUMOの情報を優先）
```

## 更新タイミング

多数決による更新は以下のタイミングで実行されます：

1. **自動更新**: 新しい掲載情報が追加された時
2. **バッチ更新**: 定期的な一括更新処理
3. **手動更新**: 管理画面からの手動実行

## 実行方法

### 1. データベースの準備

```bash
# 新しいカラムを追加
docker exec realestate-backend poetry run python /app/backend/scripts/add_listing_attributes.py
```

### 2. バッチ更新の実行

```bash
# ドライラン（確認のみ）
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py

# 実際に更新
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py --execute
```

### 3. 個別物件の更新

スクレイパー内で自動的に実行されます：

```python
# スクレイパーのコード例
listing = self.create_or_update_listing(
    master_property=master_property,
    url=url,
    title=title,
    price=price,
    # 掲載サイトごとの属性
    listing_floor_number=10,
    listing_area=65.5,
    listing_layout="2LDK",
    listing_direction="南"
)

# 多数決による更新
self.update_master_property_by_majority(master_property)
```

## 注意事項

1. **データの正規化**: 同じ情報でも表記が異なる場合があるため、適切な正規化が必要
   - 例: "10階" vs "10F" → 両方とも10として扱う
   - 例: "南向き" vs "南" → 統一した表記に変換

2. **部分的な情報**: すべてのサイトがすべての情報を持っているわけではない
   - 情報がないサイトは多数決の投票から除外
   - 1サイトしか情報を持たない場合は、その情報を採用

3. **更新の透明性**: どの情報がどのサイトから採用されたかをログに記録
   ```
   → floor_number: 10 → 11 (多数決)
   → direction: None → 南向き (多数決)
   ```

## 将来の拡張

1. **重み付け投票**: サイトごとに異なる重みを設定
2. **時系列考慮**: 最新の情報により高い重みを付与
3. **信頼度スコア**: 各サイトの過去の正確性に基づくスコアリング
4. **異常値検出**: 明らかに間違った情報の自動除外

## 関連ファイル

- `/backend/app/utils/majority_vote_updater.py` - 多数決ロジックの実装
- `/backend/app/scrapers/base_scraper.py` - スクレイパー基底クラスの多数決メソッド
- `/backend/scripts/update_by_majority_vote.py` - バッチ更新スクリプト
- `/backend/scripts/add_listing_attributes.py` - データベース拡張スクリプト