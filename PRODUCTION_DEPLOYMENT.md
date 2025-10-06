# 本番環境デプロイ手順

## 概要
メールアドレス変更確認機能、パスワードリセット機能、Googleアカウント用パスワード設定機能を本番環境に反映する手順です。

## 前提条件
- 本番サーバーへのSSHアクセス権限
- Docker Compose V2がインストール済み
- PostgreSQLコンテナが稼働中

## デプロイ手順

### ステップ1: コードの取得

```bash
# 本番サーバーにSSH接続
ssh ubuntu@your-production-server

# プロジェクトディレクトリに移動
cd /home/ubuntu/realestate

# 最新コードを取得
git pull origin master
```

### ステップ2: データベースマイグレーション

```bash
# マイグレーションSQLファイルを実行
docker exec realestate-postgres psql -U realestate -d realestate -f /app/backend/scripts/migrate_auth_tables.sql

# テーブルが正しく作成されたか確認
docker exec realestate-postgres psql -U realestate -d realestate -c "\dt pending_*"
```

**期待される出力:**
```
                      List of relations
 Schema |          Name           | Type  |   Owner
--------+-------------------------+-------+------------
 public | pending_email_changes   | table | realestate
 public | pending_password_resets | table | realestate
 public | pending_password_sets   | table | realestate
```

### ステップ3: 環境変数の設定（重要）

本番環境ではメール送信機能を有効にする必要があります。

**既存のメール設定を使用します**。`docker-compose.prod.yml`（または`docker-compose.yml`）で以下のコメントを解除して設定してください：

```yaml
# docker-compose.prod.yml の backend セクション
environment:
  # ... 既存の設定 ...

  # 以下のコメントを解除して設定
  - MAIL_USERNAME=your-email@gmail.com
  - MAIL_PASSWORD=your-app-password
  - MAIL_SERVER=smtp.gmail.com
  - MAIL_PORT=587
  - MAIL_FROM=noreply@yourdomain.com
  - MAIL_FROM_NAME=都心マンション価格チェッカー
  - MAIL_STARTTLS=True
  - MAIL_SSL_TLS=False

  # フロントエンドURL（本番環境のドメイン）
  - FRONTEND_URL=https://your-domain.com
```

**または、.envファイルで管理する場合**：

```bash
# .envファイルを作成・編集
nano /home/ubuntu/realestate/.env
```

以下を追加：
```bash
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=都心マンション価格チェッカー
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
FRONTEND_URL=https://your-domain.com
```

docker-compose.ymlで環境変数を参照：
```yaml
environment:
  - MAIL_USERNAME=${MAIL_USERNAME}
  - MAIL_PASSWORD=${MAIL_PASSWORD}
  # ... 他の設定も同様に
```

**Gmail使用時の注意:**
- 2段階認証を有効化
- アプリパスワードを生成して`MAIL_PASSWORD`に設定
- https://myaccount.google.com/apppasswords

### ステップ4: Docker再ビルド＆再起動

```bash
# 全コンテナを停止
docker compose -f docker-compose.prod.yml down

# 最新コードで再ビルド＆起動
docker compose -f docker-compose.prod.yml up -d --build

# nginxも再起動（コンテナIPが変わるため必須）
docker compose -f docker-compose.prod.yml restart nginx

# 起動状態を確認
docker compose -f docker-compose.prod.yml ps
```

**期待される出力:**
```
NAME                    STATUS
realestate-backend      Up
realestate-frontend     Up
realestate-nginx        Up
realestate-postgres     Up
```

### ステップ5: ログ確認

```bash
# バックエンドログを確認（エラーがないか）
docker compose -f docker-compose.prod.yml logs backend --tail 50

# フロントエンドログを確認
docker compose -f docker-compose.prod.yml logs frontend --tail 50

# nginxログを確認
docker compose -f docker-compose.prod.yml logs nginx --tail 50
```

### ステップ6: 動作確認

本番環境で以下の機能をテスト：

#### 6.1 パスワードリセット機能
1. https://your-domain.com/request-password-reset にアクセス
2. メールアドレスを入力して送信
3. 受信メールの確認リンクをクリック
4. 新しいパスワードを設定
5. 新しいパスワードでログインできるか確認

