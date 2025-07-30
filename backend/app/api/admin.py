"""
管理画面用APIエンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime
from backend.app.utils.exceptions import TaskPausedException, TaskCancelledException
from pydantic import BaseModel
import asyncio
import threading
import uuid
import time
import json
import os
from concurrent.futures import ThreadPoolExecutor

from backend.app.database import get_db
from backend.app.utils.debug_logger import debug_log
from backend.app.models import MasterProperty, PropertyListing, Building, ListingPriceHistory, PropertyMergeHistory, PropertyMergeExclusion, BuildingMergeHistory, BuildingExternalId
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
from sqlalchemy import func, or_, and_
from backend.app.auth import verify_admin_credentials

# 並列スクレイピングのインポート（エラー処理付き）
try:
    import sys
    import os
    # Docker環境での正しいパス設定
    # /app/backend/app/api/admin.py から /app/backend/scripts へ
    backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    scripts_path = os.path.join(backend_path, 'scripts')
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    
    # DB版を使用
    from backend.scripts.run_scrapers_parallel import ParallelScrapingManagerDB as ParallelScrapingManager
    PARALLEL_SCRAPING_ENABLED = True
    print(f"Successfully imported ParallelScrapingManagerDB (Database version) from {scripts_path}")
except ImportError as e:
    print(f"Warning: Could not import ParallelScrapingManagerDB: {e}")
    print(f"Attempted path: {scripts_path if 'scripts_path' in locals() else 'undefined'}")
    PARALLEL_SCRAPING_ENABLED = False
    ParallelScrapingManager = None

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(verify_admin_credentials)])

# タスクの永続化ファイル
# dataディレクトリに保存することで、コンテナ再起動後も保持される
TASKS_FILE = "/app/data/scraping_tasks.json"

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
# 環境変数から取得、デフォルトは30分
PAUSE_TIMEOUT_SECONDS = int(os.environ.get('SCRAPING_PAUSE_TIMEOUT', '1800'))

# スクレイパーインスタンスを保持（再開時に再利用）
scraper_instances: Dict[str, Any] = {}


def check_pause_timeout(task_id: str) -> bool:
    """一時停止のタイムアウトをチェックし、タイムアウトした場合はタスクをキャンセル"""
    # まず一時停止中かどうかを確認
    with flags_lock:
        pause_flag = task_pause_flags.get(task_id)
        if not pause_flag or not pause_flag.is_set():
            # 一時停止中でない場合は何もしない
            return False
    
    with tasks_lock:
        if task_id in task_pause_timestamps:
            elapsed_time = (datetime.now() - task_pause_timestamps[task_id]).total_seconds()
            if elapsed_time > PAUSE_TIMEOUT_SECONDS:
                print(f"[{task_id}] Pause timeout exceeded ({elapsed_time:.0f}s > {PAUSE_TIMEOUT_SECONDS}s). Cancelling task.")
                # タスクをキャンセル状態に変更
                if task_id in scraping_tasks:
                    scraping_tasks[task_id]["status"] = "cancelled"
                    scraping_tasks[task_id]["errors"].append(
                        f"タスクは一時停止タイムアウト（{PAUSE_TIMEOUT_SECONDS}秒）により自動的にキャンセルされました。"
                    )
                
                # タイムスタンプを削除
                del task_pause_timestamps[task_id]
    
                # フラグ操作は別のロックで保護
                with flags_lock:
                    # キャンセルフラグをセット
                    if task_id in task_cancel_flags:
                        task_cancel_flags[task_id].set()
                    
                    # 一時停止フラグをクリア
                    if task_id in task_pause_flags:
                        task_pause_flags[task_id].clear()
                
                # スクレイパーインスタンスをクリーンアップ
                cleanup_task_resources(task_id)
                
                return True
    
    return False


def cleanup_task_resources(task_id: str):
    """タスクに関連するリソースをクリーンアップ"""
    with instances_lock:
        # スクレイパーインスタンスを削除
        keys_to_delete = []
        for key in scraper_instances:
            if key.startswith(f"{task_id}_"):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            scraper = scraper_instances.get(key)
            if scraper:
                if hasattr(scraper, 'session'):
                    try:
                        scraper.session.close()
                    except:
                        pass
                if hasattr(scraper, 'http_session'):
                    try:
                        scraper.http_session.close()
                    except:
                        pass
                del scraper_instances[key]
                print(f"[{task_id}] Cleaned up scraper instance: {key}")


def save_tasks_to_file():
    """タスク情報をファイルに保存（シリアライズ可能なデータのみ）"""
    try:
        # シリアライズ可能なデータのみを抽出
        serializable_tasks = {}
        for task_id, task_data in scraping_tasks.items():
            serializable_task = {
                "task_id": task_data.get("task_id"),
                "status": task_data.get("status"),
                "scrapers": task_data.get("scrapers"),
                "area_codes": task_data.get("area_codes"),
                "max_properties": task_data.get("max_properties"),
                "started_at": task_data.get("started_at").isoformat() if task_data.get("started_at") else None,
                "completed_at": task_data.get("completed_at").isoformat() if task_data.get("completed_at") else None,
                "errors": task_data.get("errors", []),
                "progress": {}
            }
            
            # progressの各エントリをシリアライズ可能な形式に変換
            for progress_key, progress_data in task_data.get("progress", {}).items():
                serializable_progress = {
                    k: v for k, v in progress_data.items()
                    if k not in ["resume_state"]  # 大きなデータは除外
                }
                # resume_stateは別途処理（collected_propertiesを除外）
                if "resume_state" in progress_data and progress_data["resume_state"]:
                    resume_state = progress_data["resume_state"]
                    serializable_progress["resume_state"] = {
                        "phase": resume_state.get("phase"),
                        "current_page": resume_state.get("current_page"),
                        "processed_count": resume_state.get("processed_count"),
                        "stats": resume_state.get("stats", {}),
                        # collected_propertiesは大きすぎるので保存しない
                        # 代わりに収集済み物件数のみ保存
                        "collected_count": len(resume_state.get("collected_properties", []))
                    }
                serializable_task["progress"][progress_key] = serializable_progress
            
            serializable_tasks[task_id] = serializable_task
        
        with open(TASKS_FILE, 'w') as f:
            json.dump(serializable_tasks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving tasks to file: {e}")


def load_tasks_from_file():
    """ファイルからタスク情報を読み込み"""
    global scraping_tasks
    try:
        if os.path.exists(TASKS_FILE):
            with open(TASKS_FILE, 'r') as f:
                loaded_tasks = json.load(f)
            
            # 日付フィールドを復元
            for task_id, task_data in loaded_tasks.items():
                if task_data.get("started_at"):
                    task_data["started_at"] = datetime.fromisoformat(task_data["started_at"])
                if task_data.get("completed_at"):
                    task_data["completed_at"] = datetime.fromisoformat(task_data["completed_at"])
                
                # 実行中だったタスクはpaused状態に変更
                if task_data.get("status") == "running":
                    task_data["status"] = "paused"
                    print(f"[INIT] Task {task_id} was running, changed to paused")
                
                scraping_tasks[task_id] = task_data
            
            print(f"[INIT] Loaded {len(scraping_tasks)} tasks from file")
    except Exception as e:
        print(f"Error loading tasks from file: {e}")


# アプリケーション起動時にタスクを読み込み
load_tasks_from_file()


class DuplicateCandidate(BaseModel):
    """重複候補の物件ペア"""
    property1_id: int
    property2_id: int
    building_name: str
    floor_number: Optional[int]
    area: Optional[float]
    layout: Optional[str]
    direction1: Optional[str]
    direction2: Optional[str]
    price1: Optional[int]
    price2: Optional[int]
    agency1: Optional[str]
    agency2: Optional[str]
    room_number1: Optional[str]
    room_number2: Optional[str]
    similarity_score: float
    
    class Config:
        orm_mode = True


class PropertyDetail(BaseModel):
    """物件詳細情報"""
    id: int
    building_id: int
    building_name: str
    display_building_name: Optional[str]  # 物件独自の表示用建物名
    room_number: Optional[str]
    floor_number: Optional[int]
    area: Optional[float]
    layout: Optional[str]
    direction: Optional[str]
    listings: List[dict]
    
    class Config:
        orm_mode = True


class MergeRequest(BaseModel):
    """物件統合リクエスト"""
    primary_property_id: int
    secondary_property_id: int


@router.get("/duplicate-groups")
def get_duplicate_groups(
    min_similarity: float = 0.8,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """重複候補の物件グループを取得"""
    
    # 除外リストを取得
    exclusions = db.query(PropertyMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        excluded_pairs.add((exclusion.property1_id, exclusion.property2_id))
        excluded_pairs.add((exclusion.property2_id, exclusion.property1_id))
    
    # 重複候補を検出（グループ化用）
    query = text("""
        WITH property_details AS (
            SELECT 
                mp.id,
                mp.building_id,
                mp.room_number,
                mp.floor_number,
                mp.area,
                mp.layout,
                mp.direction,
                b.normalized_name as building_name,
                MAX(pl.current_price) as current_price,
                STRING_AGG(DISTINCT pl.agency_name, ', ') as agency_names,
                COUNT(DISTINCT pl.id) as listing_count,
                COUNT(DISTINCT pl.source_site) as source_count,
                bool_or(pl.is_active) as has_active_listing
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
            GROUP BY mp.id, mp.building_id, mp.room_number, mp.floor_number, mp.area, mp.layout, mp.direction, b.normalized_name
        )
        SELECT 
            pd.id,
            pd.building_id,
            pd.building_name,
            pd.room_number,
            pd.floor_number,
            pd.area,
            pd.layout,
            pd.direction,
            pd.current_price,
            pd.agency_names,
            pd.listing_count,
            pd.source_count,
            pd.has_active_listing,
            -- グループ識別用のキー
            pd.building_id || '-' || pd.floor_number || '-' || COALESCE(pd.layout, '') as group_key
        FROM property_details pd
        WHERE 
            -- 部屋番号がない物件のみ
            (pd.room_number IS NULL OR pd.room_number = '')
            -- アクティブな掲載がある
            AND pd.has_active_listing = true
        ORDER BY pd.building_name, pd.floor_number, pd.area
    """)
    
    result = db.execute(query)
    all_properties = list(result)
    
    # グループ化処理（処理済みの物件を追跡）
    groups = {}
    processed_properties = set()
    
    for i, prop in enumerate(all_properties):
        if prop.id in processed_properties:
            continue
            
        # 新しいグループを作成
        group_id = f"group_{len(groups) + 1}"
        group = [prop]
        processed_properties.add(prop.id)
        
        # 残りの物件から類似物件を探す
        for j in range(i + 1, len(all_properties)):
            other_prop = all_properties[j]
            if other_prop.id in processed_properties:
                continue
                
            # 類似度を計算
            similarity = calculate_similarity(prop, other_prop)
            if similarity >= min_similarity:
                # 除外ペアチェック
                if (prop.id, other_prop.id) not in excluded_pairs and (other_prop.id, prop.id) not in excluded_pairs:
                    # グループ内の他の物件とも類似度をチェック
                    can_add = True
                    for group_prop in group:
                        if (other_prop.id, group_prop.id) in excluded_pairs or (group_prop.id, other_prop.id) in excluded_pairs:
                            can_add = False
                            break
                        if calculate_similarity(other_prop, group_prop) < min_similarity:
                            can_add = False
                            break
                    
                    if can_add:
                        group.append(other_prop)
                        processed_properties.add(other_prop.id)
        
        groups[group_id] = group
    
    # 2件以上の物件を持つグループのみ返す
    duplicate_groups = []
    for group_id, properties in groups.items():
        if len(properties) >= 2:
            duplicate_groups.append({
                "group_id": group_id,
                "property_count": len(properties),
                "building_name": properties[0].building_name,
                "floor_number": properties[0].floor_number,
                "layout": properties[0].layout,
                "properties": sorted([
                    {
                        "id": p.id,
                        "room_number": p.room_number,
                        "area": p.area,
                        "direction": p.direction,
                        "current_price": p.current_price,
                        "agency_names": p.agency_names,
                        "listing_count": p.listing_count,
                        "source_count": p.source_count
                    }
                    for p in properties
                ], key=lambda x: (
                    # 1. 掲載数が多い順（重要な物件を優先）
                    -(x["listing_count"] or 0),
                    # 2. 価格がある物件を優先
                    0 if x["current_price"] else 1,
                    # 3. 価格順（安い順）
                    x["current_price"] or float('inf'),
                    # 4. 物件ID順（一定の順序を保証）
                    x["id"]
                ))
            })
    
    # 物件数の多い順にソート
    duplicate_groups.sort(key=lambda x: x["property_count"], reverse=True)
    
    return duplicate_groups[:limit]


def calculate_similarity(prop1, prop2):
    """2つの物件の類似度を計算"""
    # 同じ建物、同じ階
    if prop1.building_id != prop2.building_id or prop1.floor_number != prop2.floor_number:
        return 0.0
    
    # 間取りが同じ
    if prop1.layout != prop2.layout:
        return 0.0
    
    # 面積の差（より緩い条件に）
    area_diff = abs((prop1.area or 0) - (prop2.area or 0))
    if area_diff >= 1.0:  # 0.5から1.0に緩和
        return 0.7  # 完全に除外せず、低い類似度を返す
    
    # 方角の類似度
    if prop1.direction == prop2.direction:
        return 1.0
    elif prop1.direction and prop2.direction:
        if prop1.direction in prop2.direction or prop2.direction in prop1.direction:
            return 0.9
        else:
            return 0.8
    else:
        return 0.85  # 片方が方角情報なし


@router.get("/duplicate-candidates", response_model=List[DuplicateCandidate])
def get_duplicate_candidates(
    min_similarity: float = 0.8,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """重複候補の物件ペアを取得"""
    
    # 除外リストを取得
    exclusions = db.query(PropertyMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        # 両方向の組み合わせを除外
        excluded_pairs.add((exclusion.property1_id, exclusion.property2_id))
        excluded_pairs.add((exclusion.property2_id, exclusion.property1_id))
    
    # 類似物件を検出するクエリ
    query = text("""
        WITH property_details AS (
            SELECT 
                mp.id,
                mp.building_id,
                mp.room_number,
                mp.floor_number,
                mp.area,
                mp.layout,
                mp.direction,
                b.normalized_name as building_name,
                MAX(pl.current_price) as current_price,
                MAX(pl.agency_name) as agency_name,
                COUNT(pl.id) > 0 as has_active_listing
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            LEFT JOIN property_listings pl ON mp.id = pl.master_property_id AND pl.is_active = true
            GROUP BY mp.id, mp.building_id, mp.room_number, mp.floor_number, mp.area, mp.layout, mp.direction, b.normalized_name
        )
        SELECT 
            pd1.id as property1_id,
            pd2.id as property2_id,
            pd1.building_name,
            pd1.floor_number,
            pd1.area,
            pd1.layout,
            pd1.direction as direction1,
            pd2.direction as direction2,
            pd1.current_price as price1,
            pd2.current_price as price2,
            pd1.agency_name as agency1,
            pd2.agency_name as agency2,
            pd1.room_number as room_number1,
            pd2.room_number as room_number2,
            pd1.has_active_listing as has_active_listing1,
            pd2.has_active_listing as has_active_listing2,
            CASE 
                -- 同じ建物、同じ階、同じ面積、同じ間取り
                WHEN pd1.building_id = pd2.building_id 
                    AND pd1.floor_number = pd2.floor_number 
                    AND ABS(COALESCE(pd1.area, 0) - COALESCE(pd2.area, 0)) < 0.5
                    AND pd1.layout = pd2.layout 
                THEN 
                    CASE
                        -- 方角が完全一致
                        WHEN pd1.direction = pd2.direction THEN 1.0
                        -- 方角が似ている（片方が他方を含む）
                        WHEN pd1.direction LIKE '%' || pd2.direction || '%' 
                            OR pd2.direction LIKE '%' || pd1.direction || '%' THEN 0.9
                        -- 方角が異なる
                        ELSE 0.8
                    END
                ELSE 0.0
            END as similarity_score
        FROM property_details pd1
        JOIN property_details pd2 ON 
            pd1.building_id = pd2.building_id 
            AND pd1.id < pd2.id
        WHERE 
            -- 部屋番号がない物件のみ対象（NULLまたは空文字列）
            (pd1.room_number IS NULL OR pd1.room_number = '')
            AND (pd2.room_number IS NULL OR pd2.room_number = '')
            -- 同じ階
            AND pd1.floor_number = pd2.floor_number
            -- 面積が近い（誤差0.5㎡以内）
            AND ABS(COALESCE(pd1.area, 0) - COALESCE(pd2.area, 0)) < 0.5
            -- 同じ間取り
            AND pd1.layout = pd2.layout
            -- 両方とも掲載情報を持っている（販売終了物件同士の比較を除外）
            AND pd1.has_active_listing = true 
            AND pd2.has_active_listing = true
        ORDER BY similarity_score DESC, pd1.building_name, pd1.floor_number
        LIMIT :limit
    """)
    
    result = db.execute(query, {"limit": limit})
    candidates = []
    
    for row in result:
        # 除外リストに含まれていたらスキップ
        if (row.property1_id, row.property2_id) in excluded_pairs:
            continue
            
        if row.similarity_score >= min_similarity:
            candidates.append(DuplicateCandidate(
                property1_id=row.property1_id,
                property2_id=row.property2_id,
                building_name=row.building_name,
                floor_number=row.floor_number,
                area=row.area,
                layout=row.layout,
                direction1=row.direction1,
                direction2=row.direction2,
                price1=row.price1,
                price2=row.price2,
                agency1=row.agency1,
                agency2=row.agency2,
                room_number1=row.room_number1,
                room_number2=row.room_number2,
                similarity_score=row.similarity_score
            ))
    
    return candidates


@router.get("/properties/search")
def search_properties_for_merge(
    query: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """物件をIDまたは建物名で検索（統合用）"""
    results = []
    
    # まずIDで検索を試みる
    if query.isdigit():
        property_id = int(query)
        property_data = db.query(MasterProperty).filter(
            MasterProperty.id == property_id
        ).first()
        
        if property_data:
            building = db.query(Building).filter(
                Building.id == property_data.building_id
            ).first()
            
            # アクティブな掲載情報を取得
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id,
                PropertyListing.is_active == True
            ).all()
            
            # 最低価格を取得
            min_price = None
            if active_listings:
                prices = [l.current_price for l in active_listings if l.current_price]
                if prices:
                    min_price = min(prices)
            
            results.append({
                "id": property_data.id,
                "building_id": property_data.building_id,
                "building_name": building.normalized_name if building else "不明",
                "room_number": property_data.room_number,
                "floor_number": property_data.floor_number,
                "area": property_data.area,
                "layout": property_data.layout,
                "direction": property_data.direction,
                "current_price": min_price,
                "listing_count": len(active_listings)
            })
    
    # 建物名で検索
    # スペースで分割してAND検索 または スペースを除去した検索
    search_terms = query.replace('　', ' ').split()
    
    name_query = db.query(MasterProperty).join(
        Building, MasterProperty.building_id == Building.id
    )
    
    if len(search_terms) > 1:
        # 複数の検索語がある場合
        # 1. 各単語を含む建物を検索（AND条件）
        # 2. スペースを除去した全体文字列でも検索（OR条件）
        
        # AND検索条件
        and_conditions = []
        for term in search_terms:
            and_conditions.append(Building.normalized_name.ilike(f"%{term}%"))
        
        # スペースを除去した検索
        search_no_space = query.replace(' ', '').replace('　', '')
        
        # 複合条件
        name_query = name_query.filter(
            or_(
                and_(*and_conditions),  # 全ての単語を含む
                Building.normalized_name.ilike(f"%{search_no_space}%")  # スペースを除去した文字列に一致
            )
        )
    else:
        # 単一の検索語の場合
        name_query = name_query.filter(
            Building.normalized_name.ilike(f"%{query}%")
        )
    
    properties = name_query.limit(limit).all()
    
    for property_data in properties:
        # 既にIDで見つかった物件は除外
        if not any(r["id"] == property_data.id for r in results):
            building = db.query(Building).filter(
                Building.id == property_data.building_id
            ).first()
            
            # アクティブな掲載情報を取得
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id,
                PropertyListing.is_active == True
            ).all()
            
            # 最低価格を取得
            min_price = None
            if active_listings:
                prices = [l.current_price for l in active_listings if l.current_price]
                if prices:
                    min_price = min(prices)
            
            results.append({
                "id": property_data.id,
                "building_id": property_data.building_id,
                "building_name": building.normalized_name if building else "不明",
                "room_number": property_data.room_number,
                "floor_number": property_data.floor_number,
                "area": property_data.area,
                "layout": property_data.layout,
                "direction": property_data.direction,
                "current_price": min_price,
                "listing_count": len(active_listings)
            })
    
    return {
        "properties": results,
        "total": len(results)
    }


@router.get("/properties/{property_id}", response_model=PropertyDetail)
def get_property_detail_for_admin(property_id: int, db: Session = Depends(get_db)):
    """管理画面用の物件詳細情報を取得"""
    
    # 物件情報を取得
    property = db.query(MasterProperty).filter(
        MasterProperty.id == property_id
    ).first()
    
    if not property:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # 建物情報を取得
    building = db.query(Building).filter(
        Building.id == property.building_id
    ).first()
    
    # 掲載情報を取得（アクティブなもののみ）
    listings = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == property_id,
        PropertyListing.is_active == True
    ).all()
    
    # レスポンスを構築
    listing_data = []
    for listing in listings:
        listing_data.append({
            "id": listing.id,
            "source_site": listing.source_site,
            "url": listing.url,
            "title": listing.title,
            "current_price": listing.current_price,
            "agency_name": listing.agency_name,
            "is_active": listing.is_active,
            "last_scraped_at": listing.last_scraped_at.isoformat() if listing.last_scraped_at else None
        })
    
    return PropertyDetail(
        id=property.id,
        building_id=property.building_id,
        building_name=building.normalized_name,
        display_building_name=property.display_building_name,
        room_number=property.room_number,
        floor_number=property.floor_number,
        area=property.area,
        layout=property.layout,
        direction=property.direction,
        listings=listing_data
    )


@router.post("/merge-properties")
def merge_properties(
    merge_request: MergeRequest,
    db: Session = Depends(get_db)
):
    """2つの物件を統合"""
    
    # 物件を取得
    primary = db.query(MasterProperty).get(merge_request.primary_property_id)
    secondary = db.query(MasterProperty).get(merge_request.secondary_property_id)
    
    if not primary or not secondary:
        raise HTTPException(status_code=404, detail="One or both properties not found")
    
    # 同じ建物でない場合は警告
    if primary.building_id != secondary.building_id:
        raise HTTPException(
            status_code=400, 
            detail="Cannot merge properties from different buildings"
        )
    
    try:
        # 統合前の副物件の情報をバックアップ
        secondary_backup = {
            "id": secondary.id,
            "building_id": secondary.building_id,
            "room_number": secondary.room_number,
            "floor_number": secondary.floor_number,
            "area": secondary.area,
            "balcony_area": secondary.balcony_area,
            "layout": secondary.layout,
            "direction": secondary.direction,
            "summary_remarks": secondary.summary_remarks,
            "property_hash": secondary.property_hash
        }
        
        # 副物件の掲載情報を主物件に移動
        listings = db.query(PropertyListing).filter(
            PropertyListing.master_property_id == merge_request.secondary_property_id
        ).all()
        
        merged_count = 0
        moved_listings_info = []
        
        for listing in listings:
            # 同じソースサイトの掲載が既に存在するかチェック
            existing = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == merge_request.primary_property_id,
                PropertyListing.source_site == listing.source_site,
                PropertyListing.site_property_id == listing.site_property_id
            ).first()
            
            if existing:
                # 既存の掲載がある場合は、より新しい情報を保持
                if listing.last_scraped_at > existing.last_scraped_at:
                    # 既存の掲載の価格履歴を新しい掲載に移動
                    db.execute(text(
                        "UPDATE listing_price_history SET property_listing_id = :new_id "
                        "WHERE property_listing_id = :old_id"
                    ), {"new_id": listing.id, "old_id": existing.id})
                    
                    # 既存の掲載の画像も移動
                    db.execute(text(
                        "UPDATE property_images SET property_listing_id = :new_id "
                        "WHERE property_listing_id = :old_id"
                    ), {"new_id": listing.id, "old_id": existing.id})
                    
                    # 古い掲載を削除
                    db.delete(existing)
                    db.flush()
                    
                    # 新しい掲載を主物件に紐付け
                    listing.master_property_id = merge_request.primary_property_id
                    merged_count += 1
                    moved_listings_info.append({
                        "listing_id": listing.id,
                        "source_site": listing.source_site,
                        "url": listing.url
                    })
                else:
                    # 古い情報なので削除（まず価格履歴と画像を削除）
                    db.execute(text(
                        "DELETE FROM listing_price_history WHERE property_listing_id = :listing_id"
                    ), {"listing_id": listing.id})
                    db.execute(text(
                        "DELETE FROM property_images WHERE property_listing_id = :listing_id"
                    ), {"listing_id": listing.id})
                    db.delete(listing)
                    merged_count += 1  # 既存の掲載を保持した場合もカウント
            else:
                # 掲載を主物件に移動
                listing.master_property_id = merge_request.primary_property_id
                merged_count += 1
                moved_listings_info.append({
                    "listing_id": listing.id,
                    "source_site": listing.source_site,
                    "url": listing.url
                })
        
        # 主物件の情報を更新（より詳細な情報で）
        primary_updates = {}
        if not primary.floor_number and secondary.floor_number:
            primary.floor_number = secondary.floor_number
            primary_updates["floor_number"] = secondary.floor_number
        if not primary.area and secondary.area:
            primary.area = secondary.area
            primary_updates["area"] = secondary.area
        if not primary.layout and secondary.layout:
            primary.layout = secondary.layout
            primary_updates["layout"] = secondary.layout
        if not primary.direction and secondary.direction:
            primary.direction = secondary.direction
            primary_updates["direction"] = secondary.direction
        if not primary.room_number and secondary.room_number:
            primary.room_number = secondary.room_number
            primary_updates["room_number"] = secondary.room_number
        
        # プロパティが更新された場合、property_hashを再生成
        if primary_updates:
            from backend.app.scrapers.base_scraper import BaseScraper
            scraper = BaseScraper("ADMIN")
            scraper.session = db
            
            # 新しいハッシュを生成（部屋番号は使用しない新しいロジック）
            new_hash = scraper.generate_property_hash(
                primary.building_id,
                primary.room_number,  # 引数として渡すが、実際には使用されない
                primary.floor_number,
                primary.area,
                primary.layout,
                primary.direction
            )
            primary.property_hash = new_hash
            primary_updates["property_hash"] = new_hash
        
        # 統合履歴を記録
        merge_history = PropertyMergeHistory(
            primary_property_id=merge_request.primary_property_id,
            secondary_property_id=merge_request.secondary_property_id,
            moved_listings=merged_count,
            merge_details={
                "secondary_property": secondary_backup,
                "moved_listings": moved_listings_info,
                "primary_updates": primary_updates
            },
            merged_by="admin"  # TODO: 実際のユーザー名を記録
        )
        db.add(merge_history)
        
        # すべての変更をフラッシュしてから副物件を削除
        db.flush()
        
        # 副物件を参照している再販物件の参照を更新
        # 副物件が他の物件から再販物件として参照されている場合、主物件を参照するように更新
        db.execute(text("""
            UPDATE master_properties 
            SET resale_property_id = :primary_id 
            WHERE resale_property_id = :secondary_id
        """), {
            "primary_id": merge_request.primary_property_id,
            "secondary_id": merge_request.secondary_property_id
        })
        
        # 統合履歴の更新
        # 副物件が以前の統合でprimary_property_idとして記録されている場合、主物件に更新
        db.execute(text("""
            UPDATE property_merge_history 
            SET primary_property_id = :primary_id 
            WHERE primary_property_id = :secondary_id
        """), {
            "primary_id": merge_request.primary_property_id,
            "secondary_id": merge_request.secondary_property_id
        })
        
        # 副物件に関連する残りのデータを削除（外部キー制約を回避）
        # 1. 残っている価格履歴を削除
        db.execute(text("""
            DELETE FROM listing_price_history 
            WHERE property_listing_id IN (
                SELECT id FROM property_listings 
                WHERE master_property_id = :property_id
            )
        """), {"property_id": merge_request.secondary_property_id})
        
        # 2. 残っている画像を削除
        db.execute(text("""
            DELETE FROM property_images 
            WHERE property_listing_id IN (
                SELECT id FROM property_listings 
                WHERE master_property_id = :property_id
            )
        """), {"property_id": merge_request.secondary_property_id})
        
        # 3. 残っている掲載情報を削除
        db.execute(text(
            "DELETE FROM property_listings WHERE master_property_id = :property_id"
        ), {"property_id": merge_request.secondary_property_id})
        
        # 変更を再度フラッシュ
        db.flush()
        
        # 副物件を削除
        db.delete(secondary)
        
        # 多数決による物件情報更新
        from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
        updater = MajorityVoteUpdater(db)
        updater.update_master_property_by_majority(primary)
        
        # 建物情報と建物名も多数決で更新（物件統合により掲載情報が変わったため）
        if primary.building_id:
            building = db.query(Building).get(primary.building_id)
            if building:
                updater.update_building_by_majority(building)
            updater.update_building_name_by_majority(primary.building_id)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Successfully merged property {merge_request.secondary_property_id} into {merge_request.primary_property_id}",
            "merged_listings": merged_count,
            "history_id": merge_history.id
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_detail = f"Error merging properties: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # ログに出力
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/merge-properties-batch")
def merge_properties_batch(
    merge_requests: List[MergeRequest],
    db: Session = Depends(get_db)
):
    """複数の物件統合を一括実行"""
    
    results = []
    
    for request in merge_requests:
        try:
            result = merge_properties(request, db)
            results.append({
                "primary_id": request.primary_property_id,
                "secondary_id": request.secondary_property_id,
                "success": True,
                "message": result["message"]
            })
        except Exception as e:
            results.append({
                "primary_id": request.primary_property_id,
                "secondary_id": request.secondary_property_id,
                "success": False,
                "error": str(e)
            })
    
    return {"results": results}


class ScrapingRequest(BaseModel):
    """スクレイピングリクエスト"""
    scrapers: List[str]  # ["suumo", "homes", "rehouse", "nomu", "livable"]
    area_codes: List[str] = ["13103"]  # デフォルト: 港区
    max_properties: int = 100  # 各スクレイパー・各エリアで取得する最大件数


class ScrapingTaskStatus(BaseModel):
    """スクレイピングタスクの状態"""
    task_id: str
    type: Optional[str] = "serial"  # "serial" or "parallel"
    status: str  # "pending", "running", "paused", "completed", "failed", "cancelled"
    scrapers: List[str]
    area_codes: List[str]
    max_properties: int
    started_at: datetime
    completed_at: Optional[datetime]
    progress: Dict[str, Dict[str, Any]]  # 各スクレイパー・エリアの進行状況
    errors: List[str]
    logs: Optional[List[Dict[str, Any]]] = []  # 詳細ログ
    error_logs: Optional[List[Dict[str, Any]]] = []  # エラーログ


def run_scraping_task(task_id: str, scrapers: List[str], area_codes: List[str], max_properties: int):
    """バックグラウンドでスクレイピングを実行"""
    import subprocess
    import json
    
    print(f"[{task_id}] Starting run_scraping_task with scrapers={scrapers}, areas={area_codes}")
    
    # キャンセルフラグの初期状態をチェック
    cancel_flag = task_cancel_flags.get(task_id)
    if cancel_flag:
        print(f"[{task_id}] Cancel flag exists at start: {cancel_flag.is_set()}")
    else:
        print(f"[{task_id}] No cancel flag found at start!")
    
    # タスク状態を更新
    scraping_tasks[task_id]["status"] = "running"
    
    # スクレイパーのインポート（エラーハンドリングを分離）
    try:
        from backend.app.scrapers.suumo_scraper import SuumoScraper
        from backend.app.scrapers.homes_scraper import HomesScraper
        from backend.app.scrapers.rehouse_scraper import RehouseScraper
        from backend.app.scrapers.nomu_scraper import NomuScraper
        from backend.app.scrapers.livable_scraper import LivableScraper
        # エリア変換は各スクレイパー内部で実施するため不要
    except Exception as e:
        scraping_tasks[task_id]["status"] = "failed"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        scraping_tasks[task_id]["errors"].append(f"Failed to import scrapers: {str(e)}")
        print(f"[{task_id}] Import Error: {e}")
        return
    
    # スクレイピングの実行
    try:
        scraper_classes = {
            "suumo": SuumoScraper,
            "homes": HomesScraper,
            "rehouse": RehouseScraper,
            "nomu": NomuScraper,
            "livable": LivableScraper
        }
        
        # エリア名のマッピング（逆引き用）
        area_names = {code: name for name, code in AREA_CODES.items()}
        
        total_combinations = len(scrapers) * len(area_codes)
        completed_combinations = 0
        
        # グローバルのscraper_instancesを使用
        
        # 再開ポイントの復元
        resume_point = scraping_tasks[task_id].get("resume_point", {"scraper_index": 0, "area_index": 0})
        scraper_index = resume_point.get("scraper_index", 0)
        
        while scraper_index < len(scrapers):
            scraper_name = scrapers[scraper_index]
            if scraper_name not in scraper_classes:
                error_msg = f"Unknown scraper: {scraper_name}"
                scraping_tasks[task_id]["errors"].append(error_msg)
                scraper_index += 1
                continue
                
            # 再開時は保存されていたarea_indexから開始
            area_index = resume_point.get("area_index", 0) if scraper_index == resume_point.get("scraper_index", 0) else 0
            while area_index < len(area_codes):
                area_code = area_codes[area_index]
                
                # キャンセルチェック（一時停止はスクレイパー内部で処理）
                cancel_flag = task_cancel_flags.get(task_id)
                if cancel_flag and cancel_flag.is_set():
                    scraping_tasks[task_id]["status"] = "cancelled"
                    scraping_tasks[task_id]["completed_at"] = datetime.now()
                    print(f"[{task_id}] Task cancelled by user")
                    raise TaskCancelledException("Task cancelled by user")
                
                # 進行状況のキーを作成（スクレイパー名_エリアコード）
                progress_key = f"{scraper_name}_{area_code}"
                area_name = area_names.get(area_code, area_code)
                
                # 現在処理中の組み合わせを記録
                scraping_tasks[task_id]["current_combination"] = {
                    "scraper": scraper_name,
                    "area": area_code,
                    "progress_key": progress_key
                }
                
                try:
                    # 既存の進行状況を確認（一時停止から再開の場合）
                    existing_progress = scraping_tasks[task_id]["progress"].get(progress_key, {})
                    was_paused = existing_progress.get("status") == "paused"
                    
                    # スクレイパーの進行状況を初期化（既存の状態を保持）
                    if not existing_progress:
                        # 新規の場合は初期化
                        scraping_tasks[task_id]["progress"][progress_key] = {
                            "scraper": scraper_name,
                            "area_code": area_code,
                            "area_name": area_name,
                            "status": "running",
                            "properties_scraped": 0,
                            "new_listings": 0,
                            "updated_listings": 0,
                            "skipped_listings": 0,
                            # 詳細統計
                            "properties_found": 0,  # 一覧から取得した物件数
                            "properties_attempted": 0,  # 処理を試みた物件数
                            "detail_fetched": 0,  # 詳細取得成功数
                            "detail_fetch_failed": 0,  # 詳細ページ取得失敗数
                            "price_missing": 0,  # 価格情報なし
                            "building_info_missing": 0,  # 建物情報不足
                            "other_errors": 0,  # その他のエラー
                            "started_at": datetime.now().isoformat(),
                            "completed_at": None,
                            "error": None
                        }
                    else:
                        # 既存の場合はステータスのみ更新（他の統計は保持）
                        scraping_tasks[task_id]["progress"][progress_key]["status"] = "running"
                    
                    # スクレイピング実行
                    scraper_class = scraper_classes[scraper_name]
                    print(f"[{task_id}] Starting {scraper_name} scraper for {area_name} ({area_code})")
                    
                    # プログレスを更新する関数を定義
                    def update_progress(count, new_count=0, updated_count=0, skipped_count=0):
                        scraping_tasks[task_id]["progress"][progress_key]["properties_scraped"] = count
                        scraping_tasks[task_id]["progress"][progress_key]["new_listings"] = new_count
                        scraping_tasks[task_id]["progress"][progress_key]["updated_listings"] = updated_count
                        scraping_tasks[task_id]["progress"][progress_key]["skipped_listings"] = skipped_count
                        if count % 10 == 0:
                            print(f"[{task_id}] Progress: {progress_key} - {count}/{max_properties} properties (new: {new_count}, updated: {updated_count}, skipped: {skipped_count})")
                    
                    # 詳細統計を更新する関数
                    def update_detail_stats(**kwargs):
                        for key, value in kwargs.items():
                            if key in scraping_tasks[task_id]["progress"][progress_key]:
                                scraping_tasks[task_id]["progress"][progress_key][key] = value
                    
                    # 統計管理はスクレイパー側に委任（二重管理を避ける）
                    
                    # スクレイパーインスタンスを取得または作成
                    # task_idを含めて、タスクごとに独立したインスタンスを使用
                    instance_key = f"{task_id}_{scraper_name}_{area_code}"
                    if instance_key in scraper_instances:
                        # 保存されたインスタンスを再利用
                        scraper = scraper_instances[instance_key]
                        print(f"[{task_id}] Reusing existing scraper instance for {scraper_name} in {area_name}")
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
                        # 新しいインスタンスを作成
                        scraper = scraper_class(max_properties=max_properties)
                        scraper_instances[instance_key] = scraper
                    
                    # 一時停止・キャンセルフラグを設定（同じフラグオブジェクトを確実に使用）
                    # 重要：既存インスタンスの場合もフラグを更新する必要がある
                    scraper.pause_flag = task_pause_flags.get(task_id)
                    scraper.cancel_flag = task_cancel_flags.get(task_id)
                    print(f"[{task_id}] Scraper {scraper_name} for {area_code} - Pause flag ID: {id(scraper.pause_flag) if scraper.pause_flag else 'None'}")
                    if scraper.pause_flag:
                        print(f"[{task_id}] Pause flag is_set: {scraper.pause_flag.is_set()}")
                    
                    # ステータス更新用のコールバック関数を設定
                    def update_status(status):
                        print(f"[CALLBACK] Updating status for task {task_id}, progress_key={progress_key}: {status}")
                        scraping_tasks[task_id]["status"] = status
                        if status == "paused":
                            scraping_tasks[task_id]["progress"][progress_key]["status"] = "paused"
                        elif status == "running":
                            scraping_tasks[task_id]["progress"][progress_key]["status"] = "running"
                    
                    scraper.update_status_callback = update_status
                    
                    try:
                        # ページ取得メソッドをオーバーライド（一時停止チェックを追加）
                        # 既にオーバーライドされていない場合のみ適用
                        if not hasattr(scraper, '_fetch_page_overridden'):
                            original_fetch_page = scraper.fetch_page
                            
                            def fetch_page_with_pause_check(url):
                                # 一時停止チェック（待機方式）
                                if scraper.pause_flag and scraper.pause_flag.is_set():
                                    print(f"[{task_id}] Paused in fetch_page, waiting...")
                                    debug_log(f"[{task_id}] fetch_pageで一時停止検出。待機開始...")
                                    wait_count = 0
                                    while scraper.pause_flag.is_set():
                                        if scraper.cancel_flag and scraper.cancel_flag.is_set():
                                            print(f"[{task_id}] Cancelled during pause in fetch_page")
                                            raise TaskCancelledException("Task cancelled")
                                        time.sleep(0.1)
                                        wait_count += 1
                                        if wait_count % 50 == 0:  # 5秒ごとにログ
                                            debug_log(f"[{task_id}] fetch_page待機中... {wait_count/10}秒経過")
                                    print(f"[{task_id}] Resumed in fetch_page after {wait_count/10} seconds")
                                    debug_log(f"[{task_id}] fetch_pageで一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
                                
                                # キャンセルチェック
                                if scraper.cancel_flag and scraper.cancel_flag.is_set():
                                    print(f"[{task_id}] Cancelled in fetch_page")
                                    raise TaskCancelledException("Task cancelled")
                                
                                return original_fetch_page(url)
                            
                            scraper.fetch_page = fetch_page_with_pause_check
                            scraper._fetch_page_overridden = True
                        
                        # create_or_update_listingメソッドをオーバーライド（ログ記録のみ、統計は二重管理しない）
                        # 既にオーバーライドされていない場合のみ適用
                        if not hasattr(scraper, '_create_or_update_overridden'):
                            original_create_or_update = scraper.create_or_update_listing
                        
                            def create_or_update_with_logging(*args, **kwargs):
                                # 一時停止チェック（待機方式）
                                if scraper.pause_flag and scraper.pause_flag.is_set():
                                    print(f"[{task_id}] Paused in create_or_update_listing, waiting...")
                                    debug_log(f"[{task_id}] create_or_update_listingで一時停止検出。待機開始...")
                                    wait_count = 0
                                    while scraper.pause_flag.is_set():
                                        if scraper.cancel_flag and scraper.cancel_flag.is_set():
                                            print(f"[{task_id}] Cancelled during pause in create_or_update_listing")
                                            raise TaskCancelledException("Task cancelled")
                                        time.sleep(0.1)
                                        wait_count += 1
                                        if wait_count % 50 == 0:  # 5秒ごとにログ
                                            debug_log(f"[{task_id}] create_or_update_listing待機中... {wait_count/10}秒経過")
                                    print(f"[{task_id}] Resumed in create_or_update_listing after {wait_count/10} seconds")
                                    debug_log(f"[{task_id}] create_or_update_listingで一時停止解除。処理を再開... (待機時間: {wait_count/10}秒)")
                                
                                # キャンセルチェック
                                if scraper.cancel_flag and scraper.cancel_flag.is_set():
                                    print(f"[{task_id}] Cancelled in create_or_update_listing")
                                    raise TaskCancelledException("Task cancelled")
                                
                                # URLから既存の掲載を確認
                                url = args[1] if len(args) > 1 else kwargs.get('url')
                                existing = scraper.session.query(PropertyListing).filter_by(url=url).first()
                                
                                # 既存物件の価格を保存（ログ用）
                                old_price = existing.current_price if existing else None
                                
                                # 元のメソッドを実行
                                result = original_create_or_update(*args, **kwargs)
                                
                                # 物件情報を取得してログに記録
                                master_property = args[0] if len(args) > 0 else kwargs.get('master_property')
                                price = args[3] if len(args) > 3 else kwargs.get('price')
                                title = args[2] if len(args) > 2 else kwargs.get('title')
                                
                                # マスター物件から建物情報を取得
                                building_info = ""
                                if master_property and hasattr(master_property, 'building') and master_property.building:
                                    building = master_property.building
                                    building_info = f"{building.normalized_name}"
                                    if master_property.room_number:
                                        building_info += f" {master_property.room_number}"
                                    if master_property.floor_number:
                                        building_info += f" {master_property.floor_number}階"
                                
                                log_entry = {
                                    "timestamp": datetime.now().isoformat(),
                                    "type": "new" if not existing else "update",
                                    "scraper": scraper_name,
                                    "area": area_name,
                                    "url": url,
                                    "title": title or building_info,
                                    "price": price,
                                    "building_info": building_info
                                }
                                
                                # ログメッセージを作成（update_typeに基づく）
                                should_log = False
                                update_type = result[1] if isinstance(result, tuple) and len(result) > 1 else 'unknown'
                                
                                if update_type == 'new':
                                    log_entry["message"] = f"新規物件登録: {title} ({price}万円)"
                                    should_log = True
                                elif update_type == 'price_changed' or update_type == 'price_updated':
                                    if existing and old_price is not None:
                                        log_entry["message"] = f"価格更新: {title} ({old_price}万円 → {price}万円)"
                                        log_entry["price_change"] = {"old": old_price, "new": price}
                                    else:
                                        log_entry["message"] = f"価格更新: {title} (→ {price}万円)"
                                    should_log = True
                                elif update_type == 'other_updates':
                                    log_entry["message"] = f"その他の更新: {title} ({price}万円)"
                                    should_log = True
                                elif update_type == 'refetched_unchanged' or update_type == 'skipped':
                                    # 変更なしの場合、詳細をスキップした場合はログに記録しない
                                    pass
                                
                                # ログを追加（価格変更または新規物件のみ、最新50件のみ保持）
                                if should_log:
                                    if "logs" not in scraping_tasks[task_id]:
                                        scraping_tasks[task_id]["logs"] = []
                                    scraping_tasks[task_id]["logs"].append(log_entry)
                                    if len(scraping_tasks[task_id]["logs"]) > 50:
                                        scraping_tasks[task_id]["logs"] = scraping_tasks[task_id]["logs"][-50:]
                                
                                return result
                            
                            scraper.create_or_update_listing = create_or_update_with_logging
                            scraper._create_or_update_overridden = True
                        
                        # エラーログ記録用のメソッドを追加（未設定の場合のみ）
                        if not hasattr(scraper, '_save_error_log'):
                            def save_error_log(error_info):
                                if "error_logs" not in scraping_tasks[task_id]:
                                    scraping_tasks[task_id]["error_logs"] = []
                                
                                error_log = {
                                    "timestamp": error_info.get('timestamp', datetime.now().isoformat()),
                                    "scraper": scraper_name,
                                    "area": area_name,
                                    "url": error_info.get('url', ''),
                                    "reason": error_info.get('reason', ''),
                                    "building_name": error_info.get('building_name', ''),
                                    "price": error_info.get('price', ''),
                                    "message": f"保存失敗: {error_info.get('reason', '不明')} - URL: {error_info.get('url', '不明')}"
                                }
                                
                                scraping_tasks[task_id]["error_logs"].append(error_log)
                                # 最新30件のみ保持
                                if len(scraping_tasks[task_id]["error_logs"]) > 30:
                                    scraping_tasks[task_id]["error_logs"] = scraping_tasks[task_id]["error_logs"][-30:]
                            
                            scraper._save_error_log = save_error_log
                        
                        # 詳細取得情報を保持するための属性
                        scraper._last_property_data = None
                        
                        # update_listing_from_listメソッドは既にスクレイパー本体で統計を記録しているので、
                        # ここでは何もしない（二重カウントを避ける）
                        
                        # save_propertyメソッドのオーバーライドは削除（統計の二重管理を避ける）
                        
                        # parse_property_detailメソッドのオーバーライドも削除（統計の二重管理を避ける）
                        
                        # parse_property_listメソッドのオーバーライドも削除（統計の二重管理を避ける）
                        
                        # スクレイピング実行
                        print(f"[{task_id}] Starting {scraper_name} scraper for {area_name} (max {max_properties} properties)")
                        
                        # デバッグ：スクレイパーのフラグ状態を確認
                        if hasattr(scraper, 'pause_flag') and scraper.pause_flag:
                            print(f"[{task_id}] DEBUG: Before scrape_area - pause_flag ID: {id(scraper.pause_flag)}, is_set: {scraper.pause_flag.is_set()}")
                        
                        # 統計更新用の別スレッドを開始
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
                                                "properties_scraped": current_stats.get('properties_processed', 0),  # 処理済み物件数
                                                "detail_fetched": current_stats.get('detail_fetched', 0),  # 詳細取得成功数
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
                                except Exception as e:
                                    print(f"[{task_id}] Error updating stats: {e}")
                                time_module.sleep(2)  # 2秒ごとに更新
                        
                        stats_thread = threading.Thread(target=update_stats_periodically)
                        stats_thread.daemon = True
                        stats_thread.start()
                        
                        # 進行状態を定期的に保存するスレッド
                        def save_resume_state():
                            while not stop_stats_update.is_set():
                                try:
                                    # 一時停止のタイムアウトをチェック
                                    if check_pause_timeout(task_id):
                                        # タイムアウトした場合はスレッドを終了
                                        print(f"[{task_id}] Pause timeout detected, stopping save_resume_state thread")
                                        break
                                    
                                    # 一時停止状態をチェック（フラグロックで保護）
                                    with flags_lock:
                                        pause_flag_set = task_pause_flags.get(task_id) and task_pause_flags[task_id].is_set()
                                    
                                    # ステータス更新（タスクロックで保護）
                                    with tasks_lock:
                                        if pause_flag_set:
                                            # 一時停止中の場合、ステータスを更新
                                            if (task_id in scraping_tasks and 
                                                scraping_tasks[task_id]["status"] != "paused"):
                                                scraping_tasks[task_id]["status"] = "paused"
                                                if progress_key in scraping_tasks[task_id]["progress"]:
                                                    scraping_tasks[task_id]["progress"][progress_key]["status"] = "paused"
                                                print(f"[{task_id}] Status updated to paused")
                                        else:
                                            # 一時停止が解除された場合、ステータスを更新
                                            if (task_id in scraping_tasks and 
                                                scraping_tasks[task_id]["status"] == "paused"):
                                                scraping_tasks[task_id]["status"] = "running"
                                                if progress_key in scraping_tasks[task_id]["progress"]:
                                                    scraping_tasks[task_id]["progress"][progress_key]["status"] = "running"
                                                print(f"[{task_id}] Status updated to running (resumed)")
                                    
                                    # レジューム状態の保存
                                    if hasattr(scraper, 'get_resume_state'):
                                        resume_state = scraper.get_resume_state()
                                        # collected_propertiesのサイズを確認
                                        collected_size = len(resume_state.get('collected_properties', []))
                                        if collected_size > 0:
                                            print(f"[{task_id}] Saving resume state with {collected_size} collected properties")
                                        
                                        # レジューム状態を保存（ロックで保護）
                                        with tasks_lock:
                                            if (task_id in scraping_tasks and 
                                                progress_key in scraping_tasks[task_id]["progress"]):
                                                scraping_tasks[task_id]["progress"][progress_key]["resume_state"] = resume_state
                                except Exception as e:
                                    print(f"[{task_id}] Error saving resume state: {e}")
                                time_module.sleep(5)  # 5秒ごとに保存
                        
                        resume_thread = threading.Thread(target=save_resume_state)
                        resume_thread.daemon = True
                        resume_thread.start()
                        
                        try:
                            # 再開状態を取得して設定
                            # was_pausedを使用して一時停止から再開かどうかを判定
                            if was_paused and instance_key in scraper_instances:
                                print(f"[{task_id}] Resuming from pause with existing scraper instance")
                                # スクレイパーの内部状態を確認
                                if hasattr(scraper, '_scraping_stats'):
                                    print(f"[{task_id}] Current scraper stats: phase={scraper._scraping_stats.get('phase')}, collected={len(getattr(scraper, '_collected_properties', []))}, processed={getattr(scraper, '_processed_count', 0)}")
                                    print(f"[{task_id}] Scraper internal stats: {scraper._scraping_stats}")
                                
                                # 一時停止から再開の場合、スクレイパーインスタンスは既に
                                # 最新の状態を保持しているため、set_resume_stateは呼ばない
                                print(f"[{task_id}] Using existing scraper instance with current state")
                            else:
                                # 新規開始または別のタスクから再開の場合
                                resume_state = scraping_tasks[task_id]["progress"][progress_key].get("resume_state")
                                if resume_state and hasattr(scraper, 'set_resume_state'):
                                    scraper.set_resume_state(resume_state)
                                    print(f"[{task_id}] Setting resume state for scraper")
                                    print(f"[{task_id}] Resume state details: phase={resume_state.get('phase')}, page={resume_state.get('current_page')}, collected={len(resume_state.get('collected_properties', []))}, processed={resume_state.get('processed_count', 0)}")
                            
                            # すべてのスクレイパーにエリアコードを渡す（変換は各スクレイパー内部で実施）
                            print(f"[{task_id}] Calling scraper.scrape_area({area_code})")
                            debug_log(f"[{task_id}] Calling scraper.scrape_area({area_code})")
                            scraper.scrape_area(area_code)
                            print(f"[{task_id}] scraper.scrape_area({area_code}) returned")
                            debug_log(f"[{task_id}] scraper.scrape_area({area_code}) returned")
                        finally:
                            # 統計更新スレッドを停止
                            stop_stats_update.set()
                            stats_thread.join(timeout=1)
                            resume_thread.join(timeout=1)
                        
                        # 完了（実際の取得件数を反映）
                        final_stats = scraper.get_scraping_stats()
                        final_count = final_stats.get('detail_fetched', 0)
                        
                        # キャンセルチェック（最終統計更新前）
                        cancel_flag = task_cancel_flags.get(task_id)
                        if cancel_flag and cancel_flag.is_set():
                            print(f"[{task_id}] Task cancelled before final update")
                            raise TaskCancelledException("Task cancelled")
                        
                        # 最終統計を確実に反映
                        final_update = {
                            "status": "completed",
                            "completed_at": datetime.now().isoformat(),
                            # 最終的な詳細統計を保存
                            "properties_found": final_stats.get('properties_found', 0),
                            "properties_processed": final_stats.get('properties_processed', 0),
                            "properties_attempted": final_stats.get('properties_attempted', 0),
                            "detail_fetched": final_stats.get('detail_fetched', 0),  # 詳細取得数
                            "detail_fetch_failed": final_stats.get('detail_fetch_failed', 0),
                            "price_missing": final_stats.get('price_missing', 0),
                            "building_info_missing": final_stats.get('building_info_missing', 0),
                            "other_errors": final_stats.get('other_errors', 0),
                            "properties_scraped": final_count,  # 詳細取得数を保存
                            "skipped_listings": final_stats.get('detail_skipped', 0),
                            "new_listings": final_stats.get('new_listings', 0),
                            "price_updated": final_stats.get('price_updated', 0),
                            "other_updates": final_stats.get('other_updates', 0),
                            "refetched_unchanged": final_stats.get('refetched_unchanged', 0),
                            "save_failed": final_stats.get('save_failed', 0)  # 保存失敗数を追加
                        }
                        
                        
                        scraping_tasks[task_id]["progress"][progress_key].update(final_update)
                        
                        completed_combinations += 1
                        print(f"[{task_id}] Completed {scraper_name} scraper for {area_name} ({completed_combinations}/{total_combinations})")
                        
                    except TaskPausedException:
                        # 一時停止された場合（新しい実装では発生しないはずだが、念のため残す）
                        print(f"[{task_id}] TaskPausedException caught (should not happen with new implementation)")
                        # 通常は発生しないはず
                        pass
                        
                    except TaskCancelledException:
                        # キャンセルされた場合は特別な処理
                        print(f"[{task_id}] Scraping cancelled for {scraper_name} in {area_name}")
                        scraping_tasks[task_id]["progress"][progress_key].update({
                            "status": "cancelled",
                            "completed_at": datetime.now().isoformat()
                        })
                        # キャンセルされたら例外を再スロー
                        raise
                    except Exception as e:
                        error_msg = f"Error in {scraper_name} for {area_name}: {str(e)}"
                        print(f"[{task_id}] {error_msg}")
                        scraping_tasks[task_id]["errors"].append(error_msg)
                        scraping_tasks[task_id]["progress"][progress_key].update({
                            "status": "failed",
                            "error": str(e),
                            "completed_at": datetime.now().isoformat()
                        })
                        completed_combinations += 1
                        
                    finally:
                        # スクレイパーのセッションをクリーンアップ
                        # 一時停止の場合はセッションとインスタンスを保持（再利用のため）
                        # タスク全体のステータスもチェック
                        task_status = scraping_tasks[task_id]["status"]
                        progress_status = scraping_tasks[task_id]["progress"][progress_key].get("status")
                        
                        # 一時停止フラグがセットされているかも確認
                        pause_flag = task_pause_flags.get(task_id)
                        is_paused = (task_status == "paused" or 
                                   progress_status == "paused" or 
                                   (pause_flag and pause_flag.is_set()))
                        
                        if not is_paused:
                            if hasattr(scraper, 'session'):
                                scraper.session.close()
                            if hasattr(scraper, 'http_session'):
                                scraper.http_session.close()
                            # インスタンスも削除
                            if instance_key in scraper_instances:
                                del scraper_instances[instance_key]
                                print(f"[{task_id}] Deleted scraper instance: {instance_key}")
                                debug_log(f"[{task_id}] Deleted scraper instance: {instance_key}")
                        else:
                            print(f"[{task_id}] Keeping scraper instance for resume: {instance_key}")
                            debug_log(f"[{task_id}] Keeping scraper instance for resume: {instance_key}, is_paused={is_paused}")
                
                except TaskCancelledException:
                    # タスクキャンセルの例外は再スロー
                    raise
                except TaskPausedException:
                    # 一時停止の例外は内部で処理されるので、ここには到達しないはず
                    print(f"[{task_id}] Unexpected TaskPausedException at outer level")
                    pass
                except Exception as outer_e:
                    # 外側のtryブロックのエラー処理
                    error_msg = f"Failed to process {scraper_name} for {area_name}: {str(outer_e)}"
                    print(f"[{task_id}] {error_msg}")
                    scraping_tasks[task_id]["errors"].append(error_msg)
                    scraping_tasks[task_id]["progress"][progress_key] = {
                        "scraper": scraper_name,
                        "area_code": area_code,
                        "area_name": area_name,
                        "status": "failed",
                        "error": str(outer_e),
                        "completed_at": datetime.now().isoformat()
                    }
                    completed_combinations += 1
                    # エラーの場合は次のエリアへ
                    area_index += 1
                else:
                    # 正常終了の場合のみ次のエリアへ
                    area_index += 1
            
            # 一時停止チェックは削除（スクレイパー内部で処理されるため）
            # スクレイパーループも継続し、各スクレイパー内部で待機する
            
            # 全エリア処理完了後、次のスクレイパーへ
            scraper_index += 1
        
        # タスク完了（一時停止中でない場合のみ）
        # 一時停止フラグがセットされている場合は、pausedステータスに設定
        pause_flag = task_pause_flags.get(task_id)
        if pause_flag and pause_flag.is_set():
            scraping_tasks[task_id]["status"] = "paused"
            print(f"[{task_id}] Task is paused, keeping status as 'paused'")
        elif scraping_tasks[task_id]["status"] not in ["cancelled", "paused"]:
            scraping_tasks[task_id]["status"] = "completed"
            scraping_tasks[task_id]["completed_at"] = datetime.now()
            
    except TaskCancelledException:
        # キャンセルされた場合
        scraping_tasks[task_id]["status"] = "cancelled"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        print(f"[{task_id}] Task cancelled")
        return
    except TaskPausedException:
        # 一時停止の場合（通常はここに到達しないはず）
        print(f"[{task_id}] TaskPausedException at top level - this should not happen")
        # ステータスをpausedに設定
        scraping_tasks[task_id]["status"] = "paused"
        return
    except Exception as e:
        scraping_tasks[task_id]["status"] = "failed"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        scraping_tasks[task_id]["errors"].append(f"Unexpected error during scraping: {str(e)}")
        print(f"[{task_id}] Unexpected Error: {e}")
        return
    finally:
        # 制御フラグをクリーンアップ（キャンセル時のみ）
        if scraping_tasks[task_id]["status"] in ["cancelled", "failed"]:
            if task_id in task_cancel_flags:
                del task_cancel_flags[task_id]
            if task_id in task_pause_flags:
                del task_pause_flags[task_id]
            if task_id in task_pause_timestamps:
                del task_pause_timestamps[task_id]


@router.post("/scraping/start", response_model=ScrapingTaskStatus)
def start_scraping(
    request: ScrapingRequest,
    background_tasks: BackgroundTasks
):
    """スクレイピングを開始"""
    # タスクIDを生成
    task_id = str(uuid.uuid4())
    
    # タスク情報を初期化（ロックで保護）
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
            "logs": [],  # 詳細ログを初期化
            "error_logs": []  # エラーログを初期化
        }
    
    # 制御フラグを作成（ロックで保護）
    with flags_lock:
        task_cancel_flags[task_id] = threading.Event()
        task_pause_flags[task_id] = threading.Event()
    
    # バックグラウンドでスクレイピングを実行
    executor.submit(
        run_scraping_task,
        task_id,
        request.scrapers,
        request.area_codes,
        request.max_properties
    )
    
    return ScrapingTaskStatus(**scraping_tasks[task_id])


@router.get("/scraping/status/{task_id}", response_model=ScrapingTaskStatus)
def get_scraping_status(task_id: str):
    """スクレイピングタスクの状態を取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return ScrapingTaskStatus(**scraping_tasks[task_id])


