# Makefile for マンション一括検索サービス

.PHONY: help build up down logs shell clean

help: ## ヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build: ## Dockerイメージをビルド
	docker-compose -f docker-compose.dev.yml build

up: ## コンテナを起動
	docker-compose -f docker-compose.dev.yml up -d
	@echo "✅ サービスが起動しました"
	@echo "📍 フロントエンド: http://localhost:3001"
	@echo "📍 API: http://localhost:8000"
	@echo "📍 APIドキュメント: http://localhost:8000/docs"

down: ## コンテナを停止
	docker-compose -f docker-compose.dev.yml down

logs: ## ログを表示
	docker-compose -f docker-compose.dev.yml logs -f

logs-backend: ## バックエンドのログを表示
	docker-compose -f docker-compose.dev.yml logs -f backend

logs-frontend: ## フロントエンドのログを表示
	docker-compose -f docker-compose.dev.yml logs -f frontend

shell-backend: ## バックエンドコンテナにシェルで接続
	docker-compose -f docker-compose.dev.yml exec backend bash

shell-frontend: ## フロントエンドコンテナにシェルで接続
	docker-compose -f docker-compose.dev.yml exec frontend sh

scrape: ## スクレイピングを実行
	docker-compose -f docker-compose.dev.yml exec backend poetry run python backend/scripts/scrape_all.py

scrape-suumo: ## SUUMOのみスクレイピング
	docker-compose -f docker-compose.dev.yml exec backend poetry run python backend/scripts/run_scrapers.py --scraper suumo

db-shell: ## PostgreSQLデータベースに接続
	docker-compose -f docker-compose.dev.yml exec postgres psql -U realestate -d realestate_db

db-migrate: ## SQLiteからPostgreSQLへデータを移行
	docker-compose -f docker-compose.dev.yml exec backend poetry run python backend/scripts/migrate_to_postgres.py

clean: ## コンテナとボリュームを削除
	docker-compose -f docker-compose.dev.yml down -v

restart: down up ## コンテナを再起動

ps: ## コンテナの状態を表示
	docker-compose -f docker-compose.dev.yml ps