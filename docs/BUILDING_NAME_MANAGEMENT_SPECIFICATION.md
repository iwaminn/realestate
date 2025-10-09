# 建物名管理システム仕様書

## 概要

本システムは、複数の不動産情報サイトから収集した建物名を統一的に管理し、2段階投票アルゴリズムにより最適な建物名を決定する仕組みを提供します。

## 基本方針

1. **掲載情報からの直接取得**
   - 各サイトの建物名は`property_listings.listing_building_name`に保存
   - BuildingAliasテーブルは使用せず、掲載情報から直接多数決を実行

2. **2段階投票アルゴリズム**
   - **第1段階**: BuildingNameGrouperで表記ゆれをグループ化
   - **第2段階**: グループ内で最頻出の表記を選択

3. **広告文の除去**
   - 多数決の前に広告文除去処理を適用
   - 「徒歩○分」「駅名」などの広告的要素を除去

4. **掲載状態を考慮**
   - アクティブな掲載があればアクティブな掲載のみから取得
   - 全て非アクティブの場合は販売終了から1週間以内の掲載を優先
   - 1週間以内の情報がない場合は全ての掲載を使用

## データベース構造

### buildingsテーブル
- `id`: 建物ID
- `normalized_name`: 表示用の建物名（多数決で決定）
- `canonical_name`: 検索用の正規化された建物名
- `is_valid_name`: 建物名が妥当かどうか（Boolean）
- `address`: 住所
- その他の建物属性

### property_listingsテーブル
- `master_property_id`: 物件ID
- `source_site`: 情報源（SUUMO、HOMES等）
- `listing_building_name`: 各サイトに掲載されている建物名
- `is_active`: 掲載中フラグ

## 処理フロー

### 1. 建物名の多数決更新

`MajorityVoteUpdater.update_building_name_by_majority()`メソッドで実行：

```python
# 1. 掲載情報から建物名を取得
#    - アクティブな掲載があればアクティブな掲載のみ
#    - 全て非アクティブなら販売終了から1週間以内を優先
#    - それもなければ全ての掲載を使用

# 2. 広告文除去処理を適用
cleaned_names = [extract_building_name_from_ad_text(name) for name in raw_names]

# 3. BuildingNameGrouperでグループ化（第1段階投票）
grouped_names = grouper.group_building_names(cleaned_names)

# 4. 各グループの合計重みを計算
group_weights = {group: sum(weights) for group, names in grouped_names.items()}

# 5. 最も重みの高いグループを選択

# 6. グループ内で最適な表記を選択（第2段階投票）
best_name = grouper.find_best_representation(group_names, weights)

# 7. 建物名を更新
building.normalized_name = normalize_building_name(best_name)
building.canonical_name = canonicalize_building_name(best_name)
```

### 2. 正規化処理

#### normalize_building_name（表示用）
- 全角英数字→半角
- スペースの統一
- 記号の正規化
- 元の表記をできるだけ保持

#### canonicalize_building_name（検索用）
- より強力な正規化
- スペース・記号の完全除去
- 大文字統一
- 建物の同一性判定に使用

## 2段階投票アルゴリズムの詳細

### 第1段階：グループ化

表記ゆれを統合してグループ化：

**例**：
```
入力:
  - "白金ザ・スカイ東棟" (3票)
  - "白金ザ・スカイE棟" (2票)
  - "白金ザスカイ　東棟" (1票)
  - "パークコート麻布十番" (5票)

グループ化結果:
  グループA: ["白金ザ・スカイ東棟", "白金ザ・スカイE棟", "白金ザスカイ　東棟"] (6票)
  グループB: ["パークコート麻布十番"] (5票)

選択: グループA（6票で最多）
```

### 第2段階：最適な表記の選択

選択されたグループ内で最頻出の表記を選択：

```
グループA内:
  - "白金ザ・スカイ東棟": 3票（最多）
  - "白金ザ・スカイE棟": 2票
  - "白金ザスカイ　東棟": 1票

結果: "白金ザ・スカイ東棟"
```

## 広告文の判定と除去

`extract_building_name_from_ad_text()`関数で以下のパターンを除去：

### 前方からの除去パターン
- 「独占」「期間限定」などの宣伝文句
- 価格情報（「○万円」）
- エリア情報（括弧内の「○○区」など）

### 後方からの除去パターン
- 交通情報（「徒歩○分」「駅名」）
- 住所情報
- 間取り・階数情報
- 築年情報

### 例
```
入力: "【独占公開】パークコート麻布十番 港区麻布十番 3LDK 15階"
出力: "パークコート麻布十番"
```

## 重み付けロジック

現在の実装では**単純な出現回数**を使用：

```python
# 各建物名の重み = 掲載数
weight = count  # property_listingsでの出現回数
```

**注**: サイト別の優先順位（SUUMO > HOMES > ...）は現在実装されていません。

## 更新タイミング

建物名は以下のタイミングで自動的に多数決により更新されます：

### 1. スクレイピング時
- `base_scraper.py`の`create_or_update_listing()`メソッドで自動実行
- 新しい掲載情報を登録・更新した際に実行

### 2. 物件統合時
- 管理画面で物件重複管理機能を使用して物件を統合した際
- 統合により掲載情報が移動し、建物に紐づく情報が変わるため

### 3. 建物統合時
- 管理画面で建物重複管理機能を使用して建物を統合した際
- 複数の建物の情報が統合されるため

### 4. 統合の取り消し時
- 物件統合または建物統合を取り消して復元した際
- 掲載情報が元に戻るため、両方の建物の情報が変わる

### 5. 手動更新（バッチ処理）

必要に応じて手動でバッチ更新も可能：

```bash
# 全建物の名前を多数決で更新
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py --target building

# 特定の建物のみ更新
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py --property-id 123
```

## 建物名の品質管理

### is_valid_name フラグ

建物名が妥当かどうかを示すフラグ：

- **True**: 正常な建物名
- **False**: 広告文や不適切な名前（例：「港区の中古マンション」）

多数決で建物名が更新された場合、`is_valid_name`は自動的に`True`に設定されます。

### 検証ルール

広告文除去処理（`extract_building_name_from_ad_text`）が以下をチェック：

1. 駅名や交通情報が含まれていないか
2. 「の中古マンション」で終わっていないか
3. 最低文字数（3文字以上）
4. 価格・間取り情報が含まれていないか

## メリット

1. **シンプル**: BuildingAliasテーブルを使わず、掲載情報から直接取得
2. **精度**: 2段階投票で表記ゆれを適切に統合
3. **最新性**: アクティブな掲載を優先して最新情報を反映
4. **透明性**: どの建物名がどれだけの票を得たかログに記録

## 注意事項

1. **初期データ**: 新規建物は最初に登録された名前が使用される
2. **更新頻度**: リアルタイム更新により常に最新の多数決結果を反映
3. **手動修正**: 必要に応じて管理画面から手動修正も可能（ただし次回の多数決で上書きされる可能性）
4. **サイト優先順位**: 現在は実装されていない（将来の拡張として検討可能）

## 関連ファイル

- `backend/app/utils/majority_vote_updater.py` - 多数決ロジックの実装
- `backend/app/utils/building_name_grouper.py` - 建物名グループ化ロジック
- `backend/app/scrapers/base_scraper.py` - 広告文除去処理
- `backend/scripts/update_by_majority_vote.py` - バッチ更新スクリプト
