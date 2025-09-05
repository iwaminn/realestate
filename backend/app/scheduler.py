"""
スケジューラーサービス - APSchedulerを使用した自動スケジュール実行
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import ScrapingSchedule
# 循環インポートを避けるため、実行時にインポート
import pytz

logger = logging.getLogger(__name__)

class SchedulerService:
    """スケジューラーサービス - より安定した状態管理"""
    
    def __init__(self):
        # 日本時間のタイムゾーンを設定
        self.jst = pytz.timezone('Asia/Tokyo')
        
        # APSchedulerをバックグラウンドモードで初期化
        self.scheduler = BackgroundScheduler(
            timezone=self.jst,
            job_defaults={
                'coalesce': True,  # 同じジョブが複数回実行されないようにする
                'max_instances': 1,  # 各ジョブの最大同時実行数
                'misfire_grace_time': 300  # 実行時刻を過ぎた場合の猶予時間（秒）
            }
        )
        
        # スケジューラーの開始状態（より確実な状態管理）
        self.is_running = False
        self._initialization_complete = False
        
    def start(self):
        """スケジューラーを開始"""
        try:
            # 既にスケジューラーが動作中かチェック
            if hasattr(self.scheduler, 'state') and self.scheduler.state == 1:  # STATE_RUNNING = 1
                logger.info("スケジューラーは既に動作中です")
                self.is_running = True
                if not self._initialization_complete:
                    self._load_existing_schedules()
                    self._initialization_complete = True
                return
            
            # スケジューラーを開始
            self.scheduler.start()
            self.is_running = True
            
            # 既存のスケジュールを読み込んで登録
            self._load_existing_schedules()
            self._initialization_complete = True
            
            logger.info(f"スケジューラーが開始されました (状態: {self.scheduler.state})")
            
        except Exception as e:
            logger.error(f"スケジューラーの開始に失敗しました: {e}")
            self.is_running = False
            self._initialization_complete = False
            raise
    
    def stop(self):
        """スケジューラーを停止"""
        try:
            if hasattr(self.scheduler, 'state') and self.scheduler.state != 0:  # STATE_STOPPED = 0
                self.scheduler.shutdown(wait=False)
            self.is_running = False
            self._initialization_complete = False
            logger.info("スケジューラーが停止されました")
        except Exception as e:
            logger.error(f"スケジューラーの停止に失敗しました: {e}")
    
    def is_scheduler_running(self):
        """スケジューラーの実際の動作状態をチェック"""
        try:
            if not hasattr(self.scheduler, 'state'):
                return False
            is_actually_running = self.scheduler.state == 1  # STATE_RUNNING = 1
            
            # 内部状態と実際の状態を同期
            if self.is_running != is_actually_running:
                logger.warning(f"スケジューラー状態の不一致を検出: 内部={self.is_running}, 実際={is_actually_running}")
                self.is_running = is_actually_running
            
            return is_actually_running
        except Exception as e:
            logger.error(f"スケジューラー状態確認エラー: {e}")
            return False
    
    def _load_existing_schedules(self):
        """データベースから既存のアクティブなスケジュールを読み込み"""
        try:
            with SessionLocal() as db:
                schedules = db.query(ScrapingSchedule).filter(
                    ScrapingSchedule.is_active == True
                ).all()
                
                registered_count = 0
                for schedule in schedules:
                    try:
                        self._add_schedule_to_scheduler(schedule)
                        registered_count += 1
                    except Exception as e:
                        logger.error(f"スケジュール {schedule.id} の登録に失敗: {e}")
                        
                logger.info(f"{registered_count}/{len(schedules)}個のアクティブなスケジュールを登録しました")
                
                # 登録されたジョブの詳細をログ出力
                jobs = self.scheduler.get_jobs()
                for job in jobs:
                    logger.info(f"登録ジョブ: {job.id} - 次回実行: {job.next_run_time}")
                    
        except Exception as e:
            logger.error(f"既存スケジュールの読み込みに失敗しました: {e}")
    
    def add_schedule(self, schedule: ScrapingSchedule):
        """新しいスケジュールをスケジューラーに追加"""
        if not self.is_scheduler_running():
            logger.warning("スケジューラーが開始されていません")
            return
            
        if not schedule.is_active:
            logger.info(f"スケジュール {schedule.id} は非アクティブのため追加しません")
            return
            
        self._add_schedule_to_scheduler(schedule)
    
    def _add_schedule_to_scheduler(self, schedule: ScrapingSchedule):
        """スケジュールをAPSchedulerに登録"""
        job_id = f"schedule_{schedule.id}"
        
        # 既存のジョブがあれば削除
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        try:
            if schedule.schedule_type == 'interval':
                # 間隔指定の場合
                if not schedule.interval_minutes or schedule.interval_minutes <= 0:
                    logger.error(f"スケジュール {schedule.id}: 無効な間隔設定 ({schedule.interval_minutes})")
                    return
                
                # 次回実行時刻が過去の場合は現在時刻から開始
                start_date = schedule.next_run_at
                if not start_date or start_date <= datetime.now():
                    start_date = datetime.now() + timedelta(seconds=10)  # 10秒後から開始
                
                trigger = IntervalTrigger(
                    minutes=schedule.interval_minutes,
                    start_date=start_date,
                    timezone=self.jst
                )
                
            elif schedule.schedule_type == 'daily':
                # 毎日指定時刻の場合
                if schedule.daily_hour is None or schedule.daily_minute is None:
                    logger.error(f"スケジュール {schedule.id}: 無効な時刻設定")
                    return
                
                trigger = CronTrigger(
                    hour=schedule.daily_hour,
                    minute=schedule.daily_minute,
                    timezone=self.jst
                )
            else:
                logger.error(f"スケジュール {schedule.id}: 不明なスケジュールタイプ ({schedule.schedule_type})")
                return
            
            # ジョブを追加
            self.scheduler.add_job(
                func=self._execute_schedule,
                trigger=trigger,
                args=[schedule.id],
                id=job_id,
                name=f"Schedule: {schedule.name}",
                replace_existing=True
            )
            
            logger.info(f"スケジュール {schedule.id} ({schedule.name}) をスケジューラーに追加しました")
            
        except Exception as e:
            logger.error(f"スケジュール {schedule.id} の追加に失敗しました: {e}")
    
    def remove_schedule(self, schedule_id: int):
        """スケジュールをスケジューラーから削除"""
        if not self.is_scheduler_running():
            return
            
        job_id = f"schedule_{schedule_id}"
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"スケジュール {schedule_id} をスケジューラーから削除しました")
        except Exception as e:
            logger.error(f"スケジュール {schedule_id} の削除に失敗しました: {e}")
    
    def update_schedule(self, schedule: ScrapingSchedule):
        """既存のスケジュールを更新"""
        # いったん削除してから再追加
        self.remove_schedule(schedule.id)
        
        if schedule.is_active:
            self.add_schedule(schedule)
        else:
            logger.info(f"スケジュール {schedule.id} は非アクティブになったため削除しました")
    
    def _execute_schedule(self, schedule_id: int):
        """スケジュールを実行"""
        logger.info(f"スケジュール {schedule_id} の実行を開始します")
        
        try:
            with SessionLocal() as db:
                # 非同期関数を同期的に実行
                import asyncio
                try:
                    # 既存のイベントループがある場合は新しいスレッドで実行
                    loop = asyncio.get_running_loop()
                    import threading
                    
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            # 実行時にインポートして循環インポートを回避
                            from .api.admin_schedules import execute_scheduled_scraping
                            new_loop.run_until_complete(execute_scheduled_scraping(schedule_id, db))
                        finally:
                            new_loop.close()
                    
                    thread = threading.Thread(target=run_in_thread)
                    thread.start()
                    thread.join()
                    
                except RuntimeError:
                    # イベントループが存在しない場合は直接実行
                    from .api.admin_schedules import execute_scheduled_scraping
                    asyncio.run(execute_scheduled_scraping(schedule_id, db))
                
        except Exception as e:
            logger.error(f"スケジュール {schedule_id} の実行中にエラーが発生しました: {e}")
    
    def get_jobs(self):
        """現在登録されているジョブの一覧を取得"""
        if not self.is_scheduler_running():
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger)
            })
        return jobs
    
    def get_scheduler_status(self):
        """スケジューラーの詳細な状態を取得"""
        try:
            actual_running = self.is_scheduler_running()
            jobs = self.get_jobs()
            
            return {
                'is_running': actual_running,
                'internal_state': self.is_running,
                'scheduler_state': getattr(self.scheduler, 'state', 'unknown'),
                'initialization_complete': self._initialization_complete,
                'job_count': len(jobs),
                'jobs': jobs
            }
        except Exception as e:
            logger.error(f"スケジューラー状態取得エラー: {e}")
            return {
                'is_running': False,
                'error': str(e)
            }

# グローバルスケジューラーインスタンス
scheduler_service: Optional[SchedulerService] = None

def get_scheduler_service() -> SchedulerService:
    """スケジューラーサービスのインスタンスを取得（シングルトンパターン）"""
    global scheduler_service
    if scheduler_service is None:
        scheduler_service = SchedulerService()
        logger.info("新しいスケジューラーサービスインスタンスを作成しました")
    return scheduler_service

def start_scheduler():
    """スケジューラーを開始"""
    try:
        service = get_scheduler_service()
        logger.info(f"スケジューラー開始前の状態: {service.get_scheduler_status()}")
        service.start()
        logger.info(f"スケジューラー開始後の状態: {service.get_scheduler_status()}")
        return True
    except Exception as e:
        logger.error(f"スケジューラー開始処理でエラーが発生: {e}", exc_info=True)
        return False

def stop_scheduler():
    """スケジューラーを停止"""
    try:
        service = get_scheduler_service()
        logger.info(f"スケジューラー停止前の状態: {service.get_scheduler_status()}")
        service.stop()
        logger.info(f"スケジューラー停止後の状態: {service.get_scheduler_status()}")
        return True
    except Exception as e:
        logger.error(f"スケジューラー停止処理でエラーが発生: {e}", exc_info=True)
        return False

def diagnose_scheduler():
    """スケジューラーの詳細診断を実行"""
    try:
        service = get_scheduler_service()
        status = service.get_scheduler_status()
        
        logger.info("=== スケジューラー診断結果 ===")
        logger.info(f"実際の動作状態: {status.get('is_running', 'unknown')}")
        logger.info(f"内部状態: {status.get('internal_state', 'unknown')}")
        logger.info(f"APScheduler状態: {status.get('scheduler_state', 'unknown')}")
        logger.info(f"初期化完了: {status.get('initialization_complete', 'unknown')}")
        logger.info(f"登録ジョブ数: {status.get('job_count', 0)}")
        
        jobs = status.get('jobs', [])
        if jobs:
            logger.info("登録済みジョブ:")
            for job in jobs:
                logger.info(f"  - {job['id']}: {job['name']} (次回: {job['next_run_time']})")
        else:
            logger.info("登録済みジョブなし")
        
        # データベースのスケジュール確認
        with SessionLocal() as db:
            active_schedules = db.query(ScrapingSchedule).filter(
                ScrapingSchedule.is_active == True
            ).all()
            logger.info(f"データベース内アクティブスケジュール数: {len(active_schedules)}")
            
            for schedule in active_schedules:
                logger.info(f"  - スケジュール {schedule.id}: {schedule.name} ({schedule.schedule_type})")
        
        return status
        
    except Exception as e:
        logger.error(f"スケジューラー診断でエラーが発生: {e}", exc_info=True)
        return {'error': str(e)}
