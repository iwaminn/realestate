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

> **注意**: ドメインを使用しない場合は、このセクションをスキップしてElastic IPで直接アクセスできます。

---

#### 方法1: AWS Route 53を使用する場合（推奨）

Route 53は月額$0.50/ホストゾーンのコストがかかりますが、AWSとの統合が簡単です。

##### ステップ1: ホストゾーンの作成

1. **AWSマネジメントコンソールにログイン**
2. **Route 53サービスを開く**
   - 検索バーで「Route 53」と入力
   - または、サービス一覧から「ネットワーキングとコンテンツ配信」→「Route 53」

3. **ホストゾーンの作成**
   - 左メニューから「ホストゾーン」をクリック
   - 「ホストゾーンの作成」ボタンをクリック
   - **ドメイン名**: `mscan.jp`（取得済みのドメイン名を入力）
   - **説明**: `不動産検索システム用DNS`（任意）
   - **タイプ**: `パブリックホストゾーン`を選択
   - **タグ**: 必要に応じて追加（例: `Name: realestate-dns`）
   - 「ホストゾーンの作成」ボタンをクリック

4. **ネームサーバー情報をメモ**
   - 作成されたホストゾーンを開く
   - **NSレコード**（タイプがNS）をクリック
   - 4つのネームサーバー（例: `ns-123.awsdns-45.com`）をメモまたはコピー
   - これは後でドメインレジストラで設定します

##### ステップ2: Aレコードの作成

1. **作成したホストゾーンを開く**
2. **「レコードを作成」ボタンをクリック**
3. **ルートドメイン用のAレコード作成**
   - **レコード名**: 空白のまま（ルートドメイン`mscan.jp`用）
   - **レコードタイプ**: `A - IPv4アドレスにルーティング`
   - **値**: EC2のElastic IPアドレス（例: `52.69.123.45`）
   - **TTL**: `300`秒（デフォルト）
   - **ルーティングポリシー**: `シンプルルーティング`
   - 「レコードを作成」ボタンをクリック

4. **wwwサブドメイン用のAレコード作成**（オプション）
   - 再度「レコードを作成」をクリック
   - **レコード名**: `www`
   - **レコードタイプ**: `A - IPv4アドレスにルーティング`
   - **値**: 同じElastic IPアドレス
   - **TTL**: `300`秒
   - 「レコードを作成」ボタンをクリック

##### ステップ3: ドメインレジストラでネームサーバーを変更

ドメインを購入したレジストラ（お名前.com、ムームードメイン、Google Domains等）の管理画面で設定します。

