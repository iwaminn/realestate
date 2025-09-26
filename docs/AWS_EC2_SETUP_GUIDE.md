# AWS EC2 Ubuntu 24.04 セットアップガイド

このドキュメントでは、AWS EC2のUbuntu 24.04環境に不動産検索システムをインストールし、Web上で閲覧できるようにするまでの完全な手順を説明します。

## 前提条件

- AWSアカウントを持っていること
- EC2インスタンス作成権限があること
- ドメイン名（オプション）

## 1. EC2インスタンスの作成

### 1.1 インスタンスの起動

1. AWS マネジメントコンソールにログイン
2. EC2ダッシュボードで「インスタンスを起動」をクリック
3. 以下の設定でインスタンスを作成：

```
- 名前: realestate-server
- AMI: Ubuntu Server 24.04 LTS (HVM), SSD Volume Type
- インスタンスタイプ: t3.medium（最小推奨）またはt3.large（推奨）
- キーペア: 新規作成または既存のものを選択
- ネットワーク設定:
  - VPC: デフォルトVPCまたはカスタムVPC
  - サブネット: パブリックサブネット
  - パブリックIPの自動割り当て: 有効化
- セキュリティグループ: 新規作成
  - SSH (22): あなたのIPアドレスから
  - HTTP (80): 0.0.0.0/0から
  - HTTPS (443): 0.0.0.0/0から（HTTPS使用時）
- ストレージ: 30GB以上のgp3
```

### 1.2 Elastic IPの割り当て（推奨）

1. EC2ダッシュボードで「Elastic IP」を選択
2. 「Elastic IPアドレスを割り当てる」をクリック
3. 作成したElastic IPをインスタンスに関連付け
4. 割り当てられたIPアドレスをメモしておく（DNSレコード設定で使用）

### 1.3 ドメイン名の設定（オプション）

ドメイン名を使用する場合、DNSレコードを設定してElastic IPと紐付けます。

#### Route 53を使用する場合

1. **ホストゾーンの作成**
```bash
# AWS CLIを使用する場合
aws route53 create-hosted-zone --name your-domain.com --caller-reference $(date +%s)
```

または、AWSコンソールから：
- Route 53ダッシュボードを開く
- 「ホストゾーンの作成」をクリック
- ドメイン名（例: your-domain.com）を入力
- タイプ: パブリックホストゾーン
- 「作成」をクリック

2. **Aレコードの作成**
```bash
# AレコードでElastic IPを指定
# Route 53コンソールから：
# - ホストゾーンを選択
# - 「レコードを作成」をクリック
# - レコード名: 空白（ルートドメイン）または www
# - レコードタイプ: A
# - 値: <Elastic IPアドレス>
# - TTL: 300
# - 「レコードを作成」をクリック
```

3. **ネームサーバーの設定**
- Route 53のホストゾーンに表示されるNSレコード（ネームサーバー）をコピー
- ドメインレジストラ（お名前.com、ムームードメインなど）の管理画面でネームサーバーを変更
- 反映まで数時間～48時間かかる場合があります

#### 他のDNSサービス（お名前.com、Cloudflareなど）を使用する場合

1. **DNSレジストラの管理画面にログイン**

2. **Aレコードの追加**
```
レコードタイプ: A
ホスト名: @ （ルートドメイン）または www
値/IPアドレス: <Elastic IPアドレス>
TTL: 3600 または Auto
```

3. **DNSの反映確認**
```bash
# ローカルマシンから（DNSの反映には時間がかかります）
nslookup your-domain.com
dig your-domain.com

# IPアドレスがElastic IPと一致することを確認
```

#### ドメイン設定後の確認

```bash
# ドメインでアクセスできることを確認
curl -I http://your-domain.com

# pingテスト
ping your-domain.com
```

## 2. サーバーへの接続と初期設定

### 2.1 SSHでサーバーに接続

```bash
# ローカルマシンから
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@<インスタンスのパブリックIP>
```

