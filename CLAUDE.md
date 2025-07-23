# マンション一括検索 - 開発コンテキスト

このプロジェクトは、FastAPI (Python) と React (TypeScript) を使用した不動産検索サービスです。

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

## 最新の変更

- Docker環境の追加（Docker Composeで簡単起動）
- PostgreSQL 15を使用（開発・本番共通）
- FastAPI + Reactによるフルスタック構成
- SUUMO、AtHome、LIFULL HOME'Sのスクレイパー実装
- 階数・方角情報の追加
- 建物別物件一覧機能
- 価格履歴グラフ表示
- データベース名を`realestate`に統一

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

### 物件ハッシュ（property_hash）の仕様

物件の同一性を判定するためのハッシュ値生成ルール：

1. **部屋番号がある場合**: `建物ID + 部屋番号`
2. **部屋番号がない場合**: `建物ID + 所在階 + 平米数 + 間取り + 方角`

**重要な注意事項**：
- 方角も含めてハッシュを生成します
- 方角だけが異なる場合は別物件として扱われます
- ただし、同一物件で方角情報の有無が異なる場合があるため、管理画面の「物件重複管理」機能で人的に判断・統合する必要があります
- 物件重複候補は管理画面で確認し、必要に応じて手動で統合してください

## スクレイパー仕様

**重要**: スクレイパーの仕様変更時は必ず `docs/SCRAPER_SPECIFICATION.md` を更新してください。

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

- SUUMO: 実装済み、階数・方角対応、100件/ページ表示対応
- AtHome: 実装済み、CAPTCHA検出機能付き
- HOMES: 実装済み、新セレクタ対応
- 楽待: ユーザー要望により除外

### スマートスクレイピング機能

詳細ページの取得を最適化する機能を実装：
- 初回は全物件の詳細ページを取得
- 2回目以降は更新マークがある物件のみ詳細を取得
- 90日以上詳細を取得していない物件は自動的に再取得（環境変数で設定可能）

設定例：
```bash
export SCRAPER_DETAIL_REFETCH_DAYS=90     # 全スクレイパー共通
export SCRAPER_SUUMO_DETAIL_REFETCH_DAYS=60  # SUUMOのみ60日
```

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