@router.get("/scraping/tasks/{task_id}/debug")
def get_task_debug_info(task_id: str):
    """タスクのデバッグ情報を取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = scraping_tasks[task_id]
    pause_flag = task_pause_flags.get(task_id)
    cancel_flag = task_cancel_flags.get(task_id)
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "pause_flag_exists": pause_flag is not None,
        "pause_flag_is_set": pause_flag.is_set() if pause_flag else None,
        "cancel_flag_exists": cancel_flag is not None,
        "cancel_flag_is_set": cancel_flag.is_set() if cancel_flag else None,
        "scraper_instances": list(scraper_instances.keys()),
        "current_combination": task.get("current_combination", None)
    }

@router.get("/scraping/tasks", response_model=List[ScrapingTaskStatus])
def get_all_scraping_tasks(active_only: bool = False):
    """全てのスクレイピングタスクを取得"""
    all_tasks = []
    
    # 通常のタスクを追加
    for task_id, task in scraping_tasks.items():
        if task["status"] in ["running", "paused"]:
            print(f"[TASKS] Task {task_id}: status={task['status']}")
        # エラーログの確認
        error_logs = task.get("error_logs", [])
        if error_logs:
            print(f"[TASKS] Task {task_id}: error_logs count={len(error_logs)}")
        all_tasks.append(task)
    
    # 並列タスクも追加
    if PARALLEL_SCRAPING_ENABLED:
        try:
            # DB版の場合はデータベースから取得
            if hasattr(parallel_manager, '__class__') and 'DB' in parallel_manager.__class__.__name__:
                from backend.app.database import SessionLocal
                from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
                
                db = SessionLocal()
                try:
                    # データベースからタスクを取得（時系列順）
                    db_tasks = db.query(ScrapingTask).order_by(ScrapingTask.created_at.desc()).all()
                    
                    for db_task in db_tasks:
                        # 進捗情報を取得
                        progress_records = db.query(ScrapingTaskProgress).filter(
                            ScrapingTaskProgress.task_id == db_task.task_id
                        ).all()
                        
                        # 進捗情報を辞書形式に変換
                        progress = {}
                        for p in progress_records:
                            key = f"{p.scraper}_{p.area}"
                            progress[key] = p.to_dict()
                        
                        # タスク情報を構築
                        task = {
                            'task_id': db_task.task_id,
                            'type': 'parallel',
                            'status': db_task.status,
                            'scrapers': db_task.scrapers,
                            'area_codes': db_task.areas,
                            'max_properties': db_task.max_properties,
                            'started_at': db_task.started_at.isoformat() if db_task.started_at else None,
                            'completed_at': db_task.completed_at.isoformat() if db_task.completed_at else None,
                            'progress': progress,
                            'errors': [
                                error['error'] if isinstance(error, dict) and 'error' in error else str(error)
                                for error in (db_task.error_logs or [])
                            ],
                            'logs': db_task.logs or [],
                            'error_logs': db_task.error_logs or [],
                            'created_at': db_task.created_at.isoformat() if db_task.created_at else None,
                            'statistics': {
                                'total_processed': db_task.total_processed,
                                'total_new': db_task.total_new,
                                'total_updated': db_task.total_updated,
                                'total_errors': db_task.total_errors,
                                'elapsed_time': db_task.elapsed_time
                            },
                            'force_detail_fetch': db_task.force_detail_fetch
                        }
                        all_tasks.append(task)
                        
                finally:
                    db.close()
        except Exception as e:
            print(f"[ERROR] 並列タスクの読み込みエラー: {e}")
    
    # 最新10件のみ返す（started_atがない場合はcreated_atを使用）
    def get_sort_key(task):
        # started_at または created_at を取得
        timestamp = task.get("started_at") or task.get("created_at") or ""
        # datetime オブジェクトの場合はそのまま、文字列の場合は datetime に変換
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, str) and timestamp:
            try:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                return datetime.min
        else:
            return datetime.min
    
    # active_onlyが指定されている場合は実行中のタスクのみ返す
    if active_only:
        active_statuses = {'running', 'pending', 'paused'}
        all_tasks = [task for task in all_tasks if task.get('status') in active_statuses]
    
    sorted_tasks = sorted(
        all_tasks,
        key=get_sort_key,
        reverse=True
    )[:30]  # 最新30件に増やす
    
    return [ScrapingTaskStatus(**task) for task in sorted_tasks]


@router.get("/scraping/tasks/{task_id}")
def get_single_task(task_id: str, db: Session = Depends(get_db)):
    """特定のタスクの詳細を取得"""
    # まずメモリ内のタスクを確認
    if task_id in scraping_tasks:
        return scraping_tasks[task_id]
    
    # データベースから取得（並列タスク）
    try:
        from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
        
        db_task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 進捗情報を取得
        progress_records = db.query(ScrapingTaskProgress).filter(
            ScrapingTaskProgress.task_id == task_id
        ).all()
        
        # 進捗情報を辞書形式に変換
        progress = {}
        for p in progress_records:
            key = f"{p.scraper}_{p.area}"
            progress[key] = p.to_dict()
        
        # タスク情報を構築
        return {
            'task_id': db_task.task_id,
            'type': 'parallel',
            'status': db_task.status,
            'scrapers': db_task.scrapers,
            'area_codes': db_task.areas,
            'max_properties': db_task.max_properties,
            'started_at': db_task.started_at.isoformat() if db_task.started_at else None,
            'completed_at': db_task.completed_at.isoformat() if db_task.completed_at else None,
            'progress': progress,
            'errors': [
                error['error'] if isinstance(error, dict) and 'error' in error else str(error)
                for error in (db_task.error_logs or [])
            ],
            'logs': db_task.logs or [],
            'error_logs': db_task.error_logs or [],
            'created_at': db_task.created_at.isoformat() if db_task.created_at else None,
            'statistics': {
                'total_processed': db_task.total_processed,
                'total_new': db_task.total_new,
                'total_updated': db_task.total_updated,
                'total_errors': db_task.total_errors,
                'elapsed_time': db_task.elapsed_time
            },
            'force_detail_fetch': db_task.force_detail_fetch
        }
    except Exception as e:
        logger.error(f"Error fetching task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scraping/task/{task_id}/logs")
def get_task_logs(task_id: str, limit: int = 50):
    """特定のタスクのログを取得"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = scraping_tasks[task_id]
    logs = task.get("logs", [])
    
    # 最新のログから指定件数分を返す
    return {
        "task_id": task_id,
        "logs": logs[-limit:] if len(logs) > limit else logs,
        "total_logs": len(logs)
    }


