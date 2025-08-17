"""
スクレイピング管理API
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import threading
import uuid
import os
import json
from concurrent.futures import ThreadPoolExecutor

from ...database import get_db
from ...utils.exceptions import TaskPausedException, TaskCancelledException

# 並列スクレイピングマネージャーのインスタンス管理（将来の拡張用）
parallel_managers: Dict[str, Any] = {}

router = APIRouter(tags=["admin-scraping"])

# タスクの永続化ファイル
TASKS_FILE = "/app/data/scraping_tasks.json"

# エリアコードのマッピング（地価の高い順）
AREA_CODES = {
    "千代田区": "13101",
    "港区": "13103",
    "中央区": "13102",
    "渋谷区": "13113",
    "新宿区": "13104",
    "文京区": "13105",
    "目黒区": "13110",
    "品川区": "13109",
    "世田谷区": "13112",
    "豊島区": "13116",
    "中野区": "13114",
    "杉並区": "13115",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108"
}

# グローバルロック（スレッドセーフな操作のため）
tasks_lock = threading.Lock()
instances_lock = threading.Lock()
flags_lock = threading.Lock()

# スクレイピングタスクの状態を管理
scraping_tasks: Dict[str, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=3)

# タスクの制御フラグを管理
task_cancel_flags: Dict[str, threading.Event] = {}
task_pause_flags: Dict[str, threading.Event] = {}

# 一時停止のタイムスタンプを管理
task_pause_timestamps: Dict[str, datetime] = {}

# 一時停止のタイムアウト時間（秒）
PAUSE_TIMEOUT_SECONDS = int(os.environ.get('SCRAPING_PAUSE_TIMEOUT', '1800'))

# スクレイパーインスタンスを保持（再開時に再利用）
scraper_instances: Dict[str, Any] = {}


class ScrapingRequest(BaseModel):
    """スクレイピングリクエスト"""
    scrapers: List[str]  # ["suumo", "homes", "rehouse", "nomu", "livable"]
    area_codes: List[str] = ["13103"]  # デフォルト: 港区
    max_properties: int = 100  # 各スクレイパー・各エリアで取得する最大件数
    detail_refetch_hours: Optional[int] = None  # 詳細ページ再取得期間（時間単位）
    force_detail_fetch: bool = False  # 強制詳細取得モード
    ignore_error_history: bool = False  # エラー履歴を無視


class ParallelScrapingRequest(BaseModel):
    """並列スクレイピングリクエスト"""
    scrapers: List[str]
    area_codes: List[str] = ["13103"]
    max_properties: int = 100
    force_detail_fetch: bool = False
    detail_refetch_hours: int = 2160
    ignore_error_history: bool = False


class ScrapingTaskStatus(BaseModel):
    """スクレイピングタスクの状態"""
    task_id: str
    type: Optional[str] = "serial"  # "serial" or "parallel"
    status: str  # "pending", "running", "paused", "completed", "failed", "cancelled"
    scrapers: List[str]
    area_codes: List[str]
    max_properties: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Dict[str, Dict[str, Any]]  # 各スクレイパー・エリアの進行状況
    errors: List[str] = []
    logs: Optional[List[Dict[str, Any]]] = []  # 物件更新履歴
    error_logs: Optional[List[Dict[str, Any]]] = []  # エラーログ
    warning_logs: Optional[List[Dict[str, Any]]] = []  # 警告ログ


def load_tasks_from_file():
    """永続化ファイルからタスクを読み込む"""
    global scraping_tasks
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r') as f:
                data = json.load(f)
                # datetime文字列を復元
                for task_id, task in data.items():
                    if task.get('started_at'):
                        task['started_at'] = datetime.fromisoformat(task['started_at'])
                    if task.get('completed_at'):
                        task['completed_at'] = datetime.fromisoformat(task['completed_at'])
                scraping_tasks = data
                print(f"Loaded {len(scraping_tasks)} tasks from {TASKS_FILE}")
        except Exception as e:
            print(f"Error loading tasks from file: {e}")
            scraping_tasks = {}


def save_tasks_to_file():
    """タスクを永続化ファイルに保存"""
    try:
        # datetime を文字列に変換
        data = {}
        for task_id, task in scraping_tasks.items():
            task_copy = task.copy()
            if task_copy.get('started_at'):
                task_copy['started_at'] = task_copy['started_at'].isoformat()
            if task_copy.get('completed_at'):
                task_copy['completed_at'] = task_copy['completed_at'].isoformat()
            
            # ログは最新100件のみファイルに保存（ファイルサイズを抑える）
            if 'logs' in task_copy and task_copy['logs']:
                task_copy['logs'] = task_copy['logs'][-100:]
            if 'error_logs' in task_copy and task_copy['error_logs']:
                task_copy['error_logs'] = task_copy['error_logs'][-50:]
            if 'warning_logs' in task_copy and task_copy['warning_logs']:
                task_copy['warning_logs'] = task_copy['warning_logs'][-50:]
            
            data[task_id] = task_copy
        
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        with open(TASKS_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving tasks to file: {e}")


def check_pause_timeout(task_id: str) -> bool:
    """一時停止のタイムアウトをチェックし、タイムアウトした場合はタスクをキャンセル"""
    with flags_lock:
        pause_flag = task_pause_flags.get(task_id)
        if not pause_flag or not pause_flag.is_set():
            return False
        
        # タイムスタンプを確認
        pause_time = task_pause_timestamps.get(task_id)
        if not pause_time:
            return False
        
        # タイムアウトチェック
        elapsed = (datetime.now() - pause_time).total_seconds()
        if elapsed > PAUSE_TIMEOUT_SECONDS:
            print(f"[{task_id}] Pause timeout ({elapsed:.0f}s > {PAUSE_TIMEOUT_SECONDS}s), cancelling task")
            
            # タスクをキャンセル
            if task_id in task_cancel_flags:
                task_cancel_flags[task_id].set()
            
            # 一時停止フラグをクリア
            pause_flag.clear()
            del task_pause_timestamps[task_id]
            
            # タスクステータスを更新
            if task_id in scraping_tasks:
                scraping_tasks[task_id]["status"] = "cancelled"
                scraping_tasks[task_id]["errors"].append(f"Task cancelled due to pause timeout ({PAUSE_TIMEOUT_SECONDS}s)")
                save_tasks_to_file()
            
            return True
    
    return False


def setup_logging_handlers(scraper, task_id: str, scraper_name: str, area_name: str, progress_key: str):
    """
    スクレイパーにログハンドラーとコールバックを設定
    
    Args:
        scraper: スクレイパーインスタンス
        task_id: タスクID
        scraper_name: スクレイパー名
        area_name: エリア名
        progress_key: 進捗キー
    """
    import logging
    
    # TaskLogHandlerは手動ログシステムに統一したため無効化
    # （logger.warning()の代わりに_save_warning_log()を使用）
    
    # 物件保存時のログ記録（create_or_update_listingメソッドをラップ）
    if hasattr(scraper, 'create_or_update_listing') and not hasattr(scraper, '_create_or_update_overridden'):
        original_create_or_update = scraper.create_or_update_listing
        
        def create_or_update_with_logging(*args, **kwargs):
            # 引数を取得（位置引数として渡される）
            master_property = args[0] if len(args) > 0 else kwargs.get('master_property')
            url = args[1] if len(args) > 1 else kwargs.get('url')
            title = args[2] if len(args) > 2 else kwargs.get('title')
            price = args[3] if len(args) > 3 else kwargs.get('price')
            
            # 既存の掲載情報があるか確認（サイトIDから直接検索）
            from backend.app.database import SessionLocal
            from backend.app.models import PropertyListing
            
            # URLからサイト固有のIDを抽出
            import re
            site_property_id = None
            if scraper.source_site.value == "SUUMO":
                match = re.search(r'/nc_(\d+)/', url)
                site_property_id = match.group(1) if match else None
            elif scraper.source_site.value == "LIFULL HOME'S":
                match = re.search(r'/(\d+)/$', url)
                site_property_id = match.group(1) if match else None
            elif scraper.source_site.value == "三井のリハウス":
                match = re.search(r'/(\d+)\.html', url)
                site_property_id = match.group(1) if match else None
            elif scraper.source_site.value == "ノムコム":
                match = re.search(r'/bukken/([^/]+)/', url)
                site_property_id = match.group(1) if match else None
            elif scraper.source_site.value == "東急リバブル":
                match = re.search(r'/([A-Z0-9]+)/$', url)
                site_property_id = match.group(1) if match else None
            
            db = SessionLocal()
            try:
                # サイトIDで検索（サイトIDが取得できなかった場合はexistingはNoneになる）
                if site_property_id:
                    existing = db.query(PropertyListing).filter_by(
                        source_site=scraper.source_site.value,
                        site_property_id=site_property_id
                    ).first()
                else:
                    existing = None
                old_price = existing.current_price if existing else None
            finally:
                db.close()
            
            # オリジナルメソッドを呼び出し
            result = original_create_or_update(*args, **kwargs)
            
            # update_typeを取得
            update_type = result[1] if isinstance(result, tuple) and len(result) > 1 else 'unknown'
            
            # ログ用の情報
            building_info = master_property.building.normalized_name if master_property and master_property.building else ''
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "type": update_type,  # update_typeをそのまま使用
                "scraper": scraper_name,
                "area": area_name,
                "url": url,
                "title": title or building_info,
                "price": price,
                "building_info": building_info
            }
            
            # ログメッセージを作成（update_typeに基づく）
            should_log = False
            
            # デバッグ：update_typeの値を確認
            if update_type == 'price_updated':
                print(f"[DEBUG] 価格更新検出: update_type={update_type}, title={title}, price={price}, old_price={old_price}")
            
            if update_type == 'new':
                log_entry["message"] = f"新規物件登録: {title} ({price}万円)"
                should_log = True
            elif update_type == 'price_updated':
                if existing and old_price is not None:
                    log_entry["message"] = f"価格更新: {title} ({old_price}万円 → {price}万円)"
                    log_entry["price_change"] = {"old": old_price, "new": price}
                else:
                    log_entry["message"] = f"価格更新: {title} (→ {price}万円)"
                should_log = True
            elif update_type == 'other_updates':
                # update_detailsを取得（create_or_update_listingから返される第3要素）
                update_details = result[2] if isinstance(result, tuple) and len(result) > 2 else None
                log_entry["message"] = f"その他の更新: {title} ({price}万円)"
                if update_details:
                    log_entry["update_details"] = update_details
                should_log = True
            elif update_type == 'refetched_unchanged' or update_type == 'skipped':
                # 変更なしの場合、詳細をスキップした場合はログに記録しない
                pass
            
            # ログを追加（価格変更または新規物件のみ、最新500件を保持）
            if should_log:
                # デバッグ：ログ記録を確認
                print(f"[DEBUG] ログ記録: task_id={task_id}, update_type={update_type}, message={log_entry.get('message', '')}")
                with tasks_lock:
                    if "logs" not in scraping_tasks[task_id]:
                        scraping_tasks[task_id]["logs"] = []
                    scraping_tasks[task_id]["logs"].append(log_entry)
                    # 最新500件を保持（より多くの履歴を表示可能に）
                    if len(scraping_tasks[task_id]["logs"]) > 500:
                        scraping_tasks[task_id]["logs"] = scraping_tasks[task_id]["logs"][-500:]
            
            return result
        
        scraper.create_or_update_listing = create_or_update_with_logging
        scraper._create_or_update_overridden = True
    
    # エラーログ記録用のメソッドを追加（常にオーバーライド）
    if True:  # 常にオーバーライド
        def save_error_log(error_info):
            with tasks_lock:
                if "error_logs" not in scraping_tasks[task_id]:
                    scraping_tasks[task_id]["error_logs"] = []
                
                error_log = {
                    "timestamp": error_info.get('timestamp', datetime.now().isoformat()),
                    "scraper": scraper_name,
                    "area": area_name,
                    "url": error_info.get('url', ''),
                    "building_name": error_info.get('building_name', ''),
                    "price": error_info.get('price', ''),
                    "reason": error_info.get('reason', ''),
                    "message": f"保存失敗: {error_info.get('reason', '不明')} - URL: {error_info.get('url', '不明')}"
                }
                
                scraping_tasks[task_id]["error_logs"].append(error_log)
                # 最新100件を保持（エラーログも多めに保持）
                if len(scraping_tasks[task_id]["error_logs"]) > 100:
                    scraping_tasks[task_id]["error_logs"] = scraping_tasks[task_id]["error_logs"][-100:]
        
        scraper._save_error_log = save_error_log
    
    # 警告ログ記録用のメソッドを追加（常にオーバーライド）
    if True:  # 常にオーバーライド
        def save_warning_log(warning_info):
            with tasks_lock:
                if "warning_logs" not in scraping_tasks[task_id]:
                    scraping_tasks[task_id]["warning_logs"] = []
                
                warning_log = {
                    "timestamp": warning_info.get('timestamp', datetime.now().isoformat()),
                    "scraper": scraper_name,
                    "area": area_name,
                    "url": warning_info.get('url', ''),
                    "building_name": warning_info.get('building_name', ''),
                    "price": warning_info.get('price', ''),
                    "reason": warning_info.get('reason', ''),
                    "message": f"警告: {warning_info.get('reason', '不明')}"
                }
                
                scraping_tasks[task_id]["warning_logs"].append(warning_log)
                # 最新100件を保持（警告ログも多めに保持）
                if len(scraping_tasks[task_id]["warning_logs"]) > 100:
                    scraping_tasks[task_id]["warning_logs"] = scraping_tasks[task_id]["warning_logs"][-100:]
        
        scraper._save_warning_log = save_warning_log


def create_stats_update_thread(scraper, task_id: str, progress_key: str) -> Tuple[threading.Thread, threading.Event]:
    """
    スクレイパーの統計情報を定期的に更新するスレッドを作成
    
    Args:
        scraper: スクレイパーインスタンス
        task_id: タスクID
        progress_key: 進捗キー（例: "suumo_13103"）
    
    Returns:
        (stats_thread, stop_event): 統計更新スレッドと停止イベント
    """
    import threading
    import time as time_module
    
    stop_stats_update = threading.Event()
    
    def update_stats_periodically():
        while not stop_stats_update.is_set():
            try:
                # スクレイパーから最新の統計を取得
                current_stats = scraper.get_scraping_stats()
                
                # 統計が存在する場合のみ更新（0で上書きしない）
                if current_stats:
                    updates = {}
                    # ロックで保護して現在値を取得
                    with tasks_lock:
                        for key, value in {
                            "properties_found": current_stats.get('properties_found', 0),
                            "properties_processed": current_stats.get('properties_processed', 0),
                            "properties_attempted": current_stats.get('properties_attempted', 0),
                            "properties_scraped": current_stats.get('properties_processed', 0),
                            "detail_fetched": current_stats.get('detail_fetched', 0),
                            "new_listings": current_stats.get('new_listings', 0),
                            "price_updated": current_stats.get('price_updated', 0),
                            "other_updates": current_stats.get('other_updates', 0),
                            "refetched_unchanged": current_stats.get('refetched_unchanged', 0),
                            "skipped_listings": current_stats.get('detail_skipped', 0),
                            "detail_fetch_failed": current_stats.get('detail_fetch_failed', 0),
                            "save_failed": current_stats.get('save_failed', 0),
                            "price_missing": current_stats.get('price_missing', 0),
                            "building_info_missing": current_stats.get('building_info_missing', 0),
                            "other_errors": current_stats.get('other_errors', 0)
                        }.items():
                            # 現在の値を取得
                            if (task_id in scraping_tasks and 
                                progress_key in scraping_tasks[task_id]["progress"]):
                                current_value = scraping_tasks[task_id]["progress"][progress_key].get(key, 0)
                                # 新しい値が0でない、または現在値が0の場合のみ更新
                                if value != 0 or current_value == 0:
                                    updates[key] = value
                    
                    # 更新がある場合のみ適用（ロックで保護）
                    if updates:
                        with tasks_lock:
                            if (task_id in scraping_tasks and 
                                progress_key in scraping_tasks[task_id]["progress"]):
                                scraping_tasks[task_id]["progress"][progress_key].update(updates)
                                save_tasks_to_file()  # 更新後に保存
            except Exception as e:
                print(f"[{task_id}] Error updating stats: {e}")
            time_module.sleep(2)  # 2秒ごとに更新
    
    stats_thread = threading.Thread(target=update_stats_periodically)
    stats_thread.daemon = True
    
    return stats_thread, stop_stats_update


def run_single_scraper_for_areas(
    task_id: str,
    scraper_name: str,
    area_codes: List[str],
    max_properties: int,
    detail_refetch_hours: Optional[int] = None,
    force_detail_fetch: bool = False,
    ignore_error_history: bool = False
) -> Tuple[int, int]:
    """単一のスクレイパーで複数エリアを順次実行（並列実行時の各ワーカー用）"""
    from ...scrapers.suumo_scraper import SuumoScraper
    from ...scrapers.homes_scraper import HomesScraper
    from ...scrapers.rehouse_scraper import RehouseScraper
    from ...scrapers.nomu_scraper import NomuScraper
    from ...scrapers.livable_scraper import LivableScraper
    
    scraper_classes = {
        'suumo': SuumoScraper,
        'homes': HomesScraper,
        'rehouse': RehouseScraper,
        'nomu': NomuScraper,
        'livable': LivableScraper
    }
    
    if scraper_name.lower() not in scraper_classes:
        raise ValueError(f"Unknown scraper: {scraper_name}")
    
    total_processed = 0
    total_errors = 0
    
    for area_code in area_codes:
        # キャンセルチェック
        if task_cancel_flags[task_id].is_set():
            raise TaskCancelledException(f"Task {task_id} was cancelled")
        
        # 一時停止チェック
        while task_pause_flags[task_id].is_set():
            if check_pause_timeout(task_id):
                raise TaskCancelledException(f"Task {task_id} was cancelled due to pause timeout")
            print(f"[{task_id}] Task is paused, waiting...")
            import time
            time.sleep(1)
        
        # 進行状況を更新
        progress_key = f"{scraper_name}_{area_code}"
        
        # エリア名を取得（日本語）
        area_names = {code: name for name, code in AREA_CODES.items()}
        area_name = area_names.get(area_code, area_code)
        
        scraping_tasks[task_id]["progress"][progress_key] = {
            "scraper": scraper_name,
            "area_code": area_code,
            "area_name": area_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "properties_found": 0,
            "properties_saved": 0,
            "properties_attempted": 0,
            "detail_fetched": 0,
            "detail_fetch_failed": 0,
            "new_listings": 0,
            "price_updated": 0,
            "other_updates": 0,
            "skipped_listings": 0,
            "price_missing": 0,
            "building_info_missing": 0,
            "errors": 0,
            "save_failed": 0,
            "other_errors": 0
        }
        save_tasks_to_file()
        
        print(f"[{task_id}] Running {scraper_name} for area {area_code}")
        
        try:
            # スクレイパーインスタンスを作成
            scraper_class = scraper_classes[scraper_name.lower()]
            instance_key = f"{task_id}_{scraper_name}_{area_code}"
            
            with instances_lock:
                if instance_key in scraper_instances:
                    scraper = scraper_instances[instance_key]
                    print(f"[{task_id}] Reusing existing scraper instance for {scraper_name}")
                    
                    # セッションがクローズされている場合は新しいセッションを作成
                    if hasattr(scraper, 'session'):
                        from backend.app.database import SessionLocal
                        scraper.session = SessionLocal()
                    if hasattr(scraper, 'http_session') and scraper.http_session is None:
                        import requests
                        scraper.http_session = requests.Session()
                        scraper.http_session.headers.update({
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        })
                else:
                    # 環境変数を設定（詳細再取得期間）
                    import os
                    if detail_refetch_hours is not None:
                        # 時間を日数に変換（0時間の場合は0日）
                        detail_refetch_days = 0 if detail_refetch_hours == 0 else max(1, detail_refetch_hours // 24)
                        os.environ['SCRAPER_DETAIL_REFETCH_DAYS'] = str(detail_refetch_days)
                        print(f"[{task_id}] Setting SCRAPER_DETAIL_REFETCH_DAYS={detail_refetch_days} (from {detail_refetch_hours} hours)")
                    
                    # スクレイパーインスタンスを作成
                    scraper = scraper_class(
                        max_properties=max_properties,
                        force_detail_fetch=force_detail_fetch,
                        ignore_error_history=ignore_error_history
                    )
                    scraper_instances[instance_key] = scraper
                    
                    # 環境変数をクリア（他のタスクに影響しないように）
                    if detail_refetch_hours is not None:
                        if 'SCRAPER_DETAIL_REFETCH_DAYS' in os.environ:
                            del os.environ['SCRAPER_DETAIL_REFETCH_DAYS']
            
            # タスクIDを設定
            scraper._task_id = task_id
            
            # ログハンドラーとコールバックを設定
            setup_logging_handlers(scraper, task_id, scraper_name, area_name, progress_key)
            
            # 統計更新用の別スレッドを開始
            stats_thread, stop_stats_update = create_stats_update_thread(scraper, task_id, progress_key)
            stats_thread.start()
            
            # scrape_areaメソッドを呼び出す
            print(f"[{task_id}] Calling {scraper_name}.scrape_area for area_code {area_code}")
            
            if scraper_name.lower() in ['suumo', 'nomu']:
                scraper.scrape_area(area_code)
            else:
                from ...scrapers.area_config import get_area_romaji_from_code
                area_name_romaji = get_area_romaji_from_code(area_code)
                print(f"[{task_id}] Converted area_code {area_code} to area_name {area_name_romaji}")
                scraper.scrape_area(area_name_romaji)
            
            print(f"[{task_id}] {scraper_name}.scrape_area returned")
            
            # 統計更新スレッドを停止
            stop_stats_update.set()
            stats_thread.join(timeout=1)
            
            # 統計を取得
            final_stats = {}
            if hasattr(scraper, 'get_scraping_stats'):
                final_stats = scraper.get_scraping_stats()
            
            # 結果を記録
            scraping_tasks[task_id]["progress"][progress_key].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "properties_found": final_stats.get('properties_found', 0),
                "properties_saved": final_stats.get('detail_fetched', 0),
                "properties_attempted": final_stats.get('properties_attempted', 0),
                "detail_fetched": final_stats.get('detail_fetched', 0),
                "detail_fetch_failed": final_stats.get('detail_fetch_failed', 0),
                "new_listings": final_stats.get('new_listings', 0),
                "price_updated": final_stats.get('price_updated', 0),
                "other_updates": final_stats.get('other_updates', 0),
                "skipped_listings": final_stats.get('detail_skipped', 0),
                "price_missing": final_stats.get('price_missing', 0),
                "building_info_missing": final_stats.get('building_info_missing', 0),
                "errors": (
                    final_stats.get('detail_fetch_failed', 0) +
                    final_stats.get('save_failed', 0) +
                    final_stats.get('other_errors', 0)
                ),
                "save_failed": final_stats.get('save_failed', 0),
                "other_errors": final_stats.get('other_errors', 0)
            })
            
            total_processed += final_stats.get('properties_found', 0)
            
            # インスタンスをクリーンアップ
            pause_flag = task_pause_flags.get(task_id)
            if not pause_flag or not pause_flag.is_set():
                with instances_lock:
                    if instance_key in scraper_instances:
                        if hasattr(scraper, 'session'):
                            scraper.session.close()
                        if hasattr(scraper, 'http_session'):
                            scraper.http_session.close()
                        del scraper_instances[instance_key]
                        print(f"[{task_id}] Deleted scraper instance: {instance_key}")
            
        except TaskCancelledException:
            raise
        except TaskPausedException:
            raise
        except Exception as e:
            error_msg = f"{scraper_name} - {area_code}: {str(e)}"
            scraping_tasks[task_id]["errors"].append(error_msg)
            scraping_tasks[task_id]["progress"][progress_key].update({
                "scraper": scraper_name,
                "area_code": area_code,
                "area_name": area_name,
                "status": "failed",
                "completed_at": datetime.now().isoformat(),
                "errors": [str(e)]
            })
            print(f"[{task_id}] Error in {scraper_name} for {area_code}: {e}")
            total_errors += 1
        
        save_tasks_to_file()
    
    return total_processed, total_errors

def execute_scraping_strategy(
    task_id: str,
    scrapers: List[str],
    area_codes: List[str],
    max_properties: int,
    is_parallel: bool = False,
    detail_refetch_hours: Optional[int] = None,
    force_detail_fetch: bool = False,
    ignore_error_history: bool = False
):
    """スクレイピングタスクを実行（並列または直列の戦略に基づいて）"""
    print(f"[{task_id}] Starting {'parallel' if is_parallel else 'serial'} scraping task with scrapers: {scrapers}, areas: {area_codes}")
    
    # タスクステータスを更新
    scraping_tasks[task_id]["status"] = "running"
    save_tasks_to_file()
    
    # データベースのタスクステータスも更新
    from backend.app.database import SessionLocal
    from backend.app.models_scraping_task import ScrapingTask
    
    db = SessionLocal()
    try:
        db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
        if db_task:
            db_task.status = 'running'
            db.commit()
    finally:
        db.close()
    
    try:
        from typing import Tuple
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        if is_parallel and len(scrapers) > 1:
            # 並列実行（異なるスクレイパーを並列で実行）
            print(f"[{task_id}] Starting parallel execution with {len(scrapers)} scrapers")
            
            with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
                # 各スクレイパーに対してワーカーを起動
                futures = {}
                for scraper_name in scrapers:
                    future = executor.submit(
                        run_single_scraper_for_areas,
                        task_id, scraper_name, area_codes, max_properties,
                        detail_refetch_hours, force_detail_fetch, ignore_error_history
                    )
                    futures[future] = scraper_name
                
                # 完了を待機
                total_processed = 0
                total_errors = 0
                
                for future in as_completed(futures):
                    scraper_name = futures[future]
                    try:
                        processed, errors = future.result()
                        total_processed += processed
                        total_errors += errors
                        print(f"[{task_id}] Scraper {scraper_name} completed: {processed} processed, {errors} errors")
                    except TaskCancelledException as e:
                        print(f"[{task_id}] Scraper {scraper_name} was cancelled: {e}")
                        # 他のスクレイパーもキャンセル
                        for f in futures:
                            if f != future:
                                f.cancel()
                        raise
                    except Exception as e:
                        print(f"[{task_id}] Scraper {scraper_name} failed: {e}")
                        scraping_tasks[task_id]["errors"].append(f"{scraper_name}: {str(e)}")
                        total_errors += 1
            
            print(f"[{task_id}] Parallel execution completed: {total_processed} total processed, {total_errors} total errors")
        
        else:
            # シリアル実行（従来の実装）
            print(f"[{task_id}] Starting serial execution")
            
            # Docker環境での動的インポート
            import sys
            import os
            backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)
            
            from backend.app.scrapers.suumo_scraper import SuumoScraper
            from backend.app.scrapers.homes_scraper import HomesScraper
            from backend.app.scrapers.rehouse_scraper import RehouseScraper
            from backend.app.scrapers.nomu_scraper import NomuScraper
            from backend.app.scrapers.livable_scraper import LivableScraper
            
            scraper_index = 0
            
            for scraper_name in scrapers:
                # キャンセルチェック
                if task_cancel_flags[task_id].is_set():
                    raise TaskCancelledException(f"Task {task_id} was cancelled")
            
            # 一時停止チェック（タイムアウト付き）
            while task_pause_flags[task_id].is_set():
                if check_pause_timeout(task_id):
                    raise TaskCancelledException(f"Task {task_id} was cancelled due to pause timeout")
                print(f"[{task_id}] Task is paused, waiting...")
                import time
                time.sleep(1)
            
            for area_code in area_codes:
                # 再度キャンセル/一時停止チェック
                if task_cancel_flags[task_id].is_set():
                    raise TaskCancelledException(f"Task {task_id} was cancelled")
                
                while task_pause_flags[task_id].is_set():
                    if check_pause_timeout(task_id):
                        raise TaskCancelledException(f"Task {task_id} was cancelled due to pause timeout")
                    print(f"[{task_id}] Task is paused, waiting...")
                    import time
                    time.sleep(1)
                
                # 進行状況を更新
                progress_key = f"{scraper_name}_{area_code}"
                
                # エリア名を取得（日本語）
                area_names = {code: name for name, code in AREA_CODES.items()}
                area_name = area_names.get(area_code, area_code)
                
                scraping_tasks[task_id]["progress"][progress_key] = {
                    "scraper": scraper_name,
                    "area_code": area_code,
                    "area_name": area_name,
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "properties_found": 0,
                    "properties_saved": 0,
                    # 詳細統計
                    "properties_attempted": 0,
                    "detail_fetched": 0,
                    "detail_fetch_failed": 0,
                    "new_listings": 0,
                    "price_updated": 0,
                    "other_updates": 0,
                    "skipped_listings": 0,
                    "price_missing": 0,
                    "building_info_missing": 0,
                    "errors": 0,
                    "save_failed": 0,
                    "other_errors": 0
                }
                save_tasks_to_file()
                
                print(f"[{task_id}] Running {scraper_name} for area {area_code}")
                
                try:
                    # スクレイパーインスタンスを作成
                    scraper_classes = {
                        'suumo': SuumoScraper,
                        'homes': HomesScraper,
                        'rehouse': RehouseScraper,
                        'nomu': NomuScraper,
                        'livable': LivableScraper
                    }
                    
                    if scraper_name.lower() not in scraper_classes:
                        raise ValueError(f"Unknown scraper: {scraper_name}")
                    
                    scraper_class = scraper_classes[scraper_name.lower()]
                    
                    # スクレイパーインスタンスを取得または作成（再利用機能）
                    instance_key = f"{task_id}_{scraper_name}_{area_code}"
                    
                    with instances_lock:
                        if instance_key in scraper_instances:
                            # 保存されたインスタンスを再利用
                            scraper = scraper_instances[instance_key]
                            print(f"[{task_id}] Reusing existing scraper instance for {scraper_name}")
                            
                            # セッションがクローズされている場合は新しいセッションを作成
                            if hasattr(scraper, 'session'):
                                from backend.app.database import SessionLocal
                                scraper.session = SessionLocal()
                            if hasattr(scraper, 'http_session') and scraper.http_session is None:
                                import requests
                                scraper.http_session = requests.Session()
                                scraper.http_session.headers.update({
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                })
                        else:
                            # 環境変数を設定（詳細再取得期間）
                            import os
                            if detail_refetch_hours is not None:
                                # 時間を日数に変換（0時間の場合は0日）
                                detail_refetch_days = 0 if detail_refetch_hours == 0 else max(1, detail_refetch_hours // 24)
                                os.environ['SCRAPER_DETAIL_REFETCH_DAYS'] = str(detail_refetch_days)
                                print(f"[{task_id}] Setting SCRAPER_DETAIL_REFETCH_DAYS={detail_refetch_days} (from {detail_refetch_hours} hours)")
                            
                            # 新しいインスタンスを作成
                            scraper = scraper_class(
                                max_properties=max_properties,
                                force_detail_fetch=force_detail_fetch,
                                ignore_error_history=ignore_error_history
                            )
                            scraper_instances[instance_key] = scraper
                            
                            # 環境変数をクリア（他のタスクに影響しないように）
                            if detail_refetch_hours is not None:
                                if 'SCRAPER_DETAIL_REFETCH_DAYS' in os.environ:
                                    del os.environ['SCRAPER_DETAIL_REFETCH_DAYS']
                    
                    # スクレイピング実行
                    # タスクIDを設定
                    scraper._task_id = task_id
                    
                    # ログハンドラーとコールバックを設定
                    setup_logging_handlers(scraper, task_id, scraper_name.lower(), area_name, progress_key)
                    
                    # 統計更新用の別スレッドを開始
                    stats_thread, stop_stats_update = create_stats_update_thread(scraper, task_id, progress_key)
                    stats_thread.start()
                    
                    # scrape_areaメソッドを呼び出す
                    # SUUMO と NOMU は area_code を期待し、他は area_name を期待する
                    print(f"[{task_id}] Calling {scraper_name}.scrape_area for area_code {area_code}")
                    
                    if scraper_name.lower() in ['suumo', 'nomu']:
                        # SUUMO と NOMU は area_code を直接期待する
                        if hasattr(scraper, 'scrape_area'):
                            scraper.scrape_area(area_code)
                        elif hasattr(scraper, 'run'):
                            scraper.run(area_code)
                        else:
                            raise AttributeError(f"Scraper {scraper_name} has no scrape_area or run method")
                    else:
                        # HOMES, REHOUSE, LIVABLE は area_name を期待する
                        from ...scrapers.area_config import get_area_romaji_from_code
                        area_name = get_area_romaji_from_code(area_code)
                        print(f"[{task_id}] Converted area_code {area_code} to area_name {area_name}")
                        if hasattr(scraper, 'scrape_area'):
                            scraper.scrape_area(area_name)
                        elif hasattr(scraper, 'run'):
                            scraper.run(area_name)
                        else:
                            raise AttributeError(f"Scraper {scraper_name} has no scrape_area or run method")
                    
                    print(f"[{task_id}] {scraper_name}.scrape_area returned")
                    
                    # 統計更新スレッドを停止
                    stop_stats_update.set()
                    stats_thread.join(timeout=1)
                    
                    # 統計を取得（get_scraping_statsメソッドを使用）
                    final_stats = {}
                    if hasattr(scraper, 'get_scraping_stats'):
                        final_stats = scraper.get_scraping_stats()
                    
                    # 結果を記録（admin_old.pyと同じ詳細統計）
                    scraping_tasks[task_id]["progress"][progress_key].update({
                        "status": "completed",
                        "completed_at": datetime.now().isoformat(),
                        # 基本統計
                        "properties_found": final_stats.get('properties_found', 0),
                        "properties_saved": final_stats.get('detail_fetched', 0),
                        # 詳細統計
                        "properties_attempted": final_stats.get('properties_attempted', 0),
                        "detail_fetched": final_stats.get('detail_fetched', 0),
                        "detail_fetch_failed": final_stats.get('detail_fetch_failed', 0),
                        "new_listings": final_stats.get('new_listings', 0),
                        "price_updated": final_stats.get('price_updated', 0),
                        "other_updates": final_stats.get('other_updates', 0),
                        "skipped_listings": final_stats.get('detail_skipped', 0),
                        "price_missing": final_stats.get('price_missing', 0),
                        "building_info_missing": final_stats.get('building_info_missing', 0),
                        # エラー件数の集計
                        "errors": (
                            final_stats.get('detail_fetch_failed', 0) +
                            final_stats.get('save_failed', 0) +
                            final_stats.get('other_errors', 0)
                        ),
                        "save_failed": final_stats.get('save_failed', 0),
                        "other_errors": final_stats.get('other_errors', 0)
                    })
                    
                    # スクレイパーインスタンスをクリーンアップ（一時停止でない場合）
                    pause_flag = task_pause_flags.get(task_id)
                    if not pause_flag or not pause_flag.is_set():
                        with instances_lock:
                            if instance_key in scraper_instances:
                                if hasattr(scraper, 'session'):
                                    scraper.session.close()
                                if hasattr(scraper, 'http_session'):
                                    scraper.http_session.close()
                                del scraper_instances[instance_key]
                                print(f"[{task_id}] Deleted scraper instance: {instance_key}")
                    
                except TaskCancelledException:
                    raise
                except TaskPausedException:
                    raise
                except Exception as e:
                    # エラーを記録
                    error_msg = f"{scraper_name} - {area_code}: {str(e)}"
                    scraping_tasks[task_id]["errors"].append(error_msg)
                    scraping_tasks[task_id]["progress"][progress_key].update({
                        "scraper": scraper_name,
                        "area_code": area_code,
                        "area_name": area_name,
                        "status": "failed",
                        "completed_at": datetime.now().isoformat(),
                        "errors": [str(e)]
                    })
                    print(f"[{task_id}] Error in {scraper_name} for {area_code}: {e}")
                
                save_tasks_to_file()
                scraper_index += 1
        
        # タスク完了
        pause_flag = task_pause_flags.get(task_id)
        if pause_flag and pause_flag.is_set():
            scraping_tasks[task_id]["status"] = "paused"
            print(f"[{task_id}] Task is paused, keeping status as 'paused'")
        elif scraping_tasks[task_id]["status"] not in ["cancelled", "paused"]:
            scraping_tasks[task_id]["status"] = "completed"
            scraping_tasks[task_id]["completed_at"] = datetime.now()
            
            # データベースも更新
            db = SessionLocal()
            try:
                db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if db_task:
                    db_task.status = 'completed'
                    db_task.completed_at = datetime.now()
                    db.commit()
            finally:
                db.close()
            
    except TaskCancelledException:
        scraping_tasks[task_id]["status"] = "cancelled"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        print(f"[{task_id}] Task cancelled")
        return
    except TaskPausedException:
        print(f"[{task_id}] TaskPausedException at top level")
        scraping_tasks[task_id]["status"] = "paused"
        return
    except Exception as e:
        scraping_tasks[task_id]["status"] = "failed"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        scraping_tasks[task_id]["errors"].append(f"Unexpected error: {str(e)}")
        print(f"[{task_id}] Unexpected Error: {e}")
        return
    finally:
        # 制御フラグをクリーンアップ
        if scraping_tasks[task_id]["status"] in ["cancelled", "failed"]:
            if task_id in task_cancel_flags:
                del task_cancel_flags[task_id]
            if task_id in task_pause_flags:
                del task_pause_flags[task_id]
            if task_id in task_pause_timestamps:
                del task_pause_timestamps[task_id]
        save_tasks_to_file()


# 起動時にタスクを読み込む
load_tasks_from_file()


@router.post("/scraping/start", response_model=ScrapingTaskStatus)
def start_scraping(
    request: ScrapingRequest,
    db: Session = Depends(get_db)
):
    """スクレイピングを開始"""
    task_id = str(uuid.uuid4())
    
    # データベースにタスクを作成（スクレイパーが期待するため）
    from ...models_scraping_task import ScrapingTask
    
    db_task = ScrapingTask(
        task_id=task_id,
        status='pending',
        scrapers=request.scrapers,
        areas=request.area_codes,
        max_properties=request.max_properties,
        force_detail_fetch=False,
        started_at=datetime.now()
    )
    db.add(db_task)
    db.commit()
    
    with tasks_lock:
        scraping_tasks[task_id] = {
            "task_id": task_id,
            "type": "serial",
            "status": "pending",
            "scrapers": request.scrapers,
            "area_codes": request.area_codes,
            "max_properties": request.max_properties,
            "started_at": datetime.now(),
            "completed_at": None,
            "progress": {},
            "errors": [],
            "logs": [],
            "error_logs": [],
            "warning_logs": []
        }
    
    with flags_lock:
        task_cancel_flags[task_id] = threading.Event()
        task_pause_flags[task_id] = threading.Event()
    
    executor.submit(
        execute_scraping_strategy,
        task_id,
        request.scrapers,
        request.area_codes,
        request.max_properties,
        is_parallel=False,
        detail_refetch_hours=request.detail_refetch_hours,
        force_detail_fetch=request.force_detail_fetch,
        ignore_error_history=request.ignore_error_history
    )
    
    save_tasks_to_file()
    return ScrapingTaskStatus(**scraping_tasks[task_id])


@router.get("/scraping/status/{task_id}", response_model=ScrapingTaskStatus)
def get_scraping_status(task_id: str):
    """スクレイピングタスクの状態を取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return ScrapingTaskStatus(**scraping_tasks[task_id])


