"""
Google OAuth認証API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
import os
import secrets
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from ..database import get_db
from ..models import User
from ..utils.auth import create_access_token, create_user_session

router = APIRouter()

# Google OAuth設定
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/oauth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")

# Google OAuth URLs
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

@router.get("/google/login")
async def google_login():
    """Googleログインページへリダイレクト"""
    
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth設定が未設定です"
        )
    
    # 状態パラメータを生成（CSRF保護）
    state = secrets.token_urlsafe(32)
    
    # 認証URLを構築
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?" + "&".join([f"{k}={v}" for k, v in params.items()])
    
    return RedirectResponse(url=auth_url)

@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Googleからのコールバック処理"""
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth設定が未設定です"
        )
    
    # アクセストークンを取得
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
        
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="トークンの取得に失敗しました"
            )
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        # ユーザー情報を取得
        user_response = await client.get(
            GOOGLE_USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ユーザー情報の取得に失敗しました"
            )
        
        google_user = user_response.json()
    
    # ユーザーのメールアドレスで検索
    email = google_user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="メールアドレスが取得できませんでした"
        )
    
    # 既存ユーザーを確認
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # 新規ユーザーを作成（Googleログインの場合、パスワードは不要）
        user = User(
            email=email,
            hashed_password="",  # Googleログインの場合は空
            is_active=True,
            google_id=google_user.get("id")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Google IDを更新（初回ログイン時）
        if not user.google_id:
            user.google_id = google_user.get("id")
            db.commit()
    
    # JWTトークンを作成
    jwt_token, jti, expires_at = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # セッションを作成（トークンを有効化）
    create_user_session(db, user.id, jti, expires_at)
    
    # フロントエンドにリダイレクト（トークン付き）
    redirect_url = f"{FRONTEND_URL}/auth/callback?token={jwt_token}"
    print(f"[OAuth] Created session for user {user.id}, jti={jti}, redirect to {redirect_url[:80]}...")
    
    return RedirectResponse(url=redirect_url)