@router.post("/scraping/force-cleanup")
def force_cleanup_all_tasks():
    """すべてのタスクを強制的にクリーンアップ（緊急用）"""
    cleaned_count = 0
    cleaned_tasks = []
    
    # すべてのタスクをチェック
    for task_id in list(scraping_tasks.keys()):
        task = scraping_tasks[task_id]
        if task["status"] in ["running", "paused", "pending"]:
            # タスクを強制的にキャンセル
            task["status"] = "cancelled"
            task["completed_at"] = datetime.now()
            task["errors"].append("管理者による強制クリーンアップ")
            
            # 各スクレイパー・エリアの進行状況も更新
            for key, progress in task["progress"].items():
                if progress.get("status") in ["pending", "running", "paused"]:
                    progress["status"] = "cancelled"
                    progress["completed_at"] = datetime.now().isoformat()
            
            # フラグをクリア/セット
            if task_id in task_pause_flags:
                task_pause_flags[task_id].clear()
            if task_id in task_cancel_flags:
                task_cancel_flags[task_id].set()
            
            # リソースをクリーンアップ
            cleanup_task_resources(task_id)
            
            cleaned_count += 1
            cleaned_tasks.append({
                "task_id": task_id,
                "scrapers": task["scrapers"],
                "area_codes": task["area_codes"]
            })
    
    return {
        "success": True,
        "message": f"{cleaned_count} tasks cleaned up",
        "cleaned_tasks": cleaned_tasks
    }


