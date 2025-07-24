# 不動産スクレイパー仕様書

## 概要

このドキュメントは、マンション一括検索システムで使用されるスクレイパーの仕様と実装詳細を記載しています。

## 重要：データ正規化フレームワークの使用

**すべてのスクレイパーは必ずデータ正規化フレームワークを使用してください。**
詳細は [DATA_NORMALIZATION_GUIDE.md](./DATA_NORMALIZATION_GUIDE.md) を参照。

### 必須要件
1. 整数型フィールドは `normalize_integer()` で正規化
2. 価格は `extract_price()` で抽出（万円単位）
3. 面積は `extract_area()` で抽出（㎡単位）
4. 階数は `extract_floor_number()` で抽出
5. 間取りは `normalize_layout()` で正規化
6. 方角は `normalize_direction()` で正規化
7. 駅情報は `format_station_info()` でフォーマット
8. 月額費用は `extract_monthly_fee()` で抽出（円単位）

## スクレイピング対象サイト

1. **SUUMO** (suumo.jp)
2. **LIFULL HOME'S** (homes.co.jp) 
3. **AtHome** (athome.co.jp) - 実装済みだがCAPTCHA対策が必要
4. **三井のリハウス** (rehouse.co.jp)
5. **ノムコム** (nomu.com) - 野村不動産アーバンネット

## スクレイピングの基本フロー

### 1. 全体の流れ

```
1. エリア指定でスクレイピング開始
   ↓
2. 一覧ページから物件情報を取得（ページング対応）
   ↓
3. 各物件について：
   a. 基本情報を一覧から取得
   b. 新規または更新された物件は詳細ページを取得
   c. データベースに保存
   ↓
4. 非アクティブな物件をマーク
```

### 2. スマートスクレイピング戦略

#### 重要：価格変更ベースの詳細取得（2025年1月改訂）

- **新規物件**: 詳細ページを必ず取得
- **既存物件**: 
  - **価格が変更されている場合は詳細を再取得**（最優先）
  - 90日以上詳細を取得していない場合は再取得（環境変数で設定可能）
  - それ以外は一覧ページの情報のみで更新
- **強制詳細取得モード**: `force_detail_fetch=True`オプションですべての物件の詳細を取得

**注意事項**：
- 更新マーク（NEW、更新日表示など）は参考情報として取得するが、詳細取得の判断基準としては使用しない
- 価格変更の検出は一覧ページの価格と既存データの価格を比較して行う
- 価格が取得できない場合は、安全のため詳細ページを取得する

## 取得する情報

### 1. 建物情報 (buildings テーブル)

| 項目 | 説明 | 取得元 |
|------|------|--------|
| normalized_name | 正規化された建物名 | 一覧・詳細 |
| address | 住所 | 一覧・詳細 |
| total_floors | 総階数（地下含む） | 詳細 |
| total_units | 総戸数 | 詳細 |
| built_year | 築年 | 一覧・詳細 |
| structure | 構造（RC、SRC等） | 詳細 |
| land_rights | 権利形態（所有権、定期借地権等） | 詳細 |
| parking_info | 駐車場情報 | 詳細 |

### 2. 物件マスター情報 (master_properties テーブル)

| 項目 | 説明 | 取得元 |
|------|------|--------|
| building_id | 建物ID | - |
| room_number | 部屋番号 | 詳細 |
| floor_number | 階数 | 一覧・詳細 |
| area | 専有面積 | 一覧・詳細 |
| balcony_area | バルコニー面積 | 詳細 |
| layout | 間取り | 一覧・詳細 |
| direction | 方角 | 一覧・詳細 |
| summary_remarks | 備考要約 | 自動生成 |

### 3. 掲載情報 (property_listings テーブル)

| 項目 | 説明 | 取得元 |
|------|------|--------|
| master_property_id | 物件マスターID | - |
| source_site | サイト名 | - |
| site_property_id | サイト内物件ID | URL |
| url | 物件URL | 一覧 |
| title | タイトル | 一覧・詳細 |
| current_price | 現在価格 | 一覧・詳細 |
| management_fee | 管理費 | 詳細 |
| repair_fund | 修繕積立金 | 詳細 |
| agency_name | 不動産会社名 | 一覧・詳細 |
| agency_tel | 不動産会社電話番号 | 詳細 |
| station_info | 最寄り駅情報 | 一覧・詳細 |
| description | 物件説明 | 詳細 |
| remarks | 備考 | 詳細 |
| is_active | アクティブフラグ | - |
| has_update_mark | 更新マーク | 一覧 |
| detail_fetched_at | 詳細取得日時 | - |
| list_update_date | 一覧更新日 | 一覧 |