@router.get("/scraping/tasks", response_model=List[ScrapingTaskStatus])
def get_all_scraping_tasks(active_only: bool = False):
    """全スクレイピングタスクの一覧を取得"""
    tasks = []
    for task_data in scraping_tasks.values():
        # active_onlyが指定されている場合、実行中・一時停止中のタスクのみ
        if active_only and task_data.get("status") not in ["running", "paused", "pending"]:
            continue
        tasks.append(ScrapingTaskStatus(**task_data))
    
    # 新しいタスクが先頭になるように並び替え（started_atの降順）
    tasks.sort(key=lambda x: x.started_at if x.started_at else datetime.min, reverse=True)
    return tasks


@router.post("/scraping/pause/{task_id}")
def pause_scraping(task_id: str):
    """スクレイピングタスクを一時停止"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] != "running":
        raise HTTPException(status_code=400, detail="Task is not running")
    
    with flags_lock:
        if task_id in task_pause_flags:
            task_pause_flags[task_id].set()
            task_pause_timestamps[task_id] = datetime.now()
    
    scraping_tasks[task_id]["status"] = "paused"
    save_tasks_to_file()
    
    return {"message": "Task paused successfully"}


@router.post("/scraping/resume/{task_id}")
def resume_scraping(task_id: str):
    """スクレイピングタスクを再開"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused")
    
    with flags_lock:
        if task_id in task_pause_flags:
            task_pause_flags[task_id].clear()
        if task_id in task_pause_timestamps:
            del task_pause_timestamps[task_id]
    
    scraping_tasks[task_id]["status"] = "running"
    save_tasks_to_file()
    
    return {"message": "Task resumed successfully"}


