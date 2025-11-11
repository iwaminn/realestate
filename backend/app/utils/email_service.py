"""
メール送信サービス
"""

import os
from typing import List, Optional
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from ..utils.logger import api_logger, error_logger


# メール設定
def get_mail_config(from_email: str = None) -> ConnectionConfig:
    """
    メール設定を取得
    
    送信元アドレスに応じて適切なSMTP設定を返す：
    - noreply@mscan.jp, info@mscan.jp → AWS SES（送信専用）
    - その他（admin@mscan.jp等） → Google Workspace
    
    Args:
        from_email: 送信元メールアドレス
    """
    # AWS SESを使用するアドレス
    ses_addresses = ['noreply@mscan.jp', 'info@mscan.jp']
    
    # AWS SESの設定が存在し、対象のアドレスの場合
    if from_email in ses_addresses and os.getenv('SES_SMTP_USERNAME'):
        return ConnectionConfig(
            MAIL_USERNAME=os.getenv('SES_SMTP_USERNAME', ''),
            MAIL_PASSWORD=os.getenv('SES_SMTP_PASSWORD', ''),
            MAIL_FROM=from_email,
            MAIL_FROM_NAME=os.getenv('MAIL_FROM_NAME', '都心マンション価格チェッカー'),
            MAIL_PORT=int(os.getenv('SES_SMTP_PORT', '587')),
            MAIL_SERVER=os.getenv('SES_SMTP_HOST', 'email-smtp.ap-northeast-1.amazonaws.com'),
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )
    
    # デフォルト（Google Workspace）の設定
    return ConnectionConfig(
        MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
        MAIL_FROM=os.getenv('MAIL_FROM', 'noreply@realestate.example.com'),
        MAIL_FROM_NAME=os.getenv('MAIL_FROM_NAME', '都心マンション価格チェッカー'),
        MAIL_PORT=int(os.getenv('MAIL_PORT', '587')),
        MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
        MAIL_STARTTLS=os.getenv('MAIL_STARTTLS', 'True').lower() == 'true',
        MAIL_SSL_TLS=os.getenv('MAIL_SSL_TLS', 'False').lower() == 'true',
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )


class EmailService:
    def __init__(self):
        try:
            # テンプレートディレクトリの設定
            template_dir = Path(__file__).parent.parent / 'templates' / 'email'
            template_dir.mkdir(parents=True, exist_ok=True)
            self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))
            
            # メール送信が有効かチェック
            # Google WorkspaceまたはAWS SESのいずれかが設定されていればOK
            google_enabled = bool(os.getenv('MAIL_USERNAME') and os.getenv('MAIL_PASSWORD'))
            ses_enabled = bool(os.getenv('SES_SMTP_USERNAME') and os.getenv('SES_SMTP_PASSWORD'))
            self.enabled = google_enabled or ses_enabled
            
            if not self.enabled:
                api_logger.warning("メール送信設定が未設定です。開発モードで動作します。")
            else:
                if ses_enabled:
                    api_logger.info("AWS SES設定が検出されました。noreply@/info@はSESを使用します。")
                if google_enabled:
                    api_logger.info("Google Workspace設定が検出されました。")
                
        except Exception as e:
            error_logger.error(f"EmailService初期化エラー: {e}")
            self.enabled = False

    async def send_verification_email(self, email: str, user_name: str, verification_token: str) -> bool:
        """メールアドレス確認メールを送信"""
        # アプリ名を取得
        app_name = os.getenv('VITE_APP_NAME', '都心マンション価格チェッカー')
        
        # 確認URL生成
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3001')
        verification_url = f"{base_url}/verify-email?token={verification_token}"
        
        if not self.enabled:
            # 開発モードではログファイルに詳細を出力
            import json
            from datetime import datetime
            
            # メール内容をログファイルに記録
            log_dir = Path('/app/logs')
            log_dir.mkdir(parents=True, exist_ok=True)
            
            email_log_file = log_dir / 'email_dev.log'
            
            email_content = {
                'timestamp': datetime.utcnow().isoformat(),
                'type': 'verification',
                'to': email,
                'user_name': user_name,
                'verification_url': verification_url,
                'token': verification_token,
                'message': f'開発環境: メール確認URLは {verification_url} です'
            }
            
            # ファイルに追記
            with open(email_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(email_content, ensure_ascii=False) + '\n')
            
            # 通常のログにも出力
            api_logger.info(f"[開発モード] メール確認URL: {verification_url}")
            api_logger.info(f"[開発モード] 宛先: {email} ({user_name})")
            api_logger.info(f"[開発モード] トークン: {verification_token}")
            api_logger.info(f"[開発モード] 詳細は /app/logs/email_dev.log を確認してください")
            
            # コンソールにも表示（見やすくするため）
            print("\n" + "="*60)
            print("📧 開発環境メール確認情報")
            print("="*60)
            print(f"宛先: {email}")
            print(f"確認URL: {verification_url}")
            print(f"トークン: {verification_token}")
            print("="*60 + "\n")
            
            return True
            
        try:
            # 確認URL生成
            base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
            verification_url = f"{base_url}/verify-email?token={verification_token}"
            
            # HTMLテンプレート
            html_content = self._create_verification_html(user_name, verification_url, app_name)
            
            # テキスト版
            text_content = f"""
こんにちは{user_name or ''}様、

{app_name}にご登録いただき、ありがとうございます。

以下のリンクをクリックしてメールアドレスの確認を完了してください：
{verification_url}

このリンクは24時間有効です。

※このメールに覚えがない場合は、このメールを無視してください。

{app_name}運営チーム
            """.strip()
            
            # 送信元アドレスを指定
            from_email = "noreply@mscan.jp"
            
            # 送信元アドレスに応じた設定を取得してFastMailインスタンスを作成
            config = get_mail_config(from_email)
            fm = FastMail(config)
            
            message = MessageSchema(
                subject=f"メールアドレスの確認 - {app_name}",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            await fm.send_message(message)
            api_logger.info(f"確認メールを送信しました: {email}")
            return True
            
        except Exception as e:
            error_logger.error(f"確認メール送信エラー: {e}")
            return False

    async def send_password_set_verification_email(self, email: str, user_name: str, verification_token: str) -> bool:
        """パスワード設定確認メールを送信（Googleアカウントユーザー用）"""
        # アプリ名を取得
        app_name = os.getenv('VITE_APP_NAME', '都心マンション価格チェッカー')
        
        # 確認URL生成
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3001')
        verification_url = f"{base_url}/verify-password-set?token={verification_token}"
        
        if not self.enabled:
            # 開発モードではログファイルに詳細を出力
            import json
            from datetime import datetime
            
            # メール内容をログファイルに記録
            log_dir = Path('/app/logs')
            log_dir.mkdir(parents=True, exist_ok=True)
            
            email_log_file = log_dir / 'email_dev.log'
            
            email_content = {
                'timestamp': datetime.utcnow().isoformat(),
                'type': 'password_set_verification',
                'to': email,
                'user_name': user_name,
                'verification_url': verification_url,
                'token': verification_token,
                'message': f'開発環境: パスワード設定確認URLは {verification_url} です'
            }
            
            # ファイルに追記
            with open(email_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(email_content, ensure_ascii=False) + '\n')
            
            # 通常のログにも出力
            api_logger.info(f"[開発モード] パスワード設定確認URL: {verification_url}")
            api_logger.info(f"[開発モード] 宛先: {email} ({user_name})")
            api_logger.info(f"[開発モード] トークン: {verification_token}")
            api_logger.info(f"[開発モード] 詳細は /app/logs/email_dev.log を確認してください")
            
            # コンソールにも表示（見やすくするため）
            print("\n" + "="*60)
            print("📧 開発環境パスワード設定確認情報")
            print("="*60)
            print(f"宛先: {email}")
            print(f"確認URL: {verification_url}")
            print(f"トークン: {verification_token}")
            print("="*60 + "\n")
            
            return True
            
        try:
            # HTML テンプレート
            html_content = self._create_password_set_verification_html(user_name, verification_url, app_name)
            
            # テキスト版
            text_content = f"""
こんにちは{user_name or ''}様、

{app_name}でパスワード設定のリクエストがありました。

以下のリンクをクリックしてパスワード設定を完了してください：
{verification_url}

このリンクは24時間有効です。

※このリクエストに覚えがない場合は、このメールを無視してください。

{app_name}運営チーム
            """.strip()
            
            # 送信元アドレスを指定
            from_email = "noreply@mscan.jp"
            
            # 送信元アドレスに応じた設定を取得してFastMailインスタンスを作成
            config = get_mail_config(from_email)
            fm = FastMail(config)
            
            message = MessageSchema(
                subject=f"パスワード設定の確認 - {app_name}",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            await fm.send_message(message)
            api_logger.info(f"パスワード設定確認メールを送信しました: {email}")
            return True
            
        except Exception as e:
            error_logger.error(f"パスワード設定確認メール送信エラー: {e}")
            return False

    async def send_password_reset_email(self, email: str, user_name: str, reset_token: str) -> bool:
        """パスワードリセットメールを送信"""
        # アプリ名を取得
        app_name = os.getenv('VITE_APP_NAME', '都心マンション価格チェッカー')

        # リセットURL生成
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3001')
        reset_url = f"{base_url}/reset-password?token={reset_token}"

        if not self.enabled:
            # 開発モードではログに出力
            api_logger.info(f"[開発モード] パスワードリセットURL: {reset_url}")
            api_logger.info(f"[開発モード] 宛先: {email} ({user_name})")
            return True

        # 本番環境: aiosmtplibで直接メール送信
        try:
            # HTMLテンプレート
            html_content = self._create_password_reset_html(user_name, reset_url, app_name)

            # 送信元アドレスを指定
            from_email = "noreply@mscan.jp"

            # メール送信
            success = await self._send_html_email(
                from_email=from_email,
                to_email=email,
                subject=f"パスワードリセットのご案内 - {app_name}",
                html_content=html_content
            )

            if success:
                api_logger.info(f"パスワードリセットメールを送信しました: {email}")
            return success

        except Exception as e:
            error_logger.error(f"パスワードリセットメール送信エラー: {e}")
            return False

    async def send_email_change_verification(self, new_email: str, user_name: str, verification_token: str) -> bool:
        """メールアドレス変更確認メールを送信"""
        # アプリ名を取得
        app_name = os.getenv('VITE_APP_NAME', '都心マンション価格チェッカー')
        
        # 確認URL生成
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3001')
        verify_url = f"{base_url}/verify-email-change?token={verification_token}"
        
        if not self.enabled:
            # 開発モードではログファイルに詳細を出力
            import json
            from datetime import datetime
            
            # メール内容をログファイルに記録
            log_dir = Path('/app/logs')
            log_dir.mkdir(parents=True, exist_ok=True)
            
            email_log_file = log_dir / 'email_dev.log'
            
            email_content = {
                'timestamp': datetime.utcnow().isoformat(),
                'type': 'email_change_verification',
                'to': new_email,
                'user_name': user_name,
                'verify_url': verify_url,
                'token': verification_token,
                'message': f'開発環境: メールアドレス変更確認URLは {verify_url} です'
            }
            
            # ファイルに追記
            with open(email_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(email_content, ensure_ascii=False) + '\n')
            
            # 通常のログにも出力
            api_logger.info(f"[開発モード] メールアドレス変更確認URL: {verify_url}")
            api_logger.info(f"[開発モード] 宛先: {new_email} ({user_name})")
            api_logger.info(f"[開発モード] トークン: {verification_token}")
            api_logger.info(f"[開発モード] 詳細は /app/logs/email_dev.log を確認してください")
            
            # コンソールにも表示（見やすくするため）
            print("\n" + "="*60)
            print("📧 開発環境メールアドレス変更確認情報")
            print("="*60)
            print(f"宛先: {new_email}")
            print(f"確認URL: {verify_url}")
            print(f"トークン: {verification_token}")
            print("="*60 + "\n")
            
            return True
        
        # 本番環境でのメール送信
        try:
            # HTMLテンプレート（簡易版）
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 28px;">メールアドレス変更確認</h1>
    </div>
    <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
        <p>こんにちは{user_name or ''}様、</p>
        <p>{app_name}でメールアドレス変更のリクエストがありました。</p>
        <p>以下のボタンをクリックして、新しいメールアドレスの確認を完了してください：</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">メールアドレスを確認</a>
        </div>
        <p style="color: #666; font-size: 14px;">ボタンが機能しない場合は、以下のURLをコピーしてブラウザに貼り付けてください：</p>
        <p style="word-break: break-all; color: #667eea; font-size: 14px;">{verify_url}</p>
        <p style="color: #666; font-size: 14px; margin-top: 30px;">このリンクは24時間有効です。</p>
        <p style="color: #999; font-size: 12px; margin-top: 30px;">※このリクエストに覚えがない場合は、このメールを無視してください。</p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        <p style="color: #999; font-size: 12px; text-align: center;">{app_name}運営チーム</p>
    </div>
</body>
</html>
            """
            
            # 送信元アドレスを指定
            from_email = "noreply@mscan.jp"
            
            # 送信元アドレスに応じた設定を取得してFastMailインスタンスを作成
            config = get_mail_config(from_email)
            fm = FastMail(config)
            
            message = MessageSchema(
                subject=f"メールアドレス変更確認 - {app_name}",
                recipients=[new_email],
                body=html_content,
                subtype=MessageType.html
            )
            
            await fm.send_message(message)
            api_logger.info(f"メールアドレス変更確認メールを送信しました: {new_email}")
            return True
            
        except Exception as e:
            error_logger.error(f"メールアドレス変更確認メール送信エラー: {e}")
            return False

    def _create_password_set_verification_html(self, user_name: str, verification_url: str, app_name: str = '都心マンション価格チェッカー') -> str:
        """パスワード設定確認メールのHTMLを生成"""
        return f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>パスワード設定の確認</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1976d2;
        }}
        .header h1 {{
            color: #1976d2;
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            color: #333;
            font-size: 16px;
        }}
        .content p {{
            margin: 16px 0;
        }}
        .button {{
            display: inline-block;
            padding: 15px 30px;
            background-color: #1976d2 !important;
            color: white !important;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .button:hover {{
            background-color: #1565c0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .info {{
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            color: #0c5460;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{app_name}</h1>
        </div>
        
        <div class="content">
            <p>こんにちは{user_name or ''}様、</p>
            
            <p>{app_name}でパスワード設定のリクエストがありました。</p>
            
            <div class="info">
                <strong>重要:</strong> このパスワードを設定すると、Googleアカウントでのログインに加えて、メールアドレスとパスワードでもログインできるようになります。
            </div>
            
            <p>以下のボタンをクリックしてパスワード設定を完了してください：</p>
            
            <p style="text-align: center;">
                <a href="{verification_url}" class="button" style="display: inline-block; padding: 15px 30px; background-color: #1976d2; color: #ffffff !important; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold;">パスワードを設定する</a>
            </p>
            
            <div class="warning">
                <strong>注意:</strong> このリンクは24時間有効です。期限が切れた場合は、再度パスワード設定をお試しください。
            </div>
            
            <p>ボタンが機能しない場合は、以下のURLをブラウザにコピー&ペーストしてください：</p>
            <p style="word-break: break-all; color: #666; font-size: 14px;">{verification_url}</p>
        </div>
        
        <div class="footer">
            <p><strong>※このリクエストに覚えがない場合は、このメールを無視してください。</strong></p>
            <p>{app_name}運営チーム</p>
        </div>
    </div>
</body>
</html>
        """

    def _create_password_reset_html(self, user_name: str, reset_url: str, app_name: str = '都心マンション価格チェッカー') -> str:
        """パスワードリセットメールのHTMLを生成"""
        return f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>パスワードリセット</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1976d2;
        }}
        .header h1 {{
            color: #1976d2;
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            color: #333;
            font-size: 16px;
        }}
        .content p {{
            margin: 16px 0;
        }}
        .button {{
            display: inline-block;
            padding: 15px 30px;
            background-color: #1976d2 !important;
            color: white !important;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .button:hover {{
            background-color: #1565c0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{app_name}</h1>
        </div>
        
        <div class="content">
            <p>こんにちは{user_name or ''}様、</p>
            
            <p>{app_name}でパスワードリセットのリクエストがありました。</p>
            
            <p>以下のボタンをクリックして新しいパスワードを設定してください：</p>
            
            <p style="text-align: center;">
                <a href="{reset_url}" class="button" style="display: inline-block; padding: 15px 30px; background-color: #1976d2; color: #ffffff !important; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold;">パスワードをリセットする</a>
            </p>
            
            <div class="warning">
                <strong>注意:</strong> このリンクは24時間有効です。期限が切れた場合は、再度パスワードリセットをお試しください。
            </div>
            
            <p>ボタンが機能しない場合は、以下のURLをブラウザにコピー&ペーストしてください：</p>
            <p style="word-break: break-all; color: #666; font-size: 14px;">{reset_url}</p>
        </div>
        
        <div class="footer">
            <p><strong>※このリクエストに覚えがない場合は、このメールを無視してください。</strong></p>
            <p>誰かがあなたのメールアドレスでパスワードリセットを試みている可能性があります。</p>
            <p>{app_name}運営チーム</p>
        </div>
    </div>
</body>
</html>
        """

    def _create_verification_html(self, user_name: str, verification_url: str, app_name: str = '都心マンション価格チェッカー') -> str:
        """確認メールのHTMLを生成"""
        return f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>メールアドレスの確認</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #1976d2;
        }}
        .header h1 {{
            color: #1976d2;
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            color: #333;
            font-size: 16px;
        }}
        .content p {{
            margin: 16px 0;
        }}
        .button {{
            display: inline-block;
            padding: 15px 30px;
            background-color: #1976d2 !important;
            color: white !important;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
            font-weight: bold;
        }}
        .button:hover {{
            background-color: #1565c0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{app_name}</h1>
        </div>
        
        <div class="content">
            <p>こんにちは{user_name or ''}様、</p>
            
            <p>{app_name}にご登録いただき、ありがとうございます。</p>
            
            <p>以下のボタンをクリックしてメールアドレスの確認を完了してください：</p>
            
            <p style="text-align: center;">
                <a href="{verification_url}" class="button" style="display: inline-block; padding: 15px 30px; background-color: #1976d2; color: #ffffff !important; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold;">メールアドレスを確認する</a>
            </p>
            
            <div class="warning">
                <strong>重要:</strong> このリンクは24時間有効です。期限が切れた場合は、再度ご登録をお願いいたします。
            </div>
            
            <p>ボタンが機能しない場合は、以下のURLをブラウザにコピー&ペーストしてください：</p>
            <p style="word-break: break-all; color: #666; font-size: 14px;">{verification_url}</p>
        </div>
        
        <div class="footer">
            <p><strong>※このメールに覚えがない場合は、このメールを無視してください。</strong></p>
            <p>{app_name}運営チーム</p>
        </div>
    </div>
</body>
</html>
        """

    async def _send_html_email(self, from_email: str, to_email: str, subject: str, html_content: str) -> bool:
        """fastapi-mailを使用してHTMLメールを送信"""
        try:
            # 送信元アドレスに応じた設定を取得
            config = get_mail_config(from_email)
            
            # FastMailインスタンスを作成
            fm = FastMail(config)
            
            # メッセージを作成
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html
            )
            
            # メール送信
            await fm.send_message(message)
            
            return True
            
        except Exception as e:
            error_logger.error(f"メール送信エラー ({from_email} -> {to_email}): {e}")
            return False


# シングルトンインスタンス
email_service = EmailService()