# エリアコードのマッピング
AREA_CODES = {
    "千代田区": "13101",
    "中央区": "13102",
    "港区": "13103",
    "新宿区": "13104",
    "文京区": "13105",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108",
    "品川区": "13109",
    "目黒区": "13110",
    "大田区": "13111",
    "世田谷区": "13112",
    "渋谷区": "13113",
    "中野区": "13114",
    "杉並区": "13115",
    "豊島区": "13116",
    "北区": "13117",
    "荒川区": "13118",
    "板橋区": "13119",
    "練馬区": "13120",
    "足立区": "13121",
    "葛飾区": "13122",
    "江戸川区": "13123"
}


@router.get("/areas")
def get_areas():
    """利用可能なエリア一覧を取得"""
    return {
        "areas": [
            {"code": code, "name": name}
            for name, code in AREA_CODES.items()
        ]
    }


@router.post("/scraping/pause/{task_id}")
def pause_scraping(task_id: str):
    """スクレイピングタスクを一時停止"""
    print(f"[PAUSE] Received pause request for task: {task_id}")
    
    with tasks_lock:
        if task_id not in scraping_tasks:
            print(f"[PAUSE] Task {task_id} not found in scraping_tasks")
            print(f"[PAUSE] Available tasks: {list(scraping_tasks.keys())}")
            raise HTTPException(status_code=404, detail="Task not found")
        
        current_status = scraping_tasks[task_id]["status"]
        print(f"[PAUSE] Task {task_id} current status: {current_status}")
        
        if current_status != "running":
            raise HTTPException(
                status_code=400, 
                detail=f"Task is {current_status}, cannot pause"
            )
    
    # 一時停止フラグをセット（ロックで保護）
    with flags_lock:
        if task_id in task_pause_flags:
            task_pause_flags[task_id].set()
            print(f"[PAUSE] Pause flag set for task {task_id}, flag ID: {id(task_pause_flags[task_id])}, is_set: {task_pause_flags[task_id].is_set()}")
            debug_log(f"[PAUSE] Pause flag set for task {task_id}, flag ID: {id(task_pause_flags[task_id])}, is_set: {task_pause_flags[task_id].is_set()}")
            
            # 一時停止のタイムスタンプを記録
            task_pause_timestamps[task_id] = datetime.now()
            print(f"[PAUSE] Pause timestamp recorded for task {task_id}: {task_pause_timestamps[task_id]}")
            
            # スクレイパーインスタンスのフラグ状態も確認
            with instances_lock:
                for key, scraper in scraper_instances.items():
                    if key.startswith(task_id):
                        if hasattr(scraper, 'pause_flag'):
                            print(f"[PAUSE] Scraper {key} pause flag ID: {id(scraper.pause_flag)}, is_set: {scraper.pause_flag.is_set()}")
                            debug_log(f"[PAUSE] Scraper {key} pause flag ID: {id(scraper.pause_flag)}, is_set: {scraper.pause_flag.is_set()}")
            
            # ステータスを即座にpausedに変更（タスク全体のステータスのみ変更）
            with tasks_lock:
                scraping_tasks[task_id]["status"] = "paused"
                print(f"[PAUSE] Task {task_id} status changed to paused")
            
            return {"success": True, "message": "Pause request sent"}
        else:
            print(f"[PAUSE] Task pause flag not found for task {task_id}")
            print(f"[PAUSE] Available pause flags: {list(task_pause_flags.keys())}")
            return {"success": False, "message": "Task pause flag not found"}


