"""
スクレイパーアラート管理API
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from ...database import get_db

router = APIRouter(tags=["admin-alerts"])

# メモリ内でアラートの解決状態を管理（開発用の簡易実装）
# 本番では実際のデータベースを使用すべき
# メモリ内のアラート管理は削除（データベースのみ使用）


class ScraperAlert(BaseModel):
    """スクレイパーアラート"""
    id: int
    scraper_name: str
    alert_type: str
    message: str
    details: Optional[Dict[str, Any]]
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]


class CheckStalledTasksResult(BaseModel):
    """停滞タスクチェック結果"""
    task_id: str
    scraper_name: str
    status: str
    started_at: datetime
    last_activity: datetime
    stalled_duration_minutes: int
    action_taken: str


@router.get("/scraper-alerts", response_model=List[ScraperAlert])
async def get_scraper_alerts(
    resolved: Optional[bool] = None,
    scraper_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを取得
    
    Args:
        resolved: 解決済みのみ/未解決のみでフィルタ
        scraper_name: スクレイパー名でフィルタ
        limit: 取得件数
        offset: オフセット
    """
    from ...models import ScraperAlert as DBScraperAlert
    
    # scraper_alertsテーブルから取得
    query = db.query(DBScraperAlert)
    
    # 解決状態でフィルタ
    if resolved is not None:
        if resolved:
            # 解決済み（is_active = False）
            query = query.filter(DBScraperAlert.is_active == False)
        else:
            # 未解決（is_active = True）
            query = query.filter(DBScraperAlert.is_active == True)
    
    # スクレイパー名でフィルタ
    if scraper_name:
        query = query.filter(DBScraperAlert.source_site == scraper_name)
    
    # 新しい順にソートして取得
    db_alerts = query.order_by(DBScraperAlert.created_at.desc()).offset(offset).limit(limit).all()
    
    # DBモデルからAPIレスポンスモデルに変換
    alerts = []
    for db_alert in db_alerts:
        alerts.append(ScraperAlert(
            id=db_alert.id,
            scraper_name=db_alert.source_site,
            alert_type=db_alert.alert_type,
            message=db_alert.message,
            details=db_alert.details if db_alert.details else {},
            created_at=db_alert.created_at,
            resolved_at=db_alert.resolved_at,
            resolved_by="admin" if db_alert.resolved_at else None
        ))
    
    return alerts


@router.put("/scraper-alerts/{alert_id}/resolve")
async def resolve_scraper_alert(
    alert_id: int,
    resolved_by: str = "admin",
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを解決済みにする"""
    from ...models import ScraperAlert as DBScraperAlert
    
    # データベースからアラートを取得
    alert = db.query(DBScraperAlert).filter(DBScraperAlert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="アラートが見つかりません")
    
    # アラートを解決済みに更新
    alert.is_active = False
    alert.resolved_at = datetime.now()
    
    # データベースに保存
    db.commit()
    
    return {
        "message": "アラートを解決済みにしました",
        "alert_id": alert_id,
        "resolved_by": resolved_by,
        "resolved_at": alert.resolved_at.isoformat()
    }


@router.put("/scraper-alerts/{alert_id}/unresolve")
async def unresolve_scraper_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを未解決に戻す"""
    from ...models import ScraperAlert as DBScraperAlert
    
    # データベースからアラートを取得
    alert = db.query(DBScraperAlert).filter(DBScraperAlert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="アラートが見つかりません")
    
    # アラートを未解決に戻す
    alert.is_active = True
    alert.resolved_at = None
    
    # データベースに保存
    db.commit()
    
    return {
        "message": "アラートを未解決に戻しました",
        "alert_id": alert_id
    }


@router.post("/scraping/check-stalled-tasks")
async def check_stalled_tasks(
    stalled_threshold_minutes: int = 30,
    auto_cancel: bool = False,
    db: Session = Depends(get_db)
):
    """停滞しているタスクをチェックして対処
    
    Args:
        stalled_threshold_minutes: 停滞とみなす閾値（分）
        auto_cancel: 自動的にキャンセルするかどうか
    """
    
    # 注: 現在はダミーレスポンスを返す
    # 実際の実装では、ScrapingTaskテーブルから
    # 実行中のタスクを取得して停滞をチェックする
    
    stalled_tasks = []
    
    return {
        "message": f"{len(stalled_tasks)}個の停滞タスクが見つかりました",
        "stalled_count": len(stalled_tasks),
        "tasks": stalled_tasks
    }