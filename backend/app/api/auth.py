"""
ユーザー認証API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import re

from ..database import get_db
from ..models import User, PendingUser
from ..utils.auth import (
    authenticate_user, 
    create_access_token,
    create_refresh_token,
    get_password_hash, 
    get_current_user_from_token,
    create_user_session,
    revoke_user_session,
    send_verification_email,
    verify_email_token
)
from pydantic import BaseModel, validator

router = APIRouter()

# Cookie設定（環境変数で制御）
import os
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none")  # 開発環境: none, 本番環境: lax
security = HTTPBearer(auto_error=False)

# Pydanticモデル
class UserCreate(BaseModel):
    email: str
    password: str
    
    @validator('email')
    def validate_email(cls, v):
        import re
        # RFC 5322準拠の簡易的なメールアドレス正規表現
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('有効なメールアドレスを入力してください')
        # メールアドレスの長さチェック
        if len(v) > 254:  # RFC 5321
            raise ValueError('メールアドレスが長すぎます')
        return v.lower()  # 小文字に統一
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('パスワードは8文字以上である必要があります')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('パスワードには英字を含む必要があります')
        if not re.search(r'\d', v):
            raise ValueError('パスワードには数字を含む必要があります')
        return v

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# 認証依存関数
def get_current_user_flexible(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Cookie認証またはBearer Token認証でユーザーを取得（オプショナル）"""
    # Cookie認証を試す
    user = get_current_user_from_cookie(request, db)
    if user:
        return user
    
    # Bearer Token認証を試す
    if credentials:
        token = credentials.credentials
        user = get_current_user_from_token(db, token)
        if user:
            return user
    
    return None

