"""
ユーザー認証API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
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
    get_password_hash, 
    get_current_user_from_token,
    create_user_session,
    revoke_user_session,
    send_verification_email,
    verify_email_token
)
from pydantic import BaseModel, validator

router = APIRouter()
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

@router.post("/login", response_model=TokenResponse)
async def login_user(user_data: UserLogin, db: Session = Depends(get_db)):
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
    
    
    # JWTトークン作成
    access_token, jti, expires_at = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    # セッション記録
    create_user_session(db, user.id, jti, expires_at)
    
    # 最終ログイン時刻を更新
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """ユーザーログアウト"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です"
        )
    
    token = credentials.credentials
    from ..utils.auth import verify_token
    payload = verify_token(token)
    
    if payload:
        jti = payload.get("jti")
        if jti:
            revoke_user_session(db, jti)
    
    return {"message": "ログアウトしました"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(require_auth)):
    """現在のユーザー情報を取得"""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_user_profile(
    user_data: dict,
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """ユーザープロフィール更新"""
    
    # 現在は更新可能なフィールドなし（将来の拡張用に残す）
    
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    
    return current_user

@router.get("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
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
    
    return {"message": "メールアドレスが確認され、本登録が完了しました", "email": user.email}

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
