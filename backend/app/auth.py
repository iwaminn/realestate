"""
管理者認証モジュール
"""

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import os

security = HTTPBasic()

def verify_admin_credentials(credentials: HTTPBasicCredentials = Security(security)):
    """管理者認証を検証"""
    # 環境変数から管理者認証情報を取得
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")
    
    # ユーザー名の検証
    correct_username = secrets.compare_digest(credentials.username, admin_username)
    # パスワードの検証
    correct_password = secrets.compare_digest(credentials.password, admin_password)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username

# エイリアス
require_admin = verify_admin_credentials