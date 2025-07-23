#!/bin/bash
# 開発段階用：データベースを再作成するスクリプト

echo "=== データベース再作成スクリプト（開発用） ==="
echo ""
echo "⚠️  警告: このスクリプトは全てのデータを削除します！"
echo ""

# 環境変数を設定
export DATABASE_URL="postgresql://realestate:realestate_pass@localhost:5432/realestate"

# 確認
read -p "本当に実行しますか？ (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "キャンセルしました"
    exit 0
fi

echo ""
echo "1. 既存のテーブルを削除中..."
poetry run python backend/scripts/init_v2_schema.py --drop

echo ""
echo "2. 新しいテーブルを作成中..."
poetry run python backend/scripts/init_v2_schema.py

echo ""
echo "3. 現在のスキーマをダンプ中..."
docker exec realestate-postgres pg_dump -U realestate -d realestate --schema-only > \
    backend/migrations/001_initial_schema.sql

echo ""
echo "✅ データベースの再作成が完了しました"
echo ""
echo "次のステップ:"
echo "- テストデータが必要な場合は、スクレイピングを実行してください"
echo "- poetry run python backend/scripts/run_scrapers.py --scraper suumo --area '港区' --pages 1"