### 2.2 システムの更新

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget git build-essential
```

### 2.3 タイムゾーンの設定

```bash
sudo timedatectl set-timezone Asia/Tokyo
```

## 3. 必要なソフトウェアのインストール

### 3.1 Docker と Docker Compose のインストール

```bash
# Dockerのインストール
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 再ログインして権限を反映
exit
ssh -i your-key.pem ubuntu@<インスタンスのパブリックIP>

# Docker Composeのインストール
sudo apt install -y docker-compose-plugin

# 動作確認
docker --version
docker compose version
```

## 4. アプリケーションのセットアップ

### 4.1 リポジトリのクローン

```bash
cd /home/ubuntu
git clone https://github.com/your-username/realestate.git
cd realestate
```

### 4.2 環境変数の設定

```bash
# .envファイルの作成
cp .env.example .env
nano .env
```

以下の内容を編集：

```env
# データベース設定
DATABASE_URL=postgresql://realestate:realestate_pass@postgres:5432/realestate
POSTGRES_USER=realestate
POSTGRES_PASSWORD=your-secure-password-here  # 必ず変更
POSTGRES_DB=realestate

# 管理画面認証（本番環境では必ず変更）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password-here

# 開発時の認証バイパス（本番環境では必ずfalseにすること）
DISABLE_ADMIN_AUTH=false

# メール送信設定（本番環境で必須）
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com
MAIL_FROM_NAME=都心中古マンション価格DB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False

# フロントエンドURL（メール内のリンク用）
FRONTEND_URL=http://your-domain-or-ip

# Google OAuth設定（オプション）
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://your-domain-or-ip/api/oauth/google/callback

# スクレイパー設定
SCRAPER_DETAIL_REFETCH_DAYS=90
```

### 4.3 本番用Docker Compose設定の作成

```bash
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: realestate-postgres
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - TZ=Asia/Tokyo
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - realestate-network

  backend:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
    container_name: realestate-backend
    environment:
      - PYTHONUNBUFFERED=1
      - DATABASE_URL=${DATABASE_URL}
      - TZ=Asia/Tokyo
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - DISABLE_ADMIN_AUTH=${DISABLE_ADMIN_AUTH:-false}
      - SCRAPER_DETAIL_REFETCH_DAYS=${SCRAPER_DETAIL_REFETCH_DAYS:-90}
      - MAIL_USERNAME=${MAIL_USERNAME}
      - MAIL_PASSWORD=${MAIL_PASSWORD}
      - MAIL_SERVER=${MAIL_SERVER}
      - MAIL_PORT=${MAIL_PORT}
      - MAIL_FROM=${MAIL_FROM}
      - MAIL_FROM_NAME=${MAIL_FROM_NAME}
      - MAIL_STARTTLS=${MAIL_STARTTLS:-True}
      - MAIL_SSL_TLS=${MAIL_SSL_TLS:-False}
      - FRONTEND_URL=${FRONTEND_URL}
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI}
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - realestate-network

  frontend:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile.prod
      args:
        VITE_API_URL: /api
    container_name: realestate-frontend
    restart: unless-stopped
    networks:
      - realestate-network

  nginx:
    image: nginx:alpine
    container_name: realestate-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx-site.conf:/etc/nginx/conf.d/default.conf:ro
      - nginx_cache:/var/cache/nginx
    depends_on:
      - backend
      - frontend
    restart: unless-stopped
    networks:
      - realestate-network

networks:
  realestate-network:
    driver: bridge

volumes:
  postgres_data:
  nginx_cache:
EOF
```

### 4.4 本番用フロントエンドDockerfileの作成

```bash
cat > docker/frontend/Dockerfile.prod << 'EOF'
FROM node:18-alpine as builder

WORKDIR /app

# 依存関係のインストール
COPY frontend/package*.json ./
RUN npm ci

# アプリケーションのビルド
COPY frontend ./
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# 本番用イメージ
FROM node:18-alpine

WORKDIR /app

# serve パッケージのインストール
RUN npm install -g serve