@router.post("/scraping/cancel/{task_id}")
def cancel_scraping(task_id: str):
    """スクレイピングタスクをキャンセル"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] not in ["running", "paused", "pending"]:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    
    with flags_lock:
        if task_id in task_cancel_flags:
            task_cancel_flags[task_id].set()
        if task_id in task_pause_flags:
            task_pause_flags[task_id].clear()
    
    scraping_tasks[task_id]["status"] = "cancelled"
    scraping_tasks[task_id]["completed_at"] = datetime.now()
    save_tasks_to_file()
    
    return {"message": "Task cancelled successfully"}


@router.delete("/scraping/tasks/{task_id}")
def delete_scraping_task(task_id: str):
    """スクレイピングタスクを削除"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] in ["running", "paused"]:
        raise HTTPException(status_code=400, detail="Cannot delete running or paused task")
    
    with tasks_lock:
        del scraping_tasks[task_id]
    
    with flags_lock:
        if task_id in task_cancel_flags:
            del task_cancel_flags[task_id]
        if task_id in task_pause_flags:
            del task_pause_flags[task_id]
        if task_id in task_pause_timestamps:
            del task_pause_timestamps[task_id]
    
    save_tasks_to_file()
    
    return {"message": "Task deleted successfully"}


@router.get("/scraping/tasks/{task_id}")
def get_single_task(task_id: str):
    """特定のタスクの詳細を取得"""
    # メモリ内のタスクを確認
    if task_id in scraping_tasks:
        return scraping_tasks[task_id]
    
    # タスクが見つからない場合はダミーデータを返す
    # 実際の実装では、データベースから取得する
    return {
        'task_id': task_id,
        'type': 'serial',
        'status': 'not_found',
        'scrapers': [],
        'area_codes': [],
        'max_properties': 0,
        'started_at': None,
        'completed_at': None,
        'progress': {},
        'errors': ['Task not found'],
        'logs': [],
        'error_logs': [],
        'warning_logs': [],
        'created_at': None,
        'statistics': {
            'total_processed': 0,
            'total_new': 0,
            'total_updated': 0,
            'total_errors': 0,
            'elapsed_time': 0
        },
        'force_detail_fetch': False
    }


