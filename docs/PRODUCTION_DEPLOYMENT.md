# 本番環境デプロイ設定ガイド

## 概要
このドキュメントでは、本番環境にデプロイする際に必要なすべての設定項目をまとめています。

## 必須設定項目

### 1. データベース設定

```bash
# PostgreSQL接続設定
DATABASE_URL=postgresql://username:password@host:5432/database_name

# 例：
DATABASE_URL=postgresql://realestate:strong_password_here@postgres:5432/realestate
```

**重要**: 本番環境では必ず強力なパスワードを使用してください。

### 2. 管理画面認証

```bash
# 管理画面のBasic認証
ADMIN_USERNAME=admin_user
ADMIN_PASSWORD=very_strong_password_here

# 必ず本番環境では認証を有効にする
DISABLE_ADMIN_AUTH=false
```

### 3. メール送信設定（ユーザー登録の確認メール用）

#### Gmail使用の場合
```bash
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password  # 2段階認証を有効にしてアプリパスワードを生成
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=都心マンションDB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
FRONTEND_URL=https://yourdomain.com
```

#### SendGrid使用の場合
```bash
MAIL_USERNAME=apikey
MAIL_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxx  # SendGrid APIキー
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=都心マンションDB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
FRONTEND_URL=https://yourdomain.com
```

#### AWS SES使用の場合
```bash
MAIL_USERNAME=AKIAXXXXXXXXXXXXXXXX  # SES SMTPユーザー名
MAIL_PASSWORD=xxxxxxxxxxxxxxxxxxxxx  # SES SMTPパスワード
MAIL_SERVER=email-smtp.ap-northeast-1.amazonaws.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com  # SESで検証済みのドメイン
MAIL_FROM_NAME=都心マンションDB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
FRONTEND_URL=https://yourdomain.com
```

### 4. Google OAuth設定（Googleログイン機能用）

```bash
# Google Cloud Consoleで取得した認証情報
GOOGLE_CLIENT_ID=123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-1234567890abcdefghijklmn
GOOGLE_REDIRECT_URI=https://yourdomain.com/api/oauth/google/callback
```

### 5. セキュリティ設定

```bash
# JWT署名用の秘密鍵（必ず変更すること）
SECRET_KEY=your-very-long-random-secret-key-here-minimum-32-characters

# CORS設定（フロントエンドのURL）
CORS_ORIGINS=["https://yourdomain.com"]

# HTTPSを強制（本番環境では必須）
FORCE_HTTPS=true
```

### 6. スクレイパー設定（オプション）

```bash
# 詳細ページ再取得間隔（日数）
SCRAPER_DETAIL_REFETCH_DAYS=90

# エラー検知設定
SCRAPER_CRITICAL_ERROR_RATE=0.5
SCRAPER_CRITICAL_ERROR_COUNT=10
SCRAPER_CONSECUTIVE_ERRORS=5
```

## docker-compose.yml 本番環境設定例

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: realestate-postgres
    environment:
      - POSTGRES_DB=realestate
      - POSTGRES_USER=realestate
      - POSTGRES_PASSWORD=${DB_PASSWORD}  # .envファイルから読み込み
      - TZ=Asia/Tokyo
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - realestate-network
    restart: always

  backend:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
    container_name: realestate-backend
    environment:
      - DATABASE_URL=postgresql://realestate:${DB_PASSWORD}@postgres:5432/realestate
      - TZ=Asia/Tokyo
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - DISABLE_ADMIN_AUTH=false
      # メール設定
      - MAIL_USERNAME=${MAIL_USERNAME}
      - MAIL_PASSWORD=${MAIL_PASSWORD}
      - MAIL_SERVER=${MAIL_SERVER}
      - MAIL_PORT=${MAIL_PORT}
      - MAIL_FROM=${MAIL_FROM}
      - MAIL_FROM_NAME=${MAIL_FROM_NAME}
      - MAIL_STARTTLS=${MAIL_STARTTLS}
      - MAIL_SSL_TLS=${MAIL_SSL_TLS}
      - FRONTEND_URL=${FRONTEND_URL}
      # Google OAuth
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI}
    depends_on:
      - postgres
    networks:
      - realestate-network
    restart: always

  frontend:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile
      args:
        - REACT_APP_API_URL=${REACT_APP_API_URL}
    container_name: realestate-frontend
    networks:
      - realestate-network
    restart: always

  nginx:
    image: nginx:alpine
    container_name: realestate-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
      - ./certbot/www:/var/www/certbot
      - ./certbot/conf:/etc/letsencrypt
    depends_on:
      - backend
      - frontend
    networks:
      - realestate-network
    restart: always

