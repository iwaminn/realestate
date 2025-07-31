# マンション一括検索 - 開発コンテキスト

このプロジェクトは、FastAPI (Python) と React (TypeScript) を使用した不動産検索サービスです。

## 重要な指示

**このプロジェクトでの会話は必ず日本語で行ってください。** コードのコメントも日本語で記述してください。

## 技術スタック

- Python 3.10+ (Poetry環境)
- FastAPI 0.100+
- PostgreSQL 15 (Docker環境・ローカル開発共通)
- SQLAlchemy 2.0+
- React 18+
- TypeScript 5+
- Material-UI 5+
- Docker & Docker Compose

## 命名規約

- Pythonの関数名と変数名はsnake_case
- Pythonのクラス名はPascalCase
- データベースのテーブル名とカラム名はsnake_case
- APIエンドポイントはリソース名を複数形で（例: /api/properties）
- フロントエンドのコンポーネント名はPascalCase
- Gitコミットメッセージは日本語でOK

## ディレクトリ構造

```
realestate/
├── backend/           # バックエンドアプリケーション
│   ├── app/          # アプリケーションコード
│   │   ├── api/     # APIエンドポイント
│   │   ├── scrapers/# スクレイパー
│   │   ├── models/  # データモデル
│   │   └── utils/   # ユーティリティ
│   ├── scripts/      # 管理スクリプト
│   └── tests/        # テスト
├── frontend/          # Reactフロントエンド
│   ├── src/          # ソースコード
│   └── public/       # 静的ファイル
├── data/              # データファイル
├── logs/              # ログファイル
└── docs/              # ドキュメント
```

## 開発時の注意点

- Poetry環境でPythonコマンドを実行する（`poetry run`）
- スクレイパーのレート制限を守る（デフォルト2秒遅延）
- 環境変数ファイルは.env.exampleを参考に
- データベースは必ず`realestate`を使用（`realestate_db`は使用しない）
- **重要: データベース設計に変更を加えた場合は、必ずAPIの該当箇所も更新すること**
  - 物件一覧API (`/api/v2/properties`) と物件詳細API (`/api/v2/properties/{id}`) の両方を確認
  - 新しいフィールドを追加した場合は、APIレスポンスに含めるか検討
  - フロントエンドの型定義ファイル (`types/property.ts`) も合わせて更新

### 🚨 Dockerコンテナ再起動が必要な変更

**以下の変更を行った場合は、必ずDockerコンテナを再起動すること！**

1. **Pythonコードの変更**
   - `backend/app/api/` 配下のAPIエンドポイント
   - `backend/app/models.py` などのモデル定義
   - `backend/app/scrapers/` 配下のスクレイパー
   - `backend/scripts/` 配下のスクリプト

2. **新しいPythonパッケージの追加**
   - `pyproject.toml` への依存関係追加
   - 新しいモジュールのインポート

3. **環境変数の変更**
   - `.env` ファイルの更新

#### 再起動コマンド：
```bash
# バックエンドのみ再起動
docker restart realestate-backend

# 全コンテナ再起動
docker-compose restart

# または
make restart
```

**注意**: コンテナを再起動しないと、変更が反映されずに古いコードが実行され続けます！

### 🚨 base_scraper.py 変更時の重要な注意事項

**`backend/app/scrapers/base_scraper.py` は全てのスクレイパーの基底クラスです。このファイルへの変更は、以下のすべてのスクレイパーに影響します：**

- SUUMO (`suumo_scraper.py`)
- LIFULL HOME'S (`homes_scraper.py`)
- 三井のリハウス (`rehouse_scraper.py`)
- ノムコム (`nomu_scraper.py`)
- 東急リバブル (`livable_scraper.py`)

#### 変更前に必ず確認すること：
1. **影響範囲の確認**: 変更するメソッドが各スクレイパーでどのように使われているか確認
2. **後方互換性**: 既存のスクレイパーが正常に動作することを確認
3. **テストの実行**: 少なくとも2つ以上のスクレイパーで動作確認
4. **エラーハンドリング**: 共通処理のエラーが各スクレイパーで適切に処理されることを確認

#### よくある問題：
- 統計カウントの不整合（例：今回の`update_type`の問題）
- 必須フィールドの検証ロジック変更による既存スクレイパーの動作不良
- データベーストランザクション処理の変更による保存エラー
- 例外処理の変更による予期しない動作

### 🚨 重要：Docker環境のデータベース使用について

**必ずDocker環境のPostgreSQLデータベースを使用すること！**

データベース操作やスクリプト実行は常にDockerコンテナ内で行ってください。ローカル環境のデータベースとDocker環境のデータベースは別物です。

