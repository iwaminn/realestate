#!/usr/bin/env python3
"""
スクレイピングスケジューラー
全てのスクレイパーを定期的に実行
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import argparse
from datetime import datetime
from typing import List, Optional, Dict, Any
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


def run_all_scrapers(area: str = "minato", max_properties: int = 100, force_detail_fetch: bool = False):
    """全てのスクレイパーを実行（タスクを作成してから実行）"""
    # エリアコードに変換
    from backend.app.scrapers.area_config import get_area_code
    area_code = get_area_code(area)
    
    # タスクを作成または取得
    task_id = create_or_get_task(
        scrapers=['suumo', 'rehouse', 'homes', 'nomu', 'livable'],
        areas=[area_code],
        max_properties=max_properties,
        force_detail_fetch=force_detail_fetch
    )
    
    if not task_id:
        logger.error("Failed to create task. Aborting execution.")
        return {}
    
    logger.info(f"Starting scraping job for area: {area} (code: {area_code}) with task_id: {task_id}")
    if force_detail_fetch:
        logger.info("Force detail fetch mode is enabled")
    
    scrapers = [
        ('SUUMO', SuumoScraper(force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)),
        ('REHOUSE', RehouseScraper(force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)),
        ('HOMES', HomesScraper(force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)),
        ('NOMU', NomuScraper(force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)),
        ('LIVABLE', LivableScraper(force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)),
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


            # 進捗更新コールバックを設定
            def progress_callback(stats):
                update_task_progress(task_id, name, area_code, stats)

            scraper.set_progress_callback(progress_callback)

            # エリアコードを渡す（各スクレイパーは内部で変換を行う）
            # max_propertiesは既に__init__で設定されている
            scraper.scrape_area(area)
            results['success'] += 1
            logger.info(f"{name} scraper completed successfully")

            # 進捗ステータスを完了に更新
            update_task_progress_status(task_id, name, area_code, 'completed')
        except Exception as e:
            logger.error(f"{name} scraper failed: {e}")
            results['failed'] += 1
            results['errors'].append(f"{name}: {str(e)}")

            # エラー時も進捗ステータスを更新
            update_task_progress_status(task_id, name, area_code, 'error')
        finally:
            # スクレイパーのリソースをクリーンアップ（Playwrightブラウザ等）
            if hasattr(scraper, 'cleanup'):
                try:
                    scraper.cleanup()
                except Exception as cleanup_error:
                    logger.warning(f"{name} scraper cleanup failed: {cleanup_error}")
    
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
    
    # スクレイピング完了後に価格改定履歴キューを自動処理
    if final_status == 'completed':
        logger.info("スクレイピング完了。価格改定履歴キューの処理を開始します...")
        process_price_change_queue()
        
        # サーバーサイドキャッシュをクリア
        from backend.app.utils.cache import clear_recent_updates_cache
        clear_recent_updates_cache()
        logger.info("サーバーサイドキャッシュをクリアしました")
    
    return results


def run_single_scraper(scraper_name: str, area: str = "minato", max_properties: int = 100, force_detail_fetch: bool = False):
    """単一のスクレイパーを実行（タスクを作成してから実行）"""
    # エリアコードに変換
    from backend.app.scrapers.area_config import get_area_code
    area_code = get_area_code(area)
    
    # タスクを作成または取得
    task_id = create_or_get_task(
        scrapers=[scraper_name],
        areas=[area_code],
        max_properties=max_properties,
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
    
    scraper = None
    try:
        logger.info(f"Running {scraper_name} scraper for area: {area} (code: {area_code}) with task_id: {task_id}")
        if force_detail_fetch:
            logger.info("Force detail fetch mode is enabled")
        scraper = scrapers[scraper_name.lower()](force_detail_fetch=force_detail_fetch, max_properties=max_properties, task_id=task_id)


        # 進捗更新コールバックを設定
        def progress_callback(stats):
            update_task_progress(task_id, scraper_name, area_code, stats)

        scraper.set_progress_callback(progress_callback)

        # タスクがキャンセルされているか確認
        if check_task_cancelled(task_id):
            logger.warning(f"Task {task_id} has been cancelled. Aborting execution.")
            update_task_status(task_id, 'cancelled', completed_at=datetime.now())
            return

        if hasattr(scraper, 'run'):
            scraper.run(area)
        else:
            # max_propertiesは既に__init__で設定されている
            scraper.scrape_area(area)

        logger.info(f"{scraper_name} scraper completed successfully")

        # 進捗ステータスを完了に更新
        update_task_progress_status(task_id, scraper_name, area_code, 'completed')

        # タスクのステータスを更新
        update_task_status(task_id, 'completed', completed_at=datetime.now())

        # スクレイピング完了後に価格改定履歴キューを自動処理
        logger.info("スクレイピング完了。価格改定履歴キューの処理を開始します...")
        process_price_change_queue()

        # サーバーサイドキャッシュをクリア
        from backend.app.utils.cache import clear_recent_updates_cache
        clear_recent_updates_cache()
        logger.info("サーバーサイドキャッシュをクリアしました")

    except Exception as e:
        logger.error(f"{scraper_name} scraper failed: {e}", exc_info=True)
        update_task_status(task_id, 'error', completed_at=datetime.now(), total_errors=1)
    finally:
        # スクレイパーのリソースをクリーンアップ（Playwrightブラウザ等）
        if scraper and hasattr(scraper, 'cleanup'):
            try:
                scraper.cleanup()
            except Exception as cleanup_error:
                logger.warning(f"{scraper_name} scraper cleanup failed: {cleanup_error}")


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


def update_task_progress(task_id: str, scraper_name: str, area_code: str, stats: Dict[str, Any]):
    """タスクの進捗情報を更新"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        
        session = SessionLocal()
        try:
            task = session.query(ScrapingTask).filter(
                ScrapingTask.task_id == task_id
            ).first()
            
            if task:
                # タスク全体がキャンセルされている場合は更新しない
                if task.status == 'cancelled' or task.is_cancelled:
                    logger.info(f"Skipping progress update for cancelled task: {task_id}")
                    return
                
                # progress_detailがNoneの場合は初期化
                if task.progress_detail is None:
                    task.progress_detail = {}
                
                # スクレイパー名とエリアコードをキーとして進捗を保存
                progress_key = f"{scraper_name.lower()}_{area_code}"
                
                # 既にキャンセルされている個別タスクは更新しない
                if progress_key in task.progress_detail:
                    current_status = task.progress_detail[progress_key].get('status')
                    if current_status == 'cancelled':
                        logger.info(f"Skipping progress update for cancelled subtask: {progress_key}")
                        return
                
                # 進捗情報を更新
                task.progress_detail[progress_key] = {
                    'scraper': scraper_name.lower(),
                    'area_code': area_code,
                    'status': 'running',
                    'properties_found': stats.get('properties_found', 0),
                    'properties_processed': stats.get('properties_processed', 0),
                    'properties_attempted': stats.get('properties_attempted', 0),
                    'properties_scraped': stats.get('properties_attempted', 0),  # 互換性のため
                    'new_listings': stats.get('new_listings', 0),
                    'price_updated': stats.get('price_updated', 0),
                    'other_updates': stats.get('other_updates', 0),
                    'refetched_unchanged': stats.get('refetched_unchanged', 0),
                    'skipped_listings': stats.get('detail_skipped', 0),
                    'detail_fetched': stats.get('detail_fetched', 0),
                    'detail_skipped': stats.get('detail_skipped', 0),
                    'errors': stats.get('errors', 0),
                    'price_missing': stats.get('price_missing', 0),
                    'building_info_missing': stats.get('building_info_missing', 0),
                    'started_at': task.progress_detail.get(progress_key, {}).get('started_at', datetime.now().isoformat())
                }
                
                # フラグを立てて強制的に更新
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(task, 'progress_detail')
                
                session.commit()
                
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to update task progress: {e}")