**お名前.comの場合**:
1. [お名前.com Navi](https://www.onamae.com/navi/login/)にログイン
2. 「ドメイン」タブ→「ドメイン機能一覧」をクリック
3. 設定するドメインの「ネームサーバー」→「変更する」をクリック
4. 「他のネームサーバーを利用」を選択
5. Route 53でメモした4つのネームサーバーを入力:
   ```
   プライマリネームサーバー: ns-123.awsdns-45.com
   セカンダリネームサーバー: ns-456.awsdns-78.net
   3番目のネームサーバー: ns-789.awsdns-01.org
   4番目のネームサーバー: ns-012.awsdns-34.co.uk
   ```
6. 「確認」→「OK」をクリック

**ムームードメインの場合**:
1. [ムームードメイン](https://muumuu-domain.com/)のコントロールパネルにログイン
2. 「ドメイン管理」→「ドメイン操作」→「ネームサーバ設定変更」
3. 対象ドメインの「ネームサーバ設定変更」をクリック
4. 「GMOペパボ以外のネームサーバを使用する」を選択
5. Route 53の4つのネームサーバーを入力
6. 「ネームサーバ設定変更」をクリック

**Google Domainsの場合**:
1. [Google Domains](https://domains.google.com/)にログイン
2. 対象ドメインを選択
3. 左メニューから「DNS」をクリック
4. 「カスタムネームサーバーを使用する」を選択
5. Route 53の4つのネームサーバーを入力
6. 「保存」をクリック

> **重要**: ネームサーバーの変更は反映まで**数時間～最大48時間**かかります。

##### ステップ4: DNS反映の確認

```bash
# ローカルマシンから確認（Mac/Linux）
nslookup mscan.jp

# 期待される結果:
# Server:		8.8.8.8
# Address:	8.8.8.8#53
#
# Non-authoritative answer:
# Name:	mscan.jp
# Address: 52.69.123.45  ← Elastic IPと一致すればOK

# digコマンドでも確認可能
dig mscan.jp +short
# 52.69.123.45 ← Elastic IPが表示されればOK

# Windowsの場合
nslookup mscan.jp 8.8.8.8
```

---

#### 方法2: お名前.comやムームードメインのDNSを使用する場合（無料）

ドメインレジストラのDNS機能を使う場合は、Route 53の月額料金がかかりません。

##### お名前.comの場合

1. **お名前.com Naviにログイン**
   - https://www.onamae.com/navi/login/

2. **DNS設定を開く**
   - 「ドメイン」タブ→「DNS関連機能の設定」
   - 対象ドメインにチェック→「次へ」

3. **Aレコードを追加**
   - 「DNSレコード設定を利用する」の「設定する」をクリック
   - **ホスト名**: 空白（ルートドメイン）
   - **TYPE**: `A`
   - **VALUE**: EC2のElastic IP（例: `52.69.123.45`）
   - **TTL**: `3600`
   - 「追加」ボタンをクリック

4. **wwwサブドメイン用のAレコードを追加**（オプション）
   - **ホスト名**: `www`
   - **TYPE**: `A`
   - **VALUE**: 同じElastic IP
   - **TTL**: `3600`
   - 「追加」ボタンをクリック

5. **設定を確認して保存**
   - 画面下部の「確認画面へ進む」
   - 内容を確認して「設定する」

##### ムームードメインの場合

1. **ムームードメインのコントロールパネルにログイン**
   - https://muumuu-domain.com/

2. **DNS設定を開く**
   - 「ドメイン管理」→「ドメイン操作」→「ムームーDNS」
   - 対象ドメインの「変更」をクリック

3. **カスタム設定を選択**
   - 「カスタム設定」を選択
   - 「設定2」をクリック

4. **Aレコードを追加**
   - **サブドメイン**: 空白（ルートドメイン）
   - **種別**: `A`
   - **内容**: EC2のElastic IP（例: `52.69.123.45`）
   - **優先度**: 空白

5. **wwwサブドメイン用のAレコードを追加**
   - **サブドメイン**: `www`
   - **種別**: `A`
   - **内容**: 同じElastic IP
   - **優先度**: 空白

6. **「セットアップ情報変更」をクリック**

##### Cloudflareの場合（無料でCDN・SSL付き）

Cloudflareは無料プランでも高機能なDNS・CDN・SSL証明書を提供します。

1. **Cloudflareにサインアップ**
   - https://dash.cloudflare.com/sign-up

2. **サイトを追加**
   - 「サイトを追加」をクリック
   - ドメイン名を入力（例: `mscan.jp`）
   - 「サイトを追加」をクリック
   - プラン選択: 「Free」を選択

3. **既存のDNSレコードをスキャン**
   - Cloudflareが自動的に既存のDNSレコードをスキャン
   - スキャン結果を確認して「続行」

4. **Aレコードを追加/確認**
   - 「DNSレコードを追加」をクリック
   - **タイプ**: `A`
   - **名前**: `@`（ルートドメイン）または空白
   - **IPv4アドレス**: EC2のElastic IP
   - **プロキシ状態**: オレンジ色（プロキシ経由）またはグレー（DNSのみ）
     - オレンジ: CloudflareのCDN・SSL・DDoS保護を有効化
     - グレー: DNSのみ（直接EC2にアクセス）
   - **TTL**: `Auto`
   - 「保存」をクリック

5. **wwwレコードを追加**
   - **タイプ**: `A`
   - **名前**: `www`
   - **IPv4アドレス**: 同じElastic IP
   - プロキシ状態とTTLは同様に設定
   - 「保存」をクリック

6. **ネームサーバーを変更**
   - Cloudflareが表示する2つのネームサーバーをメモ（例: `adam.ns.cloudflare.com`）
   - ドメインレジストラの管理画面でネームサーバーを変更
   - 変更完了後、Cloudflareの画面で「完了、ネームサーバーを確認」をクリック

7. **SSL/TLS設定**（Cloudflareのプロキシ使用時）
   - 左メニュー「SSL/TLS」をクリック
   - **暗号化モード**: `フレキシブル`を選択（初期設定）
   - 後でEC2側でSSL証明書を設定したら`フル`に変更

---

#### DNS設定後の確認手順

1. **DNS反映の確認**（反映まで10分～48時間）

```bash
# ローカルマシンから
nslookup mscan.jp

# 期待される結果:
# Name:	mscan.jp
# Address: <EC2のElastic IP>

# digコマンドで詳細確認
dig mscan.jp

# オンラインツールでも確認可能
# https://www.whatsmydns.net/
# ドメイン名を入力して世界中のDNSサーバーから確認
```

2. **HTTPアクセス確認**

```bash
# ドメインでアクセスできることを確認
curl -I http://mscan.jp

# 期待される結果:
# HTTP/1.1 200 OK または 301/302 (リダイレクト)

# ブラウザでもアクセス確認
# http://mscan.jp
```

3. **pingテスト**

```bash
ping mscan.jp

# 期待される結果:
# PING mscan.jp (52.69.123.45): 56 data bytes
# 64 bytes from 52.69.123.45: icmp_seq=0 ttl=52 time=10.2 ms
```

---

#### トラブルシューティング

**DNSが反映されない場合**:
```bash
# 1. ドメインレジストラのネームサーバー設定を再確認
# 2. DNSキャッシュをクリア（ローカルマシン）

# Macの場合
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder

# Windowsの場合
ipconfig /flushdns

# Linuxの場合
sudo systemd-resolve --flush-caches

# 3. 別のDNSサーバーで確認
dig @8.8.8.8 mscan.jp        # Google DNS
dig @1.1.1.1 mscan.jp        # Cloudflare DNS
```

**「このサイトにアクセスできません」エラーの場合**:
- EC2のセキュリティグループでHTTP(80)とHTTPS(443)が開いているか確認
- Nginx/Apacheが起動しているか確認: `docker ps`
- EC2インスタンスが起動しているか確認

**Cloudflare使用時のエラー**:
- プロキシ状態をオレンジからグレーに変更して直接接続を試す
- SSL/TLS設定を「フレキシブル」に変更

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

**重要な設定項目**を以下のように編集します：

```env
# ==============================================
# 本番環境用設定（必ず変更が必要）
# ==============================================

# フロントエンド設定
VITE_API_URL=/api

# データベース設定
POSTGRES_DB=realestate
POSTGRES_USER=realestate
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD_HERE  # ← 必ず変更！
DATABASE_URL=postgresql://realestate:YOUR_STRONG_PASSWORD_HERE@postgres:5432/realestate

# 管理画面認証
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD_HERE  # ← 必ず変更！
DISABLE_ADMIN_AUTH=false  # 本番環境では必ずfalse

# メール送信設定（本番環境で必須）
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password  # Gmailの場合はアプリパスワード
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@mscan.jp
MAIL_FROM_NAME=都心マンション価格チェッカー
MAIL_STARTTLS=True
MAIL_SSL_TLS=False

# フロントエンドURL（メール内のリンク用）
FRONTEND_URL=https://mscan.jp  # HTTPSを推奨

# Google OAuth設定（オプション）
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://mscan.jp/api/oauth/google/callback

# スクレイパー設定
SCRAPER_DETAIL_REFETCH_DAYS=90
```

> **セキュリティ上の注意**:
> - `.env`ファイルはGitにコミットしないでください（`.gitignore`に含まれています）
> - パスワードは複雑で推測されにくいものを使用してください
> - 本番環境では`DISABLE_ADMIN_AUTH=false`を必ず設定してください
> - HTTPSを使用する場合は、すべてのURLを`https://`に変更してください

### 4.3 本番用Docker Compose設定の確認

本番環境用の`docker-compose.prod.yml`ファイルは既にリポジトリに含まれています。

```bash
# リポジトリのクローン時に自動的に含まれます
cd /home/ubuntu/realestate
ls -la docker-compose.prod.yml

# 確認
cat docker-compose.prod.yml
```

> **重要**: `poetry.lock` ファイルはGit管理されています。本番環境で正確な依存関係を再現するため、このファイルは削除しないでください。

**主な特徴**：
- PostgreSQL、バックエンド、フロントエンド、Nginxの4つのサービス
- 環境変数は`.env`ファイルから読み込み
- Nginxがリバースプロキシとして動作（ポート80/443のみ公開）
- 本番用Dockerfileを使用（フロントエンドは最適化されたビルド）
- ヘルスチェック機能付き
- 自動再起動設定（`restart: unless-stopped`）

> **重要**: `docker-compose.prod.yml`はGitで管理されているため、設定を変更する場合は開発環境で編集してGitにコミット→本番環境で`git pull`する流れを推奨します。

### 4.4 本番用フロントエンドDockerfileの確認

本番環境用の`docker/frontend/Dockerfile.prod`ファイルは既にリポジトリに含まれています。

```bash
# リポジトリのクローン時に自動的に含まれます
cat docker/frontend/Dockerfile.prod
```

**主な特徴**：
- **マルチステージビルド**：ビルド用と実行用の2段階で最適化
- **ビルドステージ**：依存関係のインストール→Viteでビルド
- **実行ステージ**：`serve`パッケージで静的ファイルを配信
- **軽量化**：ビルド時の依存関係は最終イメージに含まれない
- **環境変数対応**：`VITE_API_URL`をビルド時に設定可能

> **注意**: このファイルもGitで管理されているため、変更する場合は開発環境で編集してコミット→本番環境で`git pull`してください。

### 4.5 Nginx設定ファイルの確認

本番環境用のNginx設定ファイル（`nginx.conf`と`nginx-site.conf`）は既にリポジトリに含まれています。

```bash
# リポジトリのクローン時に自動的に含まれます
ls -la nginx*.conf

# 設定内容の確認
cat nginx.conf
cat nginx-site.conf
```

**nginx.conf の主な設定**：
- ワーカープロセス：自動設定
- Gzip圧縮：有効（レスポンスサイズの削減）
- レート制限：API 10req/秒、一般 30req/秒
- 最大アップロードサイズ：20MB

**nginx-site.conf の主な設定**：
- フロントエンド：ポート3000へプロキシ
- API：`/api/`パスをバックエンド（ポート8000）へプロキシ
- タイムアウト：300秒（スクレイピング対応）
- ヘルスチェック：`/health`エンドポイント
- HTTPS対応：コメントアウトされた設定あり（Let's Encrypt利用時に有効化）

**ドメイン名の設定**：
`nginx-site.conf`の`server_name`を自分のドメイン名に変更してください：
```bash
nano nginx-site.conf
# server_name _; を以下のように変更
# server_name mscan.jp;
```

> **注意**: これらのファイルもGitで管理されているため、変更する場合は開発環境で編集してコミット→本番環境で`git pull`してください。

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

#### 新規構築の場合

```bash
# データベーススキーマの作成
docker exec realestate-backend poetry run python backend/scripts/init_schema.py
```

#### バックアップから復元する場合

開発環境や既存環境からデータベースをバックアップして本番環境に復元する手順：

**1. 既存環境でバックアップを作成**

```bash
# 開発環境またはバックアップ元環境で実行
docker exec realestate-postgres pg_dump -U realestate -d realestate -F c -f /tmp/realestate_backup.dump

# バックアップファイルをホストにコピー
docker cp realestate-postgres:/tmp/realestate_backup.dump ./realestate_backup.dump
```

**2. バックアップファイルを本番環境に転送**

```bash
# ローカル環境から本番環境へ転送
scp -i ~/.ssh/your-key.pem realestate_backup.dump ubuntu@your-ec2-ip:/home/ubuntu/
```

**3. 本番環境でバックアップを復元**

```bash
# 本番環境にSSH接続
ssh -i ~/.ssh/your-key.pem ubuntu@your-ec2-ip
cd /home/ubuntu/realestate

# コンテナ名を確認（docker-compose.prod.ymlで起動している場合）
docker ps --format "table {{.Names}}\t{{.Image}}"

# バックアップファイルをコンテナにコピー（末尾のスラッシュなし）
# 注意: コンテナ名が異なる場合は上記で確認した名前を使用
docker cp /home/ubuntu/realestate_backup.dump realestate-postgres:/tmp

# データベース接続を切断してから削除・再作成
# 1. バックエンドを停止（データベース接続を切断）
docker compose -f docker-compose.prod.yml stop backend

# 2. すべてのセッションを強制終了
docker exec realestate-postgres psql -U realestate -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'realestate' AND pid <> pg_backend_pid();"

# 3. データベースを削除して再作成（既存データが削除されるので注意！）
docker exec realestate-postgres psql -U realestate -d postgres -c "DROP DATABASE IF EXISTS realestate;"
docker exec realestate-postgres psql -U realestate -d postgres -c "CREATE DATABASE realestate;"

# 4. バックアップを復元
docker exec realestate-postgres pg_restore -U realestate -d realestate -v /tmp/realestate_backup.dump

# 5. バックエンドを起動
docker compose -f docker-compose.prod.yml start backend
```

**4. 復元の確認**

```bash
# データベースに接続して確認
docker exec realestate-postgres psql -U realestate -d realestate -c "\dt"
docker exec realestate-postgres psql -U realestate -d realestate -c "SELECT COUNT(*) FROM master_properties;"
```

**注意事項**：
- 復元時は既存のデータベースを削除するため、本番環境で初めて実行する場合のみ推奨
- 定期的なバックアップは「11.2 定期メンテナンス」を参照
- 大量のデータがある場合は復元に時間がかかります

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

### 6.3 バックアップ戦略の選択

データベースのバックアップには2つの方法があります。システムの重要度とコストに応じて選択してください。

| 方法 | メリット | デメリット | 推奨用途 |
|------|---------|-----------|----------|
| **ローカルバックアップのみ** | 設定が簡単、追加コストなし | EC2障害時にデータ損失のリスク | テスト環境、開発環境 |
| **S3バックアップ（推奨）** | EC2障害時も安全、長期保存可能 | 少額のコスト（月額約20円） | 本番環境 |

#### どちらを選ぶべきか？

- **本番環境**: S3バックアップ（6.3.2）を強く推奨
- **開発・テスト環境**: ローカルバックアップ（6.3.1）でも可

---

### 6.3.1 ローカルバックアップのみ（基本）

EC2インスタンス内にバックアップを保存します。設定は簡単ですが、EC2インスタンスが停止・削除された場合、バックアップも失われます。

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

> **注意**: このバックアップ方法は、EC2インスタンスが正常に動作している場合のみ有効です。インスタンスの障害やストレージの破損には対応できません。本番環境では6.3.2のS3バックアップを使用してください。

---

### 6.3.2 S3バックアップ（推奨）

EC2インスタンスのトラブルに備えて、S3への外部バックアップを設定します。

#### 6.3.2.1 AWS CLIのインストール

```bash
# AWS CLIのインストール（Ubuntu 24.04対応）
# Snapを使用（推奨）
sudo snap install aws-cli --classic

# バージョン確認
aws --version

# 【注意】apt版（awscli）はUbuntu 24.04では利用できません
# 代替方法1: 公式インストーラーを使用する場合
# curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
# unzip awscliv2.zip
# sudo ./aws/install

# 代替方法2: pipを使用する場合
# sudo apt install -y python3-pip
# pip3 install awscli --user
```

#### 6.3.2.2 IAMロールの設定

> **重要**: S3バケットを作成する前に、IAMロールを設定する必要があります。

**AWSマネジメントコンソールでの作業：**

1. **IAMポリシーの作成**：
   - IAMコンソール → ポリシー → ポリシーを作成
   - JSONタブで以下を貼り付け：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject",
        "s3:PutBucketVersioning",
        "s3:PutLifecycleConfiguration"
      ],
      "Resource": [
        "arn:aws:s3:::realestate-backup-*/*",
        "arn:aws:s3:::realestate-backup-*"
      ]
    }
  ]
}
```

   - ポリシー名: `RealestateS3BackupPolicy`

2. **IAMロールの作成**：
   - IAMコンソール → ロール → ロールを作成
   - 信頼されたエンティティ: AWS サービス
   - ユースケース: EC2
   - 先ほど作成したポリシーをアタッチ
   - ロール名: `RealestateBackupRole`

3. **EC2インスタンスにロールをアタッチ**：
   - EC2コンソール → インスタンス選択
   - アクション → セキュリティ → IAMロールを変更
   - `RealestateBackupRole` を選択

4. **IAMロール設定の確認**：

```bash
# ロールが正しくアタッチされているか確認（数秒待ってから実行）
aws sts get-caller-identity