@router.post("/scraping/resume/{task_id}")
def resume_scraping(task_id: str):
    """スクレイピングタスクを再開"""
    print(f"[RESUME] Received resume request for task: {task_id}")
    
    if task_id not in scraping_tasks:
        print(f"[RESUME] Task {task_id} not found")
        raise HTTPException(status_code=404, detail="Task not found")
    
    current_status = scraping_tasks[task_id]["status"]
    print(f"[RESUME] Task {task_id} current status: {current_status}")
    
    if current_status != "paused":
        raise HTTPException(
            status_code=400, 
            detail=f"Task is {current_status}, cannot resume"
        )
    
    # 一時停止フラグの存在確認
    if task_id in task_pause_flags:
        pause_flag = task_pause_flags[task_id]
        print(f"[RESUME] Pause flag ID for task {task_id}: {id(pause_flag)}")
        pause_flag.clear()
        print(f"[RESUME] Pause flag cleared for task {task_id}")
        
        # 一時停止のタイムスタンプを削除
        if task_id in task_pause_timestamps:
            del task_pause_timestamps[task_id]
            print(f"[RESUME] Pause timestamp removed for task {task_id}")
        
        # ステータスをrunningに変更
        scraping_tasks[task_id]["status"] = "running"
        print(f"[RESUME] Task {task_id} status changed to running")
        
        # フラグの状態を確認
        print(f"[RESUME] Pause flag is_set after clear: {pause_flag.is_set()}")
        debug_log(f"[RESUME] Pause flag is_set after clear: {pause_flag.is_set()}")
        
        # スクレイパーインスタンスのフラグIDも確認
        found_instances = 0
        for key, scraper in scraper_instances.items():
            if key.startswith(task_id):
                found_instances += 1
                if hasattr(scraper, 'pause_flag'):
                    print(f"[RESUME] Scraper {key} pause flag ID: {id(scraper.pause_flag)}, is_set: {scraper.pause_flag.is_set()}")
                    debug_log(f"[RESUME] Scraper {key} pause flag ID: {id(scraper.pause_flag)}, is_set: {scraper.pause_flag.is_set()}")
                    # フラグが同じオブジェクトか確認
                    if scraper.pause_flag is pause_flag:
                        print(f"[RESUME] Scraper {key} has the same pause flag object")
                        debug_log(f"[RESUME] Scraper {key} has the same pause flag object")
                    else:
                        print(f"[RESUME] WARNING: Scraper {key} has a different pause flag object!")
                        debug_log(f"[RESUME] WARNING: Scraper {key} has a different pause flag object!")
        
        print(f"[RESUME] Found {found_instances} scraper instances for task {task_id}")
        debug_log(f"[RESUME] Found {found_instances} scraper instances for task {task_id}")
        
        # 全てのスクレイパーインスタンスのキーを表示
        all_keys = list(scraper_instances.keys())
        print(f"[RESUME] All scraper instance keys: {all_keys}")
        debug_log(f"[RESUME] All scraper instance keys: {all_keys}")
        
        return {"success": True, "message": "Resume request sent"}
    else:
        print(f"[RESUME] Task pause flag not found for task {task_id}")
        print(f"[RESUME] Available pause flags: {list(task_pause_flags.keys())}")
        # フラグがない場合でもステータスは変更する
        scraping_tasks[task_id]["status"] = "running"
        return {"success": False, "message": "Task pause flag not found but status updated"}