def update_task_progress_status(task_id: str, scraper_name: str, area_code: str, status: str):
    """タスクの進捗ステータスを更新"""
    try:
        from backend.app.database import SessionLocal
        from backend.app.models_scraping_task import ScrapingTask
        
        session = SessionLocal()
        try:
            task = session.query(ScrapingTask).filter(
                ScrapingTask.task_id == task_id
            ).first()
            
            if task:
                # タスク全体がキャンセルされている場合は更新しない
                if task.status == 'cancelled' or task.is_cancelled:
                    logger.info(f"Skipping progress update for cancelled task: {task_id}")
                    return
                
                if task.progress_detail:
                    progress_key = f"{scraper_name.lower()}_{area_code}"
                    if progress_key in task.progress_detail:
                        # 個別タスクがキャンセルされている場合も上書きしない
                        current_status = task.progress_detail[progress_key].get('status')
                        if current_status == 'cancelled':
                            logger.info(f"Skipping status update for cancelled subtask: {progress_key}")
                            return
                        
                        task.progress_detail[progress_key]['status'] = status
                        task.progress_detail[progress_key]['completed_at'] = datetime.now().isoformat()
                        
                        # フラグを立てて強制的に更新
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, 'progress_detail')
                        
                        session.commit()
                
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Failed to update task progress status: {e}")


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


