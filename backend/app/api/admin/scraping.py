"""
スクレイピング管理API
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple, Callable
from datetime import datetime
import threading
import uuid
import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from ...database import get_db, SessionLocal
from ...utils.exceptions import TaskPausedException, TaskCancelledException
from ...models_scraping_task import ScrapingTask, ScrapingTaskLog

# 並列スクレイピングマネージャーのインスタンス管理（将来の拡張用）
parallel_managers: Dict[str, Any] = {}

router = APIRouter(tags=["admin-scraping"])

# タスクの永続化ファイル（削除予定）
# TASKS_FILE = "/app/data/scraping_tasks.json"

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

# エリアコードから日本語名への逆マッピング
AREA_CODE_TO_NAME = {code: name for name, code in AREA_CODES.items()}

def convert_area_codes_to_names(area_codes):
    """エリアコードを日本語名に変換"""
    from ...scrapers.area_config import TOKYO_AREA_CODES
    
    if not area_codes:
        return []
    
    # 逆引き辞書を作成（エリアコード → 日本語名）
    code_to_japanese = {}
    for japanese_name, code in TOKYO_AREA_CODES.items():
        # 日本語名のみを対象とする（英語名は除く）
        if not japanese_name.islower():  # 英語名は小文字なので除外
            code_to_japanese[code] = japanese_name
    
    names = []
    for code in area_codes:
        japanese_name = code_to_japanese.get(code, code)  # 見つからない場合はそのまま
        names.append(japanese_name)
    
    return names

class TaskHooks:
    """スクレイピングタスクの実行時フックシステム"""
    
    def __init__(self):
        self.completion_hooks: List[Callable[[str, str], None]] = []
        self.error_hooks: List[Callable[[str, str, Exception], None]] = []
    
    def on_completion(self, hook: Callable[[str, str], None]):
        """タスク完了時のフック登録
        
        Args:
            hook: (task_id, status) -> None の関数
        """
        self.completion_hooks.append(hook)
    
    def on_error(self, hook: Callable[[str, str, Exception], None]):
        """タスクエラー時のフック登録
        
        Args:
            hook: (task_id, status, exception) -> None の関数
        """
        self.error_hooks.append(hook)
    
    def trigger_completion(self, task_id: str, status: str):
        """完了フックを実行
        
        Args:
            task_id: タスクID
            status: 最終ステータス (completed, failed, cancelled)
        """
        logger = logging.getLogger(__name__)
        for hook in self.completion_hooks:
            try:
                hook(task_id, status)
            except Exception as e:
                logger.warning(f"Completion hook execution failed for task {task_id}: {e}")
    
    def trigger_error(self, task_id: str, status: str, exception: Exception):
        """エラーフックを実行
        
        Args:
            task_id: タスクID
            status: 最終ステータス
            exception: 発生した例外
        """
        logger = logging.getLogger(__name__)
        for hook in self.error_hooks:
            try:
                hook(task_id, status, exception)
            except Exception as e:
                logger.warning(f"Error hook execution failed for task {task_id}: {e}")


def validate_area_codes(area_codes: List[str]) -> None:
    """エリアコードの有効性を検証
    
    Args:
        area_codes: 検証するエリアコードのリスト
        
    Raises:
        ValueError: 無効なエリアコードが含まれる場合
    """
    from ...scrapers.area_config import TOKYO_AREA_CODES
    
    if not area_codes:
        raise ValueError("エリアコードが指定されていません")
    
    valid_codes = set(TOKYO_AREA_CODES.values())
    invalid_codes = []
    
    for code in area_codes:
        if not isinstance(code, str):
            invalid_codes.append(str(code))
        elif not (code.isdigit() and len(code) == 5 and code in valid_codes):
            invalid_codes.append(code)
    
    if invalid_codes:
        raise ValueError(f"無効なエリアコードが含まれています: {', '.join(invalid_codes)}")


def create_scraping_task(
    task_id: str,
    scrapers: List[str],
    area_codes: List[str],
    max_properties: int,
    force_detail_fetch: bool = False,
    db: Session = None
) -> 'ScrapingTask':
    """スクレイピングタスクをデータベースに作成する共通関数
    
    Args:
        task_id: タスクID
        scrapers: スクレイパーのリスト
        area_codes: エリアコードのリスト（検証済み）
        max_properties: 最大取得件数
        force_detail_fetch: 強制詳細取得フラグ
        db: データベースセッション
        
    Returns:
        作成されたScrapingTaskオブジェクト
        
    Raises:
        ValueError: エリアコードが無効な場合
    """
    # エリアコードの検証
    validate_area_codes(area_codes)
    
    # データベースにタスクを作成
    from ...models_scraping_task import ScrapingTask
    
    now = datetime.now()
    db_task = ScrapingTask(
        task_id=task_id,
        status='pending',
        scrapers=scrapers,
        areas=area_codes,
        max_properties=max_properties,
        force_detail_fetch=force_detail_fetch,
        started_at=now,
        last_progress_at=now  # 最終進捗更新時刻を初期化
    )
    
    if db:
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
    
    return db_task

# グローバルロック（スレッドセーフな操作のため）
tasks_lock = threading.Lock()
instances_lock = threading.Lock()
flags_lock = threading.Lock()

# スクレイピングタスクの状態を管理（削除予定 - データベースに移行）
# scraping_tasks: Dict[str, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=3)



# 一時停止のタイムスタンプを管理（削除予定 - データベースに移行）
# task_pause_timestamps: Dict[str, datetime] = {}

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
    last_progress_at: Optional[datetime] = None  # 最終進捗更新時刻
    progress: Dict[str, Dict[str, Any]]  # 各スクレイパー・エリアの進行状況
    errors: List[str] = []
    logs: Optional[List[Dict[str, Any]]] = []  # 物件更新履歴
    error_logs: Optional[List[Dict[str, Any]]] = []  # エラーログ
    warning_logs: Optional[List[Dict[str, Any]]] = []  # 警告ログ
    statistics: Optional[Dict[str, Any]] = {}  # 統計情報
    force_detail_fetch: Optional[bool] = False  # 詳細強制取得フラグ


# ファイル管理関数は削除（データベース管理に移行）

def update_task_progress_in_db(task_id: str, progress_key: str, progress_data: dict):
    """データベースにタスクの進捗を保存"""
    # statusとis_finalフラグをログに出力
    status = progress_data.get('status', 'unknown')
    is_final = progress_data.get('_is_final', False)
    print(f"[DEBUG] Updating progress for task {task_id}, key {progress_key}, status={status}, is_final={is_final}, data_keys={list(progress_data.keys())}")
    from sqlalchemy.orm.attributes import flag_modified
    db = SessionLocal()
    try:
        # 行レベルロックを取得（FOR UPDATE）
        db_task = db.query(ScrapingTask).filter(
            ScrapingTask.task_id == task_id
        ).with_for_update().first()
        if db_task:
            if not db_task.progress_detail:
                db_task.progress_detail = {}
            
            # 既存のデータを取得してマージ
            existing_data = db_task.progress_detail.get(progress_key, {})
            
            # 重要: 最終更新フラグがある場合は、それ以降の更新を拒否
            if existing_data.get('_is_final'):
                print(f"[DEBUG] Skipping update for {progress_key} - already finalized")
                return
            
            # 重要: completedまたはfailedステータスは上書きしない
            if existing_data.get('status') in ['completed', 'failed']:
                # 既にcompletedまたはfailedの場合
                if not progress_data.get('_is_final'):
                    # 最終更新でない場合は、statusとcompleted_atを保持
                    if 'status' not in progress_data or progress_data.get('status') == 'running':
                        progress_data['status'] = existing_data['status']
                        if 'completed_at' in existing_data:
                            progress_data['completed_at'] = existing_data['completed_at']
            # statusフィールドが含まれていない更新の場合、既存のstatusを保持
            elif 'status' not in progress_data and 'status' in existing_data:
                # 既存のstatusを保持
                progress_data['status'] = existing_data['status']
            # 初回更新でstatusが含まれていない場合はrunningに設定
            elif 'status' not in progress_data and not existing_data:
                # 初回の場合、通常はrunning状態から開始
                progress_data['status'] = 'running'
            
            # 既存データと新しいデータをマージ
            merged_data = {**existing_data, **progress_data}
            db_task.progress_detail[progress_key] = merged_data
            
            # JSONフィールドの変更を明示的にマーク
            flag_modified(db_task, 'progress_detail')
            
            # last_progress_atを更新
            db_task.last_progress_at = datetime.now()
            
            db.commit()
    finally:
        db.close()

def format_error_message(exception: Exception) -> tuple[str, str]:
    """例外メッセージを分かりやすい形式に変換
    
    Args:
        exception: 発生した例外
    
    Returns:
        tuple[str, str]: (分かりやすいエラー理由, 詳細メッセージ)
    """
    error_detail = str(exception)
    
    # よくあるエラーを分かりやすいメッセージに変換
    if "SessionLocal" in error_detail and "referenced before assignment" in error_detail:
        friendly_reason = "データベース接続の初期化エラー"
        formatted_detail = f"{friendly_reason}: モジュールのインポートまたは初期化に失敗しました"
    elif "No module named" in error_detail:
        friendly_reason = "モジュールインポートエラー"
        formatted_detail = f"{friendly_reason}: {error_detail}"
    elif "Connection refused" in error_detail:
        friendly_reason = "接続エラー"
        formatted_detail = f"{friendly_reason}: サイトへの接続が拒否されました"
    elif "timeout" in error_detail.lower():
        friendly_reason = "タイムアウトエラー"
        formatted_detail = f"{friendly_reason}: 処理が時間内に完了しませんでした"
    elif "permission denied" in error_detail.lower():
        friendly_reason = "権限エラー"
        formatted_detail = f"{friendly_reason}: 必要な権限がありません"
    else:
        friendly_reason = "実行エラー"
        formatted_detail = error_detail
    
    return friendly_reason, formatted_detail

def save_log_to_db(task_id: str, log_type: str, log_entry: dict):
    """データベースにログを保存"""
    db = SessionLocal()
    try:
        log = ScrapingTaskLog(
            task_id=task_id,
            log_type=log_type,
            timestamp=datetime.now(),
            message=log_entry.get('message', ''),
            details=log_entry
        )
        db.add(log)
        db.commit()
    finally:
        db.close()

def get_task_from_db(task_id: str):
    """データベースからタスク情報を取得"""
    db = SessionLocal()
    try:
        return db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    finally:
        db.close()


def check_task_status_from_db(task_id: str) -> dict:
    """データベースからタスクの状態を確認"""
    from ...database import SessionLocal
    from ...models_scraping_task import ScrapingTask
    
    db = SessionLocal()
    try:
        db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
        if not db_task:
            return {"exists": False, "is_paused": False, "is_cancelled": False}
        
        return {
            "exists": True,
            "is_paused": db_task.is_paused,
            "is_cancelled": db_task.is_cancelled,
            "status": db_task.status,
            "pause_requested_at": db_task.pause_requested_at
        }
    finally:
        db.close()


def check_pause_timeout(task_id: str) -> bool:
    """一時停止のタイムアウトをチェックし、タイムアウトした場合はタスクをキャンセル"""
    # データベースから状態を確認
    task_status = check_task_status_from_db(task_id)
    
    if not task_status["exists"] or not task_status["is_paused"]:
        return False
    
    # タイムスタンプを確認
    pause_time = task_status.get("pause_requested_at")
    if not pause_time:
        return False
    
    # タイムアウトチェック
    elapsed = (datetime.now() - pause_time).total_seconds()
    if elapsed > PAUSE_TIMEOUT_SECONDS:
        print(f"[{task_id}] Pause timeout ({elapsed:.0f}s > {PAUSE_TIMEOUT_SECONDS}s), cancelling task")
        
        # データベースでタスクをキャンセル
        from ...database import SessionLocal
        from ...models_scraping_task import ScrapingTask
        
        db = SessionLocal()
        try:
            db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if db_task:
                db_task.is_cancelled = True
                db_task.cancel_requested_at = datetime.now()
                db_task.status = "cancelled"
                db_task.completed_at = datetime.now()
                db.commit()
        finally:
            db.close()
        
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
    
    # 進捗コールバックを設定
    def progress_callback(stats):
        """スクレイパーからの進捗を受け取ってデータベースに保存"""
        # 現在の進捗を取得してstatusを保持
        db_task = get_task_from_db(task_id)
        current_status = "running"
        if db_task and db_task.progress_detail and progress_key in db_task.progress_detail:
            current_status = db_task.progress_detail[progress_key].get('status', 'running')
        
        # 完了済みの場合は更新しない
        if current_status in ['completed', 'failed']:
            return
        
        progress_data = {
            "scraper": scraper_name,
            "area_code": progress_key.split('_')[-1],  # progress_keyから抽出
            "area_name": area_name,
            # statusは含めない（完了処理は別途行うため）
            "properties_found": stats.get('properties_found', 0),
            "properties_processed": stats.get('properties_processed', 0),
            "properties_attempted": stats.get('properties_attempted', 0),
            "properties_scraped": stats.get('properties_attempted', 0),  # 互換性のため
            "new_listings": stats.get('new_listings', 0),
            "price_updated": stats.get('price_updated', 0),
            "other_updates": stats.get('other_updates', 0),
            "refetched_unchanged": stats.get('refetched_unchanged', 0),
            "skipped_listings": stats.get('detail_skipped', 0),
            "detail_fetched": stats.get('detail_fetched', 0),
            "detail_skipped": stats.get('detail_skipped', 0),
            "errors": stats.get('errors', 0),
            "price_missing": stats.get('price_missing', 0),
            "building_info_missing": stats.get('building_info_missing', 0)
        }
        # データベースに進捗を保存
        update_task_progress_in_db(task_id, progress_key, progress_data)
    
    # スクレイパーに進捗コールバックを設定
    if hasattr(scraper, 'set_progress_callback'):
        scraper.set_progress_callback(progress_callback)
    
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
            from ...database import SessionLocal
            from ...models import PropertyListing
            
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
            
            # 物件の詳細情報を構築
            detail_info = []
            if master_property:
                if master_property.floor_number:
                    detail_info.append(f"{master_property.floor_number}階")
                if master_property.area:
                    detail_info.append(f"{master_property.area}㎡")
                if master_property.layout:
                    detail_info.append(f"{master_property.layout}")
                if master_property.direction:
                    detail_info.append(f"{master_property.direction}向き")
            
            detail_str = ' / '.join(detail_info) if detail_info else ''
            
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
            
            # update_detailsを取得（create_or_update_listingから返される第3要素）
            update_details = result[2] if isinstance(result, tuple) and len(result) > 2 else None
            
            if update_type == 'new':
                # 建物名と詳細情報を含むメッセージ
                if building_info and detail_str:
                    log_entry["message"] = f"新規物件登録: {building_info} {detail_str} ({price}万円)"
                elif building_info:
                    log_entry["message"] = f"新規物件登録: {building_info} ({price}万円)"
                elif detail_str:
                    log_entry["message"] = f"新規物件登録: {detail_str} ({price}万円)"
                else:
                    log_entry["message"] = f"新規物件登録: {title} ({price}万円)"
                should_log = True
            elif update_type == 'price_updated':
                # update_detailsから価格変更情報を抽出
                if update_details and '価格変更:' in update_details:
                    # "価格変更: 6980万円 → 6780万円" のような形式から抽出
                    import re
                    price_match = re.search(r'(\d+)万円\s*→\s*(\d+)万円', update_details)
                    if price_match:
                        old_price_from_details = int(price_match.group(1))
                        new_price_from_details = int(price_match.group(2))
                        # 建物名と詳細情報を含むメッセージ
                        if building_info and detail_str:
                            log_entry["message"] = f"価格更新: {building_info} {detail_str} ({old_price_from_details}万円 → {new_price_from_details}万円)"
                        elif building_info:
                            log_entry["message"] = f"価格更新: {building_info} ({old_price_from_details}万円 → {new_price_from_details}万円)"
                        elif detail_str:
                            log_entry["message"] = f"価格更新: {detail_str} ({old_price_from_details}万円 → {new_price_from_details}万円)"
                        else:
                            log_entry["message"] = f"価格更新: {title} ({old_price_from_details}万円 → {new_price_from_details}万円)"
                        log_entry["price_change"] = {"old": old_price_from_details, "new": new_price_from_details}
                    else:
                        if building_info and detail_str:
                            log_entry["message"] = f"価格更新: {building_info} {detail_str} (→ {price}万円)"
                        else:
                            log_entry["message"] = f"価格更新: {title} (→ {price}万円)"
                elif existing and old_price is not None:
                    # フォールバック：既存のロジック
                    if building_info and detail_str:
                        log_entry["message"] = f"価格更新: {building_info} {detail_str} ({old_price}万円 → {price}万円)"
                    elif building_info:
                        log_entry["message"] = f"価格更新: {building_info} ({old_price}万円 → {price}万円)"
                    elif detail_str:
                        log_entry["message"] = f"価格更新: {detail_str} ({old_price}万円 → {price}万円)"
                    else:
                        log_entry["message"] = f"価格更新: {title} ({old_price}万円 → {price}万円)"
                    log_entry["price_change"] = {"old": old_price, "new": price}
                else:
                    if building_info and detail_str:
                        log_entry["message"] = f"価格更新: {building_info} {detail_str} (→ {price}万円)"
                    else:
                        log_entry["message"] = f"価格更新: {title} (→ {price}万円)"
                should_log = True
            elif update_type == 'other_updates':
                # 建物名と詳細情報を含むメッセージ
                # update_detailsがある場合は詳細を含める
                details_suffix = f" - {update_details}" if update_details else ""
                
                if building_info and detail_str:
                    log_entry["message"] = f"その他の更新: {building_info} {detail_str} ({price}万円){details_suffix}"
                elif building_info:
                    log_entry["message"] = f"その他の更新: {building_info} ({price}万円){details_suffix}"
                elif detail_str:
                    log_entry["message"] = f"その他の更新: {detail_str} ({price}万円){details_suffix}"
                else:
                    log_entry["message"] = f"その他の更新: {title} ({price}万円){details_suffix}"
                if update_details:
                    log_entry["update_details"] = update_details
                should_log = True
            elif update_type == 'refetched_unchanged' or update_type == 'skipped':
                # 変更なしの場合、詳細をスキップした場合はログに記録しない
                pass
            
            # ログを追加（価格変更または新規物件のみ）
            if should_log:
                # デバッグ：ログ記録を確認
                print(f"[DEBUG] ログ記録: task_id={task_id}, update_type={update_type}, message={log_entry.get('message', '')}")
                # データベースにログを保存
                save_log_to_db(task_id, 'property_update', log_entry)
            
            return result
        
        scraper.create_or_update_listing = create_or_update_with_logging
        scraper._create_or_update_overridden = True
    
    # エラーログ記録用のメソッドを追加（常にオーバーライド）
    if True:  # 常にオーバーライド
        def save_error_log(error_info):
            # エラーメッセージの詳細を構築
            reason = error_info.get('reason', '不明なエラー')
            url = error_info.get('url', '')
            building_name = error_info.get('building_name', '')
            price = error_info.get('price', '')
            
            # わかりやすいメッセージを作成
            message_parts = []
            if reason:
                message_parts.append(reason)
            if url:
                message_parts.append(f"URL: {url}")
            if building_name:
                message_parts.append(f"建物: {building_name}")
            if price:
                message_parts.append(f"価格: {price}")
            
            display_message = " - ".join(message_parts) if message_parts else "エラーが発生しました"
            
            error_log = {
                "timestamp": error_info.get('timestamp', datetime.now().isoformat()),
                "scraper": scraper_name,
                "area": area_name,
                "url": url,
                "building_name": building_name,
                "price": price,
                "reason": reason,
                "message": display_message,
                # 追加の詳細情報
                "site_property_id": error_info.get('site_property_id', ''),
                "error_type": error_info.get('error_type', ''),
                "error_detail": error_info.get('error_detail', '')
            }
            
            # データベースにエラーログを保存
            save_log_to_db(task_id, 'error', error_log)
        
        scraper._save_error_log = save_error_log
    
    # 警告ログ記録用のメソッドを追加（常にオーバーライド）
    if True:  # 常にオーバーライド
        def save_warning_log(warning_info):
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
            
            # データベースに警告ログを保存
            save_log_to_db(task_id, 'warning', warning_log)
        
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
            # 停止フラグが設定されたら即座に終了
            if stop_stats_update.is_set():
                break
            
            try:
                # スクレイパーから最新の統計を取得
                current_stats = scraper.get_scraping_stats()
                
                # 統計が存在する場合のみ更新
                if current_stats:
                    # 重要: データベースから最新状態を取得してチェック（ロック付き）
                    # これにより、完了状態の確認と更新が原子的に実行される
                    db = SessionLocal()
                    try:
                        # 行レベルロックを取得
                        db_task = db.query(ScrapingTask).filter(
                            ScrapingTask.task_id == task_id
                        ).with_for_update().first()
                        
                        if not db_task or not db_task.progress_detail:
                            continue
                            
                        current_progress = db_task.progress_detail.get(progress_key, {})
                        
                        # 初期データが不完全な場合（scraperやarea_nameがない場合）はスキップ
                        if not current_progress.get('scraper') or not current_progress.get('area_name'):
                            continue
                        
                        # 重要: 最終更新済みの場合は統計更新をスキップ
                        if current_progress.get('_is_final'):
                            print(f"[{task_id}] Skipping stats update for {progress_key} - already finalized")
                            continue
                        
                        # 重要: statusフィールドは変更しない（completedまたはfailedの場合は更新しない）
                        if current_progress.get('status') in ['completed', 'failed']:
                            # 完了またはエラー状態の場合は更新をスキップ
                            continue
                        
                        # scraperとarea情報を抽出（progress_keyから）
                        parts = progress_key.split('_')
                        if len(parts) >= 2:
                            scraper_name = parts[0]
                            area_code = parts[-1]
                            # エリア名を取得
                            area_names = {code: name for name, code in AREA_CODES.items()}
                            area_name = area_names.get(area_code, area_code)
                        else:
                            scraper_name = "unknown"
                            area_code = "unknown"
                            area_name = "unknown"
                        
                        # scraperとarea情報が既存データにない場合は追加
                        if 'scraper' not in current_progress:
                            current_progress['scraper'] = scraper_name
                        if 'area_code' not in current_progress:
                            current_progress['area_code'] = area_code
                        if 'area_name' not in current_progress:
                            current_progress['area_name'] = area_name
                        
                        # 統計情報を更新（statusフィールドは保持）
                        # 重要: statusフィールドは更新データから除外
                        update_data = {
                            "properties_found": current_stats.get('properties_found', 0),
                            "properties_processed": current_stats.get('properties_processed', 0),
                            "properties_attempted": current_stats.get('properties_attempted', 0),
                            "properties_scraped": current_stats.get('properties_processed', 0),
                            "detail_fetched": current_stats.get('detail_fetched', 0),
                            "new_listings": current_stats.get('new_listings', 0),
                            "price_updated": current_stats.get('price_updated', 0),
                            "other_updates": current_stats.get('other_updates', 0),
                            "refetched_unchanged": current_stats.get('refetched_unchanged', 0),
                            "validation_failed": current_stats.get('validation_failed', 0),
                            "skipped_listings": current_stats.get('detail_skipped', 0),
                            "detail_fetch_failed": current_stats.get('detail_fetch_failed', 0),
                            "save_failed": current_stats.get('save_failed', 0),
                            "price_missing": current_stats.get('price_missing', 0),
                            "building_info_missing": current_stats.get('building_info_missing', 0),
                            "other_errors": current_stats.get('other_errors', 0)
                        }
                        
                        # 同じトランザクション内で更新
                        from sqlalchemy.orm.attributes import flag_modified
                        merged_data = {**current_progress, **update_data}
                        db_task.progress_detail[progress_key] = merged_data
                        flag_modified(db_task, 'progress_detail')
                        db.commit()
                        
                    finally:
                        db.close()
                        
            except Exception as e:
                print(f"[{task_id}] Error updating stats: {e}")
            
            # 2秒待機（ただし、停止イベントが設定されたら即座に終了）
            for _ in range(20):  # 0.1秒×20回 = 2秒
                if stop_stats_update.is_set():
                    break
                time_module.sleep(0.1)
    
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
        # キャンセルチェック（データベースから確認）
        task_status = check_task_status_from_db(task_id)
        if task_status.get("is_cancelled") or task_status.get("status") == "cancelled":
            raise TaskCancelledException(f"Task {task_id} was cancelled")
        
        # 一時停止チェック（データベースから確認）
        while check_task_status_from_db(task_id).get("is_paused"):
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
        
        progress_data = {
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
            "other_errors": 0,
            "_is_final": False  # running状態も最終更新ではない
        }
        # データベースに進捗を保存（統計更新スレッド開始前に必ず実行）
        update_task_progress_in_db(task_id, progress_key, progress_data)
        
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
                        from ...database import SessionLocal as LocalSessionLocal
                        scraper.session = LocalSessionLocal()
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
                        ignore_error_history=ignore_error_history,
                        task_id=task_id
                    )
                    scraper_instances[instance_key] = scraper
                    
                    # 環境変数をクリア（他のタスクに影響しないように）
                    if detail_refetch_hours is not None:
                        if 'SCRAPER_DETAIL_REFETCH_DAYS' in os.environ:
                            del os.environ['SCRAPER_DETAIL_REFETCH_DAYS']
            

            
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
            # 重要: スレッドが完全に停止するまで待つ（最大5秒）
            stats_thread.join(timeout=5)
            
            # スレッドがまだ生きている場合は警告
            if stats_thread.is_alive():
                print(f"[{task_id}] Warning: Stats thread still alive after timeout")
            

            # 統計を取得
            final_stats = {}
            if hasattr(scraper, 'get_scraping_stats'):
                final_stats = scraper.get_scraping_stats()
                print(f"[{task_id}] Final stats retrieved: detail_fetched={final_stats.get('detail_fetched', 0)}, "
                      f"new_listings={final_stats.get('new_listings', 0)}, "
                      f"price_updated={final_stats.get('price_updated', 0)}, "
                      f"other_updates={final_stats.get('other_updates', 0)}, "
                      f"refetched_unchanged={final_stats.get('refetched_unchanged', 0)}")
            
            # 結果を記録
            final_progress = {
                "scraper": scraper_name,
                "area_code": area_code,
                "area_name": area_name,
                "status": "completed",
                "_is_final": True,  # 最終更新フラグ
                "completed_at": datetime.now().isoformat(),
                "properties_found": final_stats.get('properties_found', 0),
                "properties_saved": final_stats.get('detail_fetched', 0),
                "properties_attempted": final_stats.get('properties_attempted', 0),
                "detail_fetched": final_stats.get('detail_fetched', 0),
                "detail_fetch_failed": final_stats.get('detail_fetch_failed', 0),
                "new_listings": final_stats.get('new_listings', 0),
                "price_updated": final_stats.get('price_updated', 0),
                "other_updates": final_stats.get('other_updates', 0),
                "refetched_unchanged": final_stats.get('refetched_unchanged', 0),
                "validation_failed": final_stats.get('validation_failed', 0),
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
            }
            progress_data.update(final_progress)
            update_task_progress_in_db(task_id, progress_key, progress_data)
            
            # 重要: 最終ステータスが確実に保存されるよう、再度確認して必要なら再更新
            # トランザクション内で確認
            db = SessionLocal()
            try:
                db_task = db.query(ScrapingTask).filter(
                    ScrapingTask.task_id == task_id
                ).with_for_update().first()
                if db_task and db_task.progress_detail and progress_key in db_task.progress_detail:
                    if db_task.progress_detail[progress_key].get('status') != 'completed':
                        print(f"[{task_id}] Warning: Final status not saved correctly for {progress_key}, retrying...")
                        # ステータスのみを再更新（_is_finalフラグ付き）
                        # 同じトランザクション内で更新
                        from sqlalchemy.orm.attributes import flag_modified
                        db_task.progress_detail[progress_key].update({
                            'status': 'completed', 
                            'completed_at': final_progress['completed_at'],
                            '_is_final': True  # 最終更新フラグ
                        })
                        flag_modified(db_task, 'progress_detail')
                        db.commit()
            finally:
                db.close()
            
            total_processed += final_stats.get('properties_found', 0)
            
            # インスタンスをクリーンアップ
            # データベースから一時停止状態を確認
            task_status = check_task_status_from_db(task_id)
            if not task_status.get("is_paused"):
                with instances_lock:
                    if instance_key in scraper_instances:
                        if hasattr(scraper, 'session'):
                            scraper.session.close()
                        if hasattr(scraper, 'http_session'):
                            scraper.http_session.close()
                        del scraper_instances[instance_key]
                        print(f"[{task_id}] Deleted scraper instance: {instance_key}")
            
        except TaskCancelledException:
            # キャンセル時は進捗状態をcancelledに更新
            cancel_progress = {
                "scraper": scraper_name,
                "area_code": area_code,
                "area_name": area_name,
                "status": "cancelled",
                "_is_final": True,  # 最終更新フラグ
                "completed_at": datetime.now().isoformat()
            }
            update_task_progress_in_db(task_id, progress_key, cancel_progress)
            raise
        except TaskPausedException:
            raise
        except Exception as e:
            # エラーメッセージをより分かりやすく整形
            friendly_reason, formatted_detail = format_error_message(e)
            error_msg = f"{scraper_name} - {area_code}: {formatted_detail}"
            
            # エラーログをデータベースに保存
            save_log_to_db(task_id, 'error', {
                "message": error_msg,
                "scraper": scraper_name,
                "area_code": area_code,
                "area": area_name,
                "reason": friendly_reason,
                "timestamp": datetime.now().isoformat(),
                "error_detail": str(e)  # 元のエラーメッセージも保存
            })
            # 進捗をエラー状態に更新
            progress_data.update({
                "scraper": scraper_name,
                "area_code": area_code,
                "area_name": area_name,
                "status": "failed",
                "_is_final": True,  # 最終更新フラグ
                "completed_at": datetime.now().isoformat(),
                "errors": [str(e)]
            })
            update_task_progress_in_db(task_id, progress_key, progress_data)
            print(f"[{task_id}] Error in {scraper_name} for {area_code}: {e}")
            total_errors += 1
        
        # save_tasks_to_file()  # データベースに移行
    
    return total_processed, total_errors

def execute_scraping_strategy(
    task_id: str,
    scrapers: List[str],
    area_codes: List[str],
    max_properties: int,
    is_parallel: bool = False,
    detail_refetch_hours: Optional[int] = None,
    force_detail_fetch: bool = False,
    ignore_error_history: bool = False,
    hooks: Optional[TaskHooks] = None
):
    """スクレイピングタスクを実行（並列または直列の戦略に基づいて）"""
    print(f"[{task_id}] Starting {'parallel' if is_parallel else 'serial'} scraping task with scrapers: {scrapers}, areas: {area_codes}")
    
    # タスクステータスを更新（データベースのみ更新すればよい）
    
    # データベースのタスクステータスも更新
    from ...database import SessionLocal
    from ...models_scraping_task import ScrapingTask
    
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
                        
                        # すべてのスクレイパーの進捗状態をcancelledに更新
                        # トランザクション内で一括更新
                        db = SessionLocal()
                        try:
                            db_task = db.query(ScrapingTask).filter(
                                ScrapingTask.task_id == task_id
                            ).with_for_update().first()
                            
                            if db_task and db_task.progress_detail:
                                from sqlalchemy.orm.attributes import flag_modified
                                area_names = {code: name for name, code in AREA_CODES.items()}
                                
                                for scraper in scrapers:
                                    for area in area_codes:
                                        progress_key = f"{scraper}_{area}"
                                        # 既に完了していないスクレイパーのみ更新
                                        if progress_key in db_task.progress_detail:
                                            current_status = db_task.progress_detail[progress_key].get('status')
                                            if current_status not in ['completed', 'failed', 'cancelled']:
                                                area_name = area_names.get(area, area)
                                                db_task.progress_detail[progress_key].update({
                                                    "scraper": scraper,
                                                    "area_code": area,
                                                    "area_name": area_name,
                                                    "status": "cancelled",
                                                    "_is_final": True,
                                                    "completed_at": datetime.now().isoformat()
                                                })
                                
                                flag_modified(db_task, 'progress_detail')
                                db.commit()
                        finally:
                            db.close()
                        raise
                    except Exception as e:
                        print(f"[{task_id}] Scraper {scraper_name} failed: {e}")
                        # エラーメッセージをより分かりやすく整形
                        friendly_reason, formatted_detail = format_error_message(e)
                        
                        # エラーログをデータベースに保存
                        save_log_to_db(task_id, 'error', {
                            "message": f"{scraper_name}: {formatted_detail}",
                            "scraper": scraper_name,
                            "reason": friendly_reason,
                            "timestamp": datetime.now().isoformat(),
                            "error_detail": str(e)
                        })
                        
                        # 並列実行時のエラー時も進捗ステータスを更新
                        # すべてのエリアのステータスをfailedに設定
                        for area_code in area_codes:
                            progress_key = f"{scraper_name}_{area_code}"
                            area_names = {code: name for name, code in AREA_CODES.items()}
                            area_name = area_names.get(area_code, area_code)
                            
                            error_progress = {
                                "scraper": scraper_name,
                                "area_code": area_code,
                                "area_name": area_name,
                                "status": "failed",
                                "_is_final": True,  # 最終更新フラグ
                                "completed_at": datetime.now().isoformat(),
                                "errors": [str(e)]
                            }
                            update_task_progress_in_db(task_id, progress_key, error_progress)
                        
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
            
            from ...scrapers.suumo_scraper import SuumoScraper
            from ...scrapers.homes_scraper import HomesScraper
            from ...scrapers.rehouse_scraper import RehouseScraper
            from ...scrapers.nomu_scraper import NomuScraper
            from ...scrapers.livable_scraper import LivableScraper
            
            scraper_index = 0
            
            for scraper_name in scrapers:
                # キャンセルチェック（データベースから確認）
                task_status = check_task_status_from_db(task_id)
                if task_status.get("is_cancelled") or task_status.get("status") == "cancelled":
                    raise TaskCancelledException(f"Task {task_id} was cancelled")
            
            # 一時停止チェック（データベースから確認）
            while check_task_status_from_db(task_id).get("is_paused"):
                if check_pause_timeout(task_id):
                    raise TaskCancelledException(f"Task {task_id} was cancelled due to pause timeout")
                print(f"[{task_id}] Task is paused, waiting...")
                import time
                time.sleep(1)
            
            for area_code in area_codes:
                # 再度キャンセル/一時停止チェック（データベースから確認）
                task_status = check_task_status_from_db(task_id)
                if task_status.get("is_cancelled") or task_status.get("status") == "cancelled":
                    raise TaskCancelledException(f"Task {task_id} was cancelled")
                
                while check_task_status_from_db(task_id).get("is_paused"):
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
                
                progress_data = {
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
                # データベースに進捗を保存
                update_task_progress_in_db(task_id, progress_key, progress_data)
                
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
                                from ...database import SessionLocal as DBSessionLocal
                                scraper.session = DBSessionLocal()
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
                                ignore_error_history=ignore_error_history,
                                task_id=task_id
                            )
                            scraper_instances[instance_key] = scraper
                            
                            # 環境変数をクリア（他のタスクに影響しないように）
                            if detail_refetch_hours is not None:
                                if 'SCRAPER_DETAIL_REFETCH_DAYS' in os.environ:
                                    del os.environ['SCRAPER_DETAIL_REFETCH_DAYS']
                    
                    # スクレイピング実行

                    
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
                    final_progress = {
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
                    }
                    progress_data.update(final_progress)
                    update_task_progress_in_db(task_id, progress_key, progress_data)
                    
                    # スクレイパーインスタンスをクリーンアップ（一時停止でない場合）
                    # データベースから一時停止状態を確認
                    task_status = check_task_status_from_db(task_id)
                    if not task_status.get("is_paused"):
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
                    # エラーメッセージをより分かりやすく整形
                    friendly_reason, formatted_detail = format_error_message(e)
                    
                    # エラーログをデータベースに保存
                    save_log_to_db(task_id, 'error', {
                        "message": error_msg,
                        "scraper": scraper_name,
                        "area_code": area_code,
                        "area": area_name,
                        "reason": friendly_reason,
                        "timestamp": datetime.now().isoformat(),
                        "error_detail": str(e)
                    })
                    # 進捗をエラー状態に更新
                    progress_data.update({
                        "scraper": scraper_name,
                        "area_code": area_code,
                        "area_name": area_name,
                        "status": "failed",
                        "_is_final": True,  # 最終更新フラグ
                        "completed_at": datetime.now().isoformat(),
                        "errors": [str(e)]
                    })
                    update_task_progress_in_db(task_id, progress_key, progress_data)
                    print(f"[{task_id}] Error in {scraper_name} for {area_code}: {e}")
                
                # save_tasks_to_file()  # データベースに移行
                scraper_index += 1
        
        # タスク完了
        # データベースから状態を確認
        db_task = get_task_from_db(task_id)
        if db_task and db_task.is_paused:
            print(f"[{task_id}] Task is paused, keeping status as 'paused'")
            # 一時停止状態でもフック実行
            if hooks:
                hooks.trigger_completion(task_id, "paused")
        elif db_task and db_task.status not in ["cancelled", "paused"]:
            # データベースを更新
            db = SessionLocal()
            try:
                db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
                if db_task:
                    db_task.status = 'completed'
                    db_task.completed_at = datetime.now()
                    db.commit()
                    
                    # スクレイピング完了後に価格改定履歴キューを自動処理
                    try:
                        from ...utils.price_change_calculator import PriceChangeCalculator
                        calculator = PriceChangeCalculator(db)
                        print(f"[{task_id}] スクレイピング完了。価格改定履歴キューの処理を開始します...")
                        stats = calculator.process_queue(limit=1000)
                        print(f"[{task_id}] 価格改定履歴キューの処理完了: 処理={stats['processed']}件, 失敗={stats['failed']}件, 変更={stats['changes_found']}件")
                    except Exception as queue_error:
                        print(f"[{task_id}] 価格改定履歴キューの処理に失敗: {queue_error}")
                        # キュー処理の失敗はメインタスクに影響させない
                    
                    # 正常完了フック実行
                    if hooks:
                        hooks.trigger_completion(task_id, "completed")
            finally:
                db.close()
            
    except TaskCancelledException:
        # データベースを更新
        db = SessionLocal()
        try:
            db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if db_task:
                db_task.status = "cancelled"
                db_task.completed_at = datetime.now()
                db.commit()
                # キャンセル完了フック実行
                if hooks:
                    hooks.trigger_completion(task_id, "cancelled")
        finally:
            db.close()
        print(f"[{task_id}] Task cancelled")
        return
    except TaskPausedException:
        print(f"[{task_id}] TaskPausedException at top level")
        # データベースを更新
        db = SessionLocal()
        try:
            db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if db_task:
                db_task.status = "paused"
                db.commit()
                # 一時停止フック実行
                if hooks:
                    hooks.trigger_completion(task_id, "paused")
        finally:
            db.close()
        return
    except Exception as e:
        # データベースを更新
        db = SessionLocal()
        try:
            db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
            if db_task:
                db_task.status = "failed"
                db_task.completed_at = datetime.now()
                db.commit()
                # エラー完了フック実行
                if hooks:
                    hooks.trigger_completion(task_id, "failed")
                    hooks.trigger_error(task_id, "failed", e)
        finally:
            db.close()
        # エラーメッセージをより分かりやすく整形
        friendly_reason, formatted_detail = format_error_message(e)
        
        # 予期しないエラーの場合は理由を調整
        if friendly_reason == "実行エラー":
            friendly_reason = "予期しないエラー"
        
        # エラーログを保存
        save_log_to_db(task_id, 'error', {
            "message": f"Unexpected error: {formatted_detail}",
            "reason": friendly_reason,
            "timestamp": datetime.now().isoformat(),
            "error_detail": str(e)
        })
        print(f"[{task_id}] Unexpected Error: {e}")
        return
    finally:
        # 制御フラグをクリーンアップ（データベースから状態を確認）
        db_task = get_task_from_db(task_id)
        if db_task and db_task.status in ["cancelled", "failed"]:
            # フラグのクリーンアップは不要（データベース管理に移行）
            pass


# 起動時のタスク読み込みは不要（データベースから直接読み込み）


@router.post("/scraping/start", response_model=ScrapingTaskStatus)
def start_scraping(
    request: ScrapingRequest,
    db: Session = Depends(get_db)
):
    """スクレイピングを開始"""
    task_id = str(uuid.uuid4())
    
    # 共通関数を使用してタスクを作成
    try:
        db_task = create_scraping_task(
            task_id=task_id,
            scrapers=request.scrapers,
            area_codes=request.area_codes,
            max_properties=request.max_properties,
            force_detail_fetch=request.force_detail_fetch,
            db=db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # バックグラウンドでスクレイピングを実行
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
    
    # レスポンス用のデータを作成
    return ScrapingTaskStatus(
        task_id=task_id,
        type="serial",
        status="pending",
        scrapers=request.scrapers,
        area_codes=request.area_codes,
        max_properties=request.max_properties,
        started_at=db_task.started_at,
        completed_at=None,
        progress={},
        errors=[],
        logs=[],
        error_logs=[],
        warning_logs=[]
    )


@router.get("/scraping/status/{task_id}", response_model=ScrapingTaskStatus)
def get_scraping_status(task_id: str, db: Session = Depends(get_db)):
    """スクレイピングタスクの状態を取得"""
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # データベースのタスクをScrapingTaskStatusに変換
    return ScrapingTaskStatus(
        task_id=db_task.task_id,
        type="parallel" if db_task.task_id.startswith("parallel_") else "serial",
        status=db_task.status,
        scrapers=db_task.scrapers if isinstance(db_task.scrapers, list) else [],
        area_codes=db_task.areas if isinstance(db_task.areas, list) else [],
        max_properties=db_task.max_properties,
        started_at=db_task.started_at,
        completed_at=db_task.completed_at,
        progress=db_task.progress_detail if db_task.progress_detail else {},
        errors=[],
        logs=[],
        error_logs=[],
        warning_logs=[]
    )


def cleanup_stale_tasks(db: Session):
    """
    停滞したタスクを自動的にクリーンアップする
    - 設定値以上更新がないrunning状態のタスクをfailedに変更
    - プロセスが存在しないタスクをfailedに変更
    """
    from ...models_scraping_task import ScrapingTask, ScrapingTaskLog
    from ...config.scraping_config import STALLED_TASK_THRESHOLD_MINUTES
    
    cleaned_count = 0
    now = datetime.now()
    
    # running状態のタスクを取得
    running_tasks = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
    
    for task in running_tasks:
        should_cleanup = False
        reason = ""
        
        # 1. 最終更新から設定値以上経過しているかチェック
        if task.started_at:
            # last_progress_atを使用（これは確実に更新される）
            if task.last_progress_at:
                last_update = task.last_progress_at
            else:
                last_update = task.started_at
            
            # 最終更新から設定値以上経過
            if (now - last_update).total_seconds() > (STALLED_TASK_THRESHOLD_MINUTES * 60):
                should_cleanup = True
                reason = f"最終更新から{int((now - last_update).total_seconds() / 60)}分経過"
        
        # 2. プロセスの存在チェックは、サーバー再起動後は正確でないため削除
        # 代わりに、最終更新時刻のみで判断する
        
        if should_cleanup:
            task.status = "failed"
            task.completed_at = now
            cleaned_count += 1
            
            # ログを記録
            log_entry = ScrapingTaskLog(
                task_id=task.task_id,
                log_type="error",
                message=f"タスクが異常終了しました: {reason}",
                details={"reason": reason, "auto_cleanup": True},
                timestamp=now,
                created_at=now  # created_atフィールドも必要
            )
            db.add(log_entry)
    
    if cleaned_count > 0:
        db.commit()
        # ログ出力（管理画面のコンソールには別途表示される）
        print(f"[AUTO-CLEANUP] {cleaned_count}個の停滞したタスクをfailedに変更")
    
    return cleaned_count

@router.get("/scraping/tasks", response_model=List[ScrapingTaskStatus])
def get_all_scraping_tasks(
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """全スクレイピングタスクの一覧を取得（データベースから）"""
    from ...models_scraping_task import ScrapingTask
    
    # 停滞したタスクを自動的にクリーンアップ
    cleanup_stale_tasks(db)
    
    # データベースからタスクを取得
    query = db.query(ScrapingTask)
    
    # active_onlyが指定されている場合、実行中・一時停止中のタスクのみ
    if active_only:
        query = query.filter(ScrapingTask.status.in_(["running", "paused", "pending"]))
    
    # 新しいタスクが先頭になるように並び替え（created_atの降順）
    db_tasks = query.order_by(ScrapingTask.created_at.desc()).limit(100).all()
    
    tasks = []
    for db_task in db_tasks:
        # データベースからログを取得
        property_logs = db.query(ScrapingTaskLog).filter(
            ScrapingTaskLog.task_id == db_task.task_id,
            ScrapingTaskLog.log_type == 'property_update'
        ).all()
        error_logs = db.query(ScrapingTaskLog).filter(
            ScrapingTaskLog.task_id == db_task.task_id,
            ScrapingTaskLog.log_type == 'error'
        ).all()
        warning_logs = db.query(ScrapingTaskLog).filter(
            ScrapingTaskLog.task_id == db_task.task_id,
            ScrapingTaskLog.log_type == 'warning'
        ).all()
        
        # エリアコードを日本語名に変換
        area_codes = db_task.areas if isinstance(db_task.areas, list) else []
        area_names = convert_area_codes_to_names(area_codes)
        
        # ScrapingTaskモデルからScrapingTaskStatusに変換
        task_data = {
            "task_id": db_task.task_id,
            "type": "parallel" if db_task.task_id.startswith("parallel_") else "serial",
            "status": db_task.status,
            "scrapers": db_task.scrapers if isinstance(db_task.scrapers, list) else [],
            "area_codes": area_names,  # エリア名に変換して返却
            "max_properties": db_task.max_properties,
            "force_detail_fetch": db_task.force_detail_fetch,
            "started_at": db_task.started_at,
            "completed_at": db_task.completed_at,
            "last_progress_at": db_task.last_progress_at,  # 最終進捗更新時刻を追加
            "progress": db_task.progress_detail if db_task.progress_detail else {},
            "errors": [],
            # データベースから取得したログを使用
            "logs": [log.details if log.details else {"message": log.message} for log in property_logs],
            "error_logs": [log.details if log.details else {"message": log.message} for log in error_logs],
            "warning_logs": [log.details if log.details else {"message": log.message} for log in warning_logs],
            "statistics": {
                "total_processed": db_task.total_processed,
                "total_new": db_task.total_new,
                "total_updated": db_task.total_updated,
                "total_errors": db_task.total_errors,
                "elapsed_time": db_task.elapsed_time or 0
            }
        }
        tasks.append(ScrapingTaskStatus(**task_data))
    
    return tasks

@router.get("/scraping/tasks/{task_id}/logs/diff")
def get_task_logs_diff(
    task_id: str,
    last_log_timestamp: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """タスクのログ差分を取得（最後に取得したタイムスタンプ以降のログのみ）"""
    from ...models_scraping_task import ScrapingTaskLog
    from datetime import datetime
    
    # ログを取得するクエリを構築
    query = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id
    )
    
    # タイムスタンプが指定されている場合は、それ以降のログのみ取得
    if last_log_timestamp:
        try:
            last_timestamp = datetime.fromisoformat(last_log_timestamp.replace('Z', '+00:00'))
            query = query.filter(ScrapingTaskLog.timestamp > last_timestamp)
        except:
            pass  # タイムスタンプのパースに失敗した場合は全ログを返す
    
    # ログを取得
    logs = query.order_by(ScrapingTaskLog.timestamp.asc()).all()
    
    # ログを種類別に分類
    property_logs = []
    error_logs = []
    warning_logs = []
    
    for log in logs:
        log_data = log.details or {}
        
        if log.log_type == 'property_update':
            property_logs.append({
                'timestamp': log.timestamp.isoformat(),
                'type': log_data.get('type', 'update'),
                'scraper': log_data.get('scraper', ''),
                'area': log_data.get('area', ''),
                'url': log_data.get('url', ''),
                'title': log_data.get('title', ''),
                'price': log_data.get('price', 0),
                'message': log_data.get('message', ''),
                'price_change': log_data.get('price_change'),
                'update_details': log_data.get('update_details')
            })
        elif log.log_type == 'error':
            error_logs.append({
                'timestamp': log.timestamp.isoformat(),
                'scraper': log_data.get('scraper', ''),
                'area': log_data.get('area'),
                'area_code': log_data.get('area_code'),
                'url': log_data.get('url'),
                'reason': log_data.get('reason', ''),
                'building_name': log_data.get('building_name'),
                'price': log_data.get('price')
            })
        elif log.log_type == 'warning':
            warning_logs.append({
                'timestamp': log.timestamp.isoformat(),
                'scraper': log_data.get('scraper', ''),
                'area': log_data.get('area'),
                'area_code': log_data.get('area_code'),
                'url': log_data.get('url'),
                'reason': log_data.get('reason'),
                'building_name': log_data.get('building_name'),
                'price': log_data.get('price'),
                'site_property_id': log_data.get('site_property_id'),
                'message': log_data.get('message')
            })
    
    return {
        'task_id': task_id,
        'logs': property_logs,
        'error_logs': error_logs,
        'warning_logs': warning_logs,
        'has_more': False  # 今後の拡張用
    }


@router.post("/scraping/pause/{task_id}")
def pause_scraping(task_id: str, db: Session = Depends(get_db)):
    """スクレイピングタスクを一時停止"""
    from ...models_scraping_task import ScrapingTask
    
    # データベースでタスクを確認
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if db_task.status != "running":
        raise HTTPException(status_code=400, detail="Task is not running")
    
    # データベースを更新
    db_task.is_paused = True
    db_task.pause_requested_at = datetime.now()
    db_task.status = "paused"
    db.commit()
    
    return {"message": "Task paused successfully"}


@router.post("/scraping/resume/{task_id}")
def resume_scraping(task_id: str, db: Session = Depends(get_db)):
    """スクレイピングタスクを再開"""
    from ...models_scraping_task import ScrapingTask
    
    # データベースでタスクを確認
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if db_task.status != "paused":
        raise HTTPException(status_code=400, detail="Task is not paused")
    
    # データベースを更新
    db_task.is_paused = False
    db_task.pause_requested_at = None
    db_task.status = "running"
    db.commit()
    
    return {"message": "Task resumed successfully"}


@router.post("/scraping/cancel/{task_id}")
def cancel_scraping(task_id: str, db: Session = Depends(get_db)):
    """スクレイピングタスクをキャンセル"""
    from ...models_scraping_task import ScrapingTask
    from sqlalchemy.orm.attributes import flag_modified
    
    # データベースでタスクを確認
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if db_task.status not in ["running", "paused", "pending"]:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    
    # データベースを更新
    db_task.is_cancelled = True
    db_task.cancel_requested_at = datetime.now()
    db_task.status = "cancelled"
    db_task.completed_at = datetime.now()
    
    # 個別のスクレイパータスクのステータスも更新
    if db_task.progress_detail:
        for scraper_key in db_task.progress_detail.keys():
            if isinstance(db_task.progress_detail[scraper_key], dict):
                # 実行中、一時停止中、待機中の個別タスクをキャンセル済みに設定
                current_status = db_task.progress_detail[scraper_key].get('status')
                if current_status in ['running', 'paused', 'pending']:
                    db_task.progress_detail[scraper_key]['status'] = 'cancelled'
                    db_task.progress_detail[scraper_key]['completed_at'] = datetime.now().isoformat()
        
        # JSONフィールドの変更を明示的に通知
        flag_modified(db_task, 'progress_detail')
    
    db.commit()
    
    return {"message": "Task cancelled successfully"}


@router.delete("/scraping/tasks/{task_id}")
def delete_scraping_task(task_id: str, db: Session = Depends(get_db)):
    """スクレイピングタスクを削除"""
    from ...models_scraping_task import ScrapingTaskLog
    
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if db_task.status in ["running", "paused"]:
        raise HTTPException(status_code=400, detail="Cannot delete running or paused task")
    
    # 関連するレコードを削除
    
    # ScrapingTaskLogレコードを削除
    db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id
    ).delete()
    
    # メインのタスクレコードを削除
    db.delete(db_task)
    db.commit()
    
    return {"message": "Task deleted successfully"}


@router.get("/scraping/tasks/{task_id}")
def get_single_task(task_id: str, db: Session = Depends(get_db)):
    """特定のタスクの詳細を取得"""
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
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
    
    # ScrapingTaskLogテーブルからログを取得（get_all_scraping_tasksと同じ方法）
    property_logs = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id,
        ScrapingTaskLog.log_type == 'property_update'
    ).all()
    error_logs = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id,
        ScrapingTaskLog.log_type == 'error'
    ).all()
    warning_logs = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id,
        ScrapingTaskLog.log_type == 'warning'
    ).all()
    
    # ログをフォーマット
    logs = [log.details if log.details else {"message": log.message} for log in property_logs]
    error_logs_formatted = [log.details if log.details else {"message": log.message} for log in error_logs]
    warning_logs_formatted = [log.details if log.details else {"message": log.message} for log in warning_logs]
    
    return {
        'task_id': db_task.task_id,
        'type': 'parallel' if db_task.task_id.startswith('parallel_') else 'serial',
        'status': db_task.status,
        'scrapers': db_task.scrapers if isinstance(db_task.scrapers, list) else [],
        'area_codes': convert_area_codes_to_names(db_task.areas) if isinstance(db_task.areas, list) else [],
        'max_properties': db_task.max_properties,
        'started_at': db_task.started_at,
        'completed_at': db_task.completed_at,
        'progress': db_task.progress_detail if db_task.progress_detail else {},
        'errors': [],
        'logs': logs,
        'error_logs': error_logs_formatted,
        'warning_logs': warning_logs_formatted,
        'created_at': db_task.created_at,
        'statistics': {
            'total_processed': db_task.total_processed or 0,
            'total_new': db_task.total_new or 0,
            'total_updated': db_task.total_updated or 0,
            'total_errors': db_task.total_errors or 0,
            'elapsed_time': db_task.elapsed_time or 0
        },
        'force_detail_fetch': db_task.force_detail_fetch
    }


@router.get("/scraping/task/{task_id}/logs")
def get_task_logs(task_id: str, db: Session = Depends(get_db)):
    """タスクのログを取得"""
    # データベースからタスクを確認
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # データベースからログを取得
    logs = db.query(ScrapingTaskLog).filter(ScrapingTaskLog.task_id == task_id).all()
    
    property_logs = []
    error_logs = []
    warning_logs = []
    
    for log in logs:
        if log.log_type == 'property_update':
            property_logs.append(log.details if log.details else {"message": log.message})
        elif log.log_type == 'error':
            error_logs.append(log.details if log.details else {"message": log.message})
        elif log.log_type == 'warning':
            warning_logs.append(log.details if log.details else {"message": log.message})
    
    return {
        "task_id": task_id,
        "logs": property_logs,
        "error_logs": error_logs,
        "warning_logs": warning_logs
    }


@router.get("/scraping/tasks/{task_id}/debug")
def get_task_debug_info(task_id: str, db: Session = Depends(get_db)):
    """タスクのデバッグ情報を取得"""
    db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # ログの件数を取得
    log_count = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id,
        ScrapingTaskLog.log_type == 'property_update'
    ).count()
    error_count = db.query(ScrapingTaskLog).filter(
        ScrapingTaskLog.task_id == task_id,
        ScrapingTaskLog.log_type == 'error'
    ).count()
    
    return {
        "task_id": task_id,
        "status": db_task.status,
        "is_paused": db_task.is_paused,
        "is_cancelled": db_task.is_cancelled,
        "progress_count": len(db_task.progress_detail) if db_task.progress_detail else 0,
        "error_count": error_count,
        "log_count": log_count,
        "started_at": db_task.started_at,
        "completed_at": db_task.completed_at,
        "type": "parallel" if db_task.task_id.startswith("parallel_") else "serial"
    }


@router.delete("/scraping/all-tasks")
def delete_all_scraping_tasks(db: Session = Depends(get_db)):
    """全スクレイピングタスクを削除（実行中のタスクは除く）"""
    from ...models_scraping_task import ScrapingTask, ScrapingTaskLog
    
    # 削除対象のタスクIDを取得
    tasks_to_delete = db.query(ScrapingTask.task_id).filter(
        ScrapingTask.status.notin_(["running", "paused", "pending"])
    ).all()
    
    task_ids = [task.task_id for task in tasks_to_delete]
    deleted_db_count = len(task_ids)
    
    if task_ids:
        try:
            # 関連するレコードを削除
            
            # ScrapingTaskLogレコードを削除
            db.query(ScrapingTaskLog).filter(
                ScrapingTaskLog.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            
            # メインのタスクレコードを削除
            db.query(ScrapingTask).filter(
                ScrapingTask.task_id.in_(task_ids)
            ).delete(synchronize_session=False)
            
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Error deleting tasks from database: {e}")
            deleted_db_count = 0
    
    return {
        "message": f"Deleted {deleted_db_count} tasks from database",
        "deleted_count": deleted_db_count
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
    
    # 共通関数を使用してタスクを作成
    try:
        db_task = create_scraping_task(
            task_id=task_id,
            scrapers=request.scrapers,
            area_codes=request.area_codes,
            max_properties=request.max_properties,
            force_detail_fetch=request.force_detail_fetch,
            db=db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 並列スクレイピングとして実行
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
    
    return {
        "task_id": task_id,
        "status": "running",
        "scrapers": request.scrapers,
        "area_codes": request.area_codes,
        "max_properties": request.max_properties,
        "started_at": db_task.started_at.isoformat() if db_task.started_at else datetime.now().isoformat(),
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
def pause_parallel_scraping(task_id: str, db: Session = Depends(get_db)):
    """並列スクレイピングタスクを一時停止"""
    return pause_scraping(task_id, db)


@router.post("/scraping/resume-parallel/{task_id}")
def resume_parallel_scraping(task_id: str, db: Session = Depends(get_db)):
    """並列スクレイピングタスクを再開"""
    return resume_scraping(task_id, db)


@router.post("/scraping/cancel-parallel/{task_id}")
def cancel_parallel_scraping(task_id: str, db: Session = Depends(get_db)):
    """並列スクレイピングタスクをキャンセル"""
    return cancel_scraping(task_id, db)


@router.post("/scraping/force-cleanup")
def force_cleanup_tasks(db: Session = Depends(get_db)):
    """停滞したタスクを強制的にクリーンアップ"""
    from ...models_scraping_task import ScrapingTask
    
    cleaned_count = 0
    
    # データベースから実行中のタスクを取得
    running_tasks = db.query(ScrapingTask).filter(ScrapingTask.status == "running").all()
    
    for task in running_tasks:
        # 最終進捗更新から30分以上経過している場合
        # last_progress_atがある場合はそれを、ない場合はstarted_atを使用
        last_update = task.last_progress_at or task.started_at
        if last_update:
            if (datetime.now() - last_update).total_seconds() > 1800:
                task.status = "stalled"
                cleaned_count += 1
    
    if cleaned_count > 0:
        db.commit()
    
    return {"message": f"Cleaned up {cleaned_count} stalled tasks"}