#### 正しい実行方法：
```bash
# ✅ 正しい（Docker環境内で実行）
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT COUNT(*) FROM master_properties;"

# ❌ 間違い（ローカル環境で実行）
poetry run python backend/scripts/run_scrapers.py
psql -U realestate -d realestate
```

#### よく使うDockerコマンド：
- スクリプト実行: `docker exec realestate-backend poetry run python /app/backend/scripts/スクリプト名.py`
- DB接続: `docker exec realestate-postgres psql -U realestate -d realestate`
- マイグレーション: `docker exec realestate-backend poetry run python /app/backend/scripts/init_v2_schema.py`

**注意**: ローカル環境で実行するとデータの不整合が発生し、「データベースに保存されているはずのデータが見つからない」などの問題が起きます。

### 🚨 タイムゾーンの設定について

**重要**: PostgreSQLはUTCで動作し、アプリケーション層で日本時間に変換しています。

#### 現在の設計：
- **データベース保存**: すべてのタイムスタンプをUTCで保存
- **APIレスポンス**: 日本時間（JST/+09:00）に変換して返却
- **フロントエンド表示**: APIから受け取った日本時間をそのまま表示

#### 実装の詳細：
1. **バックエンド（FastAPI）**
   - `backend/app/utils/datetime_utils.py`に`to_jst_string()`関数を実装
   - 各APIエンドポイントでタイムスタンプを日本時間に変換
   - 例：`2025-08-01T00:46:25.899041+09:00`

2. **フロントエンド（React）**
   - APIから受け取った日本時間を`toLocaleString('ja-JP')`で表示
   - タイムゾーン変換は不要（サーバー側で処理済み）

3. **注意事項**
   - データベースに保存される時刻はすべてUTC
   - 直接SQLでINSERT/UPDATEする際は時差を考慮すること
   - スクレイピング等で取得した時刻は適切にUTCに変換して保存

4. **データ修正が必要な場合**
   ```sql
   -- 誤って日本時間として保存された時刻を修正（9時間戻す）
   UPDATE テーブル名 SET created_at = created_at - INTERVAL '9 hours' WHERE created_at > NOW();
   ```

5. **Docker環境でのタイムゾーン設定**
   ```yaml
   # docker-compose.yml に設定済み（効果は限定的）
   environment:
     TZ: Asia/Tokyo
     PGTZ: Asia/Tokyo  # PostgreSQL用（ただしDBはUTCで動作）
   ```

## 最新の変更

- Docker環境の追加（Docker Composeで簡単起動）
- PostgreSQL 15を使用（開発・本番共通）
- FastAPI + Reactによるフルスタック構成
- SUUMO、LIFULL HOME'Sのスクレイパー実装
- 階数・方角情報の追加
- 建物別物件一覧機能
- 価格履歴グラフ表示
- データベース名を`realestate`に統一
- **並列スクレイピングのDB版完全移行（2025年7月）**
  - タスク情報・進捗はすべてデータベースで管理
  - ファイルベースの旧実装は削除済み
  - 直列実行モードを削除、常に並列実行を使用
- **日時表示の日本時間統一（2025年8月）**
  - APIレスポンスで日本時間を返すように統一
  - フロントエンドでのタイムゾーン変換を不要に
  - 建物・物件の統合履歴、除外履歴すべてに適用

## デプロイ・保守

**重要**: システム改修後は必ず `docs/DEPLOYMENT_CHECKLIST.md` の手順に従って動作確認を行ってください。

## ロギングシステム（2025年7月追加）

### 概要
アプリケーション全体のエラーと動作を追跡するための構造化ロギングシステムを実装しています。
すべてのログはJSON形式で記録され、エラーの原因特定が容易になっています。

### ログファイルの場所
Dockerコンテナ内: `/app/logs/`
ホスト側: `/home/ubuntu/realestate/logs/`

主要なログファイル：
- `app.log` - アプリケーション全般のログ
- `errors.log` - エラーのみを記録（スタックトレース付き）
- `api_requests.log` - APIリクエスト/レスポンスログ
- `database.log` - データベース操作ログ

### エラー発生時の確認方法

```bash
# 最新のエラーログを確認（ホスト側）
tail -n 50 /home/ubuntu/realestate/logs/errors.log | jq .

# Docker内でエラーログを確認
docker exec realestate-backend tail -n 50 /app/logs/errors.log | jq .

# 特定のエラーを検索（例：建物統合エラー）
docker exec realestate-backend grep "building_merge" /app/logs/errors.log | jq .

# APIリクエストのエラーを確認
docker exec realestate-backend grep "500" /app/logs/api_requests.log | jq .
```