# 成功すると以下のような出力が表示されます：
# {
#     "UserId": "AIDACKCEVSQ6C2EXAMPLE",
#     "Account": "123456789012",
#     "Arn": "arn:aws:sts::123456789012:assumed-role/RealestateBackupRole/i-1234567890abcdef0"
# }
```

#### 6.3.2.3 S3バケットの作成

IAMロールの設定が完了したら、S3バケットを作成します。

```bash
# バケット名を決定（グローバルでユニークな名前が必要）
BUCKET_NAME="realestate-backup-$(date +%Y%m%d)"

# S3バケットの作成（東京リージョン）
aws s3 mb s3://${BUCKET_NAME} --region ap-northeast-1

# バージョニングを有効化（誤削除対策）
aws s3api put-bucket-versioning \
  --bucket ${BUCKET_NAME} \
  --versioning-configuration Status=Enabled

# ライフサイクルポリシーの設定
cat > /tmp/lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "Id": "MoveToIA",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket ${BUCKET_NAME} \
  --lifecycle-configuration file:///tmp/lifecycle.json

# バケット名を環境変数として保存（後続のスクリプトで使用）
echo "export S3_BACKUP_BUCKET=${BUCKET_NAME}" >> ~/.bashrc
source ~/.bashrc

echo "S3バケット作成完了: ${BUCKET_NAME}"
```

#### 6.3.2.4 S3バックアップスクリプトの作成

```bash
# S3対応バックアップスクリプトの作成
cat > /home/ubuntu/backup-realestate-s3.sh << 'EOF'
#!/bin/bash