volumes:
  postgres_data:

networks:
  realestate-network:
    driver: bridge
```

## .env.production ファイル例

```bash
# データベース
DB_PASSWORD=your_very_strong_password_here

# 管理画面
ADMIN_USERNAME=admin_user
ADMIN_PASSWORD=another_very_strong_password

# メール設定（Gmail例）
MAIL_USERNAME=notification@yourdomain.com
MAIL_PASSWORD=your_gmail_app_password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=都心マンションDB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
FRONTEND_URL=https://yourdomain.com

# Google OAuth
GOOGLE_CLIENT_ID=123456789012-xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxx
GOOGLE_REDIRECT_URI=https://yourdomain.com/api/oauth/google/callback

# フロントエンド
REACT_APP_API_URL=https://yourdomain.com/api
```

## デプロイ前のチェックリスト

### セキュリティ
- [ ] すべてのパスワードを強力なものに変更
- [ ] SECRET_KEYを生成・設定
- [ ] DISABLE_ADMIN_AUTH=false に設定
- [ ] HTTPSを設定（SSL証明書の取得）
- [ ] ファイアウォールで不要なポートを閉じる

### メール設定
- [ ] メールサーバーの認証情報を設定
- [ ] 送信元メールアドレスのSPF/DKIM設定
- [ ] テストメールの送信確認

### Google OAuth
- [ ] Google Cloud ConsoleでOAuth同意画面を設定
- [ ] 本番環境のリダイレクトURIを追加
- [ ] クライアントIDとシークレットを設定
- [ ] テストログインの確認

### データベース
- [ ] 本番用のデータベースパスワードを設定
- [ ] バックアップ戦略の策定
- [ ] データベースのアクセス制限設定

### 監視・ログ
- [ ] ログファイルの保存先設定
- [ ] ログローテーションの設定
- [ ] エラー通知の設定

## SSL証明書の設定（Let's Encrypt）

```bash
# Certbotのインストール
docker run -it --rm --name certbot \
  -v "./certbot/conf:/etc/letsencrypt" \
  -v "./certbot/www:/var/www/certbot" \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  -d yourdomain.com \
  -d www.yourdomain.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# 自動更新の設定（crontab）
0 0 * * * docker run --rm --name certbot -v "./certbot/conf:/etc/letsencrypt" -v "./certbot/www:/var/www/certbot" certbot/certbot renew --quiet
```

## デプロイコマンド

```bash
# 1. 環境変数ファイルを本番用に切り替え
cp .env.production .env

# 2. Dockerイメージをビルド
docker-compose build

# 3. データベースのマイグレーション
docker-compose exec backend poetry run python backend/scripts/init_v2_schema.py
docker-compose exec backend poetry run python backend/scripts/add_google_oauth.py

# 4. サービスを起動
docker-compose up -d

# 5. ログの確認
docker-compose logs -f
```

## トラブルシューティング

### メールが送信されない
1. 環境変数が正しく設定されているか確認
2. メールサーバーの認証情報を確認
3. ファイアウォールでSMTPポートが開いているか確認
4. ログを確認: `docker logs realestate-backend | grep mail`

### Googleログインが動作しない
1. リダイレクトURIが正確に一致しているか確認
2. Google Cloud ConsoleでOAuth同意画面が設定されているか確認
3. クライアントIDとシークレットが正しいか確認
4. HTTPSが正しく設定されているか確認

### データベース接続エラー
1. PostgreSQLが起動しているか確認
2. DATABASE_URLが正しいか確認
3. ネットワーク設定を確認
4. PostgreSQLのログを確認: `docker logs realestate-postgres`

## セキュリティのベストプラクティス

1. **定期的な更新**
   - Dockerイメージを定期的に更新
   - 依存パッケージのセキュリティアップデート

2. **アクセス制限**
   - 管理画面へのIPアドレス制限
   - レート制限の実装
   - WAFの導入検討

3. **監査ログ**
   - すべての管理操作をログに記録
   - 異常なアクセスパターンの検知

4. **バックアップ**
   - データベースの定期バックアップ
   - 設定ファイルのバックアップ
   - 災害復旧計画の策定

## サポート情報

問題が発生した場合は、以下の情報を含めて報告してください：
- エラーログ（`docker-compose logs`の出力）
- 環境変数の設定（パスワード等は伏せる）
- 実行したコマンド
- 発生した問題の詳細