## サイト別の実装詳細

### SUUMO (SuumoScraper)

#### 一覧ページ
- URL形式: `/jj/bukken/ichiran/JJ012FC001/?ar=030&bs=011&sc={area_code}&ta=13&po=0&pj={page}&pc=100`
- 1ページあたり100件表示
- セレクタ:
  - 物件要素: `.property_unit`
  - 建物名: `.dottable-line`内の「物件名」
  - 価格: `.dottable-value`
  - 不動産会社: `.shopmore-title`
  - 新着/更新: `.property_unit-newmark`, `.property_unit-update`

#### 詳細ページ  
- セレクタ:
  - 物件概要: `.outline-info-tbl`
  - **所在階**: 物件概要テーブル内の単独フィールド「所在階」または「所在階ヒント」
  - **向き**: 物件概要テーブル内の単独フィールド「向き」または「向きヒント」
  - バルコニー面積: 「その他面積」欄内の「バルコニー面積：X.XXm2」
  - 総階数: 「構造・階建て」欄内の「XX階地下X階建」形式
  - 権利形態: テーブル内の「土地権利」「敷地権利」等の行
  - 駐車場: テーブル内の「駐車」を含む行
  - 管理費・修繕積立金: テーブル内の対応する行
  - 備考: 長文テキストから物件説明を抽出
  - 情報提供日: 「情報提供日」「情報公開日」「情報登録日」「登録日」等のフィールド

### LIFULL HOME'S (HomesScraper)

#### 一覧ページ
- URL形式: `/mansion/chuko/tokyo/{area}/list/?page={page}`
- セレクタ:
  - 物件要素: `.mod-mergeBuilding`
  - リンク: `a.prg-bukkenNameAnchor`
  - 新着/更新: 画像のalt属性で判定

#### 詳細ページ
- セレクタ:
  - 価格: `.priceLabel`
  - 詳細情報: `.detailInfo dl`
  - **主要採光面（向き）**: dlタグ内の「向き」「方角」「バルコニー」「採光」を含むラベル
  - 総階数: 「所在階/階数」欄で「XX階/XX階建（地下X階）」形式から抽出
  - 権利形態: テーブル内の「土地権利」「敷地権利」等の行
  - 駐車場: テーブル内の「駐車」を含む行
  - 管理費等: テーブル内の「管理費等」行
  - バルコニー面積: テーブル内の「バルコニー面積」行
  - 不動産会社: ページテキストから「問合せ先：」パターンで抽出
  - 備考: テーブル内の「備考」行
  - 情報公開日: ページテキストから「情報公開日：YYYY/MM/DD」パターンで抽出

### 三井のリハウス (RehouseScraper)

#### 一覧ページ
- URL形式: `/buy/mansion/prefecture/{都道府県コード}/city/{市区町村コード}/`
- 東京都港区の例: `/buy/mansion/prefecture/13/city/13103/`
- ページング: `?p={page}` パラメータ
- セレクタ:
  - 物件要素: 複数のセレクタを試行（`.property-item`, `.bukken-item` 等）
  - リンク: `a[href*="/bkdetail/"]`
  - 物件コード: URLから `/bkdetail/{物件コード}/` パターンで抽出

#### 詳細ページ
- URL形式: `/buy/mansion/bkdetail/{物件コード}/`
- セレクタ:
  - 価格: テーブル内の「価格」行、またはページ内の「XX万円」パターン
  - 物件名: `h1`タグ
  - 詳細情報: テーブル構造またはdl/dt/dd構造から抽出
  - **向き**: テーブル内の「向き」「採光」「バルコニー」を含むラベル
  - 総階数: テーブル内の「構造」「建物」行から「XX階建」パターンで抽出
  - 所在階: テーブル内の「所在階」「階数」行
  - 面積: テーブル内の「専有面積」「面積」行
  - 間取り: テーブル内の「間取り」行
  - バルコニー面積: テーブル内の「バルコニー」を含む行
  - 管理費: テーブル内の「管理費」行
  - 修繕積立金: テーブル内の「修繕積立金」「修繕積立費」行
  - 住所: テーブル内の「所在地」「住所」行
  - 交通情報: テーブル内の「交通」「駅」行
  - 取引態様: テーブル内の「取引態様」行
  - 現況: テーブル内の「現況」行
  - 引渡時期: テーブル内の「引渡」行
  - 不動産会社: `.agency-name`, `.company-name` 等のセレクタ
  - 電話番号: ページ内の電話番号パターン（0X-XXXX-XXXX）
  - 情報公開日: ページテキストから日付パターンで抽出
  - 備考: `.remarks`, `.feature`, `.comment` 等のセレクタ