@router.get("/scraping/task/{task_id}/logs")
def get_task_logs(task_id: str):
    """タスクのログを取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = scraping_tasks[task_id]
    return {
        "task_id": task_id,
        "logs": task.get("logs", []),
        "error_logs": task.get("error_logs", []),
        "warning_logs": task.get("warning_logs", [])
    }


@router.get("/scraping/tasks/{task_id}/debug")
def get_task_debug_info(task_id: str):
    """タスクのデバッグ情報を取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = scraping_tasks[task_id]
    
    # フラグの状態を確認
    is_paused = False
    is_cancelled = False
    
    with flags_lock:
        if task_id in task_pause_flags:
            is_paused = task_pause_flags[task_id].is_set()
        if task_id in task_cancel_flags:
            is_cancelled = task_cancel_flags[task_id].is_set()
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "is_paused": is_paused,
        "is_cancelled": is_cancelled,
        "progress_count": len(task.get("progress", {})),
        "error_count": len(task.get("errors", [])),
        "log_count": len(task.get("logs", [])),
        "started_at": task.get("started_at"),
        "completed_at": task.get("completed_at"),
        "type": task.get("type", "serial")
    }


@router.delete("/scraping/all-tasks")
def delete_all_scraping_tasks():
    """全スクレイピングタスクを削除（実行中のタスクは除く）"""
    deleted_count = 0
    deleted_progress = 0
    
    with tasks_lock:
        task_ids_to_delete = []
        for task_id, task in scraping_tasks.items():
            if task["status"] not in ["running", "paused"]:
                task_ids_to_delete.append(task_id)
                # 削除前に進捗情報をカウント
                deleted_progress += len(task.get("progress", {}))
        
        for task_id in task_ids_to_delete:
            del scraping_tasks[task_id]
            deleted_count += 1
    
    with flags_lock:
        for task_id in task_ids_to_delete:
            if task_id in task_cancel_flags:
                del task_cancel_flags[task_id]
            if task_id in task_pause_flags:
                del task_pause_flags[task_id]
            if task_id in task_pause_timestamps:
                del task_pause_timestamps[task_id]
    
    save_tasks_to_file()
    
    return {
        "message": f"Deleted {deleted_count} tasks",
        "deleted_tasks": deleted_count,
        "deleted_progress": deleted_progress
    }


# 並列スクレイピング関連のエンドポイント
@router.post("/scraping/start-parallel")
def start_parallel_scraping(
    request: ParallelScrapingRequest,
    db: Session = Depends(get_db)
):
    """並列スクレイピングを開始"""
    # 現在は通常のスクレイピングとして処理
    task_id = f"parallel_{uuid.uuid4().hex[:8]}"
    
    # データベースにタスクを作成（スクレイパーが期待するため）
    from ...models_scraping_task import ScrapingTask
    
    db_task = ScrapingTask(
        task_id=task_id,
        status='pending',
        scrapers=request.scrapers,
        areas=request.area_codes,
        max_properties=request.max_properties,
        force_detail_fetch=request.force_detail_fetch,
        started_at=datetime.now()
    )
    db.add(db_task)
    db.commit()
    
    # タスク情報を登録
    with tasks_lock:
        scraping_tasks[task_id] = {
            "task_id": task_id,
            "type": "parallel",
            "status": "pending",
            "scrapers": request.scrapers,
            "area_codes": request.area_codes,
            "max_properties": request.max_properties,
            "force_detail_fetch": request.force_detail_fetch,
            "started_at": datetime.now(),
            "completed_at": None,
            "progress": {},
            "errors": [],
            "logs": [],
            "error_logs": [],
            "warning_logs": []
        }
    
    # 並列スクレイピングとして実行
    with flags_lock:
        task_cancel_flags[task_id] = threading.Event()
        task_pause_flags[task_id] = threading.Event()
    
    executor.submit(
        execute_scraping_strategy,
        task_id,
        request.scrapers,
        request.area_codes,
        request.max_properties,
        is_parallel=True,  # 並列実行フラグを追加
        detail_refetch_hours=request.detail_refetch_hours,
        force_detail_fetch=request.force_detail_fetch,
        ignore_error_history=request.ignore_error_history
    )
    
    save_tasks_to_file()
    
    return {
        "task_id": task_id,
        "status": "running",
        "scrapers": request.scrapers,
        "area_codes": request.area_codes,
        "max_properties": request.max_properties,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "progress": {},
        "errors": [],
        "message": "並列スクレイピングを開始しました"
    }


@router.get("/scraping/parallel-status/{task_id}")
def get_parallel_scraping_status(task_id: str):
    """並列スクレイピングタスクの状態を取得"""
    return get_scraping_status(task_id)


@router.post("/scraping/pause-parallel/{task_id}")
def pause_parallel_scraping(task_id: str):
    """並列スクレイピングタスクを一時停止"""
    return pause_scraping(task_id)


@router.post("/scraping/resume-parallel/{task_id}")
def resume_parallel_scraping(task_id: str):
    """並列スクレイピングタスクを再開"""
    return resume_scraping(task_id)


@router.post("/scraping/cancel-parallel/{task_id}")
def cancel_parallel_scraping(task_id: str):
    """並列スクレイピングタスクをキャンセル"""
    return cancel_scraping(task_id)


@router.post("/scraping/force-cleanup")
def force_cleanup_tasks():
    """停滞したタスクを強制的にクリーンアップ"""
    cleaned_count = 0
    
    with tasks_lock:
        for task_id, task in scraping_tasks.items():
            if task["status"] == "running":
                # 最終更新から30分以上経過している場合
                if task.get("started_at"):
                    started = task["started_at"]
                    if isinstance(started, str):
                        started = datetime.fromisoformat(started)
                    
                    if (datetime.now() - started).total_seconds() > 1800:
                        task["status"] = "stalled"
                        cleaned_count += 1
    
    save_tasks_to_file()
    
    return {"message": f"Cleaned up {cleaned_count} stalled tasks"}