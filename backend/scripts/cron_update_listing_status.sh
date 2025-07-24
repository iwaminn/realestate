#!/bin/bash
# 掲載状態を更新するcronジョブスクリプト

# スクリプトのディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# ログファイル
LOG_FILE="$PROJECT_ROOT/logs/update_listing_status.log"
mkdir -p "$PROJECT_ROOT/logs"

# 現在時刻を記録
echo "========================================" >> "$LOG_FILE"
echo "Starting update at $(date)" >> "$LOG_FILE"

# Docker環境で実行
cd "$PROJECT_ROOT"
docker exec realestate-backend poetry run python /app/backend/scripts/update_listing_status.py >> "$LOG_FILE" 2>&1

# 終了時刻を記録
echo "Finished update at $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"