@router.post("/scraping/cancel/{task_id}")
def cancel_scraping(task_id: str):
    """スクレイピングタスクをキャンセル"""
    with tasks_lock:
        if task_id not in scraping_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if scraping_tasks[task_id]["status"] not in ["pending", "running", "paused"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Task is already {scraping_tasks[task_id]['status']}"
            )
    
    # キャンセルフラグをセット（ロックで保護）
    with flags_lock:
        if task_id in task_cancel_flags:
            task_cancel_flags[task_id].set()
            # 一時停止フラグもクリアして、待機中のスレッドを解放
            if task_id in task_pause_flags:
                task_pause_flags[task_id].clear()
    
    # ステータスを更新（ロックで保護）
    with tasks_lock:
        # 即座にステータスを更新
        scraping_tasks[task_id]["status"] = "cancelled"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        
        # 各スクレイパー・エリアの進行状況も更新
        for key, progress in scraping_tasks[task_id]["progress"].items():
            if progress.get("status") in ["pending", "running", "paused"]:
                progress["status"] = "cancelled"
                progress["completed_at"] = datetime.now().isoformat()
    
    return {"success": True, "message": "Cancel request sent"}


@router.get("/property-merge-history")
def get_property_merge_history(
    limit: int = 50,
    include_reverted: bool = False,
    db: Session = Depends(get_db)
):
    """物件統合履歴を取得"""
    query = db.query(PropertyMergeHistory)
    
    if not include_reverted:
        query = query.filter(PropertyMergeHistory.reverted_at.is_(None))
    
    histories = query.order_by(PropertyMergeHistory.merged_at.desc()).limit(limit).all()
    
    result = []
    for history in histories:
        # 主物件の情報を取得
        primary_property = db.query(MasterProperty).filter(
            MasterProperty.id == history.primary_property_id
        ).first()
        
        primary_data = {
            "id": history.primary_property_id,
            "building_name": None,
            "room_number": None,
            "floor_number": None,
            "area": None,
            "layout": None
        }
        
        if primary_property:
            primary_data.update({
                "building_name": primary_property.building.normalized_name if primary_property.building else None,
                "room_number": primary_property.room_number,
                "floor_number": primary_property.floor_number,
                "area": primary_property.area,
                "layout": primary_property.layout
            })
        
        # 副物件の情報（merge_detailsから取得）
        secondary_data = {
            "id": history.secondary_property_id,
            "building_name": None,
            "room_number": None,
            "floor_number": None,
            "area": None,
            "layout": None
        }
        
        if history.merge_details and "secondary_property" in history.merge_details:
            sec = history.merge_details["secondary_property"]
            secondary_data.update({
                "room_number": sec.get("room_number"),
                "floor_number": sec.get("floor_number"),
                "area": sec.get("area"),
                "layout": sec.get("layout")
            })
            
            # 建物名を取得
            if sec.get("building_id"):
                building = db.query(Building).filter(Building.id == sec["building_id"]).first()
                if building:
                    secondary_data["building_name"] = building.normalized_name
        
        result.append({
            "id": history.id,
            "primary_property": primary_data,
            "secondary_property": secondary_data,
            "moved_listings": history.moved_listings,
            "merge_details": history.merge_details,
            "merged_at": history.merged_at.isoformat() if history.merged_at else None,
            "merged_by": history.merged_by,
            "reverted_at": history.reverted_at.isoformat() if history.reverted_at else None,
            "reverted_by": history.reverted_by
        })
    
    return {"histories": result, "total": len(result)}


