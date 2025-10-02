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

### 8.7 Google OAuthの設定更新（HTTPS使用時）

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
MAIL_FROM_NAME=都心マンション価格チェッカー
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
MAIL_FROM=noreply@mscan.jp  # 検証済みメールアドレス
MAIL_FROM_NAME=都心マンション価格チェッカー
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