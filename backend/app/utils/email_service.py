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
def get_mail_config() -> ConnectionConfig:
    """メール設定を取得"""
    return ConnectionConfig(
        MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
        MAIL_FROM=os.getenv('MAIL_FROM', 'noreply@realestate.example.com'),
        MAIL_FROM_NAME=os.getenv('MAIL_FROM_NAME', '都心マンションDB'),
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
            self.config = get_mail_config()
            self.fast_mail = FastMail(self.config)
            
            # テンプレートディレクトリの設定
            template_dir = Path(__file__).parent.parent / 'templates' / 'email'
            template_dir.mkdir(parents=True, exist_ok=True)
            self.jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))
            
            # メール送信が有効かチェック
            self.enabled = bool(os.getenv('MAIL_USERNAME') and os.getenv('MAIL_PASSWORD'))
            
            if not self.enabled:
                api_logger.warning("メール送信設定が未設定です。開発モードで動作します。")
                
        except Exception as e:
            error_logger.error(f"EmailService初期化エラー: {e}")
            self.enabled = False

    async def send_verification_email(self, email: str, user_name: str, verification_token: str) -> bool:
        """メールアドレス確認メールを送信"""
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
            html_content = self._create_verification_html(user_name, verification_url)
            
            # テキスト版
            text_content = f"""
こんにちは{user_name or ''}様、

都心マンションDBにご登録いただき、ありがとうございます。

以下のリンクをクリックしてメールアドレスの確認を完了してください：
{verification_url}

このリンクは24時間有効です。

※このメールに覚えがない場合は、このメールを無視してください。

都心マンションDB運営チーム
            """.strip()
            
            message = MessageSchema(
                subject="メールアドレスの確認 - 都心マンションDB",
                recipients=[email],
                body=text_content,
                html=html_content,
                subtype=MessageType.html
            )
            
            await self.fast_mail.send_message(message)
            api_logger.info(f"確認メールを送信しました: {email}")
            return True
            
        except Exception as e:
            error_logger.error(f"確認メール送信エラー: {e}")
            return False

    def _create_verification_html(self, user_name: str, verification_url: str) -> str:
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
        .button {{
            display: inline-block;
            padding: 15px 30px;
            background-color: #1976d2;
            color: white;
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
            <h1>都心マンションDB</h1>
        </div>
        
        <div class="content">
            <p>こんにちは{user_name or ''}様、</p>
            
            <p>都心マンションDBにご登録いただき、ありがとうございます。</p>
            
            <p>以下のボタンをクリックしてメールアドレスの確認を完了してください：</p>
            
            <p style="text-align: center;">
                <a href="{verification_url}" class="button">メールアドレスを確認する</a>
            </p>
            
            <div class="warning">
                <strong>重要:</strong> このリンクは24時間有効です。期限が切れた場合は、再度ご登録をお願いいたします。
            </div>
            
            <p>ボタンが機能しない場合は、以下のURLをブラウザにコピー&ペーストしてください：</p>
            <p style="word-break: break-all; color: #666; font-size: 14px;">{verification_url}</p>
        </div>
        
        <div class="footer">
            <p><strong>※このメールに覚えがない場合は、このメールを無視してください。</strong></p>
            <p>都心マンションDB運営チーム</p>
        </div>
    </div>
</body>
</html>
        """

    async def send_password_reset_email(self, email: str, user_name: str, reset_token: str) -> bool:
        """パスワードリセットメールを送信（将来の実装用）"""
        # TODO: 将来パスワードリセット機能を実装する際に使用
        pass


# シングルトンインスタンス
email_service = EmailService()