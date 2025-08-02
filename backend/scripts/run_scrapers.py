#!/usr/bin/env python3
"""
スクレイピングスケジューラー
全てのスクレイパーを定期的に実行
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import schedule
import time
import logging
import argparse
from datetime import datetime
from typing import List, Optional
from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.nomu_scraper import NomuScraper
from backend.app.scrapers.livable_scraper import LivableScraper

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def run_all_scrapers(area: str = "minato", max_pages: int = 3, force_detail_fetch: bool = False):
    """全てのスクレイパーを実行（タスクを作成してから実行）"""
    # タスクを作成または取得
    task_id = create_or_get_task(
        scrapers=['suumo', 'rehouse', 'homes', 'nomu', 'livable'],
        areas=[area],
        max_properties=100,
        force_detail_fetch=force_detail_fetch
    )
    
    if not task_id:
        logger.error("Failed to create task. Aborting execution.")
        return {}
    
    logger.info(f"Starting scraping job for area: {area} with task_id: {task_id}")
    if force_detail_fetch:
        logger.info("Force detail fetch mode is enabled")
    
    scrapers = [
        ('SUUMO', SuumoScraper(force_detail_fetch=force_detail_fetch)),
        ('REHOUSE', RehouseScraper(force_detail_fetch=force_detail_fetch)),
        ('HOMES', HomesScraper(force_detail_fetch=force_detail_fetch)),
        ('NOMU', NomuScraper(force_detail_fetch=force_detail_fetch)),
        ('LIVABLE', LivableScraper(force_detail_fetch=force_detail_fetch)),
    ]
    
    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    for name, scraper in scrapers:
        # タスクがキャンセルされているか確認
        if check_task_cancelled(task_id):
            logger.warning(f"Task {task_id} has been cancelled. Stopping execution.")
            update_task_status(task_id, 'cancelled', completed_at=datetime.now())
            break
            
        try:
            logger.info(f"Running {name} scraper...")
            # スクレイパーにタスクIDを設定（キャンセルチェック用）
            scraper._task_id = task_id
            scraper.scrape_area(area, max_pages)
            results['success'] += 1
            logger.info(f"{name} scraper completed successfully")
        except Exception as e:
            logger.error(f"{name} scraper failed: {e}")
            results['failed'] += 1
            results['errors'].append(f"{name}: {str(e)}")
    
    logger.info(f"Scraping job completed. Success: {results['success']}, Failed: {results['failed']}")
    
    if results['errors']:
        logger.error(f"Errors: {', '.join(results['errors'])}")
    
    # タスクステータスを更新
    final_status = 'completed' if results['failed'] == 0 else 'error'
    update_task_status(
        task_id, 
        final_status, 
        completed_at=datetime.now(),
        total_processed=results['success'] + results['failed'],
        total_errors=results['failed']
    )
    
    return results


def run_single_scraper(scraper_name: str, area: str = "minato", max_pages: int = 3, force_detail_fetch: bool = False):
    """単一のスクレイパーを実行（タスクを作成してから実行）"""
    # タスクを作成または取得
    task_id = create_or_get_task(
        scrapers=[scraper_name],
        areas=[area],
        max_properties=100,
        force_detail_fetch=force_detail_fetch
    )
    
    if not task_id:
        logger.error("Failed to create task. Aborting execution.")
        return
    scrapers = {
        'suumo': SuumoScraper,
        'rehouse': RehouseScraper,
        'homes': HomesScraper,
        'nomu': NomuScraper,
        'livable': LivableScraper,
    }
    
    if scraper_name.lower() not in scrapers:
        logger.error(f"Unknown scraper: {scraper_name}")
        return
    
    try:
        logger.info(f"Running {scraper_name} scraper for area: {area} with task_id: {task_id}")
        if force_detail_fetch:
            logger.info("Force detail fetch mode is enabled")
        scraper = scrapers[scraper_name.lower()](force_detail_fetch=force_detail_fetch)
        
        # スクレイパーにタスクIDを設定
        scraper._task_id = task_id
        
        # タスクがキャンセルされているか確認
        if check_task_cancelled(task_id):
            logger.warning(f"Task {task_id} has been cancelled. Aborting execution.")
            update_task_status(task_id, 'cancelled', completed_at=datetime.now())
            return
            
        if hasattr(scraper, 'run'):
            scraper.run(area, max_pages)
        else:
            scraper.scrape_area(area, max_pages)
            
        logger.info(f"{scraper_name} scraper completed successfully")
        update_task_status(task_id, 'completed', completed_at=datetime.now())
    except Exception as e:
        logger.error(f"{scraper_name} scraper failed: {e}", exc_info=True)
        update_task_status(task_id, 'error', completed_at=datetime.now(), total_errors=1)


def create_or_get_task(scrapers: List[str], areas: List[str], max_properties: int = 100, 
                      force_detail_fetch: bool = False) -> Optional[str]:
    """タスクを作成（既存のタスクがある場合は新しいタスクを作成）"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        import uuid
        
        session = SessionLocal()
        try:
            # 常に新しいタスクを作成（コマンドラインからの実行も管理画面に表示するため）
            task_id = f"cmd_{uuid.uuid4().hex[:8]}"
            new_task = ScrapingTask(
                task_id=task_id,
                status='running',
                scrapers=scrapers,
                areas=areas,
                max_properties=max_properties,
                force_detail_fetch=force_detail_fetch,
                started_at=datetime.now()
            )
            session.add(new_task)
            session.commit()
            
            logger.info(f"Created new task: {task_id}")
            return task_id
            
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        # タスク作成に失敗した場合、スクレイピングを実行しない
        return None


