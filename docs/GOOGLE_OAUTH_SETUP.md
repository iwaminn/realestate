# Google OAuth設定手順書

## 概要
このドキュメントでは、Google Cloud ConsoleでOAuth 2.0を設定し、アプリケーションでGoogleログインを有効にする手順を説明します。

## 前提条件
- Googleアカウントを持っていること
- Google Cloud Platformのプロジェクトを作成できること

## 設定手順

### 1. Google Cloud Consoleにアクセス
1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. Googleアカウントでログイン

### 2. プロジェクトの作成または選択
1. ヘッダーのプロジェクトセレクタをクリック
2. 「新しいプロジェクト」を選択（既存プロジェクトを使用する場合はスキップ）
3. プロジェクト名を入力（例：「realestate-app」）
4. 「作成」をクリック

### 3. OAuth同意画面の設定
1. 左メニューから「APIとサービス」→「OAuth同意画面」を選択
2. ユーザータイプを選択：
   - 開発環境：「外部」を選択
   - 社内利用：「内部」を選択（Google Workspace必須）
3. 「作成」をクリック
4. 必須項目を入力：
   - **アプリ名**: 都心マンションDB
   - **ユーザーサポートメール**: あなたのメールアドレス
   - **デベロッパーの連絡先情報**: あなたのメールアドレス
5. 「保存して続行」をクリック
6. スコープの設定：
   - 「スコープを追加または削除」をクリック
   - 以下のスコープを選択：
     - `../auth/userinfo.email`
     - `../auth/userinfo.profile`
     - `openid`
   - 「更新」をクリック
7. 「保存して続行」をクリック
8. テストユーザー（開発環境の場合）：
   - 「ADD USERS」をクリック
   - テストで使用するメールアドレスを追加
   - 「保存して続行」をクリック

### 4. OAuth 2.0クライアントIDの作成
1. 左メニューから「APIとサービス」→「認証情報」を選択
2. 「認証情報を作成」→「OAuthクライアントID」を選択
3. アプリケーションの種類：「ウェブアプリケーション」を選択
4. 名前を入力（例：「RealeState Web Client」）
5. 承認済みのJavaScript生成元：
   - 開発環境：
     - `http://localhost:3000`
     - `http://localhost:3001`
     - `http://localhost:8000`
   - 本番環境：
     - `https://yourdomain.com`
6. 承認済みのリダイレクトURI：
   - 開発環境：
     - `http://localhost:8000/api/oauth/google/callback`
   - 本番環境：
     - `https://yourdomain.com/api/oauth/google/callback`
7. 「作成」をクリック
8. 表示されるクライアントIDとクライアントシークレットを保存

### 5. 環境変数の設定

#### docker-compose.ymlに追加：
```yaml
environment:
  - GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
  - GOOGLE_CLIENT_SECRET=your-client-secret
  - GOOGLE_REDIRECT_URI=http://localhost:8000/api/oauth/google/callback
```

#### または.envファイルに追加：
```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/oauth/google/callback
```

### 6. Dockerコンテナの再起動
```bash
docker-compose restart backend
```

## 本番環境への移行

### 1. OAuth同意画面の公開
1. 「OAuth同意画面」で「アプリを公開」をクリック
2. Googleの審査を通過する必要がある場合があります

### 2. リダイレクトURIの更新
1. 「認証情報」でOAuthクライアントを編集
2. 本番環境のURLを追加：
   - JavaScript生成元：`https://yourdomain.com`
   - リダイレクトURI：`https://yourdomain.com/api/oauth/google/callback`

### 3. 環境変数の更新
```bash
GOOGLE_REDIRECT_URI=https://yourdomain.com/api/oauth/google/callback
FRONTEND_URL=https://yourdomain.com
```

## トラブルシューティング

### よくあるエラー

#### 1. "redirect_uri_mismatch"
- **原因**: リダイレクトURIが登録されていない
- **解決**: Google Cloud ConsoleでリダイレクトURIを正確に登録

#### 2. "invalid_client"
- **原因**: クライアントIDまたはシークレットが間違っている
- **解決**: 環境変数を確認し、正しい値を設定

#### 3. "access_blocked"
- **原因**: OAuth同意画面が設定されていない
- **解決**: OAuth同意画面を完全に設定

#### 4. テストユーザー以外がログインできない
- **原因**: アプリが公開されていない（開発モード）
- **解決**: 
  - テストユーザーリストにメールアドレスを追加
  - または、アプリを公開する

## セキュリティのベストプラクティス

1. **クライアントシークレットの管理**
   - 絶対にGitにコミットしない
   - 環境変数または秘密管理サービスを使用

2. **リダイレクトURIの制限**
   - 必要最小限のURIのみ登録
   - HTTPSを使用（本番環境）

3. **スコープの最小化**
   - 必要最小限のスコープのみ要求
   - ユーザーのプライバシーを尊重

4. **定期的な監査**
   - 不要になったクライアントIDは削除
   - アクセスログを定期的に確認

## 動作確認

1. アプリケーションにアクセス
2. ログインモーダルを開く
3. 「Googleでログイン」ボタンをクリック
4. Googleアカウントを選択
5. 権限を承認
6. アプリケーションに自動的にリダイレクト・ログイン完了

## 参考リンク
- [Google OAuth 2.0 公式ドキュメント](https://developers.google.com/identity/protocols/oauth2)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)