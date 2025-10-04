"""
管理者用ユーザー管理API
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..database import get_db
from ..api.auth import get_admin_user
from ..models import User, PropertyBookmark, EmailVerificationToken
from ..utils.auth import get_password_hash

router = APIRouter(
    dependencies=[Depends(get_admin_user)]
)

# Pydanticモデル
class UserStats(BaseModel):
    """ユーザー統計情報"""
    total_bookmarks: int
    last_login_at: Optional[datetime]
    created_at: datetime
    email_verified_at: Optional[datetime]

class UserListResponse(BaseModel):
    """ユーザー一覧レスポンス"""
    id: int
    email: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    bookmark_count: int

    class Config:
        orm_mode = True

class UserDetailResponse(BaseModel):
    """ユーザー詳細レスポンス"""
    id: int
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime]
    stats: UserStats

    class Config:
        orm_mode = True

class UserUpdate(BaseModel):
    """ユーザー更新データ"""
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None  # パスワードリセット用

class AdminUserStats(BaseModel):
    """管理画面用ユーザー統計"""
    total_users: int
    active_users: int
    users_with_bookmarks: int
    new_users_today: int
    new_users_this_week: int
    new_users_this_month: int

class UserListWithPagination(BaseModel):
    """ページネーション付きユーザー一覧レスポンス"""
    users: List[UserListResponse]
    total: int
    skip: int
    limit: int

@router.get("/users", response_model=UserListWithPagination)
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = Query("created_at", regex="^(created_at|last_login_at|email|bookmark_count)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """ユーザー一覧を取得（管理者のみ）"""
    
    # ベースクエリ
    query = db.query(
        User,
        func.count(PropertyBookmark.id).label('bookmark_count')
    ).outerjoin(
        PropertyBookmark, User.id == PropertyBookmark.user_id
    ).group_by(User.id)
    
    # 検索フィルタ
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            User.email.ilike(search_pattern)
        )
    
    # ステータスフィルタ
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    # 総件数を取得
    total_query = db.query(User)
    if search:
        total_query = total_query.filter(User.email.ilike(search_pattern))
    if is_active is not None:
        total_query = total_query.filter(User.is_active == is_active)
    total = total_query.count()
    
    # ソート
    if sort_by == "email":
        order_column = User.email
    elif sort_by == "last_login_at":
        order_column = User.last_login_at
    elif sort_by == "bookmark_count":
        order_column = func.count(PropertyBookmark.id)
    else:  # created_at
        order_column = User.created_at
    
    if sort_order == "asc":
        query = query.order_by(order_column.asc())
    else:
        query = query.order_by(order_column.desc())
    
    # ページネーション
    results = query.offset(skip).limit(limit).all()
    
    # レスポンス作成
    users = []
    for user, bookmark_count in results:
        users.append(UserListResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            bookmark_count=bookmark_count
        ))
    
    return UserListWithPagination(
        users=users,
        total=total,
        skip=skip,
        limit=limit
    )

@router.get("/users/stats", response_model=AdminUserStats)
async def get_user_stats(
    db: Session = Depends(get_db)
):
    """ユーザー統計情報を取得（管理者のみ）"""
    
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    
    # 統計情報を集計
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    
    # ブックマークを持つユーザー数
    users_with_bookmarks = db.query(PropertyBookmark.user_id).distinct().count()
    
    # 新規ユーザー数
    new_users_today = db.query(User).filter(User.created_at >= today_start).count()
    new_users_this_week = db.query(User).filter(User.created_at >= week_start).count()
    new_users_this_month = db.query(User).filter(User.created_at >= month_start).count()
    
    return AdminUserStats(
        total_users=total_users,
        active_users=active_users,
        users_with_bookmarks=users_with_bookmarks,
        new_users_today=new_users_today,
        new_users_this_week=new_users_this_week,
        new_users_this_month=new_users_this_month
    )

@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db)
):
    """ユーザー詳細情報を取得（管理者のみ）"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません"
        )
    
    # ブックマーク数を取得
    bookmark_count = db.query(PropertyBookmark).filter(
        PropertyBookmark.user_id == user_id
    ).count()
    
    # メール確認日時を取得
    verification = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user_id,
        EmailVerificationToken.used_at.isnot(None)
    ).first()
    
    email_verified_at = verification.used_at if verification else None
    
    # 統計情報
    stats = UserStats(
        total_bookmarks=bookmark_count,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        email_verified_at=email_verified_at
    )
    
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        stats=stats
    )

@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db)
):
    """ユーザー情報を更新（管理者のみ）"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません"
        )
    
    # 更新データを適用
    if user_data.email is not None:
        # メールアドレスの重複チェック
        existing = db.query(User).filter(
            User.email == user_data.email,
            User.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このメールアドレスは既に使用されています"
            )
        user.email = user_data.email
    
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
    if user_data.password is not None:
        # パスワードをハッシュ化
        user.hashed_password = get_password_hash(user_data.password)
    
    db.commit()
    db.refresh(user)
    
    return {"message": "ユーザー情報を更新しました", "user_id": user.id}

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """ユーザーを削除（管理者のみ）"""
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません"
        )
    
    # 関連データも自動的に削除される（CASCADE設定）
    db.delete(user)
    db.commit()
    
    return {"message": "ユーザーを削除しました", "user_id": user_id}

# メール確認再送信エンドポイントは削除（全ユーザーが確認済みのため不要）