def update_task_status(task_id: str, status: str, **kwargs):
    """タスクのステータスを更新"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        
        session = SessionLocal()
        try:
            task = session.query(ScrapingTask).filter(
                ScrapingTask.task_id == task_id
            ).first()
            
            if task:
                task.status = status
                for key, value in kwargs.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                session.commit()
                
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to update task status: {e}")


def check_task_cancelled(task_id: str) -> bool:
    """タスクがキャンセルされているか確認"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        
        session = SessionLocal()
        try:
            task = session.query(ScrapingTask).filter(
                ScrapingTask.task_id == task_id
            ).first()
            
            return task and task.status == 'cancelled'
            
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to check task status: {e}")
        return False


def check_task_existence() -> bool:
    """データベースに実行中のタスクが存在するか確認"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        
        session = SessionLocal()
        try:
            # 実行中またはポーズ中のタスクが存在するか確認
            active_task = session.query(ScrapingTask).filter(
                ScrapingTask.status.in_(['running', 'paused'])
            ).first()
            
            if active_task:
                logger.debug(f"Active task found: {active_task.task_id}")
                return True
            else:
                logger.warning("No active tasks found in database")
                return False
                
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to check task existence: {e}")
        # エラーの場合は安全のためFalseを返す
        return False


def scheduled_job():
    """スケジュールされたジョブ"""
    logger.info("=" * 50)
    logger.info(f"Scheduled job started at {datetime.now()}")
    
    # デフォルト設定でスクレイピングを実行
    # （run_all_scrapers内でタスクが作成される）
    result = run_all_scrapers()
    
    # エラーが多い場合は継続しない
    if result and result.get('failed', 0) == 5 and result.get('success', 0) == 0:
        logger.error("All scrapers failed. Stopping scheduled execution.")
        return False
    
    logger.info(f"Scheduled job completed at {datetime.now()}")
    logger.info("=" * 50)
    return True  # 継続を示す


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='不動産スクレイピングツール')
    parser.add_argument('--scraper', type=str, help='実行するスクレイパー (suumo, athome, homes, rehouse, nomu, livable, all)')
    parser.add_argument('--area', type=str, default='minato', help='検索エリア（デフォルト: minato）')
    parser.add_argument('--pages', type=int, default=3, help='取得するページ数（デフォルト: 3）')
    parser.add_argument('--schedule', action='store_true', help='スケジュール実行モード')
    parser.add_argument('--interval', type=int, default=6, help='スケジュール実行間隔（時間）（デフォルト: 6）')
    parser.add_argument('--force-detail-fetch', action='store_true', help='強制的にすべての物件の詳細を取得')
    
    args = parser.parse_args()
    
    if args.schedule:
        # スケジュール実行モード
        logger.info(f"Starting scheduled mode. Running every {args.interval} hours")
        
        # 初回実行
        if not scheduled_job():
            logger.info("Exiting due to no active tasks in database.")
            return
        
        # スケジュール設定
        schedule.every(args.interval).hours.do(scheduled_job)
        
        # スケジュール実行
        should_continue = True
        last_check_time = time.time()
        check_interval = 30  # 30秒ごとにタスクの存在を確認
        
        while should_continue:
            schedule.run_pending()
            
            # 定期的にタスクの存在を確認
            current_time = time.time()
            if current_time - last_check_time >= check_interval:
                if not check_task_existence():
                    logger.warning("No active tasks found in database. Exiting scheduled mode.")
                    should_continue = False
                    break
                last_check_time = current_time
            
            time.sleep(10)  # 10秒ごとにチェック
        
        logger.info("Scheduled execution stopped.")
    else:
        # 単発実行モード
        if args.scraper and args.scraper.lower() != 'all':
            run_single_scraper(args.scraper, args.area, args.pages, args.force_detail_fetch)
        else:
            run_all_scrapers(args.area, args.pages, args.force_detail_fetch)


if __name__ == "__main__":
    main()