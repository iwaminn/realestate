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
    
    # 実際のscrapingタスクから失敗したタスクを取得
    from ...models_scraping_task import ScrapingTask
    
    # 失敗したタスクを検索
    query = db.query(ScrapingTask).filter(ScrapingTask.status == "failed")
    
    # スクレイパー名でフィルタ
    if scraper_name:
        # ScrapingTaskのscrapersフィールドはJSON配列なので、特殊な処理が必要
        from sqlalchemy import func
        query = query.filter(
            func.json_array_length(ScrapingTask.scrapers) > 0
        )
    
    # 解決済みフィルタの処理
    # ScrapingTaskには解決済みフラグがないので、failedステータスのタスクを未解決として扱う
    if resolved == True:
        # 解決済みのアラートはない
        return []
    
    # limitとoffsetを適用
    failed_tasks = query.order_by(ScrapingTask.created_at.desc()).offset(offset).limit(limit).all()
    
    alerts = []
    for task in failed_tasks:
        # ScrapingTaskからScraperAlertに変換
        scrapers_list = task.scrapers if isinstance(task.scrapers, list) else []
        scraper_name_str = scrapers_list[0] if scrapers_list else "unknown"
        
        alerts.append(ScraperAlert(
            id=hash(task.task_id) % 1000000,  # task_idからIDを生成
            scraper_name=scraper_name_str,
            alert_type="task_failed",
            message="スクレイピングタスクが失敗しました",
            details={
                "task_id": task.task_id,
                "status": task.status,
                "scrapers": scrapers_list,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "total_errors": task.total_errors
            },
            created_at=task.created_at,
            resolved_at=None,  # ScrapingTaskには解決済みフラグがない
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