### ログの構造
各ログエントリは以下の情報を含みます：
- `timestamp` - エラー発生時刻（UTC）
- `level` - ログレベル（INFO, ERROR等）
- `message` - エラーメッセージ
- `module` - エラーが発生したモジュール
- `function` - エラーが発生した関数名
- `line` - エラーが発生した行番号
- `exception` - 例外情報（type, message, traceback）
- その他のコンテキスト情報（例：building_id, user_id等）

### デバッグ時の活用方法
1. エラーが発生したら、まず `errors.log` を確認
2. `timestamp` でエラー発生時刻を特定
3. 同じ時刻の `api_requests.log` でリクエスト内容を確認
4. 必要に応じて `app.log` で詳細な処理フローを追跡
5. `database.log` でデータベース操作を確認

## よく使うコマンド

### Docker環境（推奨）
```bash
# コンテナビルド&起動
make build
make up

# スクレイピング
make scrape
make scrape-suumo

# PostgreSQLデータベース接続
make db-shell  # docker exec -it realestate-postgres psql -U realestate -d realestate

# ログ確認
make logs
```

### ローカル環境
```bash
# APIサーバー
poetry run python backend/app/main.py

# フロントエンド
cd frontend && npm run dev

# スクレイピング
poetry run python backend/scripts/scrape_all.py
poetry run python backend/scripts/run_scrapers.py --scraper suumo

# PostgreSQLデータベース確認
docker exec -it realestate-postgres psql -U realestate -d realestate
```

## 重要な機能

1. **物件情報の統合**: 同一物件を自動識別（property_hash）
2. **価格履歴追跡**: price_historyテーブルで価格変動を記録
3. **階数・方角情報**: floor_number、total_floors、directionカラム
4. **建物別表示**: building_nameで同じ建物の物件をグループ化
5. **マルチソース対応**: 各不動産サイトへの直接リンク提供
6. **詳細情報の取得**: 不動産会社情報、バルコニー面積、備考の取得・要約
7. **販売終了物件の価格多数決**: 販売終了前1週間の価格履歴から最も多く掲載されていた価格を最終価格として決定

### 重要仕様書

**重要**: システムの複雑な仕様については必ず以下のドキュメントを参照してください：

#### 主要な仕様書
- `docs/CRITICAL_SPECIFICATIONS.md` - システム全体の重要仕様
  - 建物名管理システム（多数決、リアルタイム更新）
  - 物件ハッシュ生成ルール（部屋番号を含まない）
  - スマートスクレイピング（価格変更ベース）
  - 掲載状態を考慮した多数決ロジック

- `docs/MAJORITY_VOTE_SYSTEM.md` - 多数決システムの詳細仕様
  - 建物レベル・物件レベルの建物名決定ロジック
  - 重み付け投票アルゴリズム
  - property_listingsからの直接集計（2025年1月改訂）
  - その他の属性（管理費、修繕積立金等）の多数決

### 物件ハッシュ（property_hash）の仕様

物件の同一性を判定するためのハッシュ値生成ルール：

**ハッシュ生成**: `建物ID + 所在階 + 平米数 + 間取り + 方角`

**重要な変更（2025年1月）**：
- 部屋番号はハッシュ生成に**使用しません**
- 理由：サイトによって部屋番号の公開状況が異なるため、同一物件が別物件として扱われる問題を防ぐ
- LIFULL HOME'Sでは部屋番号が公開されていることがありますが、ハッシュには含めません

**注意事項**：
- 方角も含めてハッシュを生成します
- 方角だけが異なる場合は別物件として扱われます
- ただし、同一物件で方角情報の有無が異なる場合があるため、管理画面の「物件重複管理」機能で人的に判断・統合する必要があります
- 物件重複候補は管理画面で確認し、必要に応じて手動で統合してください

## スクレイパー仕様

**重要**: 
- スクレイパーの仕様変更時は必ず `docs/SCRAPER_SPECIFICATION.md` を更新してください
- 有効なスクレイパーの一覧は `docs/ACTIVE_SCRAPERS.md` を参照してください

### 現在有効なスクレイパー
- SUUMO (`suumo`)
- LIFULL HOME'S (`homes`)
- 三井のリハウス (`rehouse`)
- ノムコム (`nomu`)

詳細な仕様書は上記ファイルを参照してください。主な機能：
- 不動産会社情報の取得（agency_name, agency_tel）
- バルコニー面積の取得（balcony_area）
- 物件備考の取得と要約（remarks, summary_remarks）
- スマートスクレイピング（新規・更新物件のみ詳細取得）

## データベーススキーマ（v2）

### 重要: データベース名の統一
**プロジェクト全体で使用するデータベース名: `realestate`**

