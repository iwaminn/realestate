#!/bin/bash

echo "Starting Real Estate Search System..."

# APIサーバーを起動
echo "Starting API server..."
cd /home/ubuntu/realestate
poetry run python src/api_server.py &
API_PID=$!

# 少し待機
sleep 3

# フロントエンドを起動
echo "Starting frontend..."
cd /home/ubuntu/realestate/frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "🚀 Services started:"
echo "  - API Server: http://localhost:8000"
echo "  - Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Ctrl+Cを待つ
trap "echo 'Stopping services...'; kill $API_PID $FRONTEND_PID; exit" INT

# プロセスが終了するまで待機
wait