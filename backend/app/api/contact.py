"""
お問い合わせAPI
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
import os

from ..utils.mail import send_contact_email

router = APIRouter(prefix="/api", tags=["contact"])

logger = logging.getLogger(__name__)


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str


@router.post("/contact")
async def submit_contact(request: ContactRequest):
    """
    お問い合わせフォームを送信
    
    送信内容をinfo@mscan.jpにメール送信します。
    """
    # お問い合わせ内容をログに記録
    logger.info(
        f"お問い合わせ受付: "
        f"名前={request.name}, "
        f"メール={request.email}, "
        f"件名={request.subject}"
    )
    logger.info(f"内容: {request.message}")
    
    try:
        # メール送信を試みる
        await send_contact_email(
            name=request.name,
            email=request.email,
            subject=request.subject,
            message=request.message
        )
        logger.info("お問い合わせメールを送信しました")
        
        return {
            "message": "お問い合わせを受け付けました",
            "status": "success"
        }

    except Exception as e:
        # メール送信に失敗してもログには記録されているので、エラーにしない
        logger.warning(f"メール送信に失敗しましたが、お問い合わせは記録されました: {e}")
        
        # ユーザーには成功として返す（ログには記録済み）
        return {
            "message": "お問い合わせを受け付けました",
            "status": "success"
        }
