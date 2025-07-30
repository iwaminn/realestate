#!/bin/bash
# 停止したタスクを定期的にチェックするスクリプト

while true; do
    echo "$(date) - Checking for stalled tasks..."
    
    # Dockerコンテナ内でPythonスクリプトを実行
    docker exec realestate-backend python /app/backend/scripts/check_stalled_tasks.py --threshold 10
    
    # 5分待機
    sleep 300
done