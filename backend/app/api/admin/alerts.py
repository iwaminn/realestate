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
_resolved_alerts = set()


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
    dummy_alert_id = 1
    is_resolved = dummy_alert_id in _resolved_alerts
    
    # 解決済みフィルタの処理
    if resolved is not None:
        # resolved=Trueの場合は解決済みのみ、resolved=Falseの場合は未解決のみ
        if resolved != is_resolved:
            return alerts
    
    alerts.append(ScraperAlert(
        id=dummy_alert_id,
        scraper_name=scraper_name or "suumo",
        alert_type="task_failed",
        message="スクレイピングタスクが失敗しました",
        details={
            "task_id": "dummy-task-1",
            "status": "failed",
            "error_message": "Connection timeout"
        },
        created_at=datetime.now() - timedelta(minutes=30),  # 30分前に発生したことにする
        resolved_at=datetime.now() if is_resolved else None,
        resolved_by="admin" if is_resolved else None
    ))
    
    return alerts


@router.put("/scraper-alerts/{alert_id}/resolve")
async def resolve_scraper_alert(
    alert_id: int,
    resolved_by: str = "admin",
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを解決済みにする"""
    
    # 簡易実装: メモリ内で解決状態を管理
    # 実際の実装では、scraper_alertsテーブルまたは
    # ScrapingTaskテーブルのステータスを更新する
    
    _resolved_alerts.add(alert_id)
    
    return {
        "message": "アラートを解決済みにしました",
        "alert_id": alert_id,
        "resolved_by": resolved_by,
        "resolved_at": datetime.now().isoformat()
    }


@router.put("/scraper-alerts/{alert_id}/unresolve")
async def unresolve_scraper_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを未解決に戻す"""
    
    # 簡易実装: メモリ内から解決状態を削除
    _resolved_alerts.discard(alert_id)
    
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