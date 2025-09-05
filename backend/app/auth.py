"""
管理画面用の認証モジュール
"""
import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Optional

# ベーシック認証の設定
security = HTTPBasic(auto_error=False)  # auto_error=Falseでダイアログを抑制

# 環境変数から認証情報を取得
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin_password")

# 開発環境での認証バイパス設定
DISABLE_AUTH = os.getenv("DISABLE_ADMIN_AUTH", "false").lower() == "true"

def verify_admin_credentials(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    """管理者認証を検証する"""
    # 開発環境で認証無効化が設定されている場合はバイパス
    if DISABLE_AUTH:
        return "developer"  # 開発者ユーザーとして認証
    
    # 通常の認証処理
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # タイミング攻撃を防ぐため、secrets.compare_digestを使用
    is_username_correct = secrets.compare_digest(
        credentials.username.encode("utf8"),
        ADMIN_USERNAME.encode("utf8")
    )
    is_password_correct = secrets.compare_digest(
        credentials.password.encode("utf8"),
        ADMIN_PASSWORD.encode("utf8")
    )
    
    if not (is_username_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username