# 設定
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_BACKUP_FILE="$BACKUP_DIR/realestate_db_$DATE.sql"
S3_BUCKET="YOUR_BUCKET_NAME"  # 実際のバケット名に変更
LOG_FILE="/home/ubuntu/logs/backup.log"

# ログディレクトリ作成
mkdir -p /home/ubuntu/logs

# ログ出力関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a $LOG_FILE
}

log "=== Backup started ==="

# バックアップディレクトリの作成
mkdir -p $BACKUP_DIR

# データベースのバックアップ
log "Creating database dump..."
if docker exec realestate-postgres pg_dump -U realestate realestate > $DB_BACKUP_FILE; then
    log "Database dump created successfully"
else
    log "ERROR: Database dump failed"
    exit 1
fi

# 圧縮
log "Compressing backup..."
if gzip $DB_BACKUP_FILE; then
    log "Compression completed"
    COMPRESSED_FILE="${DB_BACKUP_FILE}.gz"
else
    log "ERROR: Compression failed"
    exit 1
fi

# S3へアップロード
log "Uploading to S3..."
if aws s3 cp $COMPRESSED_FILE s3://${S3_BUCKET}/database/ \
    --storage-class STANDARD_IA \
    --metadata "backup-date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; then
    log "Upload to S3 completed: s3://${S3_BUCKET}/database/$(basename $COMPRESSED_FILE)"
else
    log "ERROR: S3 upload failed"
    exit 1
fi

# ローカルの古いバックアップを削除（7日以上前）
log "Cleaning up old local backups..."
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

# S3の古いバックアップを削除（90日以上前）
log "Cleaning up old S3 backups..."
CUTOFF_DATE=$(date -d '90 days ago' +%Y-%m-%d)
aws s3 ls s3://${S3_BUCKET}/database/ | while read -r line; do
    FILE_DATE=$(echo $line | awk '{print $1}')
    FILE_NAME=$(echo $line | awk '{print $4}')
    if [[ "$FILE_DATE" < "$CUTOFF_DATE" ]] && [[ ! -z "$FILE_NAME" ]]; then
        log "Deleting old backup: $FILE_NAME"
        aws s3 rm s3://${S3_BUCKET}/database/$FILE_NAME
    fi
done

log "=== Backup completed successfully ==="

exit 0
EOF

chmod +x /home/ubuntu/backup-realestate-s3.sh

# 6.3.2.3で設定した環境変数を使用してバケット名を置換
sed -i "s/YOUR_BUCKET_NAME/$S3_BACKUP_BUCKET/g" /home/ubuntu/backup-realestate-s3.sh

# 設定確認
echo "バックアップスクリプトに設定されたS3バケット: $S3_BACKUP_BUCKET"
grep "S3_BUCKET=" /home/ubuntu/backup-realestate-s3.sh
```

#### 6.3.2.5 cronジョブの設定

```bash
# 既存のローカルバックアップcronを削除
crontab -l | grep -v backup-realestate.sh | crontab -

