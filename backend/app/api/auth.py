"""
ユーザー認証API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Response, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import re
import secrets

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
from ..utils.datetime_utils import get_utc_now
from ..utils.email_service import EmailService
from pydantic import BaseModel, validator

router = APIRouter()

# Cookie設定（環境変数で制御）
import os
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none")  # 開発環境: none, 本番環境: lax
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)  # 本番環境: .your-domain.com
security = HTTPBearer(auto_error=False)

# Cookie設定のヘルパー関数
def set_auth_cookie(response: Response, key: str, value: str, max_age: int):
    """認証Cookieを設定（環境に応じてパラメータを調整）"""
    cookie_params = {
        "key": key,
        "value": value,
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "path": "/",
        "max_age": max_age
    }
    if COOKIE_DOMAIN:
        cookie_params["domain"] = COOKIE_DOMAIN
    response.set_cookie(**cookie_params)

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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('パスワードは8文字以上である必要があります')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('パスワードには英字を含む必要があります')
        if not re.search(r'\d', v):
            raise ValueError('パスワードには数字を含む必要があります')
        return v

class EmailChange(BaseModel):
    new_email: str
    password: str
    
    @validator('new_email')
    def validate_new_email(cls, v):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('有効なメールアドレスを入力してください')
        if len(v) > 254:
            raise ValueError('メールアドレスが長すぎます')
        return v.lower()

class PasswordSet(BaseModel):
    new_password: str
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('パスワードは8文字以上である必要があります')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('パスワードには英字を含む必要があります')
        if not re.search(r'\d', v):
            raise ValueError('パスワードには数字を含む必要があります')
        return v

class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    google_id: Optional[str]
    has_password: bool
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
    access_token = request.cookies.get("access_token")
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
    set_auth_cookie(response, "access_token", access_token, 15 * 60)  # 15分
    set_auth_cookie(response, "refresh_token", refresh_token, 7 * 24 * 60 * 60)  # 7日
    
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
    from ..utils.logger import api_logger
    
    # デバッグ: リクエストCookieを確認
    api_logger.info(f"ログアウト開始 - Cookies: {request.cookies}")
    
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
                api_logger.info(f"アクセストークンのセッションを無効化: {jti}")
    
    if refresh_token:
        from ..utils.auth import verify_token
        payload = verify_token(refresh_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                revoke_user_session(db, jti)
                api_logger.info(f"リフレッシュトークンのセッションを無効化: {jti}")
    
    # Cookieを削除（ヘルパー関数を使用してmax_age=0で削除）
    set_auth_cookie(response, "access_token", "", 0)
    set_auth_cookie(response, "refresh_token", "", 0)
    
    api_logger.info(f"Cookieを削除 - secure={COOKIE_SECURE}, samesite={COOKIE_SAMESITE}, domain={COOKIE_DOMAIN}")
    
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
    set_auth_cookie(response, "access_token", access_token, 15 * 60)  # 15分
    
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
    if not user and credentials:
        # Bearer Token認証を試す
        token = credentials.credentials
        user = get_current_user_from_token(db, token)
    
    if not user:
        # どちらの認証方法も失敗
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です"
        )
    
    # has_passwordフィールドを動的に追加
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "google_id": user.google_id,
        "has_password": bool(user.hashed_password),
        "created_at": user.created_at,
        "last_login_at": user.last_login_at
    }

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
    set_auth_cookie(response, "access_token", access_token, 15 * 60)  # 15分
    set_auth_cookie(response, "refresh_token", refresh_token, 7 * 24 * 60 * 60)  # 7日
    
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

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """パスワード変更"""
    from ..utils.auth import verify_password
    
    # 現在のパスワードを確認
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="現在のパスワードが正しくありません"
        )
    
    # 新しいパスワードが現在のパスワードと同じでないことを確認
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新しいパスワードは現在のパスワードと異なる必要があります"
        )
    
    # パスワードを更新
    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "パスワードを変更しました"}

@router.post("/change-email")
async def request_email_change(
    email_data: EmailChange,
    current_user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """メールアドレス変更リクエスト（確認メール送信）"""
    from ..utils.auth import verify_password
    from ..models import PendingEmailChange
    from ..utils.email_service import email_service
    import secrets

    # パスワードを確認
    if not verify_password(email_data.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="パスワードが正しくありません"
        )

    # 新しいメールアドレスが現在のメールアドレスと同じでないことを確認
    if email_data.new_email == current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新しいメールアドレスは現在のメールアドレスと異なる必要があります"
        )

    # 新しいメールアドレスが既に使用されていないか確認
    existing_user = db.query(User).filter(User.email == email_data.new_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このメールアドレスは既に使用されています"
        )

    # 既存の未完了リクエストを削除
    db.query(PendingEmailChange).filter(
        PendingEmailChange.user_id == current_user.id,
        PendingEmailChange.used_at == None
    ).delete()

    # 確認トークン生成
    verification_token = secrets.token_urlsafe(32)

    # 有効期限（24時間後）
    expires_at = get_utc_now() + timedelta(hours=24)

    # リクエストをデータベースに保存
    pending_change = PendingEmailChange(
        user_id=current_user.id,
        new_email=email_data.new_email,
        verification_token=verification_token,
        expires_at=expires_at
    )
    db.add(pending_change)
    db.commit()

    # 新しいメールアドレスへ確認メールを送信
    email_sent = await email_service.send_email_change_verification(
        new_email=email_data.new_email,
        user_name=current_user.email,
        verification_token=verification_token
    )

    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="確認メールの送信に失敗しました"
        )

    return {
        "message": "確認メールを送信しました。新しいメールアドレスに届いたメールから確認を完了してください。"
    }


@router.get("/verify-email-change")
async def verify_email_change(token: str, response: Response, db: Session = Depends(get_db)):
    """メールアドレス変更確認"""
    from ..models import PendingEmailChange
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"[Email Change Verification] Token received: {token}")

    # 確認リクエストを検索
    pending_change = db.query(PendingEmailChange).filter(
        PendingEmailChange.verification_token == token,
        PendingEmailChange.used_at == None,
        PendingEmailChange.expires_at > get_utc_now()
    ).first()

    # デバッグ用：トークンの状態を確認
    all_pending = db.query(PendingEmailChange).filter(
        PendingEmailChange.verification_token == token
    ).first()

    if all_pending:
        logger.info(f"[Email Change Verification] Found token. used_at: {all_pending.used_at}, expires_at: {all_pending.expires_at}, now: {get_utc_now()}")
    else:
        logger.info(f"[Email Change Verification] Token not found in database")

    if not pending_change:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無効または期限切れの確認トークンです"
        )

    # ユーザーを取得
    user = db.query(User).filter(User.id == pending_change.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません"
        )

    # 新しいメールアドレスが他のユーザーに使用されていないか再確認
    existing_user = db.query(User).filter(
        User.email == pending_change.new_email,
        User.id != user.id
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このメールアドレスは既に使用されています"
        )

    # メールアドレスを更新
    old_email = user.email
    user.email = pending_change.new_email
    user.updated_at = get_utc_now()

    # 確認を使用済みにする
    pending_change.used_at = get_utc_now()

    db.commit()

    return {
        "message": "メールアドレスを変更しました",
        "old_email": old_email,
        "new_email": user.email
    }

@router.delete("/account")
async def delete_account(
    password_data: dict,
    request: Request,
    response: Response,
    current_user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """アカウント削除"""
    from ..utils.auth import verify_password
    
    password = password_data.get("password")
    if not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="パスワードが必要です"
        )
    
    # パスワードを確認
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="パスワードが正しくありません"
        )
    
    # セッションを無効化
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    
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
    
    # ユーザーを削除（関連データもカスケード削除される）
    db.delete(current_user)
    db.commit()
    
    # Cookieを削除
    set_auth_cookie(response, "access_token", "", 0)
    set_auth_cookie(response, "refresh_token", "", 0)
    
    return {"message": "アカウントを削除しました"}


@router.post("/request-password-set")
async def request_password_set(
    password_data: PasswordSet,
    current_user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db)
):
    """パスワード設定リクエスト（Googleアカウントユーザー用・メール確認必要）"""
    
    # Googleユーザーのみ許可
    if not current_user.google_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="この機能はGoogleアカウントユーザーのみ利用できます"
        )
    
    # 既にパスワードが設定されている場合はエラー
    if current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="既にパスワードが設定されています。パスワード変更をご利用ください。"
        )
    
    # 既存のパスワード設定リクエストを削除（同じユーザーで再リクエストを許可）
    from ..models import PendingPasswordSet
    existing_pending = db.query(PendingPasswordSet).filter(
        PendingPasswordSet.user_id == current_user.id
    ).first()
    if existing_pending:
        db.delete(existing_pending)
        db.commit()
    
    # 検証トークン生成
    import secrets
    from datetime import timedelta
    
    verification_token = secrets.token_urlsafe(32)
    hashed_password = get_password_hash(password_data.new_password)
    
    # パスワード設定リクエストを保存
    pending_password_set = PendingPasswordSet(
        user_id=current_user.id,
        hashed_password=hashed_password,
        verification_token=verification_token,
        expires_at=datetime.utcnow() + timedelta(hours=24)  # 24時間有効
    )
    
    db.add(pending_password_set)
    db.commit()
    db.refresh(pending_password_set)
    
    # メール確認メールを送信
    try:
        from ..utils.email_service import EmailService
        email_service = EmailService()
        await email_service.send_password_set_verification_email(
            current_user.email,
            current_user.email,  # 名前の代わりにメールアドレスを使用
            verification_token
        )
    except Exception as e:
        # メール送信エラーでもリクエストは成功させる
        print(f"メール送信エラー（パスワード設定リクエストは保存済み）: {e}")
    
    return {"message": "パスワード設定確認メールを送信しました。メールをご確認ください。"}

@router.get("/verify-password-set")
async def verify_password_set(token: str, response: Response, db: Session = Depends(get_db)):
    """パスワード設定確認（メール確認後）"""
    from ..models import PendingPasswordSet
    
    # パスワード設定リクエストを検索
    pending_password_set = db.query(PendingPasswordSet).filter(
        PendingPasswordSet.verification_token == token,
        PendingPasswordSet.expires_at > datetime.utcnow()
    ).first()
    
    if not pending_password_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無効または期限切れの確認トークンです"
        )
    
    # ユーザーを取得
    user = db.query(User).filter(User.id == pending_password_set.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません"
        )
    
    # 既にパスワードが設定されている場合はエラー
    if user.hashed_password:
        # リクエストを削除
        db.delete(pending_password_set)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="既にパスワードが設定されています"
        )
    
    # パスワードを設定
    user.hashed_password = pending_password_set.hashed_password
    user.updated_at = datetime.utcnow()
    
    # パスワード設定リクエストを削除
    db.delete(pending_password_set)
    
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
    
    # HttpOnly Cookieにトークンを設定
    set_auth_cookie(response, "access_token", access_token, 15 * 60)  # 15分
    set_auth_cookie(response, "refresh_token", refresh_token, 7 * 24 * 60 * 60)  # 7日
    
    return {
        "message": "パスワードが設定されました。次回からメールアドレスとパスワードでもログインできます。",
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "google_id": user.google_id,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at
        }
    }


@router.post("/request-password-reset")
async def request_password_reset(
    email: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """パスワードリセット申請（メール確認）"""
    from ..models import PendingPasswordReset
    
    # ユーザーの存在確認
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # セキュリティ上、ユーザーが存在しない場合でも同じメッセージを返す
        return {
            "message": "パスワードリセットメールを送信しました。メールをご確認ください。"
        }
    
    # リセットトークン生成
    reset_token = secrets.token_urlsafe(32)
    
    # 有効期限（24時間）
    expires_at = get_utc_now() + timedelta(hours=24)
    
    # 既存のリセットリクエストを削除
    db.query(PendingPasswordReset).filter(
        PendingPasswordReset.user_id == user.id
    ).delete()
    
    # 新しいリセットリクエストを作成
    pending_reset = PendingPasswordReset(
        user_id=user.id,
        reset_token=reset_token,
        expires_at=expires_at
    )
    db.add(pending_reset)
    db.commit()
    
    # メール送信
    email_service = EmailService()
    success = await email_service.send_password_reset_email(
        email=user.email,
        user_name=user.email.split('@')[0],
        reset_token=reset_token
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="メール送信に失敗しました"
        )
    
    return {
        "message": "パスワードリセットメールを送信しました。メールをご確認ください。"
    }


@router.post("/reset-password")
async def reset_password(
    response: Response,
    token: str = Body(...),
    new_password: str = Body(...)
):
    """パスワードリセット実行（トークン検証後）"""
    from ..models import PendingPasswordReset
    
    db = next(get_db())
    
    try:
        # トークンの検証
        pending_reset = db.query(PendingPasswordReset).filter(
            PendingPasswordReset.reset_token == token,
            PendingPasswordReset.used_at == None
        ).first()
        
        if not pending_reset:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無効なリセットトークンです"
            )
        
        # 有効期限確認
        if pending_reset.expires_at < get_utc_now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="リセットトークンの有効期限が切れています"
            )
        
        # パスワードのバリデーション
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="パスワードは8文字以上である必要があります"
            )
        
        has_letter = any(c.isalpha() for c in new_password)
        has_number = any(c.isdigit() for c in new_password)
        if not has_letter or not has_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="パスワードには英字と数字を含む必要があります"
            )
        
        # ユーザーのパスワードを更新
        user = db.query(User).filter(User.id == pending_reset.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ユーザーが見つかりません"
            )
        
        # パスワードをハッシュ化して更新
        user.hashed_password = get_password_hash(new_password)

        # リセットトークンを使用済みにする
        pending_reset.used_at = get_utc_now()

        db.commit()

        # パスワードリセット成功後、自動的にログイン（Cookieを設定）
        access_token, access_jti, access_expires_at = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(
            data={"sub": str(user.id), "email": user.email}
        )

        # セッション記録
        create_user_session(db, user.id, access_jti, access_expires_at)

        # Cookieにトークンを設定（ログインと同じ処理）
        set_auth_cookie(response, "access_token", access_token, 15 * 60)  # 15分
        set_auth_cookie(response, "refresh_token", refresh_token, 7 * 24 * 60 * 60)  # 7日

        return {
            "message": "パスワードをリセットしました",
            "user": {
                "id": user.id,
                "email": user.email,
                "has_password": True,
                "is_google_user": user.google_id is not None,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"パスワードリセットに失敗しました: {str(e)}"
        )
    finally:
        db.close()
