#!/bin/bash
# 環境変数を明示的に設定してスクレイパーを実行

export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate_db"
export PYTHONPATH="/home/ubuntu/realestate"

cd /home/ubuntu/realestate

echo "Starting SUUMO scraper for 港区 (10 pages = 1000 properties)..."
echo "DATABASE_URL: $DATABASE_URL"

poetry run python backend/scripts/run_scrapers.py --scraper suumo --area "港区" --pages 10