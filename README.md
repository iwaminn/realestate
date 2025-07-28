# マンション一括検索

複数の不動産サイトから中古物件情報を収集し、横断的に検索・比較できるサービスです。

## 📋 機能

- **マルチサイトスクレイピング**: SUUMO、LIFULL HOME'S、三井のリハウス、ノムコム、東急リバブルから物件情報を収集
- **物件情報の統合**: 同一物件を自動的に識別し、情報を統合
- **詳細検索**: 価格、面積、間取り、階数、方角などで絞り込み
- **価格履歴追跡**: 物件価格の変動をグラフで可視化
- **建物別表示**: 同じ建物内の他の物件を一覧表示
- **元サイトへのリンク**: 各不動産サイトの詳細ページへ直接アクセス
- **買い取り再販物件の検出**: 再販物件を自動識別し、マーク表示
- **管理画面**: 物件・建物の重複管理、統合履歴の確認

## 🛠️ 技術スタック

- **バックエンド**: FastAPI (Python)
- **フロントエンド**: React (TypeScript) + Material-UI
- **データベース**: PostgreSQL (Docker環境) / SQLite (ローカル開発)
- **ORM**: SQLAlchemy
- **マイグレーション**: Alembic
- **スクレイピング**: BeautifulSoup4 + Requests
- **パッケージ管理**: Poetry (Python), npm (Node.js)
- **コンテナ**: Docker & Docker Compose

## 📁 プロジェクト構造

```
realestate/
├── backend/                # バックエンドアプリケーション
│   ├── app/               # アプリケーションコード
│   │   ├── api/          # APIエンドポイント
│   │   ├── scrapers/     # スクレイパー
│   │   ├── models/       # データモデル
│   │   └── utils/        # ユーティリティ
│   ├── scripts/           # 管理スクリプト
│   └── tests/             # テスト
├── frontend/               # Reactフロントエンド
│   ├── src/               # ソースコード
│   │   ├── api/          # APIクライアント
│   │   ├── components/   # Reactコンポーネント
│   │   ├── pages/        # ページコンポーネント
│   │   └── types/        # TypeScript型定義
│   └── public/            # 静的ファイル
├── data/                   # データベースとキャッシュ
├── logs/                   # ログファイル
├── docs/                   # ドキュメント
└── scripts/                # その他のスクリプト
```

## 🚀 クイックスタート

### Dockerを使用した起動（推奨）

```bash
# リポジトリのクローン
git clone https://github.com/yourusername/realestate-search.git
cd realestate-search

# Dockerコンテナのビルドと起動
make build
make up

# または直接docker-composeを使用
docker-compose -f docker-compose.dev.yml up -d
```

### アクセスURL

- 🌐 フロントエンド: http://localhost:3001
- 🔧 API: http://localhost:8000
- 📚 APIドキュメント: http://localhost:8000/docs

### ローカル環境での起動（Dockerを使わない場合）

<details>
<summary>クリックして展開</summary>

```bash
# 環境変数ファイルの作成
cp .env.example .env
# ローカル環境用にDATABASE_URLを修正（.envファイル内）
# DATABASE_URL=sqlite:///data/realestate.db

# Poetryのインストール（未インストールの場合）
curl -sSL https://install.python-poetry.org | python3 -

# 依存関係のインストール
poetry install

# データベースの初期化（SQLite使用時のみ - 通常は不要）
# poetry run python backend/scripts/update_schema_for_scraping.py

# APIサーバーの起動
poetry run python backend/app/main.py

# 別ターミナルでフロントエンドを起動
cd frontend
npm install
npm run dev
```

</details>

## 📝 使い方

### Dockerコマンド

```bash
# コンテナの状態確認
make ps

# ログの確認
make logs

# バックエンドのシェルに接続
make shell-backend

# PostgreSQLデータベースに接続
make db-shell

# SQLiteからPostgreSQLへデータ移行
make db-migrate
```

### スクレイピングの実行

```bash
# Docker環境で全サイトからスクレイピング
make scrape

# SUUMOのみスクレイピング
make scrape-suumo

# コンテナ内で直接実行
docker-compose -f docker-compose.dev.yml exec backend poetry run python backend/scripts/run_scrapers.py --scraper athome --pages 3
```

### スケジュール実行

```bash
# スクレイパーコンテナを起動（6時間ごとに実行）
docker-compose up -d scraper
```

## 🤝 貢献

プルリクエストやイシューの報告を歓迎します。

## 📜 ライセンス

MIT

## ⚠️ 注意事項

本システムは教育・研究目的で作成されています。スクレイピングを行う際は、対象サイトの利用規約を遵守し、適切なレート制限を守ってください。