#### 6.2 メールアドレス変更機能
1. ログイン後、https://your-domain.com/account/settings にアクセス
2. 新しいメールアドレスとパスワードを入力して変更申請
3. 新しいメールアドレスに届いた確認メールのリンクをクリック
4. メールアドレスが変更されたか確認

#### 6.3 Googleアカウント用パスワード設定
1. Googleアカウントでログイン
2. https://your-domain.com/account/settings にアクセス
3. 「パスワードを設定する」ボタンをクリック
4. 新しいパスワードを入力して送信
5. 受信メールの確認リンクをクリック
6. ログアウト後、メールアドレス＋パスワードでログインできるか確認

## トラブルシューティング

### エラー: テーブルが存在しない
```bash
# テーブル一覧を確認
docker exec realestate-postgres psql -U realestate -d realestate -c "\dt"

# マイグレーションを再実行
docker exec realestate-postgres psql -U realestate -d realestate -f /app/backend/scripts/migrate_auth_tables.sql
```

### エラー: メールが送信されない
```bash
# バックエンドのログでメール送信エラーを確認
docker compose -f docker-compose.prod.yml logs backend | grep -i smtp

# 環境変数が正しく読み込まれているか確認
docker compose -f docker-compose.prod.yml exec backend env | grep SMTP
```

**開発モードのメール確認（SMTP無効時）:**
```bash
# 開発モードではメールはファイルに保存されます
docker compose -f docker-compose.prod.yml exec backend cat /app/logs/email_dev.log
```

### エラー: 404 Not Found（新しいページ）
```bash
# フロントエンドを再ビルド
docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d --force-recreate frontend
docker compose -f docker-compose.prod.yml restart nginx

# ブラウザのキャッシュをクリア（Ctrl+Shift+R）
```

### エラー: APIエラー 500
```bash
# バックエンドの詳細ログを確認
docker compose -f docker-compose.prod.yml logs backend --tail 200

# データベース接続を確認
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT 1;"
```

## ロールバック手順

問題が発生した場合は以下の手順で元に戻せます：

```bash
# 1. 前のコミットに戻る
cd /home/ubuntu/realestate
git log --oneline -5  # コミット履歴を確認
git checkout <前のコミットハッシュ>

# 2. Docker再起動
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml restart nginx

# 3. 新しいテーブルを削除（必要な場合のみ）
docker exec realestate-postgres psql -U realestate -d realestate << 'EOF'
DROP TABLE IF EXISTS pending_email_changes CASCADE;
DROP TABLE IF EXISTS pending_password_resets CASCADE;
DROP TABLE IF EXISTS pending_password_sets CASCADE;
EOF
```

## デプロイ後の確認チェックリスト

- [ ] 全コンテナが正常に起動している
- [ ] データベースに3つの新テーブルが作成されている
- [ ] バックエンドログにエラーがない
- [ ] フロントエンドが正しく表示される
- [ ] パスワードリセット機能が動作する
- [ ] メールアドレス変更機能が動作する
- [ ] Googleログインが動作する
- [ ] メール送信が正常に動作する（または開発モードでログに出力される）

## 注意事項

1. **必ずバックアップを取ってからデプロイ**
   ```bash
   # データベースバックアップ
   docker exec realestate-postgres pg_dump -U realestate realestate > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **メール送信設定は必須**
   - 本番環境では実際のSMTPサーバー設定が必要
   - テスト環境では`SMTP_ENABLED=false`で開発モード（ログ出力）使用可能

3. **Docker再起動は必須**
   - Python/Reactコードの変更は再ビルドが必要
   - nginxの再起動も忘れずに

4. **セキュリティ**
   - `.env`ファイルはGitに含めない（.gitignoreに追加済み）
   - SMTPパスワードは環境変数で管理
   - 本番環境のパスワードは強固なものを使用

## 参考情報

- Docker Compose V2ドキュメント: https://docs.docker.com/compose/
- FastAPIドキュメント: https://fastapi.tiangolo.com/
- Reactドキュメント: https://react.dev/
- PostgreSQLドキュメント: https://www.postgresql.org/docs/
