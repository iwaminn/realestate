"""
価格改定履歴管理用APIエンドポイント
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from ...database import get_db
from ...api.auth import get_admin_user
from ...models import PropertyPriceChangeQueue, PropertyPriceChange, MasterProperty
from ...utils.price_change_calculator import PriceChangeCalculator

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["admin-price-changes"],
    dependencies=[Depends(get_admin_user)]
)


@router.post("/price-changes/refresh-all", response_model=Dict[str, Any])
async def refresh_all_price_changes(
    background_tasks: BackgroundTasks,
    days: int = Query(90, description="更新対象期間（日数）"),
    db: Session = Depends(get_db)
):
    """
    全物件の価格改定履歴を更新
    バックグラウンドで実行
    """
    
    def background_refresh():
        # バックグラウンドタスク内で新しいセッションを作成
        from ...database import SessionLocal
        db_session = SessionLocal()
        try:
            calculator = PriceChangeCalculator(db_session)
            stats = calculator.refresh_all_recent_changes(days)
            logger.info(f"価格改定履歴の更新完了: {stats}")
        except Exception as e:
            logger.error(f"価格改定履歴の更新に失敗: {e}", exc_info=True)
        finally:
            db_session.close()
    
    background_tasks.add_task(background_refresh)
    
    return {
        "message": "価格改定履歴の更新を開始しました",
        "days": days,
        "started_at": datetime.now().isoformat()
    }


@router.post("/price-changes/refresh-immediate", response_model=Dict[str, Any])
async def refresh_price_changes_immediate(
    days: int = Query(90, description="更新対象期間（日数）"),
    limit: int = Query(1000, description="処理する最大件数"),
    db: Session = Depends(get_db)
):
    """
    価格改定履歴を即座に更新（同期実行）
    指定期間のデータを更新する（キューは別途処理される）
    """
    try:
        calculator = PriceChangeCalculator(db)

        # 指定期間の価格改定履歴を更新
        stats = calculator.refresh_all_recent_changes(days)
        return {
            "success": True,
            "message": f"価格改定履歴を更新しました（過去{days}日間）",
            "stats": stats,
            "updated_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"価格改定履歴の更新に失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-changes/queue-status", response_model=Dict[str, Any])
async def get_queue_status(
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    価格改定キューの状態を取得
    """
    pending_count = db.query(func.count(PropertyPriceChangeQueue.id)).filter(
        PropertyPriceChangeQueue.status == 'pending'
    ).scalar()
    
    processing_count = db.query(func.count(PropertyPriceChangeQueue.id)).filter(
        PropertyPriceChangeQueue.status == 'processing'
    ).scalar()
    
    completed_count = db.query(func.count(PropertyPriceChangeQueue.id)).filter(
        PropertyPriceChangeQueue.status == 'completed'
    ).scalar()
    
    failed_count = db.query(func.count(PropertyPriceChangeQueue.id)).filter(
        PropertyPriceChangeQueue.status == 'failed'
    ).scalar()
    
    # 最近のキューアイテムを取得
    recent_items = db.query(PropertyPriceChangeQueue).order_by(
        PropertyPriceChangeQueue.created_at.desc()
    ).limit(10).all()
    
    return {
        "queue_status": {
            "pending": pending_count,
            "processing": processing_count,
            "completed": completed_count,
            "failed": failed_count
        },
        "recent_items": [
            {
                "id": item.id,
                "master_property_id": item.master_property_id,
                "reason": item.reason,
                "status": item.status,
                "priority": item.priority,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "processed_at": item.processed_at.isoformat() if item.processed_at else None,
                "error_message": item.error_message
            }
            for item in recent_items
        ]
    }


@router.post("/price-changes/process-queue", response_model=Dict[str, Any])
async def process_queue(
    limit: int = Query(1000, description="処理する最大件数"),
    db: Session = Depends(get_db)
):
    """
    キューに入っている物件を処理
    """
    try:
        calculator = PriceChangeCalculator(db)
        stats = calculator.process_queue(limit)
        
        return {
            "success": True,
            "message": "キューの処理を完了しました",
            "stats": stats,
            "processed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"キューの処理に失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/price-changes/queue/{queue_id}", response_model=Dict[str, Any])
async def delete_queue_item(
    queue_id: int,
    db: Session = Depends(get_db)
):
    """
    キューアイテムを削除
    """
    item = db.query(PropertyPriceChangeQueue).filter(
        PropertyPriceChangeQueue.id == queue_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="キューアイテムが見つかりません")
    
    db.delete(item)
    db.commit()
    
    return {
        "success": True,
        "message": f"キューアイテム {queue_id} を削除しました"
    }


@router.post("/price-changes/add-to-queue/{master_property_id}", response_model=Dict[str, Any])
async def add_property_to_queue(
    master_property_id: int,
    reason: str = Query("manual", description="キューに追加する理由"),
    priority: int = Query(0, description="優先度（0が最高）"),
    db: Session = Depends(get_db)
):
    """
    物件を価格改定キューに追加
    """
    # 物件の存在確認
    property_exists = db.query(MasterProperty).filter(
        MasterProperty.id == master_property_id
    ).first()
    
    if not property_exists:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    calculator = PriceChangeCalculator(db)
    success = calculator.add_to_queue(master_property_id, reason, priority)
    
    if success:
        return {
            "success": True,
            "message": f"物件 {master_property_id} をキューに追加しました"
        }
    else:
        raise HTTPException(status_code=500, detail="キューへの追加に失敗しました")


@router.get("/price-changes/cache-stats", response_model=Dict[str, Any])
async def get_cache_statistics(
    current_user: dict = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """
    価格改定キャッシュの統計情報を取得
    """
    total_cached = db.query(func.count(PropertyPriceChange.id)).scalar()
    
    # 物件ごとの改定回数
    properties_with_changes = db.query(
        func.count(func.distinct(PropertyPriceChange.master_property_id))
    ).scalar()
    
    # 最新の更新日時
    latest_update = db.query(func.max(PropertyPriceChange.updated_at)).scalar()
    
    # 直近30日の価格改定数
    from datetime import date, timedelta
    recent_date = date.today() - timedelta(days=30)
    recent_changes = db.query(func.count(PropertyPriceChange.id)).filter(
        PropertyPriceChange.change_date >= recent_date
    ).scalar()
    
    return {
        "total_cached_changes": total_cached,
        "properties_with_changes": properties_with_changes,
        "recent_changes_30days": recent_changes,
        "latest_update": latest_update.isoformat() if latest_update else None,
        "average_changes_per_property": (
            round(total_cached / properties_with_changes, 2) 
            if properties_with_changes > 0 else 0
        )
    }