# 重要仕様書 - 都心マンションDBシステム

このドキュメントは、システムの重要かつ複雑な仕様をまとめたものです。
仕様変更時は必ずこのドキュメントを更新してください。

最終更新日: 2025-01-26

## 目次

1. [建物名管理システム](#建物名管理システム)
2. [物件の自動紐付けルール](#物件の自動紐付けルール)
3. [スマートスクレイピング](#スマートスクレイピング)
4. [多数決システム](#多数決システム)
5. [リアルタイム更新トリガー](#リアルタイム更新トリガー)
6. [掲載状態管理](#掲載状態管理)

---

## 建物名管理システム

### 基本方針

1. **掲載情報からの直接取得**
   - 各サイトの建物名は`property_listings.listing_building_name`に保存
   - 掲載情報から直接多数決を実行

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

### 正規化処理

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

### 建物検索キー生成ロジック

```python
def canonicalize_building_name(building_name: str) -> str:
    # 1. 全角英数字→半角
    key = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
    # 2. スペースと記号の完全除去
    key = re.sub(r'[\s　・－―～〜\-]+', '', key)
    # 3. 大文字統一
    key = key.upper()
    return key
```

---

## 物件の自動紐付けルール

スクレイピング時に既存物件と自動的に紐付ける条件：

### 必須条件（すべて一致が必要）

1. **建物ID** - 完全一致
2. **階数** - 完全一致
3. **面積** - ±0.5㎡の許容誤差
4. **間取り** - 正規化後に完全一致
5. **方角** - 正規化後に完全一致（なしの場合はなし同士で一致）

### 部屋番号の特殊な扱い

- **両方に部屋番号がある場合**：一致が必要（異なる場合は別物件として扱う）
- **片方が未入力の場合**：部屋番号を無視して判定
- **理由**：同じ部屋でも別々の時期に販売される場合があるため、部屋番号が明確な場合は区別する

### 実装詳細

実装場所：`backend/app/scrapers/base_scraper.py`の`_get_or_create_master_property_with_session`メソッド

```python
# 既存のマスター物件を検索（絶対条件で）
query = session.query(MasterProperty).filter(
    MasterProperty.building_id == building.id
)

# 階数は必須条件
if floor_number is not None:
    query = query.filter(MasterProperty.floor_number == floor_number)
else:
    query = query.filter(MasterProperty.floor_number.is_(None))
    
# 面積は必須条件（0.5㎡の誤差を許容）
if area is not None:
    query = query.filter(
        MasterProperty.area.between(area - 0.5, area + 0.5)
    )
else:
    query = query.filter(MasterProperty.area.is_(None))

# 間取りは必須条件
if layout:
    normalized_layout = self.fuzzy_matcher.normalize_layout(layout)
    query = query.filter(MasterProperty.layout == normalized_layout)
else:
    query = query.filter(MasterProperty.layout.is_(None))

# 方角は必須条件（正規化して比較）
if direction:
    normalized_direction = self.fuzzy_matcher.normalize_direction(direction)
    query = query.filter(MasterProperty.direction == normalized_direction)
else:
    query = query.filter(MasterProperty.direction.is_(None))

# 部屋番号による絞り込み（特殊なロジック）
# 両方に部屋番号がある場合は一致が必要
# 片方のみの場合は無視して判定
```

---

## スマートスクレイピング

### 価格変更ベースの詳細取得

詳細ページの取得条件：
1. **強制取得モード**の場合
2. **新規物件**の場合
3. **価格が変更**されている場合（最重要）
4. **最終取得から指定日数経過**している場合（デフォルト90日）

### 環境変数設定
```bash
# 全スクレイパー共通
export SCRAPER_DETAIL_REFETCH_DAYS=90

# スクレイパー個別設定（優先）
export SCRAPER_SUUMO_DETAIL_REFETCH_DAYS=60
export SCRAPER_HOMES_DETAIL_REFETCH_DAYS=90

# スマートスクレイピングの有効/無効
export SCRAPER_SMART_SCRAPING=true
export SCRAPER_SUUMO_SMART_SCRAPING=false
```

### 価格変更検出の仕組み
1. 一覧ページから価格を取得
2. 既存データの価格と比較
3. 価格が異なる場合は詳細ページを取得して全情報を更新
4. 価格が同じ場合は最終確認日時のみ更新

---

## 多数決システム

### 建物名の多数決（2段階投票）

#### 現在の重み計算
- **単純な出現回数**のみを使用
- サイト別の優先順位は現在実装されていない

#### 掲載状態を考慮した多数決

**アクティブな掲載がある場合**：
- 24時間以内に確認された掲載情報（`is_active = True`）がある
- アクティブな掲載情報からの建物名のみを使用
- 非アクティブな掲載の情報は古い可能性があるため除外

**全ての掲載が非アクティブの場合**：
- 販売終了日（`sold_at`）から1週間以内の掲載情報を優先
- 1週間以内の情報がない場合は、全ての掲載を使用

#### 2段階投票アルゴリズムの処理フロー

```python
# 1. 掲載情報から建物名を取得（掲載状態を考慮）
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

### 建物・物件属性の多数決

物件の属性も掲載状態を考慮した多数決で決定：

#### 対象となる情報

**物件レベルの情報（master_propertiesテーブル）**：
- **階数** (`floor_number`): 所在階
- **専有面積** (`area`): 専有面積（㎡）
- **バルコニー面積** (`balcony_area`): バルコニー面積（㎡）
- **間取り** (`layout`): 部屋の間取り（例：3LDK）
- **方角** (`direction`): バルコニーの向き（例：南東）
- **管理費** (`management_fee`): 月額管理費（円）
- **修繕積立金** (`repair_fund`): 月額修繕積立金（円）
- **交通情報** (`station_info`): 駅からの距離、路線情報（可変的属性）

**建物レベルの情報（buildingsテーブル）**：
- **住所** (`address`): 建物の所在地（普遍的属性）
- **総階数** (`total_floors`): 建物の総階数（普遍的属性）
- **築年** (`built_year`): 建物の竣工年（普遍的属性）
- **構造** (`structure`): 建物構造（例：RC造）（普遍的属性）
- **建物名** (`normalized_name`): 表示用の建物名（2段階投票）

#### 普遍的属性と可変的属性の分類

システムは属性を2種類に分類し、異なる多数決ロジックを適用：

**普遍的属性（Immutable Attributes）**：
- 基本的に変化しない情報（住所、総階数、築年等）
- **全ての掲載履歴**（アクティブ+非アクティブ）から多数決
- より多くのデータを使用することで精度向上

**可変的属性（Mutable Attributes）**：
- 時間とともに変化する可能性がある情報（交通情報等）
- **アクティブな掲載のみ**から多数決
- 最新の情報を優先

#### 多数決の処理フロー
1. アクティブな掲載があるかチェック
2. 属性の種類（普遍的/可変的）に応じて対象掲載を選択
3. サイト優先順位を考慮して最頻値を決定（住所のみ）
4. その他の属性は単純な多数決（サイト優先順位なし）

### 広告文の判定パターン

`extract_building_name_from_ad_text()`関数で以下のパターンを除去：

#### 前方からの除去パターン
- 「独占」「期間限定」などの宣伝文句
- 価格情報（「○万円」）
- エリア情報（括弧内の「○○区」など）

#### 後方からの除去パターン
- 交通情報（「徒歩○分」「駅名」）
- 住所情報
- 間取り・階数情報
- 築年情報

#### 除去後の無効化処理

広告文除去処理は以下の場合に空文字を返します：

1. **記号のみが残った場合** - 英数字や日本語が含まれていない
2. **路線名のみが残った場合** - 「〜線」「JR〜」などの鉄道路線名のみ

これにより、広告文除去後に有効な建物名が残らなかった場合は、多数決の対象から除外されます。

---

## リアルタイム更新トリガー

建物名・属性は以下のタイミングで自動的に多数決により更新されます：

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

# 全物件の属性を多数決で更新
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py --target property

# 特定の物件のみ更新
docker exec realestate-backend poetry run python /app/backend/scripts/update_by_majority_vote.py --property-id 123
```

---

## 掲載状態管理

### アクティブ/非アクティブの判定
- **アクティブ**: 24時間以内に掲載が確認されている（`is_active = True`）
- **非アクティブ**: 24時間以上掲載が確認されていない（`is_active = False`）

### 掲載状態の自動更新
- スクレイパー実行時に自動更新
- 掲載が確認できた場合：`is_active = True`、`last_confirmed_at = 現在時刻`
- 掲載が確認できない場合：変更なし（別プロセスで非アクティブ化）

### 販売終了の判定
- 全ての掲載が非アクティブになった場合
- `master_properties.sold_at`に販売終了日時を記録
- 販売終了物件の最終価格は、販売終了前1週間の価格履歴から最も多く掲載されていた価格を使用

---

## 実装ファイル一覧

### コアロジック
- `/backend/app/scrapers/base_scraper.py`: スクレイピング基底クラス、広告文除去処理
- `/backend/app/utils/majority_vote_updater.py`: 多数決ロジック
- `/backend/app/utils/building_name_grouper.py`: 建物名グループ化ロジック
- `/backend/app/utils/building_name_normalizer.py`: 建物名正規化
- `/backend/app/utils/property_hasher.py`: 物件ハッシュ生成

### API/管理画面
- `/backend/app/api/admin.py`: 物件・建物統合、掲載状態更新
- `/backend/app/main.py`: 建物統合取り消し

### スクリプト
- `/backend/scripts/update_by_majority_vote.py`: バッチ更新スクリプト

### ドキュメント
- `/docs/BUILDING_NAME_MANAGEMENT_SPECIFICATION.md`: 建物名管理システム詳細仕様
- `/docs/MAJORITY_VOTE_SYSTEM.md`: 多数決システム詳細仕様
- `/docs/CRITICAL_SPECIFICATIONS.md`: 本ドキュメント
- `/CLAUDE.md`: プロジェクト全体の概要

---

## 今後の改善案

1. **サイト別の優先順位設定**
   - サイトごとの信頼性に基づく重み付け投票
   - カスタマイズ可能な優先順位設定

2. **建物名の変更履歴**
   - 建物名がいつ、どのように変更されたかの履歴
   - 変更理由の記録

3. **より高度な広告文判定**
   - 機械学習による広告文の判定
   - カスタムルールの追加

---

## データベース構造

### buildingsテーブルの主要カラム
- `id`: 建物ID
- `normalized_name`: 表示用の建物名（多数決で決定）
- `canonical_name`: 検索用の正規化された建物名
- `is_valid_name`: 建物名が妥当かどうか（Boolean）
- `address`: 住所（多数決で決定）
- `total_floors`: 総階数（多数決で決定）
- `built_year`: 築年（多数決で決定）

### property_listingsテーブルの主要カラム
- `master_property_id`: 物件ID
- `source_site`: 情報源（SUUMO、HOMES等）
- `listing_building_name`: 各サイトに掲載されている建物名
- `is_active`: 掲載中フラグ
- `listing_floor_number`: この掲載での階数情報
- `listing_area`: この掲載での専有面積
- `listing_layout`: この掲載での間取り
- `listing_direction`: この掲載での方角
- `listing_total_floors`: この掲載での総階数
- `listing_address`: この掲載での住所

---

## 変更履歴

### 2025-01-26
- ドキュメント大幅改訂
- BuildingAliasテーブルへの言及を削除（実装されていないため）
- サイト優先度の重み付けを「今後の改善案」に移動（実装されていないため）
- 広告文ペナルティへの言及を削除（実装されていないため）
- 実際の実装に合わせて内容を更新
- 普遍的属性と可変的属性の分類を追加
- 物件の自動紐付けルールを追加

### 2025-01-25
- 初版作成
