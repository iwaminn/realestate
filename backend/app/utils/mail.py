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
        recipient: 受信者メールアドレス（デフォルト: info@mscan.jp）
    """
    if recipient is None:
        recipient = os.getenv("CONTACT_EMAIL", "info@mscan.jp")

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

    text_body = f"""
お問い合わせがありました

送信者名: {name}
メールアドレス: {email}
件名: {subject}

お問い合わせ内容:
{message}

---
このメールは都心マンション価格チェッカーのお問い合わせフォームから送信されました。
    """

    # メッセージを作成
    message_schema = MessageSchema(
        subject=f"【お問い合わせ】{subject}",
        recipients=[recipient],
        body=html_body,
        subtype=MessageType.html
    )

    # メール送信
    await fm.send_message(message_schema)