def process_price_change_queue(limit: int = 1000):
    """
    価格改定履歴キューを処理
    
    Args:
        limit: 一度に処理する最大件数（デフォルト: 1000）
    """
    try:
        from backend.app.database import SessionLocal
        from backend.app.utils.price_change_calculator import PriceChangeCalculator
        
        session = SessionLocal()
        try:
            calculator = PriceChangeCalculator(session)
            
            # キューに入っている物件を処理
            logger.info(f"価格改定履歴キューの処理を開始（最大{limit}件）...")
            stats = calculator.process_queue(limit)
            
            logger.info(
                f"価格改定履歴キューの処理完了: "
                f"処理={stats['processed']}件, "
                f"失敗={stats['failed']}件, "
                f"変更={stats['changes_found']}件"
            )
            
            # サーバーサイドキャッシュをクリア
            from backend.app.utils.cache import clear_recent_updates_cache
            clear_recent_updates_cache()
            logger.info("価格改定履歴キュー処理完了後: サーバーサイドキャッシュをクリアしました")
            
            return stats
            
        finally:
            session.close()
    except Exception as e:
        logger.error(f"価格改定履歴キューの処理に失敗: {e}", exc_info=True)
        return {'processed': 0, 'failed': 0, 'changes_found': 0}



def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='不動産スクレイピングツール')
    parser.add_argument('--scraper', type=str, help='実行するスクレイパー (suumo, athome, homes, rehouse, nomu, livable, all)')
    parser.add_argument('--area', type=str, default='minato', help='検索エリア（デフォルト: minato）')
    parser.add_argument('--max-properties', type=int, default=100, help='取得する最大物件数（デフォルト: 100）')
    parser.add_argument('--pages', type=int, help='取得するページ数（--max-propertiesを使用してください、非推奨）', dest='pages_deprecated')
    parser.add_argument('--schedule', action='store_true', help='スケジュール実行モード（非推奨）')
    parser.add_argument('--interval', type=int, default=6, help='スケジュール実行間隔（時間）（デフォルト: 6）')
    parser.add_argument('--force-detail-fetch', action='store_true', help='強制的にすべての物件の詳細を取得')
    
    args = parser.parse_args()
    
    if args.schedule:
        # スケジュール実行モードは非推奨
        logger.error("スケジュール実行モードは非推奨です。管理画面からスクレイピングを実行してください。")
        return
    else:
        # 単発実行モード
        # --pagesが指定された場合は警告を表示
        if args.pages_deprecated is not None:
            logger.warning("--pagesオプションは非推奨です。--max-propertiesを使用してください。")
            max_props = args.pages_deprecated * 30  # ページ数から物件数の概算
        else:
            max_props = args.max_properties
            
        if args.scraper and args.scraper.lower() != 'all':
            run_single_scraper(args.scraper, args.area, max_props, args.force_detail_fetch)
        else:
            run_all_scrapers(args.area, max_props, args.force_detail_fetch)


if __name__ == "__main__":
    main()