# S3バックアップcronを追加（毎日午前2時に実行）
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/backup-realestate-s3.sh") | crontab -

# cronジョブの確認
crontab -l
```

#### 6.3.2.6 手動テスト

```bash
# スクリプトを手動実行してテスト
/home/ubuntu/backup-realestate-s3.sh

# ログを確認
cat /home/ubuntu/logs/backup.log

# S3のバックアップを確認
aws s3 ls s3://$S3_BACKUP_BUCKET/database/
```

#### 6.3.2.7 S3からの復元方法

```bash
# 復元スクリプトの作成
cat > /home/ubuntu/restore-from-s3.sh << 'EOF'
#!/bin/bash

S3_BUCKET="YOUR_BUCKET_NAME"  # 実際のバケット名に変更

# 利用可能なバックアップを表示
echo "Available backups in S3:"
aws s3 ls s3://${S3_BUCKET}/database/ | grep ".sql.gz"

# 復元するファイル名を入力
read -p "復元するバックアップファイル名を入力してください: " BACKUP_FILE

# S3からダウンロード
echo "Downloading backup from S3..."
aws s3 cp s3://${S3_BUCKET}/database/${BACKUP_FILE} /tmp/

# 解凍
echo "Extracting backup..."
gunzip /tmp/${BACKUP_FILE}

# データベースへの接続を強制終了
echo "Terminating database connections..."
docker exec realestate-postgres psql -U realestate -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'realestate' AND pid <> pg_backend_pid();"

# データベースを削除して再作成
echo "Recreating database..."
docker exec realestate-postgres psql -U realestate -d postgres -c "DROP DATABASE IF EXISTS realestate;"
docker exec realestate-postgres psql -U realestate -d postgres -c "CREATE DATABASE realestate;"

# 復元
echo "Restoring database..."
cat /tmp/${BACKUP_FILE%.gz} | docker exec -i realestate-postgres psql -U realestate -d realestate

echo "Restore completed!"

# 一時ファイルの削除
rm /tmp/${BACKUP_FILE} /tmp/${BACKUP_FILE%.gz}
EOF

chmod +x /home/ubuntu/restore-from-s3.sh

# 6.3.2.3で設定した環境変数を使用してバケット名を置換
sed -i "s/YOUR_BUCKET_NAME/$S3_BACKUP_BUCKET/g" /home/ubuntu/restore-from-s3.sh

# 設定確認
echo "復元スクリプトに設定されたS3バケット: $S3_BACKUP_BUCKET"
grep "S3_BUCKET=" /home/ubuntu/restore-from-s3.sh
```

#### 6.3.2.8 コスト最適化

S3のライフサイクルポリシーにより、以下のようにコストを最適化します：

- **最初の30日間**: STANDARD_IA（低頻度アクセス）
- **365日後**: 自動削除

ストレージコストの目安：
- データベースサイズ: 約50MB（圧縮後）
- 月間バックアップ数: 30個
- 月額コスト: 約$0.15（約20円）

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
sudo certbot certonly --standalone -d mscan.jp

# 証明書の確認
sudo ls -la /etc/letsencrypt/live/mscan.jp/
# fullchain.pem と privkey.pem が存在することを確認
```

### 8.2 最新コードの取得

HTTPS設定は既にリポジトリに含まれているため、最新コードを取得するだけで適用されます：

```bash
cd /home/ubuntu/realestate
git pull origin master
```

> **注意**: `nginx-site.conf` と `docker-compose.prod.yml` は既にHTTPS対応済みです。手動で編集する必要はありません。

### 8.3 環境変数の更新

HTTPSを使用する場合、.envファイルの以下の設定を更新します：

```bash
nano .env
```

```env
# HTTPSに変更
FRONTEND_URL=https://mscan.jp

# Google OAuthのリダイレクトURIもHTTPSに
GOOGLE_REDIRECT_URI=https://mscan.jp/api/oauth/google/callback
```

### 8.4 システムの再起動

```bash
# すべてのコンテナを再起動
docker compose -f docker-compose.prod.yml up -d

# ログを確認してエラーがないことを確認
docker compose -f docker-compose.prod.yml logs nginx

# HTTPSでアクセスできることを確認
curl -I https://mscan.jp
```

### 8.5 証明書の自動更新設定

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

### 8.6 HTTPSの動作確認

```bash
# HTTPアクセスがHTTPSにリダイレクトされることを確認
curl -I http://mscan.jp
# Location: https://mscan.jp が返ることを確認

# HTTPSでアクセスできることを確認
curl -I https://mscan.jp
# 200 OK が返ることを確認

# SSL証明書の有効性を確認
openssl s_client -connect mscan.jp:443 -servername mscan.jp < /dev/null
```

### 8.7 Google OAuthの設定（オプション）

Google アカウントでのログイン機能を有効にする場合は、以下の手順でGoogle OAuth 2.0を設定します。

#### 8.7.1 Google Cloud Consoleでプロジェクトを作成

1. **Google Cloud Consoleにアクセス**
   - https://console.cloud.google.com/ にアクセス
   - Googleアカウントでログイン

2. **新しいプロジェクトを作成**
   - 画面上部の「プロジェクトを選択」をクリック
   - 「新しいプロジェクト」をクリック
   - プロジェクト名: 任意（例: mscan-oauth）
   - 「作成」をクリック

3. **プロジェクトを選択**
   - 作成したプロジェクトが自動的に選択されます

#### 8.7.2 OAuth同意画面の設定

**現在のGoogle Cloud Consoleの画面構成に対応した手順:**

1. **APIとサービス → OAuth同意画面**
   - 左メニューから「APIとサービス」→「OAuth同意画面」を選択

2. **User Typeの選択**
   - **外部**を選択（一般ユーザーが利用可能）
   - 「作成」をクリック

3. **アプリ情報の入力**
   - **アプリ名**: `mscan.jp 都心マンション価格チェッカー`
   - **ユーザーサポートメール**: あなたのメールアドレス（admin@mscan.jpなど）
   - **アプリのロゴ**: （オプション）
   - **承認済みドメイン**: `mscan.jp`
   - **デベロッパーの連絡先情報**: あなたのメールアドレス
   - 「保存して次へ」をクリック