# ビルド済みファイルのコピー
COPY --from=builder /app/dist ./dist

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
EOF
```

### 4.5 Nginx設定ファイルの作成

```bash
# nginx.confの作成
cat > nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 20M;

    # Gzip圧縮
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/rss+xml application/atom+xml image/svg+xml;

    # レート制限
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=30r/s;

    include /etc/nginx/conf.d/*.conf;
}
EOF
```

```bash
# nginx-site.confの作成
cat > nginx-site.conf << 'EOF'
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:3000;
}

# HTTPSリダイレクト（HTTPS使用時はコメントアウトを解除）
# server {
#     listen 80;
#     server_name your-domain.com;
#     return 301 https://$server_name$request_uri;
# }

server {
    listen 80;
    server_name _;

    # フロントエンド
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # レート制限
        limit_req zone=general_limit burst=20 nodelay;
    }

    # API
    location /api {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # レート制限
        limit_req zone=api_limit burst=20 nodelay;

        # タイムアウト設定
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 静的ファイルのキャッシュ
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://frontend;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ヘルスチェック
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF
```

## 5. アプリケーションの起動

### 5.1 Docker イメージのビルドと起動

```bash
# Dockerコンテナの起動
docker compose -f docker-compose.prod.yml up -d --build

# ログの確認
docker compose -f docker-compose.prod.yml logs -f

# コンテナの状態確認
docker ps
```

### 5.2 データベースの初期化

```bash
# データベーススキーマの作成
docker exec realestate-backend poetry run python backend/scripts/init_v2_schema.py

# サイトマスターの初期化
docker exec realestate-backend poetry run python backend/scripts/create_site_master.py
```

## 6. システムの管理

### 6.1 systemd サービスの作成（自動起動設定）

```bash
# サービスファイルの作成
sudo nano /etc/systemd/system/realestate.service
```

以下の内容を追加：

```ini
[Unit]
Description=Real Estate Search System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/realestate
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
User=ubuntu
Group=docker

[Install]
WantedBy=multi-user.target
```

```bash
# サービスの有効化と起動
sudo systemctl daemon-reload
sudo systemctl enable realestate.service
sudo systemctl start realestate.service
sudo systemctl status realestate.service
```

### 6.2 ログローテーションの設定

```bash
# logrotateの設定
sudo nano /etc/logrotate.d/realestate
```

以下の内容を追加：

```
/home/ubuntu/realestate/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        docker exec realestate-backend kill -USR1 1 2>/dev/null || true
    endscript
}
```

### 6.3 バックアップの設定

```bash
# バックアップスクリプトの作成
cat > /home/ubuntu/backup-realestate.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_BACKUP_FILE="$BACKUP_DIR/realestate_db_$DATE.sql"

# バックアップディレクトリの作成
mkdir -p $BACKUP_DIR

# データベースのバックアップ
docker exec realestate-postgres pg_dump -U realestate realestate > $DB_BACKUP_FILE
gzip $DB_BACKUP_FILE

# 古いバックアップの削除（7日以上前）
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup completed: ${DB_BACKUP_FILE}.gz"
EOF

chmod +x /home/ubuntu/backup-realestate.sh

# cronジョブの設定（毎日午前2時に実行）
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/backup-realestate.sh") | crontab -
```

## 7. セキュリティの強化

### 7.1 ファイアウォールの設定

```bash
# UFWのインストールと設定
sudo apt install -y ufw

# 基本ルールの設定
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 必要なポートを開放
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# ファイアウォールを有効化
sudo ufw --force enable
sudo ufw status
```

### 7.2 fail2banの設定（オプション）

```bash
# fail2banのインストール
sudo apt install -y fail2ban

# 設定ファイルの作成
sudo nano /etc/fail2ban/jail.local
```

以下の内容を追加：

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
```

```bash
# fail2banの起動
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## 8. SSL/TLS証明書の設定（推奨）

HTTPSを使用することで、通信の暗号化とセキュリティが向上します。Let's Encryptの無料SSL証明書を使用します。

### 8.1 Let's Encrypt証明書の取得

```bash
# Certbotのインストール
sudo apt install -y certbot

# Nginxを一時停止
docker compose -f docker-compose.prod.yml stop nginx

# 証明書の取得
sudo certbot certonly --standalone -d your-domain.com

# 証明書の確認
sudo ls -la /etc/letsencrypt/live/your-domain.com/
# fullchain.pem と privkey.pem が存在することを確認
```

### 8.2 Nginx HTTPS設定の追加

```bash
# nginx-site.confを編集してHTTPS設定を追加
cat > nginx-site.conf << 'EOF'
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:3000;
}

# HTTPからHTTPSへのリダイレクト
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS設定
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL証明書
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL設定
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # セキュリティヘッダー
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # フロントエンド
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # レート制限
        limit_req zone=general_limit burst=20 nodelay;
    }

    # API
    location /api {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # レート制限
        limit_req zone=api_limit burst=20 nodelay;

        # タイムアウト設定
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 静的ファイルのキャッシュ
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://frontend;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # ヘルスチェック
    location /health {
        access_log off;
        return 200 "healthy
";
        add_header Content-Type text/plain;
    }
}
EOF
```

### 8.3 docker-compose.prod.ymlの更新

SSL証明書をNginxコンテナにマウントします：

```bash
# docker-compose.prod.ymlのnginxセクションを編集
nano docker-compose.prod.yml
```

nginxセクションのvolumesに証明書ディレクトリを追加：

```yaml
  nginx:
    image: nginx:alpine
    container_name: realestate-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx-site.conf:/etc/nginx/conf.d/default.conf:ro
      - nginx_cache:/var/cache/nginx
      - /etc/letsencrypt:/etc/letsencrypt:ro  # この行を追加
    depends_on:
      - backend
      - frontend
    restart: unless-stopped
    networks:
      - realestate-network
```

### 8.4 環境変数の更新

HTTPSを使用する場合、.envファイルの以下の設定を更新します：

```bash
nano .env
```

```env
# HTTPSに変更
FRONTEND_URL=https://your-domain.com

# Google OAuthのリダイレクトURIもHTTPSに
GOOGLE_REDIRECT_URI=https://your-domain.com/api/oauth/google/callback
```

### 8.5 Nginxコンテナの再起動

```bash
# 設定を反映するためにNginxコンテナを再起動
docker compose -f docker-compose.prod.yml up -d nginx

# ログを確認してエラーがないことを確認
docker compose -f docker-compose.prod.yml logs nginx

# HTTPSでアクセスできることを確認
curl -I https://your-domain.com
```

### 8.6 証明書の自動更新設定

Let's Encryptの証明書は90日間有効なため、自動更新の設定が必要です：

```bash
# 更新スクリプトの作成
cat > /home/ubuntu/renew-cert.sh << 'EOF'
#!/bin/bash
cd /home/ubuntu/realestate

# Nginxを停止
docker compose -f docker-compose.prod.yml stop nginx

# 証明書を更新
certbot renew --quiet

# Nginxを再起動
docker compose -f docker-compose.prod.yml start nginx

# ログに記録
echo "$(date): SSL certificate renewal completed" >> /home/ubuntu/cert-renewal.log
EOF

chmod +x /home/ubuntu/renew-cert.sh

# cronジョブの設定（毎月1日の午前3時に実行）
(crontab -l 2>/dev/null; echo "0 3 1 * * /home/ubuntu/renew-cert.sh") | crontab -
```

### 8.7 HTTPSの動作確認

```bash
# HTTPアクセスがHTTPSにリダイレクトされることを確認
curl -I http://your-domain.com
# Location: https://your-domain.com が返ることを確認

# HTTPSでアクセスできることを確認
curl -I https://your-domain.com
# 200 OK が返ることを確認

# SSL証明書の有効性を確認
openssl s_client -connect your-domain.com:443 -servername your-domain.com < /dev/null
```

### 8.8 Google OAuthの設定更新（HTTPS使用時）

HTTPSを有効にした後、Google Cloud ConsoleでリダイレクトURIを更新します：

1. Google Cloud Console (https://console.cloud.google.com/) にログイン
2. プロジェクトを選択
3. 「APIとサービス」→「認証情報」
4. OAuth 2.0クライアントIDを選択
5. 「承認済みのリダイレクトURI」に追加：
   - `https://your-domain.com/api/oauth/google/callback`
6. 「保存」をクリック

### 8.9 トラブルシューティング

#### SSL証明書の取得に失敗する場合

**エラー: "Port 80 is already in use"**
```bash
# Nginxが停止しているか確認
docker ps | grep nginx

# 80番ポートを使用しているプロセスを確認
sudo lsof -i :80
sudo netstat -tulpn | grep :80
```

**エラー: "Failed authorization procedure"**
```bash
# ドメインのDNSレコードが正しく設定されているか確認
nslookup your-domain.com
dig your-domain.com

# ファイアウォールで80番ポートが開いているか確認
sudo ufw status
```

#### 証明書更新に失敗する場合

```bash
# 手動で更新を試す
sudo certbot renew --dry-run

# 更新ログを確認
sudo cat /var/log/letsencrypt/letsencrypt.log
```

## 9. モニタリングの設定

### 9.1 システムモニタリング

```bash
# htopのインストール
sudo apt install -y htop

# Docker statsのエイリアス設定
echo 'alias dstats="docker stats --format \"table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\""' >> ~/.bashrc
source ~/.bashrc
```

### 9.2 アプリケーションの監視

```bash
# ヘルスチェックスクリプトの作成
cat > /home/ubuntu/health-check.sh << 'EOF'
#!/bin/bash
# フロントエンドのチェック
curl -f http://localhost/ > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Frontend: OK"
else
    echo "Frontend: FAILED"
fi

# APIのチェック
curl -f http://localhost/api/v2/stats > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "API: OK"
else
    echo "API: FAILED"
fi

# データベースのチェック
docker exec realestate-postgres pg_isready > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Database: OK"
else
    echo "Database: FAILED"
fi
EOF

chmod +x /home/ubuntu/health-check.sh
```

## 10. トラブルシューティング

### 10.1 よくある問題と解決方法

#### コンテナが起動しない場合
```bash
# ログの確認
docker compose -f docker-compose.prod.yml logs backend
docker compose -f docker-compose.prod.yml logs postgres

# コンテナの再起動
docker compose -f docker-compose.prod.yml restart
```

#### データベース接続エラー
```bash
# PostgreSQLの接続確認
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT 1;"

# 環境変数の確認
docker exec realestate-backend env | grep DATABASE_URL
```

#### ディスク容量の確認
```bash
df -h
docker system df
# 不要なDockerリソースの削除
docker system prune -a
```

### 10.2 ログの確認方法

```bash
# アプリケーションログ
tail -f /home/ubuntu/realestate/logs/app.log

# Dockerログ
docker compose -f docker-compose.prod.yml logs -f --tail 100

# Nginxログ
docker exec realestate-nginx tail -f /var/log/nginx/access.log
docker exec realestate-nginx tail -f /var/log/nginx/error.log
```

## 11. メンテナンス作業

### 11.1 アプリケーションの更新

```bash
# 最新のコードを取得
cd /home/ubuntu/realestate
git pull origin master

# コンテナの再ビルドと再起動
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build

# データベースマイグレーション（必要な場合）
docker exec realestate-backend poetry run python backend/scripts/init_v2_schema.py
```

### 11.2 定期メンテナンス

```bash
# 週次メンテナンススクリプト
cat > /home/ubuntu/weekly-maintenance.sh << 'EOF'
#!/bin/bash
echo "Starting weekly maintenance..."

# Dockerイメージの更新
cd /home/ubuntu/realestate
docker compose -f docker-compose.prod.yml pull

# ログファイルの圧縮
find /home/ubuntu/realestate/logs -name "*.log" -mtime +7 -exec gzip {} \;

# Dockerの未使用リソースのクリーンアップ
docker system prune -f

echo "Weekly maintenance completed."
EOF

chmod +x /home/ubuntu/weekly-maintenance.sh

# cronに追加（毎週日曜日午前3時）
(crontab -l 2>/dev/null; echo "0 3 * * 0 /home/ubuntu/weekly-maintenance.sh") | crontab -
```

## 12. パフォーマンスチューニング

### 12.1 PostgreSQLの最適化

```bash
# PostgreSQL設定の調整
cat > postgres-custom.conf << 'EOF'
# 接続設定
max_connections = 200

# メモリ設定（インスタンスサイズに応じて調整）
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# チェックポイント設定
checkpoint_completion_target = 0.9
wal_buffers = 16MB
min_wal_size = 1GB
max_wal_size = 2GB

# ログ設定
log_statement = 'mod'
log_duration = on
log_min_duration_statement = 100
EOF

# docker-compose.prod.ymlのpostgresセクションに追加
# volumes:
#   - ./postgres-custom.conf:/etc/postgresql/postgresql.conf:ro
# command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

### 12.2 Nginxのキャッシュ設定

nginx-site.confにキャッシュ設定を追加することで、APIレスポンスをキャッシュできます：

```nginx
# proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m use_temp_path=off;

# location /api/v2/properties {
#     proxy_cache api_cache;
#     proxy_cache_valid 200 5m;
#     proxy_cache_valid 404 1m;
#     proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
#     proxy_cache_background_update on;
#     proxy_cache_lock on;
#     add_header X-Cache-Status $upstream_cache_status;
#
#     proxy_pass http://backend;
#     # ... 他の設定
# }
```

## 13. メール送信の設定

本システムでは、ユーザー登録時のメール認証にメール送信機能を使用します。以下のいずれかのメールサービスを設定してください。

### 13.1 Gmail（開発・小規模運用向け）

#### 手順

1. **Googleアカウントで2段階認証を有効化**
   - https://myaccount.google.com/security にアクセス
   - 「2段階認証プロセス」を有効化

2. **アプリパスワードの生成**
   - https://myaccount.google.com/apppasswords にアクセス
   - アプリ名（例: 都心マンションDB）を入力
   - 「生成」をクリック
   - 表示された16文字のパスワードをコピー

3. **.envファイルに設定**
```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx  # 生成されたアプリパスワード
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=your-email@gmail.com
MAIL_FROM_NAME=都心中古マンション価格DB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
```

#### 制限事項
- 1日500通まで（Googleの制限）
- 大規模運用には不向き

### 13.2 SendGrid（中規模運用向け）

#### 手順

1. **SendGridアカウントの作成**
   - https://sendgrid.com/ にアクセス
   - 無料プランに登録（月100通まで無料）

2. **APIキーの生成**
   - SendGridダッシュボードにログイン
   - Settings → API Keys
   - 「Create API Key」をクリック
   - 名前を入力（例: realestate-prod）
   - Permissions: Full Access
   - 生成されたAPIキーをコピー（再表示できないので注意）

3. **送信元メールアドレスの検証**
   - Settings → Sender Authentication
   - 「Verify a Single Sender」をクリック
   - 送信元メールアドレスと情報を入力
   - 確認メールのリンクをクリックして認証

4. **.envファイルに設定**
```env
MAIL_USERNAME=apikey
MAIL_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxx  # 生成されたAPIキー
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com  # 検証済みメールアドレス
MAIL_FROM_NAME=都心中古マンション価格DB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
```

#### 料金プラン
- Free: 月100通まで無料
- Essentials: 月$19.95～（月50,000通）
- Pro: 月$89.95～（月100,000通）

### 13.3 AWS SES（大規模運用向け）

#### 手順

1. **AWS SESの有効化**
```bash
# AWS CLIを使用する場合
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url https://your-domain.com \
  --use-case-description "Real estate search service email verification"
```

または、AWSコンソールから：
- Amazon SESダッシュボードを開く
- 「Get started」をクリック
- リージョンを選択（推奨: ap-northeast-1 東京）

2. **送信元メールアドレスの検証**
```bash
# メールアドレスの検証
aws sesv2 create-email-identity --email-identity noreply@yourdomain.com --region ap-northeast-1
```

または、AWSコンソールから：
- Verified identities → Create identity
- Identity type: Email address
- メールアドレスを入力
- 確認メールのリンクをクリック

3. **ドメイン検証（推奨）**

ドメイン全体を検証すると、そのドメインの任意のメールアドレスから送信可能になります：

- Verified identities → Create identity
- Identity type: Domain
- ドメイン名を入力
- 表示されたDNSレコード（TXT、CNAME、MX）をRoute 53または使用中のDNSサービスに追加

4. **SMTP認証情報の作成**
```bash
# AWSコンソールから：
# - Amazon SES → SMTP settings
# - 「Create SMTP credentials」をクリック
# - IAMユーザー名を入力（例: ses-smtp-user）
# - 表示されたSMTPユーザー名とパスワードをコピー
```

5. **.envファイルに設定**
```env
MAIL_USERNAME=AKIAIOSFODNN7EXAMPLE  # SMTP認証情報のユーザー名
MAIL_PASSWORD=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY  # SMTPパスワード
MAIL_SERVER=email-smtp.ap-northeast-1.amazonaws.com
MAIL_PORT=587
MAIL_FROM=noreply@yourdomain.com  # 検証済みメールアドレス
MAIL_FROM_NAME=都心中古マンション価格DB
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
```

6. **サンドボックスモードの解除申請**

初期状態ではサンドボックスモードで、検証済みメールアドレスにしか送信できません：

- Amazon SES → Account dashboard
- 「Request production access」をクリック
- Use case、予想送信量などを入力して申請
- 承認まで24時間程度かかる場合があります

#### 料金
- 最初の62,000通/月: 無料（EC2からの送信）
- 以降: $0.10/1,000通

### 13.4 メール送信のテスト

設定後、メール送信機能をテストします：

```bash
# Dockerコンテナ内でPythonシェルを起動
docker exec -it realestate-backend poetry run python

# 以下のコードを実行
from backend.app.utils.email import send_verification_email

# テストメール送信
send_verification_email(
    email="your-test-email@example.com",
    verification_token="test-token-123"
)
```

または、実際にユーザー登録を試してメールが届くことを確認：

```bash
# フロントエンドでユーザー登録画面からテスト
# http://your-domain/（ユーザーアイコンから「新規登録」）
```

### 13.5 トラブルシューティング

#### メールが送信されない場合

1. **ログの確認**
```bash
docker exec realestate-backend tail -f /app/logs/app.log | grep -i mail
```

2. **環境変数の確認**
```bash
docker exec realestate-backend env | grep MAIL_
```

3. **SMTP接続テスト**
```bash
# telnetでSMTPサーバーに接続できるか確認
docker exec realestate-backend telnet smtp.gmail.com 587
```

#### よくあるエラー

**Gmail: "Username and Password not accepted"**
- 2段階認証が有効になっているか確認
- アプリパスワードを正しくコピーしたか確認（スペースは不要）
- 「安全性の低いアプリのアクセス」が無効になっていることを確認（アプリパスワード使用時は不要）

**SendGrid: "Authentication failed"**
- APIキーが正しいか確認
- MAIL_USERNAMEが"apikey"になっているか確認
- 送信元メールアドレスが検証済みか確認

**AWS SES: "Email address is not verified"**
- 送信元メールアドレスまたはドメインが検証済みか確認
- サンドボックスモードの場合、受信者も検証済みである必要がある
- リージョンが正しいか確認（例: ap-northeast-1）

## 14. スクレイピングの設定

### 14.1 管理画面からのスクレイピング

本番環境では、管理画面（`http://your-domain/admin`）からスクレイピングを実行します：

1. 管理画面にログイン（ADMIN_USERNAME / ADMIN_PASSWORD）
2. 「スクレイピング管理」タブを開く
3. 「新規タスク作成」から手動実行またはスケジュール設定

### 14.2 スケジュール設定の例

管理画面の「スケジュール管理」から以下のような設定が可能です：

- 毎日午前9時に全サイトをスクレイピング
- 特定のエリアのみを対象にする
- 詳細ページの再取得間隔を調整

## まとめ

このガイドに従うことで、AWS EC2 Ubuntu 24.04環境に不動産検索システムを構築し、安全かつ効率的に運用できます。定期的なバックアップとモニタリングを行い、システムの安定性を維持してください。

## 参考リンク

- [Docker公式ドキュメント](https://docs.docker.com/)
- [PostgreSQL公式ドキュメント](https://www.postgresql.org/docs/)
- [Nginx公式ドキュメント](https://nginx.org/en/docs/)
- [Ubuntu Server Guide](https://ubuntu.com/server/docs)
- [Vite公式ドキュメント](https://vitejs.dev/)