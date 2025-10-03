"""
お問い合わせAPI
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
import os

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

    現在はログに記録するのみ。
    将来的にはメール送信機能を追加予定。
    """
    try:
        # お問い合わせ内容をログに記録
        logger.info(
            f"お問い合わせ受付: "
            f"名前={request.name}, "
            f"メール={request.email}, "
            f"件名={request.subject}"
        )
        logger.info(f"内容: {request.message}")

        # TODO: 将来的にメール送信機能を追加
        # 現在はログに記録するのみ

        return {
            "message": "お問い合わせを受け付けました",
            "status": "success"
        }

    except Exception as e:
        logger.error(f"お問い合わせ処理エラー: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="お問い合わせの送信に失敗しました"
        )
