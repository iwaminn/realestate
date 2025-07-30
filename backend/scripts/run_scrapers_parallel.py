#!/usr/bin/env python3
"""
並列スクレイピング実行スクリプト（データベース版）
異なるサイトを並列で実行し、同一サイトは直列で実行
タスク情報はデータベースで管理
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import json
from threading import Lock

from backend.app.database import SessionLocal, engine
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
from backend.app.config.scraping_config import (
    PROCESS_CHECK_PAUSE_THRESHOLD_MINUTES,
    PROCESS_CHECK_RESUME_THRESHOLD_MINUTES
)
from sqlalchemy.orm import Session
from sqlalchemy import and_

# データディレクトリ
DATA_DIR = '/app/data'

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
        logging.FileHandler('scraper_parallel_db.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 東京23区のエリアリスト
TOKYO_23_AREAS = [
    '千代田区', '中央区', '港区', '新宿区', '文京区', '台東区',
    '墨田区', '江東区', '品川区', '目黒区', '大田区', '世田谷区',
    '渋谷区', '中野区', '杉並区', '豊島区', '北区', '荒川区',
    '板橋区', '練馬区', '足立区', '葛飾区', '江戸川区'
]


class ParallelScrapingManagerDB:
    """並列スクレイピング管理クラス（データベース版）"""
    
    def __init__(self):
        self.scrapers = {
            'suumo': ('SUUMO', SuumoScraper),
            'homes': ('LIFULL HOME\'S', HomesScraper),
            'rehouse': ('三井のリハウス', RehouseScraper),
            'nomu': ('ノムコム', NomuScraper),
            'livable': ('東急リバブル', LivableScraper),
        }
        self.log_lock = Lock()  # ログ追加用のロック
        
    def create_task(self, task_id: str, areas: List[str], scrapers: List[str], 
                   max_properties: int = 100, force_detail_fetch: bool = False) -> ScrapingTask:
        """新しいタスクを作成"""
        db = SessionLocal()
        try:
            # タスクを作成
            task = ScrapingTask(
                task_id=task_id,
                status='running',
                scrapers=scrapers,
                areas=areas,
                max_properties=max_properties,
                force_detail_fetch=force_detail_fetch,
                created_at=datetime.now(),
                started_at=datetime.now(),
                logs=[]  # ログを初期化
            )
            db.add(task)
            
            # 各スクレイパー・エリアの進捗レコードを作成
            for scraper_key in scrapers:
                scraper_name = self.scrapers[scraper_key][0]
                for area in areas:
                    progress = ScrapingTaskProgress(
                        task_id=task_id,
                        scraper=scraper_key,
                        area=area,
                        status='pending'
                    )
                    db.add(progress)
            
            db.commit()
            db.refresh(task)
            
            logger.info(f"タスク作成: {task_id}")
            return task
            
        except Exception as e:
            db.rollback()
            logger.error(f"タスク作成エラー: {e}")
            raise
        finally:
            db.close()
    
    def update_progress(self, task_id: str, scraper_key: str, area: str, data: Dict[str, Any]):
        """進捗を更新"""
        db = SessionLocal()
        try:
            # 進捗レコードを取得
            progress = db.query(ScrapingTaskProgress).filter(
                and_(
                    ScrapingTaskProgress.task_id == task_id,
                    ScrapingTaskProgress.scraper == scraper_key,
                    ScrapingTaskProgress.area == area
                )
            ).first()
            
            if progress:
                # 進捗データを更新
                for key, value in data.items():
                    if hasattr(progress, key):
                        setattr(progress, key, value)
                progress.last_updated = datetime.now()
                
                # タスクの統計情報も更新
                task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if task:
                    # 全進捗の合計を計算
                    all_progress = db.query(ScrapingTaskProgress).filter(
                        ScrapingTaskProgress.task_id == task_id
                    ).all()
                    
                    task.total_processed = sum(p.processed for p in all_progress)
                    task.total_new = sum(p.new_listings for p in all_progress)
                    task.total_updated = sum(p.updated_listings for p in all_progress)
                    task.total_errors = sum(p.errors for p in all_progress)
                    task.properties_found = sum(p.properties_found for p in all_progress)
                    task.detail_fetched = sum(p.detail_fetched for p in all_progress)
                    task.detail_skipped = sum(p.detail_skipped for p in all_progress)
                    task.price_missing = sum(p.price_missing for p in all_progress)
                    task.building_info_missing = sum(p.building_info_missing for p in all_progress)
                
                db.commit()
                logger.debug(f"進捗更新: {task_id}/{scraper_key}/{area}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"進捗更新エラー: {e}")
        finally:
            db.close()
    
    def add_error(self, task_id: str, scraper_key: str, area: str, error: str):
        """エラーを追加"""
        with self.log_lock:  # ロックで排他制御（logs用と同じロックを使用）
            db = SessionLocal()
            try:
                # 最新のデータを取得するため、refresh
                task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if task:
                    # 現在のデータベースから最新のエラーログを取得
                    db.refresh(task)
                    error_logs = list(task.error_logs or [])  # 新しいリストを作成
                    error_logs.append({
                        'scraper': scraper_key,
                        'area': area,
                        'error': error,
                        'timestamp': datetime.now().isoformat()
                    })
                    # 最新50件のみ保持
                    if len(error_logs) > 50:
                        error_logs = error_logs[-50:]
                    # SQLAlchemyがJSONの変更を検知できるように、新しいリストを代入
                    task.error_logs = error_logs
                    # flag_modifiedで明示的に変更を通知
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "error_logs")
                    db.commit()
                    logger.info(f"エラーログを追加しました: {task_id} - 合計{len(error_logs)}件")
                    
            except Exception as e:
                db.rollback()
                logger.error(f"エラー追加失敗: {e}")
            finally:
                db.close()
    
    def add_log(self, task_id: str, log_entry: Dict[str, Any]):
        """ログを追加（新規登録・更新など）"""
        with self.log_lock:  # ロックで排他制御
            db = SessionLocal()
            try:
                # 最新のデータを取得するため、refresh
                task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if task:
                    # 現在のデータベースから最新のログを取得
                    db.refresh(task)
                    logs = list(task.logs or [])  # 新しいリストを作成
                    logs.append(log_entry)
                    # 最新50件のみ保持
                    if len(logs) > 50:
                        logs = logs[-50:]
                    # SQLAlchemyがJSONの変更を検知できるように、新しいリストを代入
                    task.logs = logs
                    # flag_modifiedで明示的に変更を通知
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "logs")
                    db.commit()
                    logger.info(f"ログを追加しました: {task_id} - 合計{len(logs)}件")
                    
            except Exception as e:
                db.rollback()
                logger.error(f"ログ追加失敗: {e}")
            finally:
                db.close()
    
    def add_error_log(self, task_id: str, error_entry: Dict[str, Any]):
        """エラーログを追加"""
        with self.log_lock:  # ロックで排他制御
            db = SessionLocal()
            try:
                # 最新のデータを取得するため、refresh
                task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if task:
                    # 現在のデータベースから最新のエラーログを取得
                    db.refresh(task)
                    error_logs = list(task.error_logs or [])  # 新しいリストを作成
                    error_logs.append(error_entry)
                    # 最新50件のみ保持
                    if len(error_logs) > 50:
                        error_logs = error_logs[-50:]
                    # SQLAlchemyがJSONの変更を検知できるように、新しいリストを代入
                    task.error_logs = error_logs
                    # flag_modifiedで明示的に変更を通知
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "error_logs")
                    db.commit()
                    logger.info(f"エラーログを追加しました: {task_id} - 合計{len(error_logs)}件")
                    
            except Exception as e:
                db.rollback()
                logger.error(f"エラーログ追加失敗: {e}")
            finally:
                db.close()
    
    def check_pause_cancel(self, task_id: str) -> Tuple[bool, bool]:
        """一時停止・キャンセル状態をチェック"""
        db = SessionLocal()
        try:
            task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task:
                return task.is_paused, task.is_cancelled
            return False, False
        finally:
            db.close()
    
    def scrape_areas_serial(self, task_id: str, scraper_key: str, areas: List[str], 
                           max_properties: int, force_detail_fetch: bool) -> Tuple[int, int]:
        """単一スクレイパーで複数エリアを直列実行"""
        scraper_name, scraper_class = self.scrapers[scraper_key]
        total_processed = 0
        total_errors = 0
        
        logger.info(f"[{scraper_name}] スクレイピング開始 - {len(areas)}エリア")
        
        for area in areas:
            # エリア名をエリアコードに変換
            from backend.app.scrapers.area_config import get_area_code
            area_code = get_area_code(area)
            logger.info(f"[{scraper_name}] エリア変換: {area} -> {area_code}")
            
            # 一時停止・キャンセルチェック
            is_paused, is_cancelled = self.check_pause_cancel(task_id)
            
            if is_cancelled:
                logger.info(f"[{scraper_name}] キャンセルされました")
                break
            
            # 一時停止チェック
            while is_paused:
                logger.info(f"[{scraper_name}] 一時停止中...")
                time.sleep(1)
                is_paused, is_cancelled = self.check_pause_cancel(task_id)
                if is_cancelled:
                    break
            
            try:
                # 進捗を「実行中」に更新
                self.update_progress(task_id, scraper_key, area, {
                    'status': 'running',
                    'started_at': datetime.now()
                })
                
                # スレッドローカルなセッションを作成
                session = SessionLocal()
                session.autoflush = False
                
                try:
                    # スクレイパーのインスタンスを作成
                    scraper = scraper_class(
                        force_detail_fetch=force_detail_fetch,
                        max_properties=max_properties
                    )
                    # スクレイパーが作成したセッションを閉じて、新しいセッションを設定
                    if hasattr(scraper, 'session') and scraper.session:
                        try:
                            scraper.session.close()
                        except:
                            pass
                    scraper.session = session
                    
                    # majority_updaterも新しいセッションで再初期化
                    if hasattr(scraper, 'majority_updater'):
                        from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
                        scraper.majority_updater = MajorityVoteUpdater(session)
                    
                    # 進捗更新コールバックを設定（DB版）
                    def progress_callback(stats):
                        # logger.debug(f"[{scraper_name}] {area} - リアルタイム進捗: {stats}")  # 頻繁すぎるのでコメントアウト
                        update_data = {
                            'processed': stats.get('processed', 0),
                            'new_listings': stats.get('new', 0),
                            'updated_listings': stats.get('updated', 0),
                            'errors': stats.get('errors', 0),
                            'properties_found': stats.get('properties_found', 0),
                            'properties_attempted': stats.get('properties_attempted', 0),
                            'detail_fetched': stats.get('detail_fetched', 0),
                            'detail_skipped': stats.get('detail_skipped', 0),
                            'price_missing': stats.get('price_missing', 0),
                            'building_info_missing': stats.get('building_info_missing', 0)
                        }
                        self.update_progress(task_id, scraper_key, area, update_data)
                    
                    scraper.set_progress_callback(progress_callback)
                    
                    # DB版の一時停止・キャンセルチェック関数
                    def check_pause():
                        is_paused, _ = self.check_pause_cancel(task_id)
                        return is_paused
                    
                    def check_cancel():
                        _, is_cancelled = self.check_pause_cancel(task_id)
                        return is_cancelled
                    
                    # カスタムフラグオブジェクトを作成
                    class DBFlag:
                        def __init__(self, check_func):
                            self.check_func = check_func
                        
                        def is_set(self):
                            return self.check_func()
                    
                    scraper.pause_flag = DBFlag(check_pause)
                    scraper.cancel_flag = DBFlag(check_cancel)
                    
                    # スクレイパーにマネージャーとタスクIDを設定（エラーログ記録用）
                    scraper.scraping_manager = self
                    scraper.task_id = task_id
                    
                    # ログキャプチャ用のハンドラーを設定
                    import logging
                    import re
                    log_handler = None
                    if hasattr(scraper, 'logger'):
                        class LogCapture(logging.Handler):
                            def __init__(self, task_id, scraper_key, area, manager):
                                super().__init__()
                                self.task_id = task_id
                                self.scraper_key = scraper_key
                                self.area = area
                                self.manager = manager
                                
                            def emit(self, record):
                                msg = record.getMessage()
                                # デバッグログ
                                if '登録' in msg or '更新' in msg:
                                    logger.debug(f"LogCapture: ログメッセージを受信: {msg}")
                                # 新規登録・更新のログをキャプチャ
                                if '新規登録:' in msg or '価格更新:' in msg or 'その他更新:' in msg:
                                    logger.info(f"LogCapture: マッチしたログ: {msg}")
                                    log_type = 'new' if '新規登録:' in msg else 'update'
                                    # URLと価格を抽出
                                    url_match = re.search(r'https?://[^\s]+', msg)
                                    price_match = re.search(r'(\d+)万円', msg)
                                    
                                    log_entry = {
                                        'timestamp': datetime.now().isoformat(),
                                        'scraper': self.scraper_key,
                                        'area': self.area,
                                        'type': log_type,
                                        'message': msg,
                                        'url': url_match.group(0) if url_match else None,
                                        'price': int(price_match.group(1)) if price_match else None
                                    }
                                    self.manager.add_log(self.task_id, log_entry)
                        
                        log_handler = LogCapture(task_id, scraper_key, area, self)
                        scraper.logger.addHandler(log_handler)
                        logger.info(f"LogCaptureハンドラーを追加しました: {scraper_key}/{area}")
                    
                    logger.info(f"[{scraper_name}] {area} - スクレイピング開始")
                    start_time = time.time()
                    
                    # スクレイピング実行
                    try:
                        result = scraper.scrape_area(area_code)
                        
                        # 各エリア完了後にコミット
                        try:
                            session.commit()
                        except Exception as e:
                            logger.error(f"[{scraper_name}] {area} - コミットエラー: {e}")
                            session.rollback()
                    except Exception as e:
                        logger.error(f"[{scraper_name}] {area} - スクレイピングエラー: {e}")
                        session.rollback()
                        
                        # エラー統計を更新
                        self.update_progress(task_id, scraper_key, area, {
                            'status': 'error',
                            'errors': 100,
                            'completed_at': datetime.now()
                        })
                        total_errors += 100
                        continue
                    
                    elapsed_time = time.time() - start_time
                    
                    if result:
                        processed = result.get('total', 0)
                        new = result.get('new', 0)
                        updated = result.get('updated', 0)
                        
                        logger.info(f"[{scraper_name}] {area} - 完了: {processed}件処理 "
                                  f"(新規: {new}, 更新: {updated}) - {elapsed_time:.1f}秒")
                        
                        # 詳細な統計情報を含めて更新
                        progress_update = {
                            'status': 'completed',
                            'processed': processed,
                            'new_listings': new,
                            'updated_listings': updated,
                            'completed_at': datetime.now(),
                            # 詳細統計情報
                            'properties_found': result.get('properties_found', 0),
                            'properties_attempted': result.get('properties_attempted', processed),
                            'detail_fetched': result.get('detail_fetched', 0),
                            'detail_skipped': result.get('skipped', 0),
                            'detail_fetch_failed': result.get('detail_fetch_failed', 0),
                            'price_updated': result.get('price_updated', 0),
                            'other_updates': result.get('other_updates', 0),
                            'refetched_unchanged': result.get('refetched_unchanged', 0),
                            'save_failed': result.get('save_failed', 0),
                            'price_missing': result.get('price_missing', 0),
                            'building_info_missing': result.get('building_info_missing', 0)
                        }
                        
                        self.update_progress(task_id, scraper_key, area, progress_update)
                        
                        total_processed += processed
                    else:
                        logger.warning(f"[{scraper_name}] {area} - 処理結果なし")
                        self.update_progress(task_id, scraper_key, area, {
                            'status': 'completed',
                            'processed': 0,
                            'completed_at': datetime.now()
                        })
                
                finally:
                    # ログハンドラーを削除（メモリリークを防ぐ）
                    if log_handler and hasattr(scraper, 'logger'):
                        scraper.logger.removeHandler(log_handler)
                    
                    # トランザクションが残っている場合はロールバック
                    try:
                        if session.in_transaction():
                            session.rollback()
                    except:
                        pass
                    session.close()
                
                # エリア間の待機
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"[{scraper_name}] {area} - エラー: {e}")
                self.add_error(task_id, scraper_key, area, str(e))
                self.update_progress(task_id, scraper_key, area, {
                    'status': 'error',
                    'errors': 1,
                    'completed_at': datetime.now()
                })
                total_errors += 1
        
        logger.info(f"[{scraper_name}] 完了 - 処理: {total_processed}件, エラー: {total_errors}件")
        return total_processed, total_errors
    
    def run_parallel(self, task_id: str, areas: List[str], scrapers: List[str], 
                    max_properties: int = 100, force_detail_fetch: bool = False):
        """並列スクレイピングを実行"""
        # タスクを作成
        task = self.create_task(task_id, areas, scrapers, max_properties, force_detail_fetch)
        
        logger.info(f"並列スクレイピング開始 - タスクID: {task_id}")
        logger.info(f"対象サイト: {len(scrapers)}サイト, 対象エリア: {len(areas)}エリア")
        logger.info(f"最大取得数: {max_properties}件/エリア")
        if force_detail_fetch:
            logger.info("強制詳細取得モード: 有効")
        
        start_time = time.time()
        
        try:
            # ThreadPoolExecutorで並列実行
            with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
                # 各スクレイパーに対してワーカーを起動
                futures = {}
                for scraper_key in scrapers:
                    future = executor.submit(
                        self.scrape_areas_serial,
                        task_id, scraper_key, areas, max_properties, force_detail_fetch
                    )
                    futures[future] = scraper_key
                
                # 完了を待機
                total_processed = 0
                total_errors = 0
                failed_scrapers = []
                
                for future in as_completed(futures):
                    scraper_key = futures[future]
                    try:
                        processed, errors = future.result(timeout=300)  # 5分のタイムアウト
                        total_processed += processed
                        total_errors += errors
                    except Exception as e:
                        logger.error(f"スクレイパー {scraper_key} で予期しないエラー: {e}")
                        total_errors += 1
                        failed_scrapers.append(scraper_key)
                        
                        # エラーが発生したスクレイパーの進捗を更新
                        for area in areas:
                            self.update_progress(task_id, scraper_key, area, {
                                'status': 'error',
                                'errors': 100,
                                'completed_at': datetime.now()
                            })
                        
                        # エラーを記録
                        self.add_error(task_id, scraper_key, 'all', f"スクレイパープロセスが異常終了: {str(e)}")
        
        except Exception as e:
            logger.error(f"並列実行中に予期しないエラー: {e}")
        
        finally:
            elapsed_time = time.time() - start_time
            
            # タスクを完了に更新（エラーがある場合はerrorステータスに）
            db = SessionLocal()
            try:
                task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if task:
                    # エラーが多い場合はタスク全体をエラーとする
                    if total_errors > 0 and failed_scrapers:
                        task.status = 'error'
                        logger.error(f"タスクエラー: {task_id} - 失敗したスクレイパー: {failed_scrapers}")
                    else:
                        task.status = 'completed'
                        logger.info(f"タスク完了: {task_id}")
                    
                    task.completed_at = datetime.now()
                    task.elapsed_time = elapsed_time
                    db.commit()
            finally:
                db.close()
            
            logger.info(f"並列スクレイピング完了 - タスクID: {task_id}")
            logger.info(f"総処理数: {total_processed}件, 総エラー数: {total_errors}件")
            logger.info(f"実行時間: {elapsed_time:.1f}秒 ({elapsed_time/60:.1f}分)")
            
            return {
                'task_id': task_id,
                'total_processed': total_processed,
                'total_errors': total_errors,
                'elapsed_time': elapsed_time
            }
    
    def pause_task(self, task_id: str):
        """タスクを一時停止"""
        db = SessionLocal()
        try:
            task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task and task.status == 'running':
                # 最新の進捗を確認してタスクが実際に動いているかチェック
                from datetime import timedelta
                now = datetime.now()
                threshold = now - timedelta(minutes=PROCESS_CHECK_PAUSE_THRESHOLD_MINUTES)  # 設定値（デフォルト5分）以内に更新があるかチェック
                
                latest_progress = db.query(ScrapingTaskProgress).filter(
                    ScrapingTaskProgress.task_id == task_id
                ).order_by(
                    ScrapingTaskProgress.last_updated.desc()
                ).first()
                
                if latest_progress and latest_progress.last_updated < threshold:
                    # 5分以上更新がない場合は既に停止している可能性が高い
                    logger.warning(f"タスク {task_id} は既に停止している可能性があります（最終更新: {latest_progress.last_updated}）")
                    
                    # エラーステータスに変更
                    task.status = 'error'
                    task.completed_at = now
                    error_logs = task.error_logs or []
                    error_logs.append({
                        'error': 'Task appears to be stalled when pause was requested',
                        'timestamp': now.isoformat(),
                        'details': f'Last update was {(now - latest_progress.last_updated).total_seconds() / 60:.1f} minutes ago'
                    })
                    task.error_logs = error_logs
                    
                    # 進捗ステータスも更新（completed, cancelled以外をerrorに）
                    db.query(ScrapingTaskProgress).filter(
                        ScrapingTaskProgress.task_id == task_id,
                        ScrapingTaskProgress.status.in_(['running', 'pending', 'paused'])
                    ).update({
                        'status': 'error',
                        'completed_at': now
                    })
                    
                    db.commit()
                    logger.error(f"タスク {task_id} を停止済みとして検出、エラーステータスに変更しました")
                    raise ValueError("タスクは既に停止しています")
                
                # 通常の一時停止処理
                task.is_paused = True
                task.pause_requested_at = datetime.now()
                task.status = 'paused'
                db.commit()
                logger.info(f"タスク一時停止: {task_id}")
                return True
            return False
        finally:
            db.close()
    
    def resume_task(self, task_id: str):
        """タスクを再開"""
        db = SessionLocal()
        try:
            task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task and task.status == 'paused':
                # 最新の進捗を確認してタスクが実際に再開可能かチェック
                from datetime import timedelta
                now = datetime.now()
                threshold = now - timedelta(minutes=PROCESS_CHECK_RESUME_THRESHOLD_MINUTES)  # 設定値（デフォルト10分）以内に更新があるかチェック
                
                latest_progress = db.query(ScrapingTaskProgress).filter(
                    ScrapingTaskProgress.task_id == task_id
                ).order_by(
                    ScrapingTaskProgress.last_updated.desc()
                ).first()
                
                if latest_progress and latest_progress.last_updated < threshold:
                    # 10分以上更新がない場合はプロセスが終了している
                    logger.warning(f"タスク {task_id} のプロセスは既に終了しています（最終更新: {latest_progress.last_updated}）")
                    
                    # エラーステータスに変更
                    task.status = 'error'
                    task.completed_at = now
                    error_logs = task.error_logs or []
                    error_logs.append({
                        'error': 'Task process not found when resume was requested',
                        'timestamp': now.isoformat(),
                        'details': f'Last update was {(now - latest_progress.last_updated).total_seconds() / 60:.1f} minutes ago'
                    })
                    task.error_logs = error_logs
                    
                    # 進捗ステータスも更新（completed, cancelled以外をerrorに）
                    db.query(ScrapingTaskProgress).filter(
                        ScrapingTaskProgress.task_id == task_id,
                        ScrapingTaskProgress.status.in_(['running', 'pending', 'paused'])
                    ).update({
                        'status': 'error',
                        'completed_at': now
                    })
                    
                    db.commit()
                    logger.error(f"タスク {task_id} のプロセスが見つかりません、エラーステータスに変更しました")
                    raise ValueError("タスクのプロセスが終了しているため再開できません")
                
                # 通常の再開処理
                task.is_paused = False
                task.pause_requested_at = None
                task.status = 'running'
                db.commit()
                logger.info(f"タスク再開: {task_id}")
                return True
            return False
        finally:
            db.close()
    
    def cancel_task(self, task_id: str):
        """タスクをキャンセル"""
        db = SessionLocal()
        try:
            task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if task and task.status in ['running', 'paused']:
                # pausedタスクの場合、実際にプロセスが生きているかチェック
                if task.status == 'paused':
                    from datetime import timedelta
                    now = datetime.now()
                    threshold = now - timedelta(minutes=PROCESS_CHECK_RESUME_THRESHOLD_MINUTES)  # 設定値（デフォルト10分）以内に更新があるかチェック
                    
                    latest_progress = db.query(ScrapingTaskProgress).filter(
                        ScrapingTaskProgress.task_id == task_id
                    ).order_by(
                        ScrapingTaskProgress.last_updated.desc()
                    ).first()
                    
                    if latest_progress and latest_progress.last_updated < threshold:
                        # 10分以上更新がない場合はプロセスが終了している
                        logger.warning(f"タスク {task_id} のプロセスは既に終了しています（最終更新: {latest_progress.last_updated}）")
                        
                        # 既に終了しているが、キャンセル要求なのでcancelledステータスにする
                        task.status = 'cancelled'
                        task.completed_at = now
                        task.is_cancelled = True
                        task.cancel_requested_at = now
                        
                        # エラーログに記録
                        error_logs = task.error_logs or []
                        error_logs.append({
                            'error': 'Task process was already terminated when cancel was requested',
                            'timestamp': now.isoformat(),
                            'details': f'Last update was {(now - latest_progress.last_updated).total_seconds() / 60:.1f} minutes ago'
                        })
                        task.error_logs = error_logs
                        
                        # 進捗もキャンセル状態に更新（completed以外をerrorに）
                        db.query(ScrapingTaskProgress).filter(
                            ScrapingTaskProgress.task_id == task_id,
                            ScrapingTaskProgress.status.in_(['running', 'pending', 'paused'])
                        ).update({
                            'status': 'error',
                            'completed_at': now
                        })
                        
                        db.commit()
                        logger.info(f"タスク {task_id} をキャンセルしました（プロセスは既に終了）")
                        return True
                
                # 通常のキャンセル処理
                task.is_cancelled = True
                task.cancel_requested_at = datetime.now()
                task.status = 'cancelled'
                db.commit()
                logger.info(f"タスクキャンセル: {task_id}")
                return True
            return False
        finally:
            db.close()


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='並列不動産スクレイピングツール（DB版）')
    parser.add_argument('--areas', nargs='+', default=TOKYO_23_AREAS, 
                       help='検索エリア（デフォルト: 東京23区）')
    parser.add_argument('--scrapers', nargs='+', 
                       default=['suumo', 'homes', 'rehouse', 'nomu', 'livable'],
                       help='実行するスクレイパー')
    parser.add_argument('--max-properties', type=int, default=100,
                       help='各エリアの最大取得数（デフォルト: 100）')
    parser.add_argument('--force-detail-fetch', action='store_true',
                       help='強制的にすべての物件の詳細を取得')
    parser.add_argument('--task-id', type=str, 
                       default=f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                       help='タスクID')
    
    args = parser.parse_args()
    
    # 並列スクレイピング実行
    manager = ParallelScrapingManagerDB()
    manager.run_parallel(
        task_id=args.task_id,
        areas=args.areas,
        scrapers=args.scrapers,
        max_properties=args.max_properties,
        force_detail_fetch=args.force_detail_fetch
    )


if __name__ == "__main__":
    main()