4. **OAuth同意画面が作成されます**
   - 画面左にメニューが表示されます：
     - **概要** (Overview)
     - **ブランディング** (Branding)
     - **対象** (Audience)
     - **クライアント** (Clients)
     - **データアクセス** (Data Access)
     - **検証センター** (Verification Center)

5. **スコープの設定**
   - 左メニューから「**データアクセス**」をクリック
   - 「スコープを追加または削除」ボタンをクリック
   - 検索ボックスで以下のスコープを検索して選択：
     - `.../auth/userinfo.email` （メールアドレスの取得）
     - `.../auth/userinfo.profile` （プロフィール情報の取得）
   - 「更新」ボタンをクリック
   - 画面上部の「保存して次へ」をクリック

6. **テストユーザーの追加**（オプション - 本番公開前のテスト用）
   - 左メニューから「**対象**」をクリック
   - 「テストユーザーを追加」セクションで、テストに使用するGoogleアカウントを追加
   - **注意**: テストステータスのままでも、後で本番公開申請を行えば全ユーザーがログイン可能になります
   - 今は追加せずスキップしても問題ありません

7. **設定完了の確認**
   - 左メニューの「**概要**」をクリック
   - 以下が設定されていることを確認：
     - ✓ アプリ名が表示されている
     - ✓ スコープが2件追加されている
     - ✓ 公開ステータスが「テスト」または「本番環境」になっている

#### 8.7.3 OAuth 2.0クライアントIDの作成

1. **認証情報ページを開く**
   - 左メニューから「APIとサービス」→「認証情報」を選択

2. **OAuth 2.0クライアントIDを作成**
   - 「認証情報を作成」→「OAuth 2.0クライアントID」をクリック

3. **アプリケーションの種類を選択**
   - **アプリケーションの種類**: `ウェブアプリケーション`
   - **名前**: `mscan.jp Web Client`

4. **承認済みのリダイレクトURIを追加**
   
   **開発環境用（ローカル）:**
   ```
   http://localhost:3001/api/oauth/google/callback
   ```
   
   **本番環境用（HTTPS）:**
   ```
   https://mscan.jp/api/oauth/google/callback
   ```
   
   > **注意**: 両方を追加することで、開発環境と本番環境の両方で使用可能になります。
   > 開発環境ではViteのプロキシを経由してバックエンドにアクセスするため、3001番ポートを使用します。

5. **作成**
   - 「作成」ボタンをクリック
   - **クライアントIDとクライアントシークレット**が表示されます
   - これらをコピーして安全な場所に保存（**重要: クライアントシークレットは再表示できません**）

#### 8.7.4 環境変数の設定

本番サーバーの`.env`ファイルにOAuth設定を追加します：

```bash
cd /home/ubuntu/realestate
nano .env
```

以下を追加：

```env
# Google OAuth設定
GOOGLE_CLIENT_ID=123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abcdefghijklmnopqrstuvwxyz
GOOGLE_REDIRECT_URI=https://mscan.jp/api/oauth/google/callback
```

**開発環境の場合**（`/home/ubuntu/realestate/.env`）:
```env
GOOGLE_REDIRECT_URI=http://localhost:3001/api/oauth/google/callback
```

> **注意**: 開発環境ではViteのプロキシ（localhost:3001）を経由してバックエンドにアクセスするため、3001番ポートを使用します。

#### 8.7.5 コンテナの再起動

```bash
cd /home/ubuntu/realestate
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

#### 8.7.6 動作確認

1. **フロントエンドにアクセス**
   - https://mscan.jp にアクセス
   - ユーザーアイコンをクリック
   - 「Googleでログイン」ボタンが表示されることを確認

2. **ログインテスト**
   - 「Googleでログイン」をクリック
   - Googleアカウント選択画面が表示される
   - アカウントを選択してログイン
   - mscan.jpにリダイレクトされ、ログイン状態になる

#### 8.7.7 本番公開（オプション）

テストユーザーのみでなく、一般ユーザーにも公開する場合：

1. **Google Cloud Console → OAuth同意画面**
2. **「アプリを公開」ボタンをクリック**
3. 確認画面で「確認」をクリック

> **注意**: 本番公開前に、プライバシーポリシーと利用規約のURLを設定する必要がある場合があります。

#### 8.7.8 HTTPSへの移行時の更新

HTTPSを有効にした後、Google Cloud ConsoleでリダイレクトURIを更新します：

1. Google Cloud Console (https://console.cloud.google.com/) にログイン
2. プロジェクトを選択
3. 「APIとサービス」→「認証情報」
4. OAuth 2.0クライアントIDを選択
5. 「承認済みのリダイレクトURI」に追加：
   - `https://mscan.jp/api/oauth/google/callback`
6. 「保存」をクリック

### 8.8 トラブルシューティング

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
nslookup mscan.jp
dig mscan.jp

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
docker exec realestate-backend poetry run python backend/scripts/init_schema.py
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

## 13. メール機能の設定（Google Workspace）

本システムでは、独自ドメイン（mscan.jp）を使用したプロフェッショナルなメール送受信のため、Google Workspaceを使用します。

### 13.1 Google Workspaceアカウントの作成

#### 手順

1. **Google Workspaceに登録**
   - https://workspace.google.com/ にアクセス
   - 「使ってみる」をクリック
   - ビジネス名: 任意（例: mscan.jp）
   - 従業員数: 自分のみ
   - 国/地域: 日本

2. **ドメインの設定**
   - 「使用するドメインを指定」を選択
   - ドメイン名: `mscan.jp` を入力
   - 「次へ」をクリック

3. **管理者アカウントの作成**
   - メールアドレス: `admin@mscan.jp`（推奨）または任意
   - パスワードを設定

4. **プランの選択**
   - **Business Starter**: 月額680円/ユーザー（推奨）
     - 30GBストレージ
     - カスタムメール（@mscan.jp）
     - セキュアなビデオ会議
   - **Business Standard**: 月額1,360円/ユーザー
     - 2TBストレージ
     - その他ビジネス機能

### 13.2 ドメイン所有権の確認

Google Workspaceの設定ウィザードに従ってドメイン所有権を確認します。

#### 方法1: TXTレコードによる確認（推奨）

