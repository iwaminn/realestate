# デプロイメント・チェックリスト

システム改修後の確認手順とトラブルシューティング

最終更新日: 2025-01-23

## 1. コード変更後の確認手順

### フロントエンド変更時

1. **TypeScriptコンパイルエラーの確認**
   ```bash
   cd frontend
   npm run type-check
   ```

2. **Lintエラーの確認**
   ```bash
   npm run lint
   ```

3. **開発サーバーでの動作確認**
   ```bash
   npm run dev
   ```

4. **Dockerコンテナの再起動**
   ```bash
   docker compose restart frontend
   ```

### バックエンド変更時

1. **Pythonシンタックスチェック**
   ```bash
   docker exec realestate-backend poetry run python -m py_compile backend/app/main.py
   ```

2. **インポートエラーの確認**
   ```bash
   docker exec realestate-backend poetry run python -c "from backend.app.main import app"
   ```

3. **Dockerコンテナの再起動**
   ```bash
   docker compose restart backend
   ```

## 2. システム全体の再起動手順

### 通常の再起動
```bash
# すべてのコンテナを再起動
docker compose restart

# 個別に再起動
docker compose restart frontend
docker compose restart backend
docker compose restart postgres
```

### 完全な再起動（問題が解決しない場合）
```bash
# コンテナを停止
docker compose down

# コンテナを起動
docker compose up -d

# ログを確認
docker compose logs -f
```

## 3. 動作確認チェックリスト

### ✅ 基本動作確認

- [ ] フロントエンドページが表示される（http://localhost:3001）
- [ ] APIが応答する（http://localhost:8000/api/health）
- [ ] 物件検索が動作する
- [ ] 管理画面にアクセスできる（/admin）

### ✅ データベース接続確認

```bash
# PostgreSQLの接続確認
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT 1;"

# テーブルの確認
docker exec realestate-postgres psql -U realestate -d realestate -c "\dt"
```

### ✅ ログ確認

```bash
# 全体のログ
docker compose logs

# フロントエンドのログ
docker compose logs frontend

# バックエンドのログ
docker compose logs backend

# リアルタイムログ監視
docker compose logs -f
```

## 4. よくあるトラブルと対処法

### 🔴 「ページが表示されません」

1. **コンテナの状態確認**
   ```bash
   docker compose ps
   ```
   すべてのコンテナが "Up" 状態であることを確認

2. **ポートの確認**
   - フロントエンド: http://localhost:3001
   - バックエンド: http://localhost:8000
   - PostgreSQL: localhost:5432

3. **ネットワークの確認**
   ```bash
   docker network ls
   docker network inspect realestate_default
   ```

### 🔴 「APIエラーが発生する」

1. **APIヘルスチェック**
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **CORS設定の確認**
   - `backend/app/main.py` の CORS 設定を確認

3. **環境変数の確認**
   ```bash
   docker exec realestate-backend env | grep DATABASE_URL
   ```

### 🔴 「データベースに接続できない」

1. **PostgreSQLコンテナの確認**
   ```bash
   docker exec realestate-postgres pg_isready
   ```

2. **接続文字列の確認**
   ```bash
   # 正しい接続文字列
   DATABASE_URL=postgresql://realestate:realestate_pass@postgres:5432/realestate
   ```

## 5. コード変更時の注意事項

### スクレイパー追加・変更時
1. 以下のファイルを全て更新する：
   - `/frontend/src/components/AdminScraping.tsx`
   - `/backend/app/api/admin.py`
   - `/backend/scripts/run_scrapers.py`
   - `/docs/ACTIVE_SCRAPERS.md`

### データベーススキーマ変更時
1. `backend/app/models.py` を更新
2. マイグレーションスクリプトを実行
3. APIエンドポイントの更新を確認

### 環境変数追加時
1. `.env.example` を更新
2. `docker-compose.yml` に反映
3. ドキュメントに記載

## 6. デプロイ前チェックリスト

- [ ] すべてのコンテナが正常に起動する
- [ ] ユニットテストが通る（実装されている場合）
- [ ] 基本的な CRUD 操作が動作する
- [ ] スクレイパーが正常に動作する
- [ ] ログにエラーが出力されていない
- [ ] メモリ使用量が適切である

## 7. 緊急時の対応

### システム全体のリセット
```bash
# すべてを停止
docker compose down

# ボリュームも含めて削除（データが消えるので注意！）
docker compose down -v

# 再ビルドして起動
docker compose build --no-cache
docker compose up -d
```

### ログの保存
```bash
# 現在のログを保存
docker compose logs > logs/system_logs_$(date +%Y%m%d_%H%M%S).log
```

## 8. モニタリング

### リソース使用状況
```bash
# コンテナのリソース使用状況
docker stats

# ディスク使用量
docker system df
```

### プロセス確認
```bash
# バックエンドのプロセス
docker exec realestate-backend ps aux

# データベースの接続数
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT count(*) FROM pg_stat_activity;"
```

---

このチェックリストに従って作業を行うことで、システム改修後のトラブルを最小限に抑えることができます。