# 並列スクレイピング管理インスタンス
parallel_manager = ParallelScrapingManager() if PARALLEL_SCRAPING_ENABLED else None


class ParallelScrapingRequest(BaseModel):
    """並列スクレイピングリクエスト"""
    scrapers: List[str]
    area_codes: List[str]
    max_properties: int = 100
    force_detail_fetch: bool = False


@router.post("/scraping/start-parallel")
def start_parallel_scraping(
    request: ParallelScrapingRequest,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """並列スクレイピングを開始"""
    if not PARALLEL_SCRAPING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="並列スクレイピング機能は現在利用できません。Dockerコンテナを再起動してください。"
        )
    
    task_id = f"parallel_{uuid.uuid4().hex[:8]}"
    
    # エリアコードから区名に変換
    code_to_area = {v: k for k, v in AREA_CODES.items()}
    areas = [code_to_area.get(code, code) for code in request.area_codes]
    
    # タスク情報を登録（並列タスクはparallel_managerでのみ管理）
    # scraping_tasksには追加しない
    task_info = {
        "task_id": task_id,
        "type": "parallel",
        "status": "running",
        "scrapers": request.scrapers,
        "area_codes": request.area_codes,
        "areas": areas,
        "max_properties": request.max_properties,
            "force_detail_fetch": request.force_detail_fetch,
            "started_at": datetime.now().isoformat(),  # started_atを追加
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "progress": {},
            "errors": [],
            "logs": []
        }
    
    # バックグラウンドで並列実行
    def run_parallel_task():
        try:
            
            # 並列スクレイピングを実行（parallel_managerが状態を管理）
            result = parallel_manager.run_parallel(
                task_id=task_id,
                areas=areas,
                scrapers=request.scrapers,
                max_properties=request.max_properties,
                force_detail_fetch=request.force_detail_fetch
            )
            
        except Exception as e:
            logger.error(f"並列スクレイピングエラー: {e}")
            import traceback
            traceback.print_exc()
    
    # ThreadPoolExecutorで実行
    future = executor.submit(run_parallel_task)
    
    # 通常のタスク形式に合わせたレスポンスを返す
    return {
        "task_id": task_id,
        "status": "running",
        "scrapers": request.scrapers,
        "area_codes": request.area_codes,
        "areas": areas,
        "max_properties": request.max_properties,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "progress": {},
        "errors": [],
        "message": "並列スクレイピングを開始しました"
    }


@router.get("/scraping/parallel-status/{task_id}")
def get_parallel_scraping_status(task_id: str):
    """並列スクレイピングのステータスを取得"""
    if not PARALLEL_SCRAPING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="並列スクレイピング機能は現在利用できません。"
        )
    
    # データベースから直接タスク情報を取得
    from backend.app.database import SessionLocal
    from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
    
    db = SessionLocal()
    try:
        task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
        
        if task:
            # 進捗情報を取得
            progress_records = db.query(ScrapingTaskProgress).filter(
                ScrapingTaskProgress.task_id == task_id
            ).all()
            
            # 進捗情報を辞書形式に変換
            progress = {}
            for p in progress_records:
                key = f"{p.scraper}_{p.area}"
                progress[key] = p.to_dict()
            
            # レスポンスデータを構築
            response_data = {
                'task_id': task.task_id,
                'type': 'parallel',
                'status': task.status,
                'scrapers': task.scrapers,
                'area_codes': task.areas,
                'max_properties': task.max_properties,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'progress': progress,
                'errors': [
                    error['error'] if isinstance(error, dict) and 'error' in error else str(error)
                    for error in (task.error_logs or [])
                ],
                'logs': [],
                'error_logs': [],
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'statistics': {
                    'total_processed': task.total_processed,
                    'total_new': task.total_new,
                    'total_updated': task.total_updated,
                    'total_errors': task.total_errors,
                    'elapsed_time': task.elapsed_time
                },
                'force_detail_fetch': task.force_detail_fetch
            }
            
            return response_data
        else:
            raise HTTPException(status_code=404, detail="タスクが見つかりません")
    finally:
        db.close()


@router.post("/scraping/pause-parallel/{task_id}")
def pause_parallel_scraping(task_id: str):
    """並列スクレイピングを一時停止"""
    if not PARALLEL_SCRAPING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="並列スクレイピング機能は現在利用できません。"
        )
    
    try:
        # parallel_managerのDB版メソッドを使用
        result = parallel_manager.pause_task(task_id)
        
        return {
            "task_id": task_id,
            "message": "タスクを一時停止しました"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scraping/resume-parallel/{task_id}")
def resume_parallel_scraping(task_id: str):
    """並列スクレイピングを再開"""
    if not PARALLEL_SCRAPING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="並列スクレイピング機能は現在利用できません。"
        )
    
    try:
        # parallel_managerのDB版メソッドを使用
        result = parallel_manager.resume_task(task_id)
        
        return {
            "task_id": task_id,
            "message": "タスクを再開しました"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scraping/cancel-parallel/{task_id}")
def cancel_parallel_scraping(task_id: str):
    """並列スクレイピングをキャンセル"""
    if not PARALLEL_SCRAPING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="並列スクレイピング機能は現在利用できません。"
        )
    
    parallel_manager.cancel_task(task_id)
    
    return {
        "task_id": task_id,
        "message": "タスクをキャンセルしました"
    }