1. **Google Workspaceで確認コードを取得**
   - 管理コンソール (https://admin.google.com/) にログイン
   - 「ドメインの確認」画面で表示される確認コードをコピー

2. **Route 53でTXTレコードを追加**
```bash
# AWS CLIでTXTレコードを追加する場合
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_HOSTED_ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "mscan.jp",
        "Type": "TXT",
        "TTL": 3600,
        "ResourceRecords": [{
          "Value": "\"google-site-verification=YOUR_VERIFICATION_CODE\""
        }]
      }
    }]
  }'
```

または、**Route 53コンソールで手動設定**：
   - Route 53コンソール → ホストゾーン → mscan.jp
   - 「レコードを作成」をクリック
   - レコードタイプ: TXT
   - 名前: （空欄）
   - 値: `google-site-verification=YOUR_VERIFICATION_CODE`
   - TTL: 3600
   - 「レコードを作成」

3. **Google側で確認を実行**
   - Google Workspace管理コンソールに戻る
   - 「ドメインの所有権を確認」をクリック
   - 確認には数分～最大48時間かかる場合があります

### 13.3 MXレコードの設定（メール受信用）

メールを受信するため、MXレコードをGoogleのメールサーバーに向けます。

#### Route 53での設定

**Route 53コンソール**:
1. Route 53コンソール → ホストゾーン → mscan.jp
2. 「レコードを作成」をクリック
3. 以下の5つのMXレコードを追加（優先度順）:

| 優先度 | メールサーバー |
|--------|----------------|
| 1      | ASPMX.L.GOOGLE.COM |
| 5      | ALT1.ASPMX.L.GOOGLE.COM |
| 5      | ALT2.ASPMX.L.GOOGLE.COM |
| 10     | ALT3.ASPMX.L.GOOGLE.COM |
| 10     | ALT4.ASPMX.L.GOOGLE.COM |

**設定例（最初のレコード）**:
- レコード名: （空欄）
- レコードタイプ: MX
- 値: `1 ASPMX.L.GOOGLE.COM`
- TTL: 3600

**AWS CLIでの設定例**:
```bash
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_HOSTED_ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "mscan.jp",
        "Type": "MX",
        "TTL": 3600,
        "ResourceRecords": [
          {"Value": "1 ASPMX.L.GOOGLE.COM"},
          {"Value": "5 ALT1.ASPMX.L.GOOGLE.COM"},
          {"Value": "5 ALT2.ASPMX.L.GOOGLE.COM"},
          {"Value": "10 ALT3.ASPMX.L.GOOGLE.COM"},
          {"Value": "10 ALT4.ASPMX.L.GOOGLE.COM"}
        ]
      }
    }]
  }'
```

### 13.4 SPF/DKIM/DMARCレコードの設定（送信認証用）

メール送信の信頼性を高めるため、認証レコードを設定します。

#### SPFレコード（送信者認証）

**Route 53で設定**:
- レコードタイプ: TXT
- 名前: （空欄）
- 値: `v=spf1 include:_spf.google.com ~all`
- TTL: 3600

#### DKIMレコード（電子署名）

1. **Google Workspace管理コンソールでDKIMを有効化**
   - https://admin.google.com/ にログイン
   - アプリ → Google Workspace → Gmail → メールの認証
   - 「新しいレコードを生成」をクリック
   - DKIM鍵のサイズ: 2048ビット（推奨）
   - 表示されるDNSレコードをコピー

2. **Route 53でTXTレコードを追加**
   - レコード名: `google._domainkey`
   - レコードタイプ: TXT
   - 値: Google Workspaceで表示されたDKIM鍵（例: `v=DKIM1; k=rsa; p=MIGfMA0GCS...`）
   - TTL: 3600

3. **Google側でDKIMを有効化**
   - 管理コンソールで「認証を開始」をクリック

#### DMARCレコード（ポリシー設定）

**Route 53で設定**:
- レコード名: `_dmarc`
- レコードタイプ: TXT
- 値: `v=DMARC1; p=quarantine; rua=mailto:admin@mscan.jp`
- TTL: 3600

**DMARCポリシーの意味**:
- `p=quarantine`: 認証失敗メールを迷惑メールフォルダに
- `p=reject`: 認証失敗メールを拒否（より厳格）
- `rua=`: レポート送信先メールアドレス

### 13.5 メールアドレスの作成

#### 推奨メールアドレス構成

1. **admin@mscan.jp** - 管理者用（既に作成済み）
2. **noreply@mscan.jp** - システム送信用（パスワードリセット等）
3. **info@mscan.jp** - 問い合わせ用（オプション）

#### メールアドレスの作成手順

以下の手順で、noreply@mscan.jpとinfo@mscan.jpの両方を作成します。

##### 共通手順: ユーザーの追加

1. **Google Workspace管理コンソールにアクセス**
   - https://admin.google.com/ にログイン
   - admin@mscan.jpアカウントでログイン

2. **新しいユーザーを追加**
   - 左メニューから「ディレクトリ」→「ユーザー」をクリック
   - 「新しいユーザーを追加」ボタンをクリック

##### noreply@mscan.jpの作成

1. **ユーザー情報を入力**
   - **名**: No
   - **姓**: Reply
   - **メインのメールアドレス**: `noreply`（@mscan.jpは自動的に付加されます）
   - **パスワード**: 自動生成またはカスタム設定（16文字以上推奨）
   - 「追加」をクリック

2. **アプリパスワードの生成（SMTP用）**
   - noreply@mscan.jpアカウントでログイン（https://mail.google.com/）
   - https://myaccount.google.com/security にアクセス
   - 「2段階認証プロセス」を有効化
   - https://myaccount.google.com/apppasswords にアクセス
   - アプリ名: `都心マンション価格チェッカー`
   - 「生成」をクリック
   - 表示された16文字のパスワードをコピー（**重要: 再表示できません**）
   - このパスワードを`.env`ファイルの`MAIL_PASSWORD`に設定

##### info@mscan.jpの作成

1. **ユーザー情報を入力**
   - 管理コンソールで再度「新しいユーザーを追加」をクリック
   - **名**: Info
   - **姓**: mscan.jp
   - **メインのメールアドレス**: `info`
   - **パスワード**: 強力なパスワードを設定（16文字以上推奨）
   - 「追加」をクリック

2. **メールの受信確認**
   - info@mscan.jpアカウントでログイン（https://mail.google.com/）
   - 正常にログインできることを確認
   - このアカウントでメールの送受信が可能になります

3. **メール転送設定（オプション）**
   
   info@mscan.jpへのメールをadmin@mscan.jpに転送したい場合：
   
   - info@mscan.jpでログイン
   - Gmail設定（右上の歯車アイコン）→「すべての設定を表示」
   - 「メール転送とPOP/IMAP」タブ
   - 「転送先アドレスを追加」をクリック
   - admin@mscan.jpを入力
   - 確認コードを入力（admin@mscan.jpに届いたメールから）
   - 「受信メールをadmin@mscan.jpに転送して、infoのコピーを受信トレイに残す」を選択
   - 「変更を保存」

##### 作成したメールアドレスの用途

| メールアドレス | 用途 | SMTP送信 | 受信 |
|----------------|------|----------|------|
| admin@mscan.jp | 管理者用 | - | ✅ |
| noreply@mscan.jp | システム送信専用 | ✅ | - |
| info@mscan.jp | 問い合わせ受付 | - | ✅ |

> **ヒント**: info@mscan.jpは問い合わせフォームやフッターに記載する公開メールアドレスとして使用できます。

### 13.6 アプリケーションのメール設定

#### .envファイルの設定

本番サーバー（EC2）の`.env`ファイルを編集：

```bash
cd /home/ubuntu/realestate
nano .env
```

以下の内容を設定：

```env
# メール送信設定（Google Workspace）
MAIL_USERNAME=noreply@mscan.jp
MAIL_PASSWORD=abcdefghijklmnop  # 生成されたアプリパスワード（16文字、スペースなし）
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_FROM=noreply@mscan.jp
MAIL_FROM_NAME=都心マンション価格チェッカー
MAIL_STARTTLS=True
MAIL_SSL_TLS=False
```

> **重要**: Googleが表示するアプリパスワードは `xxxx xxxx xxxx xxxx` のようにスペース区切りですが、`.env`ファイルには**スペースを削除して** `xxxxxxxxxxxxxxxx` のように16文字連続で入力してください。

#### 設定の反映

**重要**: `.env`ファイルを変更した場合は、コンテナを完全に再起動する必要があります。

```bash
cd /home/ubuntu/realestate

# コンテナを完全に停止して再起動
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# 環境変数が正しく読み込まれたか確認
docker exec realestate-backend env | grep MAIL_
```

### 13.7 メール送信のテスト

#### テストスクリプトの作成と実行

**方法1: コンテナ内に直接作成して実行（推奨）**

```bash
# test_email.pyをコンテナ内の/tmpに作成
docker exec realestate-backend bash -c 'cat > /tmp/test_email.py << '\''EOF'\''
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import asyncio

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
)

async def send_test_email():
    message = MessageSchema(
        subject="【テスト】メール送信確認",
        recipients=["YOUR_EMAIL@example.com"],  # ← あなたのメールアドレスに変更
        body="Google Workspaceからのメール送信テストです。",
        subtype="html"
    )
    
    fm = FastMail(conf)
    await fm.send_message(message)
    print("✓ メール送信成功")

if __name__ == "__main__":
    asyncio.run(send_test_email())
EOF'

# テスト実行（YOUR_EMAIL@example.comを実際のアドレスに変更してから実行）
docker exec realestate-backend bash -c "cd /app && poetry run python /tmp/test_email.py"
```

**方法2: ホスト側で作成してコピー**

```bash
# ホスト側でファイルを作成
cd /home/ubuntu/realestate
cat > test_email.py << 'EOF'
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import asyncio

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
)

async def send_test_email():
    message = MessageSchema(
        subject="【テスト】メール送信確認",
        recipients=["YOUR_EMAIL@example.com"],  # ← あなたのメールアドレスに変更
        body="Google Workspaceからのメール送信テストです。",
        subtype="html"
    )
    
    fm = FastMail(conf)
    await fm.send_message(message)
    print("✓ メール送信成功")

if __name__ == "__main__":
    asyncio.run(send_test_email())
EOF

# コンテナにコピー
docker cp test_email.py realestate-backend:/tmp/

# テスト実行
docker exec realestate-backend bash -c "cd /app && poetry run python /tmp/test_email.py"
```

> **重要**: `YOUR_EMAIL@example.com` を実際にメールを受信したいアドレスに変更してから実行してください

**成功した場合**: `✓ メール送信成功` と表示され、指定したメールアドレスにメールが届きます。

**失敗した場合のトラブルシューティング**:
- アプリパスワードが正しいか確認
- 2段階認証が有効になっているか確認
- `.env`ファイルのメールアドレスが正しいか確認

### 13.8 料金について

#### Google Workspace Business Starter（推奨構成：コスト最適化版）
- **月額**: 950円/ユーザー（2024年価格改定後）
- **年間**: 11,400円/ユーザー
- **推奨ユーザー数**: 1ユーザー
  - admin@mscan.jp（管理者用 - 受信・管理に使用）
- **AWS SES**: 無料（EC2から送信の場合、月62,000通まで無料）
  - noreply@mscan.jp（システム送信用）
  - info@mscan.jp（お問い合わせフォーム用）
- **合計**: 月額950円、年間11,400円

#### 追加費用
- ドメイン登録（Route 53）: 年間約1,500円（既存）
- EC2インスタンス: 既存のコスト

**合計運用コスト**: 月額約950円（Google Workspace 1ユーザー + AWS SES無料）

**コスト削減**: 従来の3ユーザー構成（2,850円/月）と比較して、月額1,900円（年間22,800円）の削減

#### AWS SES移行のメリット
- ✅ 送信専用メール（noreply@, info@）のコスト削減
- ✅ 月62,000通まで無料（現在の送信量で十分）
- ✅ admin@mscan.jpは引き続き受信・返信が可能
- ✅ 実装済み（環境変数設定のみで動作）
- ⚠️ セットアップ手順は `docs/AWS_SES_SETUP.md` を参照

## 手順

1. **AWS SESの有効化**
```bash
# AWS CLIを使用する場合
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url https://mscan.jp \
  --use-case-description "Real estate search service email verification"
```

または、AWSコンソールから：
- Amazon SESダッシュボードを開く
- 「Get started」をクリック
- リージョンを選択（推奨: ap-northeast-1 東京）

2. **送信元メールアドレスの検証**
```bash
# メールアドレスの検証
aws sesv2 create-email-identity --email-identity noreply@mscan.jp --region ap-northeast-1
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
MAIL_FROM=noreply@mscan.jp  # 検証済みメールアドレス
MAIL_FROM_NAME=都心マンション価格チェッカー
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