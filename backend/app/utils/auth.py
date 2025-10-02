"""
認証関連のユーティリティ
"""

import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from ..models import User, UserSession, EmailVerificationToken
from ..utils.email_service import email_service
import uuid

# パスワードハッシュ化コンテキスト
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT設定
SECRET_KEY = "realestate_secret_key_change_in_production"  # 本番環境では環境変数から取得
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30日間

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """パスワードを検証"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """パスワードをハッシュ化"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWTアクセストークンを作成"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # JTI (JWT ID) を追加
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti, expire

def verify_token(token: str) -> Optional[Dict[Any, Any]]:
    """JWTトークンを検証"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"[Auth] Token verified successfully: jti={payload.get('jti')[:8] if payload.get('jti') else 'None'}...")
        return payload
    except jwt.PyJWTError as e:
        print(f"[Auth] Token verification failed: {e}")
        return None

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """ユーザー認証"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def create_user_session(db: Session, user_id: int, jti: str, expires_at: datetime) -> UserSession:
    """ユーザーセッションを作成"""
    session = UserSession(
        user_id=user_id,
        jti=jti,
        expires_at=expires_at
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def revoke_user_session(db: Session, jti: str) -> bool:
    """ユーザーセッションを無効化"""
    session = db.query(UserSession).filter(UserSession.jti == jti).first()
    if session:
        session.is_revoked = True
        db.commit()
        return True
    return False

def is_token_revoked(db: Session, jti: str) -> bool:
    """トークンが無効化されているかチェック"""
    session = db.query(UserSession).filter(UserSession.jti == jti).first()
    result = session.is_revoked if session else True
    print(f"[Auth] Token revoked check: jti={jti[:8]}..., session_exists={session is not None}, is_revoked={result}")
    return result

def get_current_user_from_token(db: Session, token: str) -> Optional[User]:
    """トークンから現在のユーザーを取得"""
    payload = verify_token(token)
    if payload is None:
        return None
    
    # トークンが無効化されていないかチェック
    jti = payload.get("jti")
    if not jti or is_token_revoked(db, jti):
        return None
    
    # ユーザーIDを取得
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    
    try:
        user_id: int = int(user_id_str)
    except (ValueError, TypeError):
        return None
    
    # ユーザーを取得
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user

def cleanup_expired_sessions(db: Session) -> int:
    """期限切れセッションをクリーンアップ"""
    expired_count = db.query(UserSession).filter(
        UserSession.expires_at < datetime.utcnow()
    ).count()
    
    db.query(UserSession).filter(
        UserSession.expires_at < datetime.utcnow()
    ).delete()
    
    db.commit()
    return expired_count

def generate_verification_token() -> str:
    """メール確認用のトークンを生成"""
    return secrets.token_urlsafe(32)

async def create_email_verification_token(db: Session, user_id: int) -> str:
    """メール確認トークンを作成してデータベースに保存"""
    # 既存の未使用トークンを削除
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user_id,
        EmailVerificationToken.used_at.is_(None)
    ).delete()
    
    # 新しいトークンを生成
    token = generate_verification_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)  # 24時間有効
    
    verification_token = EmailVerificationToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )
    
    db.add(verification_token)
    db.commit()
    
    return token

async def send_verification_email(db: Session, user: User) -> bool:
    """メール確認メールを送信"""
    try:
        # 確認トークンを生成
        token = await create_email_verification_token(db, user.id)
        
        # メール送信
        success = await email_service.send_verification_email(
            email=user.email,
            user_name=user.email.split('@')[0],
            verification_token=token
        )
        
        return success
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return False

def verify_email_token(db: Session, token: str) -> Optional[User]:
    """メール確認トークンを検証してユーザーを取得"""
    # トークンを検索
    verification_token = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token == token,
        EmailVerificationToken.used_at.is_(None),
        EmailVerificationToken.expires_at > datetime.utcnow()
    ).first()
    
    if not verification_token:
        return None
    
    # ユーザーを取得
    user = db.query(User).filter(User.id == verification_token.user_id).first()
    if not user:
        return None
    
    # トークンを使用済みにマーク
    verification_token.used_at = datetime.utcnow()
    
    # ユーザーはメール確認時に作成されるため、is_verifiedフィールドは不要
    
    db.commit()
    
    return user

def cleanup_expired_verification_tokens(db: Session) -> int:
    """期限切れの確認トークンをクリーンアップ"""
    expired_count = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.expires_at < datetime.utcnow()
    ).count()
    
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.expires_at < datetime.utcnow()
    ).delete()
    
    db.commit()
    return expired_count