def require_auth_flexible(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Cookie認証またはBearer Token認証が必須のエンドポイント用"""
    user = get_current_user_flexible(request, credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です"
        )
    return user

def get_admin_user(
    request: Request,
    db: Session = Depends(get_db)
) -> dict:
    """管理画面用Cookie認証（admin_access_tokenから取得）"""
    from ..utils.auth import verify_token

    # 管理者用Cookieからトークンを取得
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

def get_current_user_from_cookie(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Cookieから現在のユーザーを取得"""
    # デバッグ: Cookieの内容を確認
    print(f"[DEBUG] Cookies: {request.cookies}")
    access_token = request.cookies.get("access_token")
    print(f"[DEBUG] access_token from cookie: {access_token}")
    if not access_token:
        return None
    
    user = get_current_user_from_token(db, access_token)
    return user

def require_auth_cookie(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Cookie認証が必須のエンドポイント用"""
    user = get_current_user_from_cookie(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です"
        )
    return user

# 旧バージョン（Bearer Token）- 後方互換性のため残す
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """現在のユーザーを取得（オプショナル）"""
    if not credentials:
        return None
    
    token = credentials.credentials
    user = get_current_user_from_token(db, token)
    return user

def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """認証が必須のエンドポイント用"""
    print(f"[Auth] require_auth called, credentials={credentials}")
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    user = get_current_user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    
    return user

@router.post("/register")
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """仮登録処理"""
    
    # 本登録済みのメールアドレスチェック
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このメールアドレスは既に登録されています"
        )
    
    # 既存の仮登録を削除（同じメールアドレスで再登録を許可）
    existing_pending = db.query(PendingUser).filter(
        PendingUser.email == user_data.email
    ).first()
    if existing_pending:
        db.delete(existing_pending)
        db.commit()
    
    # 仮登録ユーザー作成
    import secrets
    from datetime import datetime, timedelta
    
    verification_token = secrets.token_urlsafe(32)
    hashed_password = get_password_hash(user_data.password)
    
    pending_user = PendingUser(
        email=user_data.email,
        hashed_password=hashed_password,
        verification_token=verification_token,
        expires_at=datetime.utcnow() + timedelta(hours=24)  # 24時間有効
    )
    
    db.add(pending_user)
    db.commit()
    db.refresh(pending_user)
    
    # メール確認メールを送信
    try:
        from ..utils.email_service import EmailService
        email_service = EmailService()
        await email_service.send_verification_email(
            user_data.email,
            user_data.email,  # 名前の代わりにメールアドレスを使用
            verification_token
        )
    except Exception as e:
        # メール送信エラーでも仮登録は成功させる
        print(f"メール送信エラー（仮登録は成功）: {e}")
    
    return {"message": "仮登録が完了しました。メールをご確認ください。"}

@router.post("/login")
async def login_user(user_data: UserLogin, response: Response, db: Session = Depends(get_db)):
    """ユーザーログイン"""
    
    # ユーザー認証
    user = authenticate_user(db, user_data.email, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="アカウントが無効になっています"
        )
    
    # アクセストークン作成（15分）
    access_token, access_jti, access_expires_at = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # リフレッシュトークン作成（7日）
    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # セッション記録（両方のトークン）
    create_user_session(db, user.id, access_jti, access_expires_at)
    create_user_session(db, user.id, refresh_jti, refresh_expires_at)
    
    # 最終ログイン時刻を更新
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    # HttpOnly Cookieにトークンを設定
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=15 * 60  # 15分
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 24 * 60 * 60  # 7日
    )
    
    return {
        "message": "ログインしました",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at
        }
    }

@router.post("/logout")
async def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """ユーザーログアウト"""
    # Cookieからトークンを取得
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    
    # セッションを無効化
    if access_token:
        from ..utils.auth import verify_token
        payload = verify_token(access_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                revoke_user_session(db, jti)
    
    if refresh_token:
        from ..utils.auth import verify_token
        payload = verify_token(refresh_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                revoke_user_session(db, jti)
    
    # Cookieを削除
    response.delete_cookie(key="access_token", samesite=COOKIE_SAMESITE)
    response.delete_cookie(key="refresh_token", samesite=COOKIE_SAMESITE)
    
    return {"message": "ログアウトしました"}

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """アクセストークンをリフレッシュ"""
    # Cookieからリフレッシュトークンを取得
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="リフレッシュトークンがありません"
        )
    
    # リフレッシュトークンを検証
    from ..utils.auth import verify_token
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なリフレッシュトークンです"
        )
    
    # ユーザーを取得
    user_id = int(payload.get("sub"))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザーが見つかりません"
        )
    
    # 新しいアクセストークンを作成
    access_token, access_jti, access_expires_at = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # セッション記録
    create_user_session(db, user.id, access_jti, access_expires_at)
    
    # HttpOnly Cookieに新しいアクセストークンを設定
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=15 * 60  # 15分
    )
    
    return {"message": "トークンをリフレッシュしました"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    """現在のユーザー情報を取得（Cookie認証またはBearer Token認証）"""
    # Cookie認証を試す
    user = get_current_user_from_cookie(request, db)
    if user:
        return user
    
    # Bearer Token認証を試す
    if credentials:
        token = credentials.credentials
        user = get_current_user_from_token(db, token)
        if user:
            return user
    
    # どちらの認証方法も失敗
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証が必要です"
    )

@router.put("/me", response_model=UserResponse)
async def update_user_profile(
    user_data: dict,
    current_user: User = Depends(require_auth_cookie),
    db: Session = Depends(get_db)
):
    """ユーザープロフィール更新"""
    
    # 現在は更新可能なフィールドなし（将来の拡張用に残す）
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    
    return current_user

@router.get("/verify-email")
async def verify_email(token: str, response: Response, db: Session = Depends(get_db)):
    """メールアドレス確認（仮登録→本登録）"""
    
    # 仮登録ユーザーを検索
    pending_user = db.query(PendingUser).filter(
        PendingUser.verification_token == token,
        PendingUser.expires_at > datetime.utcnow()
    ).first()
    
    if not pending_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無効または期限切れの確認トークンです"
        )
    
    # 本登録ユーザーを作成
    user = User(
        email=pending_user.email,
        hashed_password=pending_user.hashed_password,
        is_active=True
    )
    
    db.add(user)
    
    # 仮登録を削除
    db.delete(pending_user)
    
    db.commit()
    db.refresh(user)
    
    # アクセストークン作成（15分）
    access_token, access_jti, access_expires_at = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # リフレッシュトークン作成（7日）
    refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # セッション記録（両方のトークン）
    create_user_session(db, user.id, access_jti, access_expires_at)
    create_user_session(db, user.id, refresh_jti, refresh_expires_at)
    
    # 最終ログイン時刻を更新
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    # HttpOnly Cookieにトークンを設定
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=15 * 60  # 15分
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=7 * 24 * 60 * 60  # 7日
    )
    
    return {
        "message": "メールアドレスが確認され、本登録が完了しました",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at
        }
    }

@router.post("/resend-verification")
async def resend_verification_email(
    email_data: dict,
    db: Session = Depends(get_db)
):
    """確認メールを再送信"""
    email = email_data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="メールアドレスが必要です"
        )
    
    # 本登録済みか確認
    user = db.query(User).filter(User.email == email).first()
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このメールアドレスは既に本登録済みです"
        )
    
    # 仮登録ユーザーを検索
    pending_user = db.query(PendingUser).filter(PendingUser.email == email).first()
    if not pending_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="仮登録が見つかりません。もう一度新規登録してください。"
        )
    
    # 確認メールを再送信
    try:
        from ..utils.email_service import EmailService
        email_service = EmailService()
        await email_service.send_verification_email(
            pending_user.email,
            pending_user.email,  # 名前の代わりにメールアドレスを使用
            pending_user.verification_token
        )
        return {"message": "確認メールを再送信しました"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="メール送信に失敗しました"
        )