## エラーハンドリング

### 基本的なエラー処理

1. **ネットワークエラー**: 3回までリトライ
2. **404エラー**: 物件を非アクティブとしてマーク
3. **CAPTCHA**: エラーログに記録（AtHomeで発生）
4. **レート制限**: デフォルト1秒の遅延（環境変数で設定可能）

### 安全設計の原則

**重要**: 詳細ページで正しくデータが取得できなくなった場合、データの登録・更新を行わずエラーとして処理することで、不正確なデータの混入を防ぎます。

1. **詳細ページ解析の失敗時の動作**:
   - 詳細ページの解析に失敗した場合、その物件はスキップされます
   - 不完全なデータでの登録・更新は行いません
   - エラーは詳細なコンテキストと共にログに記録されます
   - エラー統計にカウントされ、サーキットブレーカーの判定に使用されます

2. **データ検証の失敗時の動作**:
   - 必須フィールドの欠如や不正な値を検出した場合、その物件はスキップされます
   - 検証エラーの詳細（どのフィールドが問題か）がログに記録されます
   - 部分的に正しいデータであっても、検証に失敗した場合は保存されません

3. **例外処理の設計**:
   ```python
   # 各スクレイパーでの実装例
   def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
       try:
           # 詳細ページの解析処理
           ...
       except Exception as e:
           # エラーをログに記録
           self.record_error('parsing', url=url, error=e)
           # Noneを返すことで、この物件の処理をスキップ
           return None
   ```

### サーキットブレーカー機能

誤ったデータの大量更新を防ぐため、すべてのスクレイパーに以下の安全機能が実装されています：

#### 1. エラー閾値による自動停止
- **エラー率監視**: 処理した物件のうち、エラー率が50%を超えた場合に自動停止
- **最低試行回数**: 10件以上処理してからエラー率をチェック（少数のエラーで停止しない）
- **環境変数設定**:
  ```bash
  SCRAPER_ERROR_THRESHOLD=0.5  # エラー率の閾値（0.5 = 50%）
  SCRAPER_MIN_ATTEMPTS=10      # エラー率チェック前の最低試行回数
  ```

#### 2. 連続エラーによる自動停止
- **連続エラー検知**: 10件連続でエラーが発生した場合に自動停止
- **環境変数設定**:
  ```bash
  SCRAPER_CONSECUTIVE_ERROR_LIMIT=10  # 連続エラーの上限
  ```

#### 3. サーキットブレーカーの無効化
- 必要に応じて機能を無効化可能:
  ```bash
  SCRAPER_CIRCUIT_BREAKER=false  # サーキットブレーカーを無効化
  ```

### データ検証機能

#### 1. 強化されたデータ検証
各スクレイパーは`base_scraper.py`の共通検証ロジックを使用します：

**必須フィールドの検証**:
- `url`: 有効なHTTP/HTTPS URLか
- `price`: 100万円〜100億円の範囲内か
- `building_name`: 3文字以上100文字以下か
- `area`: 10㎡〜1000㎡の範囲内か（オプション）
- `layout`: 20文字以下か（オプション）
- `floor_number`: -5階〜100階の範囲内か（オプション）

**データ整合性チェック**:
- 階数の整合性: `floor_number` ≤ `total_floors`
- 汎用的な建物名の拒否: "港区の物件"、"物件"、"東京都の物件"、"不明"
- 駅名だけの建物名を拒否

**共通検証メソッド**:
```python
# base_scraper.py で提供される共通メソッド
- validate_property_data(): 基本的な必須フィールド検証
- enhanced_validate_property_data(): 型チェックと範囲チェックを含む詳細検証
- validate_html_structure(): HTML構造の検証
- is_advertising_text(): 広告テキストの検出
```

