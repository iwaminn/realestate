# ログアウト機能修正の本番環境デプロイ手順

## 問題
本番環境でログアウトボタンが機能しない

## 原因
1. 初回修正：Cookie削除時に必要なパラメータ（httponly、secure、samesite、path）が不足
2. 追加修正：`delete_cookie()`の代わりに`set_cookie()`で`max_age=0`を使用する方法に変更
   - 一部のブラウザや環境で`delete_cookie()`が正しく動作しないケースがある
   - `set_cookie(value="", max_age=0)`の方がより確実

## 修正内容
`backend/app/api/auth.py`のログアウトエンドポイントを修正：
- `delete_cookie()`から`set_cookie(value="", max_age=0)`に変更
- すべてのパラメータを明示的に指定

## 本番環境デプロイ手順

### ステップ0: 環境変数の設定（重要）

本番環境の`.env`ファイルに`COOKIE_DOMAIN`を追加してください：

```bash
# 本番サーバーにSSH接続
cd /home/ubuntu/realestate

# .envファイルを編集
nano .env
```

以下を追加：
```bash
# Cookie設定（本番環境用）
COOKIE_DOMAIN=.your-domain.com  # 例: .mansion-checker.com
```

**重要**：
- ドメイン名の前に`.`（ドット）を付けてください（例：`.mansion-checker.com`）
- これにより、サブドメインでもCookieが共有されます
- ドメインが`https://mansion-checker.com`の場合は`.mansion-checker.com`と設定

### ステップ1: 最新コードを取得

```bash
# 本番サーバーにSSH接続
cd /home/ubuntu/realestate

# 最新コードを取得
git pull origin master

# 最新のコミットを確認（d750976が含まれているか）
git log --oneline -3
```

期待される出力：
```
d750976 fix: ログアウト機能が正常に動作しない問題を修正
c6af8f7 feat: ブックマーク一覧の並び順を物件一覧と統一し、坪単価ソートを追加
ce9cfd3 docs: 本番環境デプロイ手順書とデータベースマイグレーションスクリプトを追加
```

### ステップ2: バックエンドを再ビルド＆再起動

```bash
# バックエンドのみ再ビルド
docker compose -f docker-compose.prod.yml build backend

# バックエンドを再起動
docker compose -f docker-compose.prod.yml up -d --force-recreate backend

# 起動確認
docker compose -f docker-compose.prod.yml ps backend
```

期待される出力：
```
NAME                    STATUS
realestate-backend      Up
```

### ステップ3: バックエンドログを確認

```bash
# エラーがないか確認
docker compose -f docker-compose.prod.yml logs backend --tail 50
```

### ステップ4: ブラウザキャッシュをクリア

ユーザー側で以下の操作が必要：

1. **ハードリロード**（最も簡単）
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`

2. **完全なキャッシュクリア**（推奨）
   - Chrome: 設定 → プライバシーとセキュリティ → 閲覧履歴データの削除
   - 「キャッシュされた画像とファイル」を選択
   - 時間範囲: 「全期間」
   - 削除

3. **開発者ツールで確認**
   - F12で開発者ツールを開く
   - Network タブを開く
   - 「Disable cache」にチェック

### ステップ5: 動作確認

1. ブラウザで本番サイトにアクセス
2. ログイン
3. ユーザーメニューから「ログアウト」をクリック
4. ログアウトが成功することを確認
5. F12 → Application → Cookies で、`access_token`と`refresh_token`が削除されていることを確認

## トラブルシューティング

### ログアウトしてもログイン状態が継続する場合

**原因1: ブラウザキャッシュ**
```bash
# ハードリロード: Ctrl + Shift + R
# または完全なキャッシュクリア
```

**原因2: Cookieが削除されていない**
```bash
# 開発者ツール（F12）で確認
# Application → Cookies → https://your-domain.com
# access_token と refresh_token が残っている場合は手動で削除
```

**原因3: バックエンドが再起動されていない**
```bash
# バックエンドコンテナの起動時刻を確認
docker compose -f docker-compose.prod.yml ps backend

# 最新のログを確認
docker compose -f docker-compose.prod.yml logs backend --tail 100 | grep "logout"
```

**原因4: 古いイメージが使われている**
```bash
# イメージを完全に再ビルド
docker compose -f docker-compose.prod.yml build --no-cache backend
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

### ログアウトAPI自体が動作しない場合

```bash
# curlでテスト（本番サーバー上で実行）
curl -X POST https://your-domain.com/api/auth/logout \
  -H "Cookie: access_token=your-token" \
  -v

# 期待される出力:
# < HTTP/2 200
# < set-cookie: access_token=; Max-Age=0; ...
# < set-cookie: refresh_token=; Max-Age=0; ...
# {"message":"ログアウトしました"}
```

### バックエンドログでエラーを確認

```bash
# ログアウト時のエラーログを確認
docker compose -f docker-compose.prod.yml logs backend --tail 200 | grep -i "error\|logout"
```

## 注意事項

1. **バックエンドの再ビルドは必須**
   - 本番環境ではコードがDockerイメージにビルドされているため、`git pull`だけでは反映されません
   - 必ず`docker compose build`を実行してください

2. **ブラウザキャッシュのクリアが必要**
   - 古いJavaScriptがキャッシュされている場合があります
   - ユーザーにハードリロードを案内してください

3. **Cookie設定の確認**
   - 本番環境の`.env`ファイルで以下が正しく設定されているか確認：
     ```
     COOKIE_SECURE=true
     COOKIE_SAMESITE=lax
     ```

## 検証

正常に動作する場合、以下のような挙動になります：

1. ログアウトボタンをクリック
2. `/api/auth/logout` APIが呼ばれる
3. レスポンスヘッダーで`Set-Cookie`が2つ（access_token、refresh_token）送られる
4. 両方のCookieの`Max-Age=0`が設定される（即座に削除）
5. ブラウザがCookieを削除
6. ページがリロードされ、未ログイン状態になる

開発者ツールのNetworkタブで確認できます：
```
POST /api/auth/logout
Response Headers:
  set-cookie: access_token=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0
  set-cookie: refresh_token=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0
```