### 主要テーブル
- `buildings`: 建物マスター
  - normalized_name（正規化された建物名）、address（住所）
  - total_floors（総階数）、built_year（築年）
- `building_aliases`: 建物名の表記ゆれ管理
- `master_properties`: 物件マスター（重複排除済み）
  - building_id、room_number、floor_number、area、layout、direction
- `property_listings`: 各サイトの掲載情報
  - master_property_id、source_site、current_price、station_info
  - is_active（掲載中フラグ）
- `listing_price_history`: 価格変更履歴
- `property_images`: 物件画像

### データベース初期化
```bash
# スキーマの初期化
docker compose exec backend poetry run python backend/scripts/init_v2_schema.py
```

### 特徴
- 同一物件の重複を排除
- 複数サイト・複数業者の掲載を統合管理
- 建物名の表記ゆれを吸収
- 掲載ごとの詳細な価格履歴

## API構成

- `GET /api/v2/properties`: 重複排除された物件一覧
- `GET /api/v2/properties/{id}`: 物件詳細（全掲載情報含む）
- `GET /api/v2/buildings/{building_id}/properties`: 建物内の全物件
- `GET /api/v2/stats`: 統計情報

## スクレイパー設定

### 現在有効なスクレイパー
- SUUMO (`suumo`): 最も安定して動作、階数・方角対応、100件/ページ表示対応
- LIFULL HOME'S (`homes`): 新セレクタ対応済み
- 三井のリハウス (`rehouse`): 2025年1月復活
- ノムコム (`nomu`): 住所・総階数対応済み
- 東急リバブル (`livable`): 2025年7月追加

### 無効化されたスクレイパー
- AtHome: CAPTCHA対策により2025年1月23日に無効化（削除済み）
- 楽待: ユーザー要望により除外

詳細は `docs/ACTIVE_SCRAPERS.md` を参照してください。

### 並列スクレイピング機能（2025年1月追加）

異なるサイトを並列で実行し、スクレイピング時間を大幅に短縮：

```bash
# 並列実行（全サイト・全エリア）
make scrape-parallel

# テスト実行（2サイト・2エリア）
make scrape-parallel-test
```

**特徴**：
- 異なるサイト（SUUMO、LIFULL HOME'S等）は並列実行
- 同一サイトの異なるエリアは直列実行（レート制限遵守）
- 約5倍の高速化を実現（230分→46分）
- 各スクレイパーごとの一時停止・再開・キャンセル機能
- スレッドセーフな進捗管理とデータベース接続

### スマートスクレイピング機能（2025年1月改訂）

詳細ページの取得を最適化する機能を実装：
- 初回は全物件の詳細ページを取得
- 2回目以降は**価格が変更された物件のみ詳細を取得**（最重要）
- 90日以上詳細を取得していない物件は自動的に再取得（環境変数で設定可能）
- 更新マーク（NEW表示など）は参考情報として保存するが、詳細取得の判断には使用しない

設定例：
```bash
export SCRAPER_DETAIL_REFETCH_DAYS=90     # 全スクレイパー共通
export SCRAPER_SUUMO_DETAIL_REFETCH_DAYS=60  # SUUMOのみ60日
```

**価格変更検出の仕組み**：
1. 一覧ページから価格を取得
2. 既存データの価格と比較
3. 価格が異なる場合は詳細ページを取得して全情報を更新
4. 価格が同じ場合は最終確認日時のみ更新

## データベース管理

### 重要：データベーススキーマ変更時の手順（開発段階）

1. **必ず** `backend/app/models.py` を編集してモデルを変更
2. データベースを再作成:
   ```bash
   export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate"
   poetry run python backend/scripts/init_v2_schema.py --drop  # 既存テーブル削除
   poetry run python backend/scripts/init_v2_schema.py        # テーブル再作成
   ```
3. 必要に応じてテストデータを再投入

### データベース定義ファイルの場所
- **正式な定義**: `backend/app/models.py` （SQLAlchemy ORMモデル）
- **マイグレーション履歴**: `backend/alembic/versions/`
- **管理ドキュメント**: `backend/DATABASE_MANAGEMENT.md`

### チェックスクリプト
```bash
# データベースの状態をチェック
poetry run python backend/scripts/check_migrations.py
```

## バージョン管理ルール
開発段階では混乱を避けるため、以下のルールを厳守してください：
- v2、v3などのバージョン番号が付いたファイルやメソッドは作成しない
- 既存のバージョン付きファイルは最新版に統一し、旧バージョンは削除する
- メソッド名も同様に、_v2、_v3などのサフィックスは使用しない
- 新しい実装を行う場合は、既存のファイル/メソッドを更新する
- APIエンドポイントのバージョニング（/api/v2/）は例外とする