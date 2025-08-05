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
  - カスタムTCP (3001): 0.0.0.0/0から（フロントエンド用）
- ストレージ: 30GB以上のgp3
```

### 1.2 Elastic IPの割り当て（推奨）

1. EC2ダッシュボードで「Elastic IP」を選択
2. 「Elastic IPアドレスを割り当てる」をクリック
3. 作成したElastic IPをインスタンスに関連付け

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

### 3.2 Python 3.10+ と Poetry のインストール

```bash
# Python 3.10のインストール（Ubuntu 24.04にはデフォルトで含まれています）
python3 --version  # 3.10以上であることを確認

# pipのインストール
sudo apt install -y python3-pip python3-venv

# Poetryのインストール
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
poetry --version
```

### 3.3 Node.js と npm のインストール

```bash
# NodeSourceリポジトリの追加
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -

# Node.jsとnpmのインストール
sudo apt install -y nodejs

# 動作確認
node --version  # v18.x.x
npm --version
```

### 3.4 PostgreSQL クライアントのインストール（デバッグ用）

```bash
sudo apt install -y postgresql-client
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
POSTGRES_PASSWORD=realestate_pass
POSTGRES_DB=realestate

# アプリケーション設定
FRONTEND_URL=http://your-domain-or-ip:3001
API_URL=http://your-domain-or-ip:8000

# セキュリティ（本番環境では必ず変更）
SECRET_KEY=your-secret-key-here

# スクレイピング設定
SCRAPER_DELAY=3
SCRAPER_CONCURRENT_TASKS=3
```

### 4.3 Docker Compose の設定を本番用に調整

```bash
# docker-compose.prod.ymlを作成
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: realestate-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      TZ: Asia/Tokyo
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U realestate"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: realestate-backend
    environment:
      DATABASE_URL: ${DATABASE_URL}
      TZ: Asia/Tokyo
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
      args:
        REACT_APP_API_URL: ${API_URL}
    container_name: realestate-frontend
    environment:
      REACT_APP_API_URL: ${API_URL}
    restart: unless-stopped

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

volumes:
  postgres_data:
  nginx_cache:
EOF
```

### 4.4 Nginx設定ファイルの作成

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

    # 管理画面
    location /admin {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        
        # 管理画面へのアクセス制限（必要に応じて）
        # allow 192.168.1.0/24;
        # deny all;
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

### 4.5 フロントエンドのDockerfileを作成

```bash
# frontend/Dockerfileの作成
cat > frontend/Dockerfile << 'EOF'
FROM node:18-alpine as builder

WORKDIR /app

# 依存関係のインストール
COPY frontend/package*.json ./
RUN npm ci --only=production

# アプリケーションのビルド
COPY frontend/ .
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

# 本番用イメージ
FROM node:18-alpine

WORKDIR /app

# serve パッケージのインストール
RUN npm install -g serve

# ビルド済みファイルのコピー
COPY --from=builder /app/build ./build

EXPOSE 3000

CMD ["serve", "-s", "build", "-l", "3000"]
EOF
```

### 4.6 バックエンドのDockerfileを作成（既存の場合は確認）

```bash
# backend/Dockerfileの確認・作成
cat > backend/Dockerfile << 'EOF'
FROM python:3.10-slim

WORKDIR /app

# システムパッケージのインストール
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Poetryのインストール
RUN pip install poetry

# 依存関係のインストール
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# アプリケーションコードのコピー
COPY backend/ ./backend/
COPY data/ ./data/

# ログディレクトリの作成
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
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

# 初期データの投入（必要に応じて）
docker exec realestate-backend poetry run python backend/scripts/seed_initial_data.py
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
        docker exec realestate-backend kill -USR1 1
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

## 8. SSL/TLS証明書の設定（オプション）

### 8.1 Let's Encrypt証明書の取得

```bash
# Certbotのインストール
sudo apt install -y certbot

# Nginxを一時停止
docker compose -f docker-compose.prod.yml stop nginx

# 証明書の取得
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Nginxを再起動
docker compose -f docker-compose.prod.yml start nginx
```

### 8.2 Nginx設定の更新

nginx-site.confのHTTPSセクションのコメントを解除し、証明書のパスを設定します。

## 9. モニタリングの設定

### 9.1 システムモニタリング

```bash
# htopのインストール
sudo apt install -y htop

# Docker statsのエイリアス設定
echo "alias dstats='docker stats --format \"table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\"'" >> ~/.bashrc
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
git pull origin main

# コンテナの再ビルドと再起動
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build

# データベースマイグレーション（必要な場合）
docker exec realestate-backend poetry run python backend/scripts/migrate_database.py
```

### 11.2 定期メンテナンス

```bash
# 週次メンテナンススクリプト
cat > /home/ubuntu/weekly-maintenance.sh << 'EOF'
#!/bin/bash
echo "Starting weekly maintenance..."

# Dockerイメージの更新
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
#   - ./postgres-custom.conf:/etc/postgresql/postgresql.conf
# command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

### 12.2 Nginxのキャッシュ設定

```bash
# nginx-site.confに追加
# proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m use_temp_path=off;

# location /api {
#     proxy_cache api_cache;
#     proxy_cache_valid 200 1m;
#     proxy_cache_valid 404 1m;
#     proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
#     proxy_cache_background_update on;
#     proxy_cache_lock on;
#     add_header X-Cache-Status $upstream_cache_status;
# }
```

## まとめ

このガイドに従うことで、AWS EC2 Ubuntu 24.04環境に不動産検索システムを構築し、安全かつ効率的に運用できます。定期的なバックアップとモニタリングを行い、システムの安定性を維持してください。

## 参考リンク

- [Docker公式ドキュメント](https://docs.docker.com/)
- [PostgreSQL公式ドキュメント](https://www.postgresql.org/docs/)
- [Nginx公式ドキュメント](https://nginx.org/en/docs/)
- [Ubuntu Server Guide](https://ubuntu.com/server/docs)