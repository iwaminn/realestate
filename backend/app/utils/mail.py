"""
メール送信ユーティリティ
"""
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from typing import List
import os
from pathlib import Path

# メール設定
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
    MAIL_FROM=os.getenv("MAIL_FROM", "noreply@mscan.jp"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# FastMailインスタンス
fm = FastMail(conf)


async def send_contact_email(
    name: str,
    email: str,
    subject: str,
    message: str,
    recipient: str = None
):
    """
    お問い合わせメールを送信

    Args:
        name: 送信者名
        email: 送信者メールアドレス
        subject: 件名
        message: メッセージ本文
        recipient: 受信者メールアドレス（デフォルト: admin@mscan.jp）
    """
    if recipient is None:
        recipient = os.getenv("CONTACT_EMAIL", "admin@mscan.jp")

    # 送信元アドレスはinfo@mscan.jp
    from_email = "info@mscan.jp"

    # AWS SESの設定があれば使用、なければGoogle Workspace
    if os.getenv('SES_SMTP_USERNAME'):
        # AWS SES用の設定
        conf_contact = ConnectionConfig(
            MAIL_USERNAME=os.getenv('SES_SMTP_USERNAME', ''),
            MAIL_PASSWORD=os.getenv('SES_SMTP_PASSWORD', ''),
            MAIL_FROM=from_email,
            MAIL_PORT=int(os.getenv('SES_SMTP_PORT', '587')),
            MAIL_SERVER=os.getenv('SES_SMTP_HOST', 'email-smtp.ap-northeast-1.amazonaws.com'),
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )
    else:
        # Google Workspace用の設定（既存）
        conf_contact = conf

    fm_contact = FastMail(conf_contact)

    # メール本文を作成
    html_body = f"""
    <html>
        <body>
            <h2>お問い合わせがありました</h2>
            <p><strong>送信者名:</strong> {name}</p>
            <p><strong>メールアドレス:</strong> {email}</p>
            <p><strong>件名:</strong> {subject}</p>
            <hr>
            <h3>お問い合わせ内容:</h3>
            <p style="white-space: pre-wrap;">{message}</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                このメールは都心マンション価格チェッカーのお問い合わせフォームから送信されました。
            </p>
        </body>
    </html>
    """

    # メッセージを作成（Reply-Toヘッダーを追加）
    message_schema = MessageSchema(
        subject=f"【お問い合わせ】{subject}",
        recipients=[recipient],
        body=html_body,
        subtype=MessageType.html,
        reply_to=[email]  # 返信先を送信者のメールアドレスに設定
    )

    # メール送信
    await fm_contact.send_message(message_schema)
