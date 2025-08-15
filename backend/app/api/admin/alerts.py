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
    
    # 注: 現在はダミーデータを返す
    # 実際の実装では、scraper_alertsテーブルまたは
    # ScrapingTaskテーブルからアラート情報を取得する
    
    alerts = []
    
    # ダミーアラートを返す（テスト用）
    if not resolved:
        alerts.append(ScraperAlert(
            id=1,
            scraper_name=scraper_name or "suumo",
            alert_type="task_failed",
            message="スクレイピングタスクが失敗しました",
            details={
                "task_id": "dummy-task-1",
                "status": "failed",
                "error_message": "Connection timeout"
            },
            created_at=datetime.now(),
            resolved_at=None,
            resolved_by=None
        ))
    
    return alerts


@router.put("/scraper-alerts/{alert_id}/resolve")
async def resolve_scraper_alert(
    alert_id: int,
    resolved_by: str = "admin",
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを解決済みにする"""
    
    # 注: 現在はダミーレスポンスを返す
    # 実際の実装では、scraper_alertsテーブルまたは
    # ScrapingTaskテーブルのステータスを更新する
    
    return {
        "message": "アラートを解決済みにしました",
        "alert_id": alert_id,
        "resolved_by": resolved_by
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