#### 2. HTML構造検証
サイトのHTML構造が変更された場合を検知：
- 各スクレイパーは必須セレクタの存在を確認
- 必要な要素が見つからない場合は警告を出してスキップ

### エラー統計の追跡

スクレイパーは以下のエラー統計を記録します：
- `total_attempts`: 総試行回数
- `total_errors`: 総エラー数
- `validation_errors`: データ検証エラー
- `parsing_errors`: HTML解析エラー
- `saving_errors`: 保存エラー
- `detail_page_errors`: 詳細ページ取得エラー

これらの統計は管理画面で確認できます。

### エラーハンドリングの実装例

```python
# BaseScraper の主要メソッド

def enhanced_validate_property_data(self, property_data):
    """強化されたデータ検証"""
    # 必須フィールドと型チェック
    # 値の範囲チェック
    # データ整合性チェック
    
def validate_html_structure(self, soup, required_selectors):
    """HTML構造の検証"""
    # 必須要素の存在確認
    
def check_circuit_breaker(self):
    """サーキットブレーカーのチェック"""
    # エラー率の計算
    # 連続エラーのチェック
    # 閾値を超えたら例外を投げて停止
    
def record_success(self):
    """成功を記録"""
    # 連続エラーカウントをリセット
    
def record_error(self, error_type):
    """エラーを記録してサーキットブレーカーをチェック"""
    # エラータイプ別にカウント
    # サーキットブレーカーの発動チェック
```

## 環境変数

```bash
# 詳細ページ再取得までの日数（デフォルト: 90日）
DETAIL_REFETCH_DAYS=90

# スクレイピング時の遅延（秒）
SCRAPER_DELAY=1

# サーキットブレーカー設定
SCRAPER_ERROR_THRESHOLD=0.5          # エラー率の閾値（0.5 = 50%）
SCRAPER_MIN_ATTEMPTS=10              # エラー率チェック前の最低試行回数
SCRAPER_CONSECUTIVE_ERROR_LIMIT=10   # 連続エラーの上限
SCRAPER_CIRCUIT_BREAKER=true         # サーキットブレーカーの有効/無効
```

## 実行方法

### 全サイトスクレイピング
```bash
docker compose exec backend poetry run python backend/scripts/scrape_all.py
```

### 特定サイトのみ
```bash
docker compose exec backend poetry run python backend/scripts/run_scrapers.py --scraper suumo --max-pages 5
```

### 強制詳細取得モード
```bash
# スクリプトから実行
docker compose exec backend poetry run python backend/scripts/run_scrapers.py --scraper suumo --force-detail-fetch

# Pythonコードから実行
from backend.app.scrapers.suumo_scraper import SuumoScraper
scraper = SuumoScraper(force_detail_fetch=True)
scraper.scrape_area("minato", max_pages=1)
```

## データベーススキーマとの関係

1. **重複排除**: 同一物件は`property_hash`で識別
   - 部屋番号がある場合: 建物ID + 部屋番号
   - 部屋番号がない場合: 建物ID + 所在階 + 向き + 平米（専有面積）
2. **価格履歴**: `listing_price_history`テーブルで全ての価格変更を記録
3. **建物名の正規化**: `building_aliases`テーブルで表記ゆれを管理
4. **備考の要約**: `RemarksSummarizer`ユーティリティで複数サイトの備考を統合

## 同一物件判定ロジック

### 基本原則
同一物件かどうかは以下の要素で判定します：

1. **部屋番号がある場合**
   - 建物ID + 部屋番号 のみで判定
   - 最もシンプルで確実な判定方法

2. **部屋番号がない場合**
   - 以下の3項目すべてが一致する場合に同一物件と判定：
     - 建物ID（同じ建物）
     - 所在階（floor_number）
     - 平米数（area、小数点第1位まで）

### 実装詳細
```python
# base_scraper.py の generate_property_hash メソッド
if room_number:
    data = f"{building_id}:{room_number}"
else:
    floor_str = f"F{floor_number}" if floor_number else "F?"
    area_str = f"A{area:.1f}" if area else "A?"
    data = f"{building_id}:{floor_str}_{area_str}"
```

### 注意事項
- 間取り（layout）は判定基準に含めない（同じ物件でもサイトによって表記が異なるため）
- 向き（direction）は判定基準に含めない（同じ部屋でも向きの記載が異なることがあるため）
- 面積は小数点第1位まで（誤差を吸収するため）
- 向きはSUUMOでは「向き」、HOMESでは「主要採光面」から取得して別途記録

## 今後の拡張時の注意点

1. **新しいサイトを追加する場合**:
   - `BaseScraper`を継承
   - `scrape_area`メソッドを実装（スマートスクレイピング対応）
   - `parse_property_list`と`parse_property_detail`を実装
   - コンストラクタで`force_detail_fetch`パラメータをサポート

2. **新しいフィールドを追加する場合**:
   - データベーススキーマを更新
   - 各スクレイパーの該当メソッドを更新
   - APIレスポンススキーマを更新
   - フロントエンドの型定義を更新

3. **セレクタを更新する場合**:
   - `analyze_page_structure.py`スクリプトで実際のHTMLを分析
   - 複数のページでテストしてから本番適用

## データ形式の仕様

### 総階数 (total_floors)
- データ型: String（地下階の表記に対応）
- 形式: 
  - 地下なし: `"10階建"`
  - 地下あり: `"14階地下1階建"`
- 注意: データベースではString型で保存

### 権利形態 (land_rights)
- データ型: String
- 主な値:
  - `"所有権"`
  - `"定期借地権"`
  - `"普通借地権"`
  - `"区分所有権"`

### 駐車場情報 (parking_info)
- データ型: Text
- 例:
  - `"敷地内（3万円／月）"`
  - `"近隣（月額5万円）"`
  - `"なし"`
  - `"機械式：2万円/月、平置き：3万円/月"`

### 交通情報 (station_info)
- データ型: Text
- 形式: 路線ごとに改行で区切る
- 例:
  ```
  東京メトロ日比谷線「六本木」歩10分
  東京メトロ千代田線「乃木坂」歩13分
  ```
- 注意: スクレイパー側で不要な文言（[乗り換え案内]等）を削除し、改行を挿入

## 更新履歴

- 2025-07-24: 安全設計とエラーハンドリング機能の強化
  - 詳細ページ解析失敗時の安全な処理を明文化
  - 共通検証ロジックの活用を明記
  - サーキットブレーカー機能を実装（エラー率50%または連続10件のエラーで自動停止）
  - データ検証機能を強化（必須フィールドの型チェック、値の範囲チェック、データ整合性チェック）
  - HTML構造検証機能を追加（サイト構造変更の検知）
  - エラー統計の詳細追跡機能を追加
  - すべてのスクレイパーに共通のエラーハンドリング機能を実装

- 2025-07-18: 三井のリハウススクレイパーを追加
  - `rehouse_scraper.py`を実装
  - URLパターン: `https://www.rehouse.co.jp/buy/mansion/prefecture/{都道府県}/city/{市区町村}/`
  - 物件詳細URL: `https://www.rehouse.co.jp/buy/mansion/bkdetail/{物件コード}/`
  - 建物名、価格、面積、間取り、階数、向き、管理費、修繕積立金等の取得に対応
  - 不動産会社情報、物件の特徴・備考の取得に対応

- 2025-07-18: 同一物件判定ロジックの修正
  - 物件の同一判定基準を「建物ID、所在階、平米数」の3項目に変更
  - 向き（direction）を判定基準から除外（同じ部屋でも向きの記載が異なることがあるため）

- 2025-07-17: 物件識別ロジックと方角情報取得の強化
  - SUUMOの所在階取得ロジックを修正（物件概要テーブルから単独フィールドとして取得）
  - SUUMOで「向き」フィールドから方角情報を取得
  - HOMESで「主要採光面」フィールドから方角情報を取得
  - 情報提供日（published_at）の取得機能を追加

- 2025-07-17: 総階数、権利形態、駐車場情報の取得機能を追加
  - `total_floors`をString型に変更（地下階表記対応）
  - `land_rights`（権利形態）カラムを追加
  - `parking_info`（駐車場情報）カラムを追加
  - SUUMOとHOMESのスクレイパーを更新
  - 交通情報の整形処理をスクレイパー側に移動

- 2025-07-17: 初版作成
  - 不動産会社情報、バルコニー面積、備考の取得機能を追加
  - SUUMOとHOMESのセレクタを更新
  - 強制詳細取得モード（force_detail_fetch）を追加
  - スマートスクレイピング機能の実装