@router.delete("/scraping/tasks/{task_id}")
def delete_scraping_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """完了またはキャンセルされたタスクを削除"""
    # データベースからタスクを取得
    task = db.query(ScrapingTask).filter(ScrapingTask.task_id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    # completedまたはcancelledのタスクのみ削除可能
    if task.status not in ["completed", "cancelled", "error"]:
        raise HTTPException(
            status_code=400,
            detail=f"タスクのステータスが'{task.status}'のため削除できません。completedまたはcancelledのタスクのみ削除可能です。"
        )
    
    try:
        # 関連する進捗情報も削除
        db.query(ScrapingTaskProgress).filter(
            ScrapingTaskProgress.task_id == task_id
        ).delete()
        
        # タスク本体を削除
        db.delete(task)
        db.commit()
        
        return {"message": f"タスク {task_id} を削除しました"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"タスクの削除に失敗しました: {str(e)}")


@router.delete("/scraping/all-tasks")
def delete_all_scraping_tasks(
    db: Session = Depends(get_db)
):
    """すべてのスクレイピング履歴を削除"""
    try:
        # 最初に進捗情報を削除
        deleted_progress = db.query(ScrapingTaskProgress).delete()
        
        # タスク本体を削除
        deleted_tasks = db.query(ScrapingTask).delete()
        
        db.commit()
        
        return {
            "message": f"すべてのスクレイピング履歴を削除しました",
            "deleted_tasks": deleted_tasks,
            "deleted_progress": deleted_progress
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"履歴の削除に失敗しました: {str(e)}")


@router.post("/revert-building-merge/{history_id}")
def revert_building_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """建物統合を取り消す"""
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    if history.reverted_at:
        raise HTTPException(status_code=400, detail="既に取り消し済みです")
    
    try:
        # 主建物の存在確認
        primary_building = db.query(Building).filter(
            Building.id == history.primary_building_id
        ).first()
        
        if not primary_building:
            raise HTTPException(status_code=404, detail="主建物が見つかりません")
        
        # 統合された建物を復元
        merged_building_ids = history.merged_building_ids
        merge_details = history.merge_details or {}
        
        restored_buildings = []
        
        # merged_buildingsはリストとして保存されている
        merged_buildings_list = merge_details.get("merged_buildings", [])
        
        # リストを辞書に変換（IDをキーにする）
        merged_buildings_dict = {}
        for building_data in merged_buildings_list:
            if isinstance(building_data, dict) and "id" in building_data:
                merged_buildings_dict[building_data["id"]] = building_data
        
        for building_id in merged_building_ids:
            # merge_detailsから建物情報を取得
            building_data = merged_buildings_dict.get(building_id, {})
            
            if building_data:
                # 建物を復元
                restored_building = Building(
                    id=building_id,
                    normalized_name=building_data.get("normalized_name"),
                    canonical_name=building_data.get("canonical_name"),
                    address=building_data.get("address"),
                    built_year=building_data.get("built_year"),
                    total_floors=building_data.get("total_floors"),
                    basement_floors=building_data.get("basement_floors"),
                    total_units=building_data.get("total_units"),
                    structure=building_data.get("structure"),
                    land_rights=building_data.get("land_rights"),
                    parking_info=building_data.get("parking_info")
                )
                db.add(restored_building)
                restored_buildings.append(building_id)
                
                # 外部IDを復元
                external_ids = merge_details.get("external_ids", {}).get(str(building_id), [])
                for ext_id_data in external_ids:
                    external_id = BuildingExternalId(
                        building_id=building_id,
                        source_site=ext_id_data["source_site"],
                        external_id=ext_id_data["external_id"]
                    )
                    db.add(external_id)
        
        # 移動された物件を元に戻す
        # 各建物から移動された物件数に基づいて物件を戻す
        for building_id in merged_building_ids:
            building_data = merged_buildings_dict.get(building_id, {})
            properties_moved = building_data.get("properties_moved", 0)
            
            if properties_moved > 0:
                # この建物から移動された物件を元に戻す
                # 主建物に現在ある物件のうち、指定された数だけを元の建物に戻す
                properties_to_restore = db.query(MasterProperty).filter(
                    MasterProperty.building_id == history.primary_building_id
                ).limit(properties_moved).all()
                
                for property in properties_to_restore:
                    property.building_id = building_id
        
        # 履歴を更新
        history.reverted_at = datetime.now()
        history.reverted_by = "admin"  # TODO: 実際のユーザー名を記録
        
        db.commit()
        
        return {
            "success": True,
            "message": f"建物統合を取り消しました。{len(restored_buildings)}件の建物を復元しました。",
            "restored_buildings": restored_buildings
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/revert-property-merge/{history_id}")
def revert_property_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """物件統合を取り消す"""
    history = db.query(PropertyMergeHistory).filter(
        PropertyMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    if history.reverted_at:
        raise HTTPException(status_code=400, detail="既に取り消し済みです")
    
    try:
        # 主物件の存在確認
        primary_property = db.query(MasterProperty).filter(
            MasterProperty.id == history.primary_property_id
        ).first()
        
        if not primary_property:
            raise HTTPException(status_code=404, detail="主物件が見つかりません")
        
        # 副物件を復元
        secondary_data = history.merge_details.get("secondary_property", {})
        secondary_property = MasterProperty(
            id=secondary_data["id"],
            building_id=secondary_data["building_id"],
            room_number=secondary_data.get("room_number"),
            floor_number=secondary_data.get("floor_number"),
            area=secondary_data.get("area"),
            balcony_area=secondary_data.get("balcony_area"),
            layout=secondary_data.get("layout"),
            direction=secondary_data.get("direction"),
            summary_remarks=secondary_data.get("summary_remarks"),
            property_hash=secondary_data.get("property_hash")
        )
        db.add(secondary_property)
        
        # 移動された掲載情報を元に戻す
        moved_listings = history.merge_details.get("moved_listings", [])
        restored_count = 0
        
        for listing_info in moved_listings:
            listing = db.query(PropertyListing).filter(
                PropertyListing.id == listing_info["listing_id"]
            ).first()
            
            if listing and listing.master_property_id == history.primary_property_id:
                listing.master_property_id = history.secondary_property_id
                restored_count += 1
        
        # 主物件の更新を元に戻す（必要に応じて）
        primary_updates = history.merge_details.get("primary_updates", {})
        if primary_updates:
            # 更新された項目を確認し、副物件の値で上書きされていた場合は元に戻す
            # ただし、その後別の更新があった可能性もあるため、慎重に処理
            pass
        
        # 履歴を更新
        history.reverted_at = datetime.now()
        history.reverted_by = "admin"  # TODO: 実際のユーザー名を記録
        
        # 多数決による建物名更新（掲載情報が移動したため）
        from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
        updater = MajorityVoteUpdater(db)
        
        # 主物件の建物名を更新（掲載情報が減ったため）
        if primary_property and primary_property.building_id:
            updater.update_building_name_by_majority(primary_property.building_id)
        
        # 副物件の建物名を更新（掲載情報が戻ったため）
        if secondary_property and secondary_property.building_id:
            updater.update_building_name_by_majority(secondary_property.building_id)
        
        db.commit()
        
        return {
            "success": True,
            "message": f"物件統合を取り消しました。{restored_count}件の掲載情報を復元しました。",
            "restored_listings": restored_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


class ExcludePropertiesRequest(BaseModel):
    """物件除外リクエスト"""
    property1_id: int
    property2_id: int
    reason: Optional[str] = None


@router.post("/exclude-properties")
def exclude_properties(
    request: ExcludePropertiesRequest,
    db: Session = Depends(get_db)
):
    """物件ペアを統合候補から除外（別物件として維持）"""
    
    # 既に除外されているかチェック
    from sqlalchemy import or_, and_
    existing = db.query(PropertyMergeExclusion).filter(
        or_(
            and_(
                PropertyMergeExclusion.property1_id == request.property1_id,
                PropertyMergeExclusion.property2_id == request.property2_id
            ),
            and_(
                PropertyMergeExclusion.property1_id == request.property2_id,
                PropertyMergeExclusion.property2_id == request.property1_id
            )
        )
    ).first()
    
    if existing:
        return {"success": False, "message": "既に除外済みです"}
    
    # 小さいIDを property1_id として保存（一貫性のため）
    if request.property1_id > request.property2_id:
        property1_id = request.property2_id
        property2_id = request.property1_id
    else:
        property1_id = request.property1_id
        property2_id = request.property2_id
    
    exclusion = PropertyMergeExclusion(
        property1_id=property1_id,
        property2_id=property2_id,
        reason=request.reason,
        excluded_by="admin"  # TODO: 実際のユーザー名を記録
    )
    db.add(exclusion)
    db.commit()
    
    return {"success": True, "exclusion_id": exclusion.id}


@router.delete("/exclude-properties/{exclusion_id}")
def remove_property_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db)
):
    """物件除外を取り消す"""
    exclusion = db.query(PropertyMergeExclusion).filter(
        PropertyMergeExclusion.id == exclusion_id
    ).first()
    
    if not exclusion:
        raise HTTPException(status_code=404, detail="除外記録が見つかりません")
    
    db.delete(exclusion)
    db.commit()
    
    return {"success": True}


@router.get("/property-exclusions")
def get_property_exclusions(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """物件除外リストを取得"""
    exclusions = db.query(PropertyMergeExclusion).order_by(
        PropertyMergeExclusion.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for exclusion in exclusions:
        # 物件情報を取得
        prop1 = db.query(MasterProperty).filter(
            MasterProperty.id == exclusion.property1_id
        ).first()
        prop2 = db.query(MasterProperty).filter(
            MasterProperty.id == exclusion.property2_id
        ).first()
        
        if prop1 and prop1.building:
            prop1_info = f"{prop1.building.normalized_name}"
            if prop1.room_number:
                prop1_info += f" {prop1.room_number}"
            if prop1.floor_number:
                prop1_info += f" {prop1.floor_number}階"
        else:
            prop1_info = f"物件ID: {exclusion.property1_id}"
            
        if prop2 and prop2.building:
            prop2_info = f"{prop2.building.normalized_name}"
            if prop2.room_number:
                prop2_info += f" {prop2.room_number}"
            if prop2.floor_number:
                prop2_info += f" {prop2.floor_number}階"
        else:
            prop2_info = f"物件ID: {exclusion.property2_id}"
        
        result.append({
            "id": exclusion.id,
            "property1": {
                "id": exclusion.property1_id,
                "info": prop1_info
            },
            "property2": {
                "id": exclusion.property2_id,
                "info": prop2_info
            },
            "reason": exclusion.reason,
            "excluded_by": exclusion.excluded_by,
            "created_at": exclusion.created_at.isoformat() if exclusion.created_at else None
        })
    
    return {"exclusions": result, "total": len(result)}


@router.post("/update-listing-status")
def update_listing_status(db: Session = Depends(get_db)):
    """掲載状態を手動で更新（24時間以上確認されていない掲載を終了）"""
    from datetime import datetime, timedelta
    
    try:
        # 現在時刻
        now = datetime.now()
        
        # 24時間前
        threshold = now - timedelta(hours=24)
        
        # 24時間以上確認されていないアクティブな掲載を非アクティブに
        inactive_listings = db.query(PropertyListing).filter(
            PropertyListing.is_active == True,
            PropertyListing.last_confirmed_at < threshold
        ).all()
        
        inactive_count = len(inactive_listings)
        
        # 掲載を非アクティブ化し、影響を受ける建物IDと物件IDを収集
        affected_building_ids = set()
        affected_property_ids = set()
        for listing in inactive_listings:
            listing.is_active = False
            # 掲載に関連する建物IDと物件IDを収集
            if listing.master_property:
                affected_property_ids.add(listing.master_property_id)
                if listing.master_property.building_id:
                    affected_building_ids.add(listing.master_property.building_id)
        
        db.flush()
        
        # 物件ごとにすべての掲載がアクティブでないかチェック
        # アクティブな掲載がなくなった物件を取得
        properties_to_check = db.query(MasterProperty).filter(
            MasterProperty.id.in_([listing.master_property_id for listing in inactive_listings])
        ).all()
        
        sold_count = 0
        
        for property in properties_to_check:
            # この物件のアクティブな掲載があるかチェック
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property.id,
                PropertyListing.is_active == True
            ).count()
            
            # アクティブな掲載がなく、まだ販売終了日が設定されていない場合
            if active_listings == 0 and property.sold_at is None:
                property.sold_at = now
                
                # 最終販売価格を取得（最も新しい掲載の価格）
                last_listing = db.query(PropertyListing).filter(
                    PropertyListing.master_property_id == property.id
                ).order_by(PropertyListing.last_scraped_at.desc()).first()
                
                if last_listing and last_listing.current_price:
                    property.last_sale_price = last_listing.current_price
                
                sold_count += 1
        
        db.commit()
        
        # 販売終了物件の価格を多数決で更新
        price_update_count = 0
        building_update_count = 0
        
        try:
            from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
            updater = MajorityVoteUpdater(db)
            
            # 販売終了物件の価格を更新
            if sold_count > 0:
                # 今回販売終了となった物件の価格を更新
                for property in properties_to_check:
                    if property.sold_at == now:  # 今回販売終了となった物件
                        result = updater.update_sold_property_price(property.id)
                        if result:
                            price_update_count += 1
            
            # 掲載状態が変わった物件の情報を更新
            property_update_count = 0
            for property_id in affected_property_ids:
                property = db.query(MasterProperty).get(property_id)
                if property and updater.update_master_property_by_majority(property):
                    property_update_count += 1
            
            # 掲載状態が変わった建物の名前を更新
            for building_id in affected_building_ids:
                if updater.update_building_name_by_majority(building_id):
                    building_update_count += 1
            
            db.commit()
        except Exception as e:
            # 更新のエラーはログに記録するが、メイン処理は成功とする
            print(f"Error updating sold property prices or building names: {e}")
        
        return {
            "success": True,
            "inactive_listings": inactive_count,
            "sold_properties": sold_count,
            "price_updates": price_update_count,
            "property_updates": property_update_count,
            "building_updates": building_update_count,
            "message": f"{inactive_count}件の掲載を終了、{sold_count}件の物件を販売終了としました。{price_update_count}件の価格、{property_update_count}件の物件情報、{building_update_count}件の建物名を多数決で更新しました。",
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        error_detail = f"Error updating listing status: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-sold-property-prices")
def update_sold_property_prices(
    property_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """販売終了物件の価格を多数決で更新"""
    
    try:
        from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
        
        updater = MajorityVoteUpdater(db)
        
        if property_id:
            # 特定の物件のみ更新
            result = updater.update_sold_property_price(property_id)
            
            if result:
                db.commit()
                return {
                    "success": True,
                    "message": f"物件ID {property_id} の価格を更新しました",
                    "old_price": result[0],
                    "new_price": result[1]
                }
            else:
                return {
                    "success": False,
                    "message": "更新対象がありませんでした"
                }
        else:
            # 全件更新
            updates = updater.update_all_sold_property_prices()
            db.commit()
            
            return {
                "success": True,
                "message": f"{len(updates)}件の物件価格を更新しました",
                "updates": [
                    {
                        "property_id": prop_id,
                        "old_price": old_price,
                        "new_price": new_price
                    }
                    for prop_id, old_price, new_price in updates[:20]  # 最初の20件のみ返す
                ],
                "total_updated": len(updates)
            }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scraping/check-stalled-tasks")
def check_stalled_tasks(
    threshold_minutes: int = 10,
    db: Session = Depends(get_db)
):
    """停止したタスクを検出してエラーステータスに変更"""
    from datetime import datetime, timedelta
    from backend.app.config.scraping_config import STALLED_PAUSED_TASK_THRESHOLD_MINUTES
    
    now = datetime.now()
    threshold = now - timedelta(minutes=threshold_minutes)
    
    # runningまたはpausedステータスのタスクを取得
    active_tasks = db.query(ScrapingTask).filter(
        ScrapingTask.status.in_(['running', 'paused'])
    ).all()
    
    stalled_tasks = []
    
    for task in active_tasks:
        # タスクの進捗を確認
        latest_progress = db.query(ScrapingTaskProgress).filter(
            ScrapingTaskProgress.task_id == task.task_id
        ).order_by(
            ScrapingTaskProgress.last_updated.desc()
        ).first()
        
        if latest_progress:
            # 最終更新時刻をチェック
            if latest_progress.last_updated < threshold:
                time_since_update = now - latest_progress.last_updated
                minutes_since_update = time_since_update.total_seconds() / 60
                
                # pausedステータスの場合は、より長い時間待つ
                if task.status == 'paused':
                    # pausedの場合は設定値（デフォルト30分）待つ
                    if minutes_since_update > STALLED_PAUSED_TASK_THRESHOLD_MINUTES:
                        stalled_tasks.append(task)
                else:
                    stalled_tasks.append(task)
        else:
            # 進捗レコードがない場合
            if task.started_at and task.started_at < threshold:
                stalled_tasks.append(task)
    
    # 停止したタスクをエラーステータスに変更
    updated_count = 0
    for task in stalled_tasks:
        # タスクステータスを更新
        task.status = 'error'
        task.completed_at = now
        
        # エラーログを追加
        error_logs = task.error_logs or []
        error_logs.append({
            'error': 'Task stalled - no progress updates',
            'timestamp': now.isoformat(),
            'details': f'No updates for more than {threshold_minutes} minutes'
        })
        task.error_logs = error_logs
        
        # 進捗ステータスも更新（completed, cancelled以外をerrorに）
        db.query(ScrapingTaskProgress).filter(
            ScrapingTaskProgress.task_id == task.task_id,
            ScrapingTaskProgress.status.in_(['running', 'pending', 'paused'])
        ).update({
            'status': 'error',
            'completed_at': now
        })
        
        updated_count += 1
    
    if stalled_tasks:
        db.commit()
    
    return {
        "checked_tasks": len(active_tasks),
        "stalled_tasks": updated_count,
        "threshold_minutes": threshold_minutes,
        "message": f"{updated_count}個のタスクをエラーステータスに変更しました"
    }
