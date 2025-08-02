# 多数決システム仕様書

最終更新日: 2025-01-28

## 概要

本システムでは、複数の不動産情報サイトから収集した物件情報を統合管理するために、多数決システムを採用しています。同一物件でもサイトによって情報が異なる場合があるため、多数決により最も信頼性の高い情報を決定します。

## 1. 建物名の多数決システム

### 1.1 基本的な仕組み

建物名は以下の2つのレベルで管理されます：

1. **建物レベル** (`buildings.normalized_name`) ※2025年1月改訂
   - 建物全体で共通の表示用建物名
   - `property_listings.listing_building_name`から直接多数決で決定
   - `building_aliases`は補助的な役割（掲載情報がない場合のフォールバック）

2. **物件レベル** (`master_properties.display_building_name`) ※2025年1月追加
   - 各物件（部屋）固有の表示用建物名
   - その物件に紐づく`property_listings`の`listing_building_name`から多数決で決定

### 1.2 データ構造

#### 関連テーブル

```sql
-- 建物マスター
buildings
├── id
├── normalized_name       -- 多数決で決定された建物名
└── ...

-- 物件掲載情報（建物名の主要なソース）
property_listings
├── master_property_id
├── source_site
├── listing_building_name -- この掲載での建物名（多数決の元データ）
└── is_active            -- 掲載中かどうか

-- 物件マスター
master_properties
├── id
├── building_id
├── display_building_name -- 物件独自の表示用建物名（多数決で決定）
└── ...

-- 注：building_aliasesテーブルは現在のスキーマには存在しません
-- 建物名の表記ゆれは property_listings.listing_building_name で管理されています
```

### 1.3 多数決アルゴリズム

#### 重み付け投票

1. **基本の重み**: 出現回数
2. **サイト優先度による重み付け**:
   - SUUMO: 5倍
   - LIFULL HOME'S: 4倍
   - 三井のリハウス: 3倍
   - ノムコム: 2倍
   - 東急リバブル: 1倍

3. **広告文ペナルティ**: 0.1倍
   - 「徒歩○分」「○○駅」などの広告的な文言を含む場合

#### 掲載状態を考慮した多数決

**アクティブな掲載がある場合**：
- 24時間以内に確認された掲載情報（`is_active = True`）のみを使用
- 非アクティブな掲載の情報は古い可能性があるため除外

**全ての掲載が非アクティブの場合**：
- 販売終了日から1週間以内の掲載情報を優先
- 1週間以内の情報がない場合は、全ての情報を使用

### 1.4 更新タイミング

#### 建物レベルの建物名更新

1. **掲載情報の追加・更新時**
   - `base_scraper.py`の`create_or_update_listing`メソッド
   - 新しい`listing_building_name`が追加された時
   - 既存の掲載情報が更新された時

2. **掲載情報の削除時**
   - 掲載が終了した時（`is_active = False`）
   - 残りのアクティブな掲載から再計算

3. **物件・建物統合時**
   - 管理画面での手動統合操作時
   - 関連する掲載情報が統合される時

#### 物件レベルの建物名更新

1. **掲載情報の追加・更新時**
   - 新しい掲載情報が追加された時
   - 既存の掲載情報が更新された時

2. **掲載情報の削除時**
   - 掲載が終了した時（`is_active = False`）
   - 残りのアクティブな掲載から再計算

## 2. その他の属性の多数決

### 2.1 対象となる情報

#### 物件レベルの情報（`master_properties`テーブル）
- **管理費** (`management_fee`)
- **修繕積立金** (`repair_fund`)
- **交通情報** (`station_info`)

#### 建物レベルの情報（`buildings`テーブル）
- **住所** (`address`)
- **総階数** (`total_floors`)
- **築年** (`built_year`)
- **構造** (`structure`)

### 2.2 多数決の方法

物件の付属情報も建物名と同様のアルゴリズムで決定：
1. アクティブな掲載を優先
2. サイト優先順位を考慮
3. 最頻値を採用

### 2.3 価格情報の特別処理

価格は多数決ではなく、以下のルールで処理：
- **表示**: 最小値〜最大値の範囲表示
- **対象**: アクティブな掲載の価格のみ
- **販売終了物件**: `last_sale_price`を使用

## 3. 実装詳細

### 3.1 主要クラス・メソッド

#### `MajorityVoteUpdater`クラス（`backend/app/utils/majority_vote_updater.py`）

主要メソッド：
- `update_building_name_by_majority(building_id)`: 建物名を多数決で更新
- `update_property_building_name_by_majority(property_id)`: 物件の建物名を多数決で更新
- `update_master_property_by_majority(property)`: 物件の付属情報を多数決で更新
- `update_building_by_majority(building)`: 建物の付属情報を多数決で更新

### 3.2 処理フロー

```python
# 1. 掲載情報の保存時
listing = create_or_update_listing(
    ...,
    listing_building_name="パークハウス白金"  # 掲載での建物名を保存
)

# 2. 建物レベルの建物名更新（property_listingsから直接集計）
update_building_name_by_majority(building_id)

# 3. 物件レベルの建物名更新（関連するproperty_listingsから集計）
update_property_building_name_by_majority(property_id)

# 4. 建物名エイリアスの追加（補助データとして）
_add_building_alias(building_id, "パークハウス白金")
```

## 4. メリット

### 4.1 データの信頼性向上
- 複数のソースから最も信頼できる情報を自動選択
- サイトの信頼度を考慮した重み付け
- 広告文の自動除外

### 4.2 リアルタイム性
- 掲載情報の変更が即座に建物名に反映
- BuildingAliasを介さない直接的な集計により、最新の情報を使用
- 掲載の追加・削除に完全に連動した多数決

### 4.3 エラー検出
- 物件が誤った建物に紐付けられた場合、物件レベルの建物名との不一致で検出可能
- 管理画面で視覚的に確認可能（異なる建物名は赤色表示）

## 5. 注意事項

### 5.1 パフォーマンス
- 多数決計算は掲載情報の更新時にリアルタイムで実行
- 大量の掲載情報がある場合は処理時間に注意

### 5.2 データ整合性
- 建物レベルと物件レベルの建物名が異なる場合がある
- これは正常な動作（物件の誤った紐付けを検出するため）

### 5.3 BuildingAliasの役割
- 2025年1月の改訂により、BuildingAliasは補助的な役割に変更
- 主に以下の場合に使用：
  - 掲載情報が存在しない建物の場合のフォールバック
  - 建物名の履歴管理
  - 表記ゆれの統計情報として

## 6. 関連ドキュメント

- [重要仕様書](CRITICAL_SPECIFICATIONS.md) - 建物名管理システムの詳細
- [データベース管理](../backend/DATABASE_MANAGEMENT.md) - テーブル構造の詳細
- [スクレイパー仕様](SCRAPER_SPECIFICATION.md) - スクレイピング時の処理