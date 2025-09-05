"""
管理者用スケジュール管理API
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from ..database import get_db
from ..models import ScrapingSchedule, ScrapingScheduleHistory
# スケジューラーサービスは遅延インポートで使用
from ..auth import verify_admin_credentials

router = APIRouter(prefix="/api/admin", tags=["admin-schedules"])


class ScheduleCreateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scrapers: List[str]
    areas: Optional[List[str]] = None
    schedule_type: str = 'interval'  # 'interval' or 'daily'
    interval_minutes: Optional[int] = None
    daily_hour: Optional[int] = None
    daily_minute: Optional[int] = None
    max_properties: int = 100
    is_active: bool = True


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scrapers: Optional[List[str]] = None
    areas: Optional[List[str]] = None
    schedule_type: Optional[str] = None  # 'interval' or 'daily'
    interval_minutes: Optional[int] = None
    daily_hour: Optional[int] = None
    daily_minute: Optional[int] = None
    max_properties: Optional[int] = None
    is_active: Optional[bool] = None

def convert_areas_to_codes(areas, strict=False):
    """エリア名（日本語/英語）をエリアコードに変換
    
    Args:
        areas: エリア名のリスト
        strict: True の場合、無効なエリア名があると例外を発生させる
    
    Returns:
        エリアコードのリスト
        
    Raises:
        ValueError: strict=True で無効なエリア名が含まれる場合
    """
    from backend.app.scrapers.area_config import TOKYO_AREA_CODES
    
    if not areas:
        return []
    
    codes = []
    invalid_areas = []
    
    for area in areas:
        # すでにエリアコードの場合はそのまま
        if area.isdigit() and len(area) == 5:
            # エリアコードが有効かチェック
            if area in TOKYO_AREA_CODES.values():
                codes.append(area)
            else:
                invalid_areas.append(area)
        else:
            # TOKYO_AREA_CODESから検索（大文字小文字を区別しない）
            area_lower = area.lower()
            area_code = TOKYO_AREA_CODES.get(area, TOKYO_AREA_CODES.get(area_lower, None))
            if area_code:
                codes.append(area_code)
            else:
                invalid_areas.append(area)
    
    # strict モードで無効なエリアがある場合は例外を発生
    if strict and invalid_areas:
        raise ValueError(f"無効なエリア名が含まれています: {', '.join(invalid_areas)}")
    
    return codes


@router.get("/schedules")
async def get_schedules(
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """スケジュール一覧を取得"""
    # まず、running状態のスケジュール履歴で対応するタスクが完了している場合は自動更新
    await _update_running_schedule_histories(db)
    
    schedules = db.query(ScrapingSchedule).order_by(ScrapingSchedule.created_at.desc()).all()
    
    result = []
    for schedule in schedules:
        # 最新の実行履歴を取得
        latest_history = db.query(ScrapingScheduleHistory).filter(
            ScrapingScheduleHistory.schedule_id == schedule.id
        ).order_by(ScrapingScheduleHistory.started_at.desc()).first()
        
        # エリアコードを日本語名に変換
        from ..api.admin.scraping import convert_area_codes_to_names
        area_names = convert_area_codes_to_names(schedule.areas) if schedule.areas else []
        
        result.append({
            'id': schedule.id,
            'name': schedule.name,
            'description': schedule.description,
            'scrapers': schedule.scrapers,
            'areas': area_names,  # 日本語名に変換
            'schedule_type': schedule.schedule_type,
            'interval_minutes': schedule.interval_minutes,
            'daily_hour': schedule.daily_hour,
            'daily_minute': schedule.daily_minute,
            'max_properties': schedule.max_properties,
            'is_active': schedule.is_active,
            'last_run_at': schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            'next_run_at': schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            'last_task_id': schedule.last_task_id,
            'created_by': schedule.created_by,
            'created_at': schedule.created_at.isoformat(),
            'updated_at': schedule.updated_at.isoformat(),
            'last_status': latest_history.status if latest_history else None,
            'last_error': latest_history.error_message if latest_history else None,
        })
    
    return {"schedules": result}


async def _update_running_schedule_histories(db: Session):
    """running状態のスケジュール履歴で対応するタスクが完了している場合は自動更新"""
    from ..models_scraping_task import ScrapingTask
    from ..utils.datetime_utils import get_utc_now
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # running状態のスケジュール履歴を取得
        running_histories = db.query(ScrapingScheduleHistory).filter(
            ScrapingScheduleHistory.status == "running"
        ).all()
        
        if not running_histories:
            return
        
        logger.info(f"Found {len(running_histories)} running schedule histories to check")
        
        for history in running_histories:
            try:
                # task_idから対応するスクレイピングタスクを検索
                if not history.task_id:
                    logger.warning(f"Schedule history {history.id} has no task_id")
                    continue
                
                # task_idの形式を確認
                
                # 数値IDに対応するUUIDタスクを検索（最近の作成時刻のものから）
                recent_tasks = db.query(ScrapingTask).filter(
                    ScrapingTask.created_at >= history.started_at
                ).order_by(ScrapingTask.created_at.asc()).all()
                
                matching_task = None
                for task in recent_tasks:
                    # タスクが履歴の開始時刻前後に作成されている場合
                    time_diff = abs((task.created_at - history.started_at).total_seconds())
                    if time_diff <= 60:  # 1分以内に作成されたタスク
                        matching_task = task
                        break
                
                if not matching_task:
                    logger.warning(f"Could not find matching task for schedule history {history.id} (task_id: {history.task_id})")
                    continue
                
                task_status = matching_task.status
                logger.info(f"Found matching task {matching_task.task_id} with status {task_status} for schedule history {history.id}")
                
                # タスクが完了している場合は履歴を更新
                if task_status in ["completed", "failed", "cancelled"]:
                    completion_time = get_utc_now()
                    
                    if task_status == "completed":
                        history.status = "completed"
                    elif task_status == "failed":
                        history.status = "error"
                        if not history.error_message:
                            history.error_message = "スクレイピングタスクが失敗しました"
                    elif task_status == "cancelled":
                        history.status = "cancelled"
                    
                    history.completed_at = completion_time
                    
                    logger.info(f"Updated schedule history {history.id} from running to {history.status}")
                    
            except Exception as e:
                logger.error(f"Error updating schedule history {history.id}: {str(e)}")
        
        # 変更をコミット
        db.commit()
        
    except Exception as e:
        logger.error(f"Error in _update_running_schedule_histories: {str(e)}")
        db.rollback()


@router.post("/schedules")
async def create_schedule(
    request: ScheduleCreateRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """新しいスケジュールを作成"""
    from ..utils.datetime_utils import get_utc_now
    
    # バリデーション
    if request.schedule_type == 'interval' and not request.interval_minutes:
        raise HTTPException(status_code=400, detail="間隔モードでは実行間隔が必要です")
    if request.schedule_type == 'daily' and (request.daily_hour is None or request.daily_minute is None):
        raise HTTPException(status_code=400, detail="日次モードでは実行時刻が必要です")
    
    # 名前が未入力の場合は自動生成
    if not request.name or request.name.strip() == "":
        if request.schedule_type == 'interval':
            interval_text = f"{request.interval_minutes}分間隔" if request.interval_minutes else "間隔"
            request.name = f"{', '.join(request.scrapers)} - {interval_text}"
        else:  # daily
            hour_str = str(request.daily_hour or 0).zfill(2)
            minute_str = str(request.daily_minute or 0).zfill(2)
            request.name = f"{', '.join(request.scrapers)} - 毎日{hour_str}:{minute_str}"
    
    # 次回実行時刻を計算
    now = get_utc_now()
    if request.schedule_type == 'interval':
        next_run_at = now + timedelta(minutes=request.interval_minutes)
    else:  # daily
        # 今日の指定時刻を計算
        today = now.date()
        target_time = now.replace(hour=request.daily_hour, minute=request.daily_minute, second=0, microsecond=0)
        if target_time <= now:
            # 今日の時刻を過ぎている場合は明日
            target_time += timedelta(days=1)
        next_run_at = target_time
    
    # エリア名をエリアコードに変換（厳密モードで検証）
    try:
        converted_areas = convert_areas_to_codes(request.areas, strict=True) if request.areas else []
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    schedule = ScrapingSchedule(
        name=request.name,
        description=request.description,
        scrapers=request.scrapers,
        areas=converted_areas,
        schedule_type=request.schedule_type,
        interval_minutes=request.interval_minutes,
        daily_hour=request.daily_hour,
        daily_minute=request.daily_minute,
        max_properties=request.max_properties,
        is_active=request.is_active,
        next_run_at=next_run_at,
        created_by="admin",  # TODO: 実際のユーザー名を取得
        created_at=now,
        updated_at=now
    )
    
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    
    # スケジューラーに追加
    try:
        from ..scheduler import get_scheduler_service
        scheduler_service = get_scheduler_service()
        if schedule.is_active:
            scheduler_service.add_schedule(schedule)
    except Exception as e:
        # スケジューラーのエラーは警告として記録（スケジュール作成自体は成功）
        import logging
        logging.getLogger(__name__).warning(f"スケジューラーへの追加に失敗しましたが、スケジュールは作成されました: {e}")
    
    return {
        "success": True,
        "message": "スケジュールを作成しました",
        "schedule_id": schedule.id
    }


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """スケジュール詳細を取得"""
    schedule = db.query(ScrapingSchedule).filter(ScrapingSchedule.id == schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    # 実行履歴を取得
    history = db.query(ScrapingScheduleHistory).filter(
        ScrapingScheduleHistory.schedule_id == schedule_id
    ).order_by(ScrapingScheduleHistory.started_at.desc()).limit(20).all()
    
    return {
        'id': schedule.id,
        'name': schedule.name,
        'description': schedule.description,
        'scrapers': schedule.scrapers,
        'areas': schedule.areas,
        'schedule_type': schedule.schedule_type,
        'interval_minutes': schedule.interval_minutes,
        'daily_hour': schedule.daily_hour,
        'daily_minute': schedule.daily_minute,
        'is_active': schedule.is_active,
        'last_run_at': schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        'next_run_at': schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        'last_task_id': schedule.last_task_id,
        'created_by': schedule.created_by,
        'created_at': schedule.created_at.isoformat(),
        'updated_at': schedule.updated_at.isoformat(),
        'history': [
            {
                'id': h.id,
                'task_id': h.task_id,
                'started_at': h.started_at.isoformat(),
                'completed_at': h.completed_at.isoformat() if h.completed_at else None,
                'status': h.status,
                'error_message': h.error_message,
            }
            for h in history
        ]
    }


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    request: ScheduleUpdateRequest,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """スケジュールを更新"""
    from ..utils.datetime_utils import get_utc_now
    
    schedule = db.query(ScrapingSchedule).filter(ScrapingSchedule.id == schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    # 更新可能なフィールドを更新
    if request.name is not None:
        schedule.name = request.name
    if request.description is not None:
        schedule.description = request.description
    if request.scrapers is not None:
        schedule.scrapers = request.scrapers
    if request.areas is not None:
        try:
            schedule.areas = convert_areas_to_codes(request.areas, strict=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if request.schedule_type is not None:
        schedule.schedule_type = request.schedule_type
    if request.interval_minutes is not None:
        schedule.interval_minutes = request.interval_minutes
    if request.daily_hour is not None:
        schedule.daily_hour = request.daily_hour
    if request.daily_minute is not None:
        schedule.daily_minute = request.daily_minute
    if request.max_properties is not None:
        schedule.max_properties = request.max_properties
    if request.is_active is not None:
        schedule.is_active = request.is_active
    
    # スケジュール設定が変更された場合は次回実行時刻を再計算
    if (request.schedule_type is not None or 
        request.interval_minutes is not None or 
        request.daily_hour is not None or 
        request.daily_minute is not None):
        
        now = get_utc_now()
        if schedule.schedule_type == 'interval':
            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
        else:  # daily
            target_time = now.replace(hour=schedule.daily_hour, minute=schedule.daily_minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            schedule.next_run_at = target_time
    
    schedule.updated_at = get_utc_now()
    
    db.commit()
    db.refresh(schedule)
    
    # スケジューラーを更新
    try:
        from ..scheduler import get_scheduler_service
        scheduler_service = get_scheduler_service()
        scheduler_service.update_schedule(schedule)
    except Exception as e:
        # スケジューラーのエラーは警告として記録（スケジュール作成自体は成功）
        import logging
        logging.getLogger(__name__).warning(f"スケジューラーへの追加に失敗しましたが、スケジュールは作成されました: {e}")
    
    return {
        "success": True,
        "message": "スケジュールを更新しました",
        "schedule": {
            "id": schedule.id,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            "updated_at": schedule.updated_at.isoformat()
        }
    }


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """スケジュールを削除"""
    schedule = db.query(ScrapingSchedule).filter(ScrapingSchedule.id == schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    # 実行履歴も削除
    db.query(ScrapingScheduleHistory).filter(
        ScrapingScheduleHistory.schedule_id == schedule_id
    ).delete()
    
    # スケジューラーから削除
    try:
        from ..scheduler import get_scheduler_service
        scheduler_service = get_scheduler_service()
        scheduler_service.remove_schedule(schedule_id)
    except Exception as e:
        # スケジューラーのエラーは警告として記録
        import logging
        logging.getLogger(__name__).warning(f"スケジューラーからの削除に失敗しました: {e}")
    
    db.delete(schedule)
    db.commit()
    
    return {
        "success": True,
        "message": "スケジュールを削除しました"
    }


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """スケジュールを即座に実行"""
    schedule = db.query(ScrapingSchedule).filter(ScrapingSchedule.id == schedule_id).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="スケジュールが見つかりません")
    
    # バックグラウンドタスクでスクレイピングを実行
    background_tasks.add_task(execute_scheduled_scraping, schedule_id, db)
    
    return {
        "success": True,
        "message": "スケジュールされたスクレイピングを開始しました"
    }


async def execute_scheduled_scraping(schedule_id: int, db: Session):
    """スケジュールされたスクレイピングを実行"""
    from ..utils.datetime_utils import get_utc_now
    from ..database import SessionLocal
    import logging
    import uuid
    
    logger = logging.getLogger(__name__)
    
    try:
        schedule = db.query(ScrapingSchedule).filter(ScrapingSchedule.id == schedule_id).first()
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return
        
        # 実行履歴を記録
        now = get_utc_now()
        history = ScrapingScheduleHistory(
            schedule_id=schedule_id,
            started_at=now,
            status="running"
        )
        db.add(history)
        db.commit()
        db.refresh(history)
        
        # 実行中のスクレイパーをチェック（重複防止）
        from ..models_scraping_task import ScrapingTask
        
        running_tasks = db.query(ScrapingTask).filter(
            ScrapingTask.status.in_(['pending', 'running'])
        ).all()
        
        # 実行中のスクレイパーを抽出
        running_scrapers = set()
        for task in running_tasks:
            if task.scrapers:
                running_scrapers.update(task.scrapers)
        
        # 重複チェック
        conflict_scrapers = set(schedule.scrapers) & running_scrapers
        if conflict_scrapers:
            error_msg = f"以下のスクレイパーが既に実行中です: {', '.join(conflict_scrapers)}"
            logger.warning(f"Schedule {schedule_id} skipped: {error_msg}")
            
            # 履歴にエラーを記録
            history.completed_at = get_utc_now()
            history.status = "skipped"
            history.error_message = error_msg
            db.commit()
            return
        
        # 実際のスクレイピングタスクを作成
        task_id = str(uuid.uuid4())
        
        # 実際のスクレイピングタスクを作成（共通関数を使用）
        task_id = str(uuid.uuid4())
        
        try:
            # 共通関数を使用してタスクを作成（エリアコード検証も含む）
            from ..api.admin.scraping import create_scraping_task
            
            # スケジュールのエリア情報をエリアコードに変換
            area_codes = convert_areas_to_codes(schedule.areas, strict=True) if schedule.areas else []
            
            db_task = create_scraping_task(
                task_id=task_id,
                scrapers=schedule.scrapers,
                area_codes=area_codes,
                max_properties=schedule.max_properties,
                force_detail_fetch=False,
                db=db
            )
                
        except ValueError as e:
            error_msg = f"スケジュールのエリア設定に問題があります: {str(e)}"
            logger.error(f"Schedule {schedule_id} failed: {error_msg}")
            
            # 履歴にエラーを記録
            history.completed_at = get_utc_now()
            history.status = "error"
            history.error_message = error_msg
            db.commit()
            return
        
        # 履歴にタスクIDを記録
        history.task_id = int(task_id.replace('-', '')[:8], 16)  # UUIDから数値IDを生成
        
        # 並列スクレイピングを開始
        
        # スクレイピングを実行
        
        def run_scraping():
            try:
                from .admin.scraping import execute_scraping_strategy, TaskHooks
                
                logger.info(f"Starting scheduled scraping for schedule {schedule_id}, task {task_id}")
                
                # フックシステムを作成
                hooks = TaskHooks()
                
                # スケジュール履歴更新フックを登録
                def update_schedule_history(task_id: str, final_status: str):
                    """スクレイピング完了時にスケジュール履歴を更新"""
                    try:
                        with SessionLocal() as session:
                            logger.info(f"Hook: Updating schedule history for task {task_id} with status {final_status}")
                            
                            # スケジュール履歴を検索
                            hist = session.query(ScrapingScheduleHistory).filter(
                                ScrapingScheduleHistory.id == history.id
                            ).first()
                            
                            if not hist:
                                logger.warning(f"Hook: History with id {history.id} not found, searching by schedule_id")
                                hist = session.query(ScrapingScheduleHistory).filter(
                                    ScrapingScheduleHistory.schedule_id == schedule_id,
                                    ScrapingScheduleHistory.status == "running"
                                ).order_by(ScrapingScheduleHistory.started_at.desc()).first()
                            
                            if hist:
                                completion_time = get_utc_now()
                                
                                # タスクの最終状態に基づいてスケジュール履歴のステータスを決定
                                if final_status == "completed":
                                    hist.status = "completed"
                                    logger.info(f"Hook: Setting schedule history {hist.id} to completed")
                                elif final_status == "cancelled":
                                    hist.status = "cancelled"
                                    logger.info(f"Hook: Setting schedule history {hist.id} to cancelled")
                                elif final_status == "failed":
                                    hist.status = "error"
                                    if not hist.error_message:
                                        hist.error_message = "スクレイピングタスクが失敗しました"
                                    logger.info(f"Hook: Setting schedule history {hist.id} to error")
                                elif final_status == "paused":
                                    # 一時停止の場合はrunningのまま
                                    logger.info(f"Hook: Task paused, keeping schedule history {hist.id} as running")
                                    return
                                else:
                                    # その他の状態の場合はcompletedにする
                                    hist.status = "completed"
                                    logger.warning(f"Hook: Unexpected status {final_status}, setting history to completed")
                                
                                hist.completed_at = completion_time
                                session.commit()
                                logger.info(f"Hook: Successfully updated schedule history {hist.id} to {hist.status}")
                                
                                # スケジュール自体のlast_run_atも更新
                                schedule_obj = session.query(ScrapingSchedule).filter(
                                    ScrapingSchedule.id == schedule_id
                                ).first()
                                if schedule_obj:
                                    if not schedule_obj.last_run_at or schedule_obj.last_run_at < hist.started_at:
                                        schedule_obj.last_run_at = hist.started_at
                                        session.commit()
                                        logger.info(f"Hook: Updated schedule {schedule_id} last_run_at")
                            else:
                                logger.error(f"Hook: Could not find schedule history for schedule {schedule_id}")
                                
                    except Exception as e:
                        logger.error(f"Hook: Error updating schedule history: {str(e)}", exc_info=True)
                
                # フック登録
                hooks.on_completion(update_schedule_history)
                
                execute_scraping_strategy(
                    task_id=task_id,
                    scrapers=schedule.scrapers,
                    area_codes=area_codes,
                    max_properties=schedule.max_properties,
                    is_parallel=True,
                    detail_refetch_hours=2160,  # 90日
                    force_detail_fetch=False,
                    ignore_error_history=False,
                    hooks=hooks  # フックを渡す
                )
                
                logger.info(f"Scheduled scraping completed for schedule {schedule_id}, task {task_id}")
                        
            except Exception as e:
                logger.error(f"Error in scheduled scraping thread: {str(e)}", exc_info=True)
                # エラー処理はフックシステムで自動的に処理される
        
        # スクレイピングを直接実行（スレッド問題を回避）
        try:
            run_scraping()
        except Exception as e:
            logger.error(f"Error in run_scraping: {str(e)}", exc_info=True)
        
        # スケジュールの次回実行時刻を更新
        schedule.last_run_at = now
        if schedule.schedule_type == 'interval':
            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
        else:  # daily
            # 明日の同じ時刻に設定
            tomorrow = now + timedelta(days=1)
            schedule.next_run_at = tomorrow.replace(hour=schedule.daily_hour, minute=schedule.daily_minute, second=0, microsecond=0)
        schedule.last_task_id = int(task_id.replace('-', '')[:8], 16)
        db.commit()
        
        logger.info(f"Schedule {schedule_id} started with task {task_id}")
        
    except Exception as e:
        logger.error(f"Error executing schedule {schedule_id}: {str(e)}")
        
        # エラーを履歴に記録
        if 'history' in locals():
            history.completed_at = get_utc_now()
            history.status = "error"
            history.error_message = str(e)
            db.commit()


@router.get("/schedules/due")
async def get_due_schedules(
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """実行予定のスケジュールを取得（スケジューラー用）"""
    from ..utils.datetime_utils import get_utc_now
    
    now = get_utc_now()
    due_schedules = db.query(ScrapingSchedule).filter(
        and_(
            ScrapingSchedule.is_active == True,
            ScrapingSchedule.next_run_at <= now
        )
    ).all()
    
    return {
        "schedules": [
            {
                'id': s.id,
                'name': s.name,
                'scrapers': s.scrapers,
                'areas': s.areas,
                'next_run_at': s.next_run_at.isoformat() if s.next_run_at else None,
            }
            for s in due_schedules
        ]
    }