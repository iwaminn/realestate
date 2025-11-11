# AWS SES セットアップガイド

## 概要

Google Workspaceのコストを削減するため、送信専用メールアドレス（noreply@mscan.jp, info@mscan.jp）をAWS SESに移行します。

## コスト比較

### 現在
- **Google Workspace**: 3ユーザー × 950円 = **月額2,850円**
  - admin@mscan.jp
  - noreply@mscan.jp
  - info@mscan.jp

### 移行後
- **Google Workspace**: 1ユーザー × 950円 = **月額950円**
  - admin@mscan.jp（受信・管理に使用）
- **AWS SES**: EC2から送信の場合、月62,000通まで**無料**
  - noreply@mscan.jp（送信専用）
  - info@mscan.jp（送信専用）

### 削減額
- **月額1,900円削減 →年間22,800円の削減**

## AWS SESセットアップ手順

### 1. AWS SESでドメインを検証

1. AWS Management Console → Amazon SES
2. リージョンを選択（東京: ap-northeast-1推奨）
3. 左メニュー「Verified identities」→「Create identity」
4. 以下を入力：
   - Identity type: **Domain**
   - Domain: **mscan.jp**
   - Advanced DKIM settings: デフォルト（Easy DKIM推奨）
5. 「Create identity」をクリック

### 2. DNS設定を追加

SESがドメイン検証用のDNSレコードを表示します。Route 53を使用している場合は自動で設定可能です。

以下のレコードをDNSに追加：
- **DKIMレコード（3つ）**: CNAME
- **ドメイン検証用**: TXT

### 3. 送信元メールアドレスの検証（追加で）

個別のメールアドレスも検証します：

1. 「Verified identities」→「Create identity」
2. Identity type: **Email address**
3. 以下を順番に検証：
   - **noreply@mscan.jp**
   - **info@mscan.jp**
4. 各アドレスに確認メールが送信されるので、リンクをクリック

### 4. サンドボックスモードの解除（本番運用時）

初期状態はサンドボックスモード（検証済みアドレスにのみ送信可能）です。
本番運用時は以下の手順で解除申請：

1. SESコンソール左メニュー →「Account dashboard」
2. 「Request production access」をクリック
3. フォームに以下を入力：
   - **Mail type**: Transactional
   - **Use case description**:
     ```
     We operate a real estate search platform (mscan.jp) and need to send:
     - User registration verification emails
     - Password reset emails
     - Contact form notifications

     Expected volume: ~100 emails/day
     We have proper unsubscribe mechanisms and comply with email best practices.
     ```
   - **Expected sending rate**: 100 emails per day
4. 申請を送信（通常1営業日程度で承認）

### 5. SMTP認証情報の作成

1. SESコンソール左メニュー →「SMTP settings」
2. 「Create SMTP credentials」をクリック
3. IAMユーザー名を入力（例: `ses-smtp-user-mscan`）
4. 「Create user」をクリック
5. **SMTP Username**と**SMTP Password**が表示されるので、必ず保存
   - ⚠️ この画面を閉じると再表示できません

### 6. 環境変数の設定

`.env`ファイルまたは`docker-compose.prod.yml`に以下を追加：

``bash
# AWS SES設定
SES_SMTP_HOST=email-smtp.ap-northeast-1.amazonaws.com
SES_SMTP_PORT=587
SES_SMTP_USERNAME=<ステップ5で取得したSMTPユーザー名>
SES_SMTP_PASSWORD=<ステップ5で取得したSMTPパスワード>

# 既存のGoogle Workspace設定はadmin@mscan.jp用に残す
MAIL_USERNAME=admin@mscan.jp
MAIL_PASSWORD=<Google Workspaceのパスワード>
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587

# お問い合わせの受信先（admin@mscan.jpに変更）
CONTACT_EMAIL=admin@mscan.jp
```

### 7. Dockerコンテナを再起動

```bash
# 開発環境
docker compose restart backend

# 本番環境
docker compose -f docker-compose.prod.yml restart backend
```

## メール送信の仕組み

コードが自動的に送信元アドレスに応じてSMTP設定を切り替えます：

| 送信元アドレス | SMTP設定 | 用途 |
|---|---|---|
| noreply@mscan.jp | AWS SES | ユーザー登録確認、パスワードリセット |
| info@mscan.jp | AWS SES | お問い合わせフォーム |
| admin@mscan.jp | Google Workspace | （将来の拡張用） |

## テスト手順

### 1. 開発環境でテスト

```bash
# メール送信テスト（開発モードでログ出力）
docker compose logs backend | grep "メール"
```

### 2. AWS SES設定後のテスト

```bash
# ユーザー登録でメール送信をテスト
# フロントエンドから新規ユーザー登録を実行

# ログで送信成功を確認
docker compose logs backend | grep "確認メールを送信"
```

### 3. 本番環境でテスト

サンドボックスモード中は、検証済みメールアドレスにのみ送信できます。
自分のメールアドレスで新規登録してテストしてください。

## トラブルシューティング

### Q. メールが送信されない

A. 以下を確認：
1. 環境変数が正しく設定されているか
2. Dockerコンテナが再起動されているか
3. SESのSMTP認証情報が正しいか
4. サンドボックスモードの場合、受信者が検証済みか

### Q. "Email address not verified"エラー

A. サンドボックスモード中は検証済みアドレスにのみ送信可能です。
本番運用には「Request production access」で解除申請が必要です。

### Q. SMTP接続エラー

A. 以下を確認：
1. EC2のセキュリティグループでポート587が許可されているか
2. SES_SMTP_HOSTのリージョンが正しいか（ap-northeast-1等）
3. SMTP認証情報が正しいか

## Google Workspaceアカウントの解約手順

AWS SESが正常に動作することを確認してから：

1. Google Workspace管理コンソール
2. ユーザー管理
3. noreply@mscan.jp を削除
4. info@mscan.jp を削除
5. admin@mscan.jp のみ残す

⚠️ **注意**: 必ずAWS SESが正常に動作することを確認してから解約してください。

## 料金

### AWS SES（EC2から送信）
- 最初の62,000通/月: **無料**
- その後: $0.10/1,000通

### 現在の送信量
- 月間送信予想: 約100通（登録確認、パスワードリセット、お問い合わせ）
- **完全に無料枠内で収まります**

## まとめ

- ✅ 月額1,900円（年間22,800円）のコスト削減
- ✅ 実装済み（環境変数設定のみで動作）
- ✅ AWS無料枠で運用可能
- ✅ admin@mscan.jpは引き続き受信・返信が可能
