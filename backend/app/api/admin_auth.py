"""
管理者認証API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..models import User
from ..utils.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user_session,
    revoke_user_session,
    verify_token
)

router = APIRouter()

# Cookie設定（環境変数で制御）
import os
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none")  # 開発環境: none, 本番環境: lax

class AdminLoginRequest(BaseModel):
    username: str
    password: str

@router.post("/admin/login")
async def admin_login(
    login_data: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """管理者ログイン（環境変数ベース）"""

    # 環境変数から管理者認証情報を取得
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")

    # 認証チェック
    import secrets
    correct_username = secrets.compare_digest(login_data.username, admin_username)
    correct_password = secrets.compare_digest(login_data.password, admin_password)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません"
        )

    # 管理者用のトークンを作成（ユーザーIDは "admin" として扱う）
    # アクセストークン作成（1時間）
    access_token, access_jti, access_expires_at = create_access_token(
        data={"sub": "admin", "username": login_data.username, "is_admin": True}
    )

    # リフレッシュトークン作成（7日）
    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(
        data={"sub": "admin", "username": login_data.username, "is_admin": True}
    )

    # HttpOnly Cookieにトークンを設定
    response.set_cookie(
        key="admin_access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60  # 1時間
    )

    response.set_cookie(
        key="admin_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 24 * 60 * 60  # 7日
    )

    return {
        "message": "ログインしました",
        "user": {
            "username": login_data.username,
            "is_admin": True
        }
    }

@router.post("/admin/logout")
async def admin_logout(
    response: Response
):
    """管理者ログアウト"""
    # Cookieを削除
    response.delete_cookie(key="admin_access_token", samesite=COOKIE_SAMESITE)
    response.delete_cookie(key="admin_refresh_token", samesite=COOKIE_SAMESITE)

    return {"message": "ログアウトしました"}

@router.post("/admin/refresh")
async def admin_refresh_token(
    request: Request,
    response: Response
):
    """管理者アクセストークンをリフレッシュ"""
    # Cookieからリフレッシュトークンを取得
    refresh_token = request.cookies.get("admin_refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="リフレッシュトークンがありません"
        )

    # リフレッシュトークンを検証
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なリフレッシュトークンです"
        )

    # 新しいアクセストークンを作成
    username = payload.get("username", "admin")
    access_token, access_jti, access_expires_at = create_access_token(
        data={"sub": "admin", "username": username, "is_admin": True}
    )

    # HttpOnly Cookieに新しいアクセストークンを設定
    response.set_cookie(
        key="admin_access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=60 * 60  # 1時間
    )

    return {"message": "トークンをリフレッシュしました"}

@router.get("/admin/me")
async def get_admin_user_info(
    request: Request
):
    """現在の管理者ユーザー情報を取得"""
    # Cookieからトークンを取得
    access_token = request.cookies.get("admin_access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です"
        )

    # トークンを検証
    payload = verify_token(access_token)
    if not payload or not payload.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです"
        )

    return {
        "username": payload.get("username", "admin"),
        "is_admin": True
    }
