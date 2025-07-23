# Docker環境での開発

## 必要なソフトウェア

- Docker Desktop (Windows/Mac) または Docker Engine (Linux)
- Docker Compose v2.0以上
- Make (オプション、Makefileを使用する場合)

## クイックスタート

### 1. 環境変数の設定

```bash
cp .env.example .env
```

### 2. Dockerコンテナの起動

```bash
# Makefileを使用
make build  # 初回のみ
make up

# または直接docker-composeを使用
docker-compose -f docker-compose.dev.yml build  # 初回のみ
docker-compose -f docker-compose.dev.yml up -d
```

### 3. サービスへのアクセス

- フロントエンド: http://localhost:3001
- API: http://localhost:8000
- APIドキュメント: http://localhost:8000/docs

## 便利なコマンド

### コンテナ管理

```bash
# 状態確認
make ps

# ログ確認
make logs
make logs-backend   # バックエンドのみ
make logs-frontend  # フロントエンドのみ

# コンテナ停止
make down

# 再起動
make restart
```

### 開発作業

```bash
# バックエンドのシェルに接続
make shell-backend

# フロントエンドのシェルに接続
make shell-frontend

# データベースに接続
make db-shell
```

### スクレイピング

```bash
# 全サイトをスクレイピング
make scrape

# SUUMOのみ
make scrape-suumo

# カスタムコマンド
docker-compose -f docker-compose.dev.yml exec backend \
  poetry run python backend/scripts/run_scrapers.py --scraper athome --pages 5
```

## ディレクトリ構造

```
docker/
├── backend/
│   └── Dockerfile      # バックエンド用Dockerfile
└── frontend/
    └── Dockerfile      # フロントエンド用Dockerfile

docker-compose.dev.yml  # 開発環境用設定
docker-compose.yml      # 本番環境用設定（将来用）
```

## トラブルシューティング

### ポートが使用中の場合

```bash
# 使用中のポートを確認
lsof -i :8000
lsof -i :3001

# docker-compose.dev.ymlでポートを変更
ports:
  - "8001:8000"  # 8001に変更
```

### データベースエラーの場合

```bash
# コンテナ内でデータベースを再作成
make shell-backend
poetry run python backend/scripts/update_schema_for_scraping.py
```

### ビルドキャッシュをクリア

```bash
docker-compose -f docker-compose.dev.yml build --no-cache
```

## 本番環境へのデプロイ

本番環境用の設定は`docker-compose.yml`を使用します：

```bash
docker-compose up -d
```

主な違い：
- ボリュームマウントなし（コード変更の自動反映なし）
- 最適化されたビルド
- 環境変数による設定