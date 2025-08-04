# スクレイパー実行ガイド

このドキュメントでは、不動産スクレイパーの実行方法について説明します。

## 重要な変更（2025年8月）

**すべてのスクレイパー実行は管理画面に表示されるようになりました。**
- コマンドラインから実行されたスクレイパーも自動的にデータベースにタスクとして登録されます
- 管理画面から実行状況の確認、一時停止、キャンセルが可能です
- データベースにタスクが登録されていない場合、スクレイピングは実行されません

## 実行方法

### 1. 管理画面からの実行（推奨）

管理画面（http://localhost:3001/admin）から実行するのが最も簡単で安全な方法です。

1. 管理画面にアクセス
2. 「スクレイピング管理」タブを選択
3. 「新しいタスクを開始」をクリック
4. スクレイパー、エリア、オプションを選択して実行

### 2. コマンドラインからの実行

コマンドラインから実行した場合も、自動的に管理画面に表示されます。

#### Docker環境での実行（推奨）

```bash
# 全スクレイパーを実行（港区、最大100件）
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py

# 特定のスクレイパーを実行
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py --scraper suumo --area minato --max-properties 150

# 詳細取得を強制（すべての物件の詳細を再取得）
docker exec realestate-backend poetry run python /app/backend/scripts/run_scrapers.py --force-detail-fetch
```

#### ローカル環境での実行

```bash
# バックエンドディレクトリに移動
cd backend

# 全スクレイパーを実行
poetry run python scripts/run_scrapers.py

# 特定のスクレイパーを実行
poetry run python scripts/run_scrapers.py --scraper homes --area minato --max-properties 300
```

### 3. スケジュール実行

定期的に自動実行する場合：

```bash
# Docker Composeでスクレイパーコンテナを起動（6時間ごとに実行）
docker-compose up -d scraper

# カスタム間隔で実行（例：3時間ごと）
docker exec -d realestate-backend poetry run python /app/backend/scripts/run_scrapers.py --schedule --interval 3
```

**注意**: スケジュール実行も管理画面に表示され、そこから停止可能です。

## コマンドラインオプション

| オプション | 説明 | デフォルト値 |
|----------|------|------------|
| `--scraper` | 実行するスクレイパー（suumo, homes, rehouse, nomu, livable, all） | all |
| `--area` | 検索エリア（minato, shibuya, shinjuku等） | minato |
| `--max-properties` | 取得する最大物件数 | 100 |
| `--pages` | 取得するページ数（非推奨、--max-propertiesを使用） | - |
| `--force-detail-fetch` | すべての物件の詳細を強制取得 | false |
| `--schedule` | スケジュール実行モード | false |
| `--interval` | スケジュール実行間隔（時間） | 6 |

## タスク管理

### タスクIDの形式

- 管理画面から実行: `web_xxxxxxxx`
- コマンドラインから実行: `cmd_xxxxxxxx`
- スケジュール実行: `cmd_xxxxxxxx`（各実行ごとに新規作成）

### タスクの状態

- **running**: 実行中
- **paused**: 一時停止中
- **completed**: 正常完了
- **error**: エラーで終了
- **cancelled**: キャンセルされた

### タスクの制御

管理画面から以下の操作が可能です：
- **一時停止**: 実行中のタスクを一時的に停止
- **再開**: 一時停止したタスクを再開
- **キャンセル**: タスクを完全に停止

## 並列実行

複数のスクレイパーを同時に実行する場合：

```bash
# 並列実行（全サイト・全エリア）
make scrape-parallel

# テスト実行（2サイト・2エリア）
make scrape-parallel-test
```

## トラブルシューティング

### タスクが管理画面に表示されない

1. データベース接続を確認
   ```bash
   docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT * FROM scraping_tasks ORDER BY created_at DESC LIMIT 5;"
   ```

2. バックエンドコンテナのログを確認
   ```bash
   docker logs realestate-backend --tail 50
   ```

### スクレイピングが開始されない

1. 既存のタスクを確認
   ```bash
   docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT task_id, status FROM scraping_tasks WHERE status IN ('running', 'paused');"
   ```

2. 実行中のタスクがある場合は、管理画面から停止するか、以下のコマンドで手動停止
   ```bash
   docker exec realestate-postgres psql -U realestate -d realestate -c "UPDATE scraping_tasks SET status = 'cancelled' WHERE status IN ('running', 'paused');"
   ```

### エラーログの確認

```bash
# スクレイパーのエラーログ
tail -n 100 /home/ubuntu/realestate/logs/errors.log | jq .

# タスク別のエラー
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT task_id, error_logs FROM scraping_tasks WHERE status = 'error' ORDER BY created_at DESC LIMIT 1;"
```

## ベストプラクティス

1. **管理画面から実行することを推奨**
   - 進捗状況が視覚的に確認できる
   - 簡単に一時停止・再開できる
   - エラーが発生した場合の詳細が確認できる

2. **初回実行時は少ないページ数で**
   - まず1-2ページでテスト実行
   - 正常に動作することを確認してから本番実行

3. **定期的な監視**
   - スケジュール実行時も定期的に管理画面で状況を確認
   - エラーが多い場合は原因を調査

4. **適切な実行間隔**
   - 同じサイトへの負荷を避けるため、最低でも6時間以上の間隔を推奨
   - 深夜や早朝の実行を推奨（サーバー負荷が低い時間帯）

## セキュリティ上の注意

- データベースにタスクが登録されていないスクレイパーは実行されません
- これにより、不正なスクレイピングや管理外の実行を防止します
- すべての実行履歴がデータベースに記録されます