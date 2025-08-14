"""
管理画面用APIエンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
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
from time import time as time_now
from functools import lru_cache

from backend.app.database import get_db
from backend.app.utils.enhanced_building_matcher import EnhancedBuildingMatcher
from backend.app.utils.building_search import apply_building_search_to_query
from backend.app.utils.search_normalizer import create_search_patterns, normalize_search_text
from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
import re
import logging

# ロガーの設定
logger = logging.getLogger(__name__)

# 重複建物検索のキャッシュ
_duplicate_buildings_cache = {}
_duplicate_buildings_cache_time = 0
CACHE_DURATION = 300  # 5分間のキャッシュ

from backend.app.database import get_db
from backend.app.utils.debug_logger import debug_log
from backend.app.models import MasterProperty, PropertyListing, Building, ListingPriceHistory, PropertyMergeHistory, PropertyMergeExclusion, BuildingMergeHistory, BuildingExternalId, BuildingMergeExclusion
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
from sqlalchemy import func, or_, and_, distinct
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

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[])

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


@router.get("/duplicate-buildings")
def get_duplicate_buildings(
    search: Optional[str] = None,
    min_similarity: float = 0.7,
    limit: int = 30,
    db: Session = Depends(get_db)
):
    """建物の重複候補を取得（改善版）"""
    global _duplicate_buildings_cache, _duplicate_buildings_cache_time
    import re
    
    # キャッシュキーの作成
    cache_key = f"{search}_{min_similarity}_{limit}"
    current_time = time_now()
    
    # キャッシュが有効な場合は返す（検索なしの場合のみ）
    if (not search and 
        cache_key in _duplicate_buildings_cache and 
        current_time - _duplicate_buildings_cache_time < CACHE_DURATION):
        return _duplicate_buildings_cache[cache_key]
    
    # EnhancedBuildingMatcherのインスタンスを作成
    matcher = EnhancedBuildingMatcher()
    
    # 検索条件がある場合は通常通り処理
    if search:
        # ベースクエリ
        base_query = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).group_by(Building.id).having(
            func.count(MasterProperty.id) > 0  # 物件がある建物のみ
        )
        
        from backend.app.utils.search_normalizer import normalize_search_text
        normalized_search = normalize_search_text(search)
        search_terms = normalized_search.split()
        
        for term in search_terms:
            base_query = base_query.filter(Building.normalized_name.ilike(f"%{term}%"))
        
        buildings_with_count = base_query.order_by(Building.normalized_name).all()
    else:
        # 検索条件がない場合：重複の可能性が高い建物群を効率的に見つける
        
        # 優先度1: 同じ建物名を持つ建物（最も重複の可能性が高い）
        subquery = db.query(
            Building.normalized_name,
            func.count(Building.id).label('name_count')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            )
        ).group_by(Building.normalized_name).having(
            func.count(Building.id) > 1  # 同じ名前の建物が2つ以上
        ).subquery()
        
        # 同名建物をすべて取得
        buildings_with_count = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).filter(
            Building.normalized_name.in_(
                db.query(subquery.c.normalized_name)
            )
        ).group_by(Building.id).order_by(
            Building.normalized_name,
            Building.id  # 同じ名前内でもID順で安定したソート
        ).all()
        
        # 優先度2: 同じ住所・築年・階数の組み合わせを持つ建物を追加
        if len(buildings_with_count) < limit * 3:
            # 同じ住所前半部分、同じ築年、同じ階数を持つ建物のグループを検索
            # これらは表記ゆれや入力ミスによる重複の可能性が高い
            duplicate_candidates = db.query(
                Building,
                func.count(MasterProperty.id).label('property_count')
            ).outerjoin(
                MasterProperty, Building.id == MasterProperty.building_id
            ).filter(
                Building.id.notin_([b[0].id for b in buildings_with_count])
            ).group_by(Building.id).having(
                func.count(MasterProperty.id) > 0
            )
            
            # サブクエリで重複の可能性が高い組み合わせを特定
            attribute_groups = db.query(
                func.substring(Building.address, 1, 15).label('address_prefix'),  # 住所の前半部分
                Building.built_year,
                Building.total_floors,
                func.count(Building.id).label('group_count')
            ).filter(
                Building.id.in_(
                    db.query(MasterProperty.building_id).distinct()
                ),
                Building.built_year.isnot(None),
                Building.total_floors.isnot(None)
            ).group_by(
                func.substring(Building.address, 1, 15),
                Building.built_year,
                Building.total_floors
            ).having(
                func.count(Building.id) > 1  # 同じ属性の組み合わせが2つ以上
            ).limit(50).all()
            
            # 見つかった組み合わせに一致する建物を取得
            for group in attribute_groups:
                if len(buildings_with_count) >= limit * 3:
                    break
                matching_buildings = duplicate_candidates.filter(
                    Building.address.like(f"{group.address_prefix}%"),
                    Building.built_year == group.built_year,
                    Building.total_floors == group.total_floors
                ).limit(10).all()
                buildings_with_count.extend(matching_buildings)
        
        # 優先度3: まだ枠がある場合は、通常の建物を追加（フォールバック）
        if len(buildings_with_count) < 500:
            remaining_buildings = db.query(
                Building,
                func.count(MasterProperty.id).label('property_count')
            ).outerjoin(
                MasterProperty, Building.id == MasterProperty.building_id
            ).filter(
                Building.id.notin_([b[0].id for b in buildings_with_count])
            ).group_by(Building.id).having(
                func.count(MasterProperty.id) > 0
            ).order_by(
                Building.normalized_name
            ).limit(500 - len(buildings_with_count)).all()
            
            buildings_with_count.extend(remaining_buildings)
    
    # 除外ペアを取得
    exclusions = db.query(BuildingMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        excluded_pairs.add((exclusion.building1_id, exclusion.building2_id))
        excluded_pairs.add((exclusion.building2_id, exclusion.building1_id))
    
    duplicate_groups = []
    processed_ids = set()
    
    for building1, count1 in buildings_with_count:
        if building1.id in processed_ids:
            continue
        
        # SQLで類似候補を絞り込む条件を作成
        # 住所の地名部分（丁目より前）を抽出
        area_condition = None
        if building1.normalized_address:
            # 正規化された住所から地名部分（丁目より前）を抽出
            # 例：「東京都港区六本木3-16-33」→「東京都港区六本木」
            # 「東京都港区六本木1」や「東京都港区六本木１」のような形式にも対応
            addr_match = re.match(r'(.*?[区市町村][^0-9０-９]*)', building1.normalized_address)
            if addr_match:
                area_prefix = addr_match.group(1)
                area_condition = Building.normalized_address.like(f"{area_prefix}%")
        
        if area_condition is None and building1.address:
            addr_match = re.match(r'(.*?[区市町村][^0-9０-９]*)', building1.address)
            if addr_match:
                area_prefix = addr_match.group(1)
                area_condition = Building.address.like(f"{area_prefix}%")
        
        # 住所条件がない場合でも、建物名が完全一致する場合は候補として扱う
        if area_condition is None:
            # 建物名が完全一致する場合のみ続行
            same_name_condition = Building.normalized_name == building1.normalized_name
            area_condition = same_name_condition
        
        # 3つの条件パターンのいずれかに一致する建物を候補とする
        candidate_conditions = []
        
        # パターン1: 住所（地名まで）+ 築年が同一
        if building1.built_year:
            candidate_conditions.append(
                and_(
                    area_condition,
                    Building.built_year == building1.built_year
                )
            )
        
        # パターン2: 住所（地名まで）+ 総階数が同一
        if building1.total_floors:
            candidate_conditions.append(
                and_(
                    area_condition,
                    Building.total_floors == building1.total_floors
                )
            )
        
        # パターン3: 住所（地名まで）+ 築年 + 総階数が同一
        if building1.built_year and building1.total_floors:
            candidate_conditions.append(
                and_(
                    area_condition,
                    Building.built_year == building1.built_year,
                    Building.total_floors == building1.total_floors
                )
            )
        
        # いずれの条件も作成できない場合はスキップ
        if not candidate_conditions:
            continue
        
        # 候補を取得（OR条件で結合）
        candidate_query = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).filter(
            and_(
                Building.id != building1.id,
                Building.id.notin_(processed_ids),
                or_(*candidate_conditions)  # いずれかの条件に一致
            )
        ).group_by(Building.id).having(
            func.count(MasterProperty.id) > 0
        ).limit(20)  # 各建物に対して最大20候補
        
        candidate_buildings = candidate_query.all()
        
        # 詳細な類似度計算
        candidates = []
        for building2, count2 in candidate_buildings:
            # 除外ペアはスキップ
            if (building1.id, building2.id) in excluded_pairs:
                continue
            
            # 類似度を計算
            similarity = matcher.calculate_comprehensive_similarity(building1, building2)
            
            if similarity >= min_similarity:
                candidates.append({
                    "id": building2.id,
                    "normalized_name": building2.normalized_name,
                    "address": building2.address,
                    "total_floors": building2.total_floors,
                    "built_year": building2.built_year,
                    "built_month": building2.built_month,
                    "property_count": count2 or 0,
                    "similarity": round(similarity, 3)
                })
                processed_ids.add(building2.id)
        
        if candidates:
            duplicate_groups.append({
                "primary": {
                    "id": building1.id,
                    "normalized_name": building1.normalized_name,
                    "address": building1.address,
                    "total_floors": building1.total_floors,
                    "built_year": building1.built_year,
                    "built_month": building1.built_month,
                    "property_count": count1 or 0
                },
                "candidates": sorted(candidates, key=lambda x: x["similarity"], reverse=True)
            })
            processed_ids.add(building1.id)
            
            # limit に達したら終了
            if len(duplicate_groups) >= limit:
                break
    
    # 結果をキャッシュに保存
    result = {
        "duplicate_groups": duplicate_groups[:limit],
        "total_groups": len(duplicate_groups)
    }
    
    if not search:
        _duplicate_buildings_cache = {cache_key: result}
        _duplicate_buildings_cache_time = current_time
    
    return result


@router.get("/duplicate-groups")
def get_duplicate_groups(
    min_similarity: float = 0.8,
    limit: int = 50,
    offset: int = 0,
    building_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """重複候補の物件グループを取得（改善版）"""
    
    # 新しい効率的な実装を使用
    return get_duplicate_groups_v2(min_similarity, limit, offset, building_name, db)


@router.get("/duplicate-groups-v2")
def get_duplicate_groups_v2(
    min_similarity: float = 0.8,
    limit: int = 50,
    offset: int = 0,
    building_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """重複候補の物件グループを取得（効率化版）"""
    
    # 除外リストを取得
    exclusions = db.query(PropertyMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        excluded_pairs.add((exclusion.property1_id, exclusion.property2_id))
        excluded_pairs.add((exclusion.property2_id, exclusion.property1_id))
    
    # 建物名フィルタの準備
    building_filter = None
    if building_name:
        from backend.app.utils.search_normalizer import normalize_search_text
        normalized_search = normalize_search_text(building_name)
        search_terms = normalized_search.split()
        
        building_filter = Building.id.in_(
            db.query(Building.id).filter(
                and_(*[Building.normalized_name.ilike(f"%{term}%") for term in search_terms])
            )
        )
    
    # 優先度1: 同じ建物・同じ階・同じ面積の物件（最も重複の可能性が高い）
    # 部屋番号なしの物件で、同じ建物・階・面積の組み合わせを持つグループを検索
    base_query = db.query(
        MasterProperty.building_id,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        func.count(MasterProperty.id).label('count')
    ).filter(
        or_(MasterProperty.room_number.is_(None), MasterProperty.room_number == ''),
        MasterProperty.id.in_(
            db.query(PropertyListing.master_property_id).filter(
                PropertyListing.is_active == True
            ).distinct()
        )
    )
    
    if building_filter:
        base_query = base_query.filter(MasterProperty.building_id.in_(
            db.query(Building.id).filter(building_filter)
        ))
    
    # 同じ属性の組み合わせが2つ以上ある物件グループ
    potential_groups = base_query.group_by(
        MasterProperty.building_id,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout
    ).having(
        func.count(MasterProperty.id) > 1
    ).limit(100).all()  # 最大100グループ
    
    # 各グループの物件を取得
    duplicate_groups = []
    for group in potential_groups:
        # グループ内の物件を取得
        properties_query = db.query(
            MasterProperty,
            Building.normalized_name.label('building_name'),
            func.count(PropertyListing.id).label('listing_count'),
            func.max(PropertyListing.current_price).label('current_price')
        ).join(
            Building, MasterProperty.building_id == Building.id
        ).outerjoin(
            PropertyListing, MasterProperty.id == PropertyListing.master_property_id
        ).filter(
            MasterProperty.building_id == group.building_id,
            MasterProperty.floor_number == group.floor_number,
            MasterProperty.area == group.area,
            or_(MasterProperty.room_number.is_(None), MasterProperty.room_number == ''),
            PropertyListing.is_active == True
        ).group_by(
            MasterProperty.id,
            Building.normalized_name
        ).all()
        
        # 除外ペアのチェック
        property_ids = [p[0].id for p in properties_query]
        
        # 除外ペアがあるかチェック
        has_exclusion = False
        for i, id1 in enumerate(property_ids):
            for id2 in property_ids[i+1:]:
                if (id1, id2) in excluded_pairs:
                    has_exclusion = True
                    break
            if has_exclusion:
                break
        
        # 除外ペアがない場合のみグループに追加
        if not has_exclusion and len(properties_query) >= 2:
            duplicate_groups.append({
                "group_id": f"group_{len(duplicate_groups) + 1}",
                "property_count": len(properties_query),
                "building_name": properties_query[0].building_name,
                "floor_number": group.floor_number,
                "layout": group.layout,
                "area": group.area,
                "properties": sorted([
                    {
                        "id": prop[0].id,
                        "room_number": prop[0].room_number,
                        "area": prop[0].area,
                        "layout": prop[0].layout,
                        "direction": prop[0].direction,
                        "current_price": prop.current_price,
                        "listing_count": prop.listing_count or 0
                    }
                    for prop in properties_query
                ], key=lambda x: (-x["listing_count"], x["id"]))
            })
    
    # 優先度2: より緩い条件で追加のグループを検索（必要に応じて）
    if len(duplicate_groups) < limit and min_similarity < 0.85:
        # 同じ建物・同じ階の物件（面積は異なってもOK）
        additional_groups = base_query.group_by(
            MasterProperty.building_id,
            MasterProperty.floor_number,
            MasterProperty.layout
        ).having(
            func.count(MasterProperty.id) > 1
        ).limit(50).all()
        
        for group in additional_groups:
            if len(duplicate_groups) >= limit:
                break
                
            # 既存のグループと重複しないかチェック
            existing_key = f"{group.building_id}_{group.floor_number}_{group.layout}"
            if any(f"{g['floor_number']}_{g['layout']}" in existing_key for g in duplicate_groups):
                continue
            
            properties_query = db.query(
                MasterProperty,
                Building.normalized_name.label('building_name'),
                func.count(PropertyListing.id).label('listing_count'),
                func.max(PropertyListing.current_price).label('current_price')
            ).join(
                Building, MasterProperty.building_id == Building.id
            ).outerjoin(
                PropertyListing, MasterProperty.id == PropertyListing.master_property_id
            ).filter(
                MasterProperty.building_id == group.building_id,
                MasterProperty.floor_number == group.floor_number,
                MasterProperty.layout == group.layout,
                or_(MasterProperty.room_number.is_(None), MasterProperty.room_number == ''),
                PropertyListing.is_active == True
            ).group_by(
                MasterProperty.id,
                Building.normalized_name
            ).all()
            
            if len(properties_query) >= 2:
                duplicate_groups.append({
                    "group_id": f"group_{len(duplicate_groups) + 1}",
                    "property_count": len(properties_query),
                    "building_name": properties_query[0].building_name,
                    "floor_number": group.floor_number,
                    "layout": group.layout,
                    "area": None,  # 面積は統一されていない
                    "properties": sorted([
                        {
                            "id": prop[0].id,
                            "room_number": prop[0].room_number,
                            "area": prop[0].area,
                            "layout": prop[0].layout,
                            "direction": prop[0].direction,
                            "current_price": prop.current_price,
                            "listing_count": prop.listing_count or 0
                        }
                        for prop in properties_query
                    ], key=lambda x: (-x["listing_count"], x["id"]))
                })
    
    # 物件数の多い順にソート
    duplicate_groups.sort(key=lambda x: x["property_count"], reverse=True)
    
    # offset と limit を適用
    start_idx = offset
    end_idx = offset + limit
    result = duplicate_groups[start_idx:end_idx]
    
    return {
        "groups": result,
        "total": len(duplicate_groups),
        "has_more": end_idx < len(duplicate_groups)
    }


def get_duplicate_groups_simple(db: Session, limit: int, offset: int, building_name: Optional[str] = None):
    """簡易的な重複グループ取得（高速版）"""
    # 建物名フィルタリング用の条件
    building_filter = ""
    params = {"limit": limit, "offset": offset}
    
    if building_name:
        from backend.app.utils.building_search import create_building_search_params
        from backend.app.utils.search_normalizer import normalize_search_text
        
        # 検索文字列を正規化してAND検索用に分割
        normalized_search = normalize_search_text(building_name)
        search_terms = normalized_search.split()
        
        # 検索条件を生成
        if len(search_terms) > 1:
            # 複数の検索語がある場合：AND条件と完全一致の両方
            and_conditions = []
            param_count = 0
            
            # 各単語のAND条件
            for term in search_terms:
                term_conditions = []
                from backend.app.utils.search_normalizer import create_search_patterns
                term_patterns = create_search_patterns(term)
                for pattern in term_patterns:
                    param_name = f"building_name_{param_count}"
                    term_conditions.append(f"b.normalized_name ILIKE :{param_name}")
                    params[param_name] = f"%{pattern}%"
                    param_count += 1
                if term_conditions:
                    and_conditions.append(f"({' OR '.join(term_conditions)})")
            
            # 完全な文字列でも検索
            full_patterns = create_search_patterns(building_name)
            full_conditions = []
            for pattern in full_patterns:
                param_name = f"building_name_{param_count}"
                full_conditions.append(f"b.normalized_name ILIKE :{param_name}")
                params[param_name] = f"%{pattern}%"
                param_count += 1
            
            # AND条件と完全一致をORで結合
            all_conditions = []
            if and_conditions:
                all_conditions.append(f"({' AND '.join(and_conditions)})")
            if full_conditions:
                all_conditions.extend(full_conditions)
            
            if all_conditions:
                building_filter = f"AND ({' OR '.join(all_conditions)})"
        else:
            # 単一の検索語の場合
            from backend.app.utils.search_normalizer import create_search_patterns
            search_patterns = create_search_patterns(building_name)
            conditions = []
            for i, pattern in enumerate(search_patterns):
                param_name = f"building_name_{i}"
                conditions.append(f"b.normalized_name ILIKE :{param_name}")
                params[param_name] = f"%{pattern}%"
            
            if conditions:
                building_filter = f"AND ({' OR '.join(conditions)})"
    
    # SQLで面積を基準にした重複グループを検出（間取りが異なる場合も含む）
    query = text(f"""
        WITH property_candidates AS (
            -- 部屋番号なしでアクティブな物件を取得
            SELECT 
                mp.id,
                mp.building_id,
                mp.floor_number,
                mp.layout,
                mp.area,
                mp.direction,
                b.normalized_name as building_name
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            JOIN property_listings pl ON mp.id = pl.master_property_id
            WHERE 
                (mp.room_number IS NULL OR mp.room_number = '')
                AND pl.is_active = true
                {building_filter}
        ),
        property_groups AS (
            -- 建物・階でグループ化し、面積の範囲を確認
            SELECT 
                building_id,
                floor_number,
                building_name,
                -- 間取りが複数ある場合は代表的なものを表示
                (ARRAY_AGG(DISTINCT layout ORDER BY layout))[1] as layout,
                STRING_AGG(DISTINCT layout, ', ' ORDER BY layout) as all_layouts,
                MIN(COALESCE(area, 0)) as min_area,
                MAX(COALESCE(area, 0)) as max_area,
                ARRAY_AGG(DISTINCT id ORDER BY id) as property_ids,
                COUNT(DISTINCT id) as property_count
            FROM property_candidates
            GROUP BY building_id, floor_number, building_name
            HAVING 
                COUNT(DISTINCT id) >= 2  -- 2件以上のグループのみ
                AND MAX(COALESCE(area, 0)) - MIN(COALESCE(area, 0)) < 0.5  -- グループ内の面積差が0.5㎡未満
        )
        SELECT 
            pg.*,
            ROUND(CAST((min_area + max_area) / 2 AS numeric), 2) as avg_area
        FROM property_groups pg
        ORDER BY property_count DESC, building_name, floor_number
        LIMIT :limit OFFSET :offset
    """)
    
    result = db.execute(query, params)
    groups = []
    
    for row in result:
        # 各グループの物件詳細を取得（方角でソート）
        property_query = text("""
            WITH price_votes AS (
                -- アクティブな掲載から価格を集計（多数決用）
                SELECT 
                    pl.master_property_id as property_id,
                    pl.current_price,
                    COUNT(*) as vote_count
                FROM property_listings pl
                WHERE pl.is_active = true 
                    AND pl.current_price IS NOT NULL
                    AND pl.master_property_id = ANY(:ids)
                GROUP BY pl.master_property_id, pl.current_price
            ),
            majority_prices AS (
                -- 各物件の多数決価格を決定
                SELECT 
                    property_id,
                    current_price,
                    vote_count,
                    ROW_NUMBER() OVER (PARTITION BY property_id ORDER BY vote_count DESC, current_price ASC) as rn
                FROM price_votes
            )
            SELECT 
                mp.id,
                mp.room_number,
                mp.area,
                mp.layout,
                mp.direction,
                COALESCE(maj.current_price, MAX(pl.current_price)) as current_price,  -- 多数決価格、なければ最大価格
                STRING_AGG(DISTINCT pl.agency_name, ', ') as agency_names,
                COUNT(DISTINCT pl.id) as listing_count,
                COUNT(DISTINCT pl.source_site) as source_count
            FROM master_properties mp
            LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
            LEFT JOIN majority_prices maj ON mp.id = maj.property_id AND maj.rn = 1
            WHERE mp.id = ANY(:ids)
            GROUP BY mp.id, mp.room_number, mp.area, mp.layout, mp.direction, maj.current_price
            ORDER BY 
                mp.direction NULLS LAST,  -- 方角がある物件を優先
                mp.area,
                mp.id
        """)
        
        properties = []
        prop_result = db.execute(property_query, {"ids": row.property_ids})
        for prop in prop_result:
            properties.append({
                "id": prop.id,
                "room_number": prop.room_number,
                "area": prop.area,
                "layout": prop.layout,
                "direction": prop.direction,
                "current_price": prop.current_price,
                "agency_names": prop.agency_names,
                "listing_count": prop.listing_count,
                "source_count": prop.source_count
            })
        
        groups.append({
            "group_id": f"group_{row.building_id}_{row.floor_number}_{row.layout}_{int(row.avg_area)}",
            "property_count": row.property_count,
            "building_name": row.building_name,
            "floor_number": row.floor_number,
            "layout": row.layout,
            "properties": properties
        })
    
    # 全体の件数を取得
    count_query = text(f"""
        WITH property_candidates AS (
            SELECT 
                mp.id,
                mp.building_id,
                mp.floor_number,
                mp.area
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            JOIN property_listings pl ON mp.id = pl.master_property_id
            WHERE 
                (mp.room_number IS NULL OR mp.room_number = '')
                AND pl.is_active = true
                {building_filter}
        ),
        property_groups AS (
            SELECT 
                building_id,
                floor_number,
                MIN(COALESCE(area, 0)) as min_area,
                MAX(COALESCE(area, 0)) as max_area,
                COUNT(DISTINCT id) as property_count
            FROM property_candidates
            GROUP BY building_id, floor_number
            HAVING 
                COUNT(DISTINCT id) >= 2
                AND MAX(COALESCE(area, 0)) - MIN(COALESCE(area, 0)) < 0.5
        )
        SELECT COUNT(*) as total FROM property_groups
    """)
    
    total_result = db.execute(count_query, params).fetchone()
    total = total_result.total if total_result else 0
    
    return {
        "groups": groups,
        "total": total,
        "has_more": offset + limit < total
    }


def calculate_similarity(prop1, prop2):
    """2つの物件の類似度を計算"""
    # 同じ建物、同じ階
    if prop1.building_id != prop2.building_id or prop1.floor_number != prop2.floor_number:
        return 0.0
    
    # 面積の差
    area_diff = abs((prop1.area or 0) - (prop2.area or 0))
    
    # 間取りが異なる場合の特別処理
    if prop1.layout != prop2.layout:
        # 面積が非常に近い（0.5㎡以内）場合は、間取り表記の違いの可能性
        if area_diff < 0.5:
            # 例: "1LDK"と"1SLDK"、"2DK"と"2LDK"などの表記ゆれ
            return 0.75  # 中程度の類似度
        else:
            return 0.0  # 面積も異なる場合は別物件
    
    # 以下、間取りが同じ場合の処理
    if area_diff >= 1.0:
        return 0.7  # 面積差が大きい
    
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
    from backend.app.utils.search_normalizer import create_search_patterns, normalize_search_text
    
    # 検索文字列を正規化
    normalized_query = normalize_search_text(query)
    search_terms = normalized_query.split()
    
    name_query = db.query(MasterProperty).join(
        Building, MasterProperty.building_id == Building.id
    )
    
    if len(search_terms) > 1:
        # 複数の検索語がある場合
        # 各検索語のパターンを生成
        all_conditions = []
        
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                term_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
            if term_conditions:
                and_conditions.append(or_(*term_conditions))
        
        if and_conditions:
            all_conditions.append(and_(*and_conditions))
        
        # 全体文字列のパターンでも検索
        full_patterns = create_search_patterns(query)
        for pattern in full_patterns:
            all_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
        
        if all_conditions:
            name_query = name_query.filter(or_(*all_conditions))
    else:
        # 単一の検索語の場合
        search_patterns = create_search_patterns(query)
        search_conditions = []
        for pattern in search_patterns:
            search_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
        
        if search_conditions:
            name_query = name_query.filter(or_(*search_conditions))
    
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


# 削除: admin_properties.pyに移行


@router.post("/merge-buildings")
def merge_buildings(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None  # オプショナルなバックグラウンドタスク
):
    """複数の建物を統合"""
    import json
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[DEBUG] merge_buildings request: {json.dumps(request)}")
    
    primary_id = request.get("primary_id")
    secondary_ids = request.get("secondary_ids", [])
    
    logger.info(f"[DEBUG] primary_id: {primary_id} (type: {type(primary_id)}), secondary_ids: {secondary_ids} (types: {[type(x) for x in secondary_ids]})")
    
    if not primary_id or not secondary_ids:
        raise HTTPException(status_code=400, detail="primary_id and secondary_ids are required")
    
    # 主建物を取得
    primary_building = db.query(Building).filter(Building.id == primary_id).first()
    if not primary_building:
        raise HTTPException(status_code=404, detail="Primary building not found")
    
    # 副建物を取得
    secondary_buildings = db.query(Building).filter(Building.id.in_(secondary_ids)).all()
    if len(secondary_buildings) != len(secondary_ids):
        # デバッグ情報を追加
        found_ids = [b.id for b in secondary_buildings]
        missing_ids = [sid for sid in secondary_ids if sid not in found_ids]
        logger.error(f"[DEBUG] Requested secondary_ids: {secondary_ids}")
        logger.error(f"[DEBUG] Found building IDs: {found_ids}")
        logger.error(f"[DEBUG] Missing building IDs: {missing_ids}")
        raise HTTPException(
            status_code=404, 
            detail=f"One or more secondary buildings not found. Missing IDs: {missing_ids}"
        )
    
    try:
        import time
        start_time = time.time()
        timeout_seconds = 30  # 30秒のタイムアウト
        
        merged_count = 0
        moved_properties = 0
        # 削除前に建物情報を保存（履歴記録用）
        building_infos = []
        for secondary_building in secondary_buildings:
            properties = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary_building.id
            ).all()
            
            # 移動する物件のIDリストを記録
            property_ids = [prop.id for prop in properties]
            
            building_infos.append({
                "building": secondary_building,
                "property_count": len(properties),
                "property_ids": property_ids  # 移動する物件のIDリスト
            })
        
        # 副建物の物件を主建物に移動
        for building_index, secondary_building in enumerate(secondary_buildings):
            # タイムアウトチェック
            if time.time() - start_time > timeout_seconds:
                logger.error(f"[DEBUG] Timeout after {timeout_seconds} seconds at building {building_index+1}/{len(secondary_buildings)}")
                raise HTTPException(status_code=408, detail=f"処理がタイムアウトしました（{timeout_seconds}秒）")
            
            logger.info(f"[DEBUG] Processing building {building_index+1}/{len(secondary_buildings)}: {secondary_building.normalized_name} (ID: {secondary_building.id})")
            
            # 副建物の物件を主建物に移動
            properties_to_move = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary_building.id
            ).all()
            
            logger.info(f"[DEBUG] Moving {len(properties_to_move)} properties from building {secondary_building.id} to {primary_id}")
            
            # 一括で既存の物件をチェック（パフォーマンス向上）
            existing_properties_dict = {}
            if len(properties_to_move) > 0:
                # 主建物の既存物件を取得してキャッシュ
                existing_properties = db.query(MasterProperty).filter(
                    MasterProperty.building_id == primary_id
                ).all()
                
                for ep in existing_properties:
                    key = (ep.floor_number, ep.area, ep.layout, ep.direction)
                    existing_properties_dict[key] = ep
                    
            for prop in properties_to_move:
                # 移動先に同じ物件が既に存在するかチェック（辞書検索で高速化）
                prop_key = (prop.floor_number, prop.area, prop.layout, prop.direction)
                existing_property = existing_properties_dict.get(prop_key)
                
                if existing_property:
                    logger.info(f"[DEBUG] Duplicate property found: building={primary_id}, floor={prop.floor_number}, area={prop.area}, layout={prop.layout}, direction={prop.direction}")
                    
                    # 掲載情報を既存の物件に移動（SQLで直接更新）
                    result = db.execute(
                        text("""
                            UPDATE property_listings 
                            SET master_property_id = :existing_id 
                            WHERE master_property_id = :old_id
                        """),
                        {"existing_id": existing_property.id, "old_id": prop.id}
                    )
                    
                    listings_moved = result.rowcount
                    logger.info(f"[DEBUG] Moved {listings_moved} listings from property {prop.id} to {existing_property.id} using SQL")
                    
                    # 掲載情報が確実に移動したか確認（フラッシュは後でまとめて行う）
                    remaining_listings = db.query(PropertyListing).filter(
                        PropertyListing.master_property_id == prop.id
                    ).count()
                    
                    if remaining_listings > 0:
                        logger.error(f"[DEBUG] Property {prop.id} still has {remaining_listings} listings!")
                        raise ValueError(f"Property {prop.id} still has {remaining_listings} listings after moving!")
                    
                    # 重複する物件を削除（SQLで直接削除）
                    db.execute(
                        text("DELETE FROM master_properties WHERE id = :prop_id"),
                        {"prop_id": prop.id}
                    )
                    logger.info(f"[DEBUG] Deleted duplicate property {prop.id} using SQL")
                    # 削除した物件も移動としてカウント（掲載情報は移動したため）
                    moved_properties += 1
                else:
                    # 重複がない場合は通常通り移動
                    logger.info(f"[DEBUG] Moving property {prop.id} from building {prop.building_id} to {primary_id}")
                    if primary_id is None:
                        raise ValueError(f"primary_id is None! Cannot move property {prop.id}")
                    if not isinstance(primary_id, int):
                        raise ValueError(f"primary_id is not an integer: {type(primary_id)} = {primary_id}")
                    prop.building_id = primary_id
                    moved_properties += 1
            
            # 物件の移動を確実にするため、一旦フラッシュ（建物ごとに一度だけ）
            db.flush()
            
            # 副建物にまだ物件が残っていないか確認
            remaining_properties = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary_building.id
            ).count()
            
            if remaining_properties > 0:
                raise ValueError(f"Building {secondary_building.id} still has {remaining_properties} properties!")
            
            # この建物が他の建物の統合先として参照されていないか確認
            referencing_merges = db.query(BuildingMergeHistory).filter(
                or_(
                    BuildingMergeHistory.primary_building_id == secondary_building.id,
                    BuildingMergeHistory.direct_primary_building_id == secondary_building.id,
                    BuildingMergeHistory.final_primary_building_id == secondary_building.id
                )
            ).all()
            
            if referencing_merges:
                # 参照している統合履歴の統合先を更新
                for ref_merge in referencing_merges:
                    logger.info(f"[DEBUG] 統合履歴の参照を更新: {ref_merge.merged_building_name} の統合先を {secondary_building.id} → {primary_id}")
                    if ref_merge.primary_building_id == secondary_building.id:
                        ref_merge.primary_building_id = primary_id
                    if ref_merge.direct_primary_building_id == secondary_building.id:
                        ref_merge.direct_primary_building_id = primary_id
                    if ref_merge.final_primary_building_id == secondary_building.id:
                        ref_merge.final_primary_building_id = primary_id
                    ref_merge.merge_depth += 1  # 統合の深さを増やす
            
            # 副建物に関連する除外設定を削除
            # building_merge_exclusionsテーブルから、この建物が関わっている除外設定を削除
            exclusions_to_delete = db.query(BuildingMergeExclusion).filter(
                or_(
                    BuildingMergeExclusion.building1_id == secondary_building.id,
                    BuildingMergeExclusion.building2_id == secondary_building.id
                )
            ).all()
            
            for exclusion in exclusions_to_delete:
                logger.info(f"[DEBUG] 建物統合による除外設定削除: building1_id={exclusion.building1_id}, building2_id={exclusion.building2_id}")
                db.delete(exclusion)
            
            # 副建物を削除
            db.delete(secondary_building)
            merged_count += 1
        
        # 各副建物に対して個別に統合履歴を記録（新スキーマに合わせて）
        for info in building_infos:
            building = info["building"]
            
            # ハイブリッド方式：この建物が以前に他の建物を統合していた場合の処理
            # final_primary_building_idのみを更新し、direct_primary_building_idは保持
            old_merges = db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.final_primary_building_id == building.id
            ).all()
            
            for old_merge in old_merges:
                # 最終統合先のみ更新（直接の統合先は保持）
                old_merge.final_primary_building_id = primary_id
                old_merge.merge_depth += 1  # 統合の深さを増やす
                # primary_building_idも互換性のため更新
                old_merge.primary_building_id = primary_id
                logger.info(f"[DEBUG] ハイブリッドチェイン統合: {old_merge.merged_building_name} → final:{primary_id}, depth:{old_merge.merge_depth}")
            
            # 新しい統合履歴を追加（merge_detailsに詳細情報を含める）
            merge_details = {
                "merged_buildings": [{
                    "id": building.id,
                    "normalized_name": building.normalized_name,
                    "address": building.address,
                    "total_floors": building.total_floors,
                    "built_year": building.built_year,
                    "construction_type": building.construction_type,  # 構造タイプも保存
                    "properties_moved": info["property_count"],
                    "property_ids": info["property_ids"]  # 移動した物件のIDリスト
                }]
            }
            
            merge_history = BuildingMergeHistory(
                # 互換性のためprimary_building_idも設定
                primary_building_id=primary_id,
                # ハイブリッド方式の新フィールド
                direct_primary_building_id=primary_id,  # 直接の統合先
                final_primary_building_id=primary_id,   # 最終的な統合先（現時点では同じ）
                merge_depth=0,                          # 直接統合なので深さは0
                merged_building_id=building.id,
                merged_building_name=building.normalized_name,
                # canonical_nameがある場合は保存、なければNone
                canonical_merged_name=building.canonical_name if hasattr(building, 'canonical_name') else None,
                merged_by="admin",
                reason="管理画面から手動統合",
                property_count=info["property_count"],
                merge_details=merge_details  # 詳細情報を追加
            )
            db.add(merge_history)
        
        db.commit()
        
        # 統合後に主建物の情報を多数決で更新
        from ..utils.majority_vote_updater import MajorityVoteUpdater
        updater = MajorityVoteUpdater(db)
        logger.info(f"[DEBUG] Updating primary building {primary_id} with majority vote after merge")
        updater.update_building_name_by_majority(primary_id)
        
        # 統合結果の詳細を取得
        final_property_count = db.query(MasterProperty).filter(
            MasterProperty.building_id == primary_building.id
        ).count()
        
        # キャッシュをクリア（統合により建物リストが変更されたため）
        global _duplicate_buildings_cache, _duplicate_buildings_cache_time
        _duplicate_buildings_cache = {}
        _duplicate_buildings_cache_time = 0
        logger.info("[DEBUG] Cleared duplicate buildings cache after merge")
        
        return {
            "success": True,
            "merged_count": merged_count,
            "moved_properties": moved_properties,
            "primary_building": {
                "id": primary_building.id,
                "normalized_name": primary_building.normalized_name,
                "address": primary_building.address,
                "property_count": final_property_count
            },
            "message": f"{merged_count}件の建物を統合し、{moved_properties}件の物件を処理しました。重複物件は自動的に統合されました。"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"[DEBUG] Error in merge_buildings: {str(e)}")
        logger.error(f"[DEBUG] Error type: {type(e)}")
        logger.error(f"[DEBUG] primary_id at error: {primary_id}")
        logger.error(f"[DEBUG] secondary_ids at error: {secondary_ids}")
        import traceback
        logger.error(f"[DEBUG] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/move-property-to-building")
def move_property_to_building(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """物件を別の建物に移動"""
    import logging
    logger = logging.getLogger(__name__)
    
    property_id = request.get("property_id")
    target_building_id = request.get("target_building_id")
    
    if not property_id or not target_building_id:
        raise HTTPException(status_code=400, detail="property_id and target_building_id are required")
    
    # 物件を取得
    property_obj = db.query(MasterProperty).filter(MasterProperty.id == property_id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # 移動先の建物を取得
    target_building = db.query(Building).filter(Building.id == target_building_id).first()
    if not target_building:
        raise HTTPException(status_code=404, detail="Target building not found")
    
    # 元の建物IDを記録
    original_building_id = property_obj.building_id
    
    if original_building_id == target_building_id:
        raise HTTPException(status_code=400, detail="Property is already in the target building")
    
    try:
        # 移動先に同じ物件が既に存在するかチェック
        existing_property = db.query(MasterProperty).filter(
            MasterProperty.building_id == target_building_id,
            MasterProperty.floor_number == property_obj.floor_number,
            MasterProperty.area == property_obj.area,
            MasterProperty.layout == property_obj.layout,
            MasterProperty.direction == property_obj.direction,
            MasterProperty.id != property_id
        ).first()
        
        if existing_property:
            # 重複物件が存在する場合の処理
            logger.warning(
                f"Duplicate property found in target building: "
                f"building={target_building_id}, floor={property_obj.floor_number}, "
                f"area={property_obj.area}, layout={property_obj.layout}"
            )
            
            # 掲載情報を既存の物件に移動
            db.execute(
                text("""
                    UPDATE property_listings 
                    SET master_property_id = :existing_id 
                    WHERE master_property_id = :old_id
                """),
                {"existing_id": existing_property.id, "old_id": property_id}
            )
            
            # 移動元の物件を削除
            db.delete(property_obj)
            moved_property_id = existing_property.id
            message = f"物件を移動し、重複物件と統合しました（物件ID: {property_id} → {existing_property.id}）"
        else:
            # 重複がない場合は通常の移動
            property_obj.building_id = target_building_id
            moved_property_id = property_id
            message = f"物件を建物ID {original_building_id} から {target_building_id} に移動しました"
        
        db.flush()
        
        # 多数決による建物情報の更新
        from ..utils.majority_vote_updater import MajorityVoteUpdater
        updater = MajorityVoteUpdater(db)
        
        # 元の建物の情報を更新（物件が減ったため）
        if original_building_id:
            logger.info(f"Updating original building {original_building_id} with majority vote")
            updater.update_building_name_by_majority(original_building_id)
        
        # 移動先の建物の情報を更新（物件が増えたため）
        logger.info(f"Updating target building {target_building_id} with majority vote")
        updater.update_building_name_by_majority(target_building_id)
        
        db.commit()
        
        # 結果を返す
        return {
            "success": True,
            "message": message,
            "moved_property_id": moved_property_id,
            "original_building_id": original_building_id,
            "target_building_id": target_building_id
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error moving property: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


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
            "property_hash": secondary.property_hash,
            "management_fee": secondary.management_fee,
            "repair_fund": secondary.repair_fund,
            "station_info": secondary.station_info,
            "parking_info": secondary.parking_info,
            "display_building_name": secondary.display_building_name
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
                    # 古い情報なので削除（まず価格履歴を削除）
                    db.execute(text(
                        "DELETE FROM listing_price_history WHERE property_listing_id = :listing_id"
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
        
        # ハイブリッド方式：副物件が以前に他の物件を統合していた場合の処理
        # final_primary_property_idのみを更新し、direct_primary_property_idは保持
        old_merges = db.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.final_primary_property_id == secondary.id
        ).all()
        
        for old_merge in old_merges:
            # 最終統合先のみ更新（直接の統合先は保持）
            old_merge.final_primary_property_id = primary.id
            old_merge.merge_depth += 1  # 統合の深さを1増やす
        
        # 統合履歴を記録
        merge_history = PropertyMergeHistory(
            # 互換性のためprimary_property_idも設定
            primary_property_id=merge_request.primary_property_id,
            # ハイブリッド方式の新フィールド
            direct_primary_property_id=merge_request.primary_property_id,  # 直接の統合先
            final_primary_property_id=merge_request.primary_property_id,   # 最終的な統合先（現時点では同じ）
            merge_depth=0,                          # 直接統合なので深さは0
            merged_property_id=merge_request.secondary_property_id,
            moved_listings=merged_count,
            listing_count=merged_count,
            merge_details={
                "secondary_property": secondary_backup,
                "moved_listings": moved_listings_info,
                "primary_updates": primary_updates
            },
            merged_by="admin",  # TODO: 実際のユーザー名を記録
            reason="手動統合"
        )
        db.add(merge_history)
        
        # すべての変更をフラッシュしてから副物件を削除
        db.flush()
        
        # 再販物件の参照更新は削除（resale_property_idカラムは現在のスキーマに存在しない）
        
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
        
        
        # 2. 残っている掲載情報を削除
        db.execute(text(
            "DELETE FROM property_listings WHERE master_property_id = :property_id"
        ), {"property_id": merge_request.secondary_property_id})
        
        # 3. ambiguous_property_matchesテーブルの参照を更新
        # 副物件が選択物件として参照されている場合、主物件に更新
        db.execute(text("""
            UPDATE ambiguous_property_matches 
            SET selected_property_id = :primary_id 
            WHERE selected_property_id = :secondary_id
        """), {
            "primary_id": merge_request.primary_property_id,
            "secondary_id": merge_request.secondary_property_id
        })
        
        # 4. candidate_property_idsに副物件IDが含まれている場合も更新
        # JSON配列内のIDを置換する必要があるため、より複雑な処理が必要
        db.execute(text("""
            UPDATE ambiguous_property_matches 
            SET candidate_property_ids = (
                SELECT json_agg(
                    CASE 
                        WHEN elem::text::int = :secondary_id THEN :primary_id 
                        ELSE elem::text::int 
                    END
                )
                FROM json_array_elements(candidate_property_ids) AS elem
            )
            WHERE candidate_property_ids::text LIKE '%' || :secondary_id || '%'
        """), {
            "primary_id": merge_request.primary_property_id,
            "secondary_id": merge_request.secondary_property_id
        })
        
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
    started_at: Optional[datetime] = None  # Noneを許可
    completed_at: Optional[datetime] = None
    progress: Dict[str, Dict[str, Any]]  # 各スクレイパー・エリアの進行状況
    errors: List[str]
    logs: Optional[List[Dict[str, Any]]] = []  # 詳細ログ
    error_logs: Optional[List[Dict[str, Any]]] = []  # エラーログ
    warning_logs: Optional[List[Dict[str, Any]]] = []  # 警告ログ


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
                    
                    # カスタムログハンドラーを設定（警告ログをキャプチャ）
                    import logging
                    
                    class TaskLogHandler(logging.Handler):
                        """タスクのログに警告を追加するハンドラー"""
                        def emit(self, record):
                            if record.levelno >= logging.WARNING:  # WARNING以上のログをキャプチャ
                                log_entry = {
                                    "timestamp": datetime.now().isoformat(),
                                    "type": "warning",
                                    "level": record.levelname,
                                    "scraper": scraper_name,
                                    "area": area_name,
                                    "message": record.getMessage()
                                }
                                
                                # ⚠️ マークが含まれる曖昧なマッチングログを特別扱い
                                if "⚠️" in record.getMessage() and "曖昧なマッチング" in record.getMessage():
                                    log_entry["type"] = "ambiguous_match"
                                    # メッセージから詳細を抽出
                                    import re
                                    match = re.search(r"選択ID=(\d+).*候補数=(\d+).*信頼度=([\d.]+%)", record.getMessage())
                                    if match:
                                        log_entry["property_id"] = int(match.group(1))
                                        log_entry["candidates"] = int(match.group(2))
                                        log_entry["confidence"] = match.group(3)
                                
                                # タスクのログに追加
                                if "logs" not in scraping_tasks[task_id]:
                                    scraping_tasks[task_id]["logs"] = []
                                scraping_tasks[task_id]["logs"].append(log_entry)
                                if len(scraping_tasks[task_id]["logs"]) > 100:  # 最大100件まで保持
                                    scraping_tasks[task_id]["logs"] = scraping_tasks[task_id]["logs"][-100:]
                                
                                # warning_logsにも追加（フロントエンド用）
                                if "warning_logs" not in scraping_tasks[task_id]:
                                    scraping_tasks[task_id]["warning_logs"] = []
                                scraping_tasks[task_id]["warning_logs"].append(log_entry)
                                if len(scraping_tasks[task_id]["warning_logs"]) > 50:  # 最大50件まで保持
                                    scraping_tasks[task_id]["warning_logs"] = scraping_tasks[task_id]["warning_logs"][-50:]
                    
                    # scraperのloggerにハンドラーを追加
                    task_log_handler = TaskLogHandler()
                    task_log_handler.setLevel(logging.WARNING)
                    if hasattr(scraper, 'logger'):
                        scraper.logger.addHandler(task_log_handler)
                    
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
                                    # update_detailsを取得（create_or_update_listingから返される第3要素）
                                    update_details = result[2] if isinstance(result, tuple) and len(result) > 2 else None
                                    log_entry["message"] = f"その他の更新: {title} ({price}万円)"
                                    if update_details:
                                        log_entry["update_details"] = update_details  # update_detailsをログエントリに追加
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
                        # ログハンドラーを削除（メモリリーク防止）
                        if hasattr(scraper, 'logger') and 'task_log_handler' in locals():
                            scraper.logger.removeHandler(task_log_handler)
                        
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
            "error_logs": [],  # エラーログを初期化
            "warning_logs": []  # 警告ログを初期化（曖昧なマッチング等）
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
                        
                        # progress_detailからも進捗情報を取得（コマンドライン実行用）
                        if db_task.progress_detail:
                            # 通常のスクレイピングタスクの場合
                            for key, detail in db_task.progress_detail.items():
                                if key not in progress:  # 既存の進捗情報を優先
                                    progress[key] = detail
                        
                        # タスクのタイプを判定
                        task_type = 'parallel'
                        
                        # タスク情報を構築
                        task = {
                            'task_id': db_task.task_id,
                            'type': task_type,
                            'status': db_task.status,
                            'scrapers': db_task.scrapers or [],
                            'area_codes': db_task.areas or [],
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
                            'warning_logs': db_task.warning_logs or [],
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
        
        # progress_detailからも進捗情報を取得（コマンドライン実行用）
        if db_task.progress_detail:
            for key, detail in db_task.progress_detail.items():
                if key not in progress:  # 既存の進捗情報を優先
                    progress[key] = detail
        
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
            'warning_logs': db_task.warning_logs or [],
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


# エリアコードのマッピング（地価の高い順）
# 2024年時点の公示地価・路線価を参考に並び替え
AREA_CODES = {
    "千代田区": "13101",  # 最も地価が高い
    "港区": "13103",      # 2番目
    "中央区": "13102",    # 3番目
    "渋谷区": "13113",    # 4番目
    "新宿区": "13104",    # 5番目
    "文京区": "13105",    # 6番目
    "目黒区": "13110",    # 7番目
    "品川区": "13109",    # 8番目
    "世田谷区": "13112",  # 9番目
    "豊島区": "13116",    # 10番目
    "台東区": "13106",    # 11番目
    "中野区": "13114",    # 12番目
    "杉並区": "13115",    # 13番目
    "江東区": "13108",    # 14番目
    "大田区": "13111",    # 15番目
    "墨田区": "13107",    # 16番目
    "北区": "13117",      # 17番目
    "荒川区": "13118",    # 18番目
    "板橋区": "13119",    # 19番目
    "練馬区": "13120",    # 20番目
    "江戸川区": "13123",  # 21番目
    "葛飾区": "13122",    # 22番目
    "足立区": "13121"     # 23番目
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


@router.get("/building-merge-history")
def get_building_merge_history(
    limit: int = 50,
    include_reverted: bool = False,
    db: Session = Depends(get_db)
):
    """建物統合履歴を取得"""
    from backend.app.utils.datetime_utils import to_jst_string
    
    query = db.query(BuildingMergeHistory).join(
        Building, BuildingMergeHistory.primary_building_id == Building.id, isouter=True
    )
    
    histories = query.order_by(BuildingMergeHistory.merged_at.desc()).limit(limit).all()
    
    result = []
    for history in histories:
        # 主建物の情報
        primary_building = history.primary_building
        primary_data = {
            "id": primary_building.id,
            "normalized_name": primary_building.normalized_name
        } if primary_building else {
            "id": history.primary_building_id,
            "normalized_name": "（削除済み）"
        }
        
        # 統合された建物の情報
        secondary_data = {
            "id": history.merged_building_id,
            "normalized_name": history.merged_building_name or "（不明）",
            "properties_moved": history.property_count
        }
        
        result.append({
            "id": history.id,
            "primary_building": primary_data,
            "secondary_building": secondary_data,
            "moved_properties": history.property_count or 0,
            "merge_details": {
                "reason": history.reason,
                "merged_by": history.merged_by
            },
            "created_at": to_jst_string(history.merged_at)
        })
    
    return {"histories": result, "total": len(result)}


@router.get("/property-merge-history")
def get_property_merge_history(
    limit: int = 50,
    include_reverted: bool = False,
    db: Session = Depends(get_db)
):
    """物件統合履歴を取得"""
    from backend.app.utils.datetime_utils import to_jst_string
    
    # 取り消し時に履歴を削除する仕様のため、すべての履歴を表示
    histories = db.query(PropertyMergeHistory).order_by(
        PropertyMergeHistory.merged_at.desc()
    ).limit(limit).all()
    
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
            "id": history.merged_property_id,
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
            "merged_at": to_jst_string(history.merged_at),
            "merged_by": history.merged_by
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
    detail_refetch_hours: Optional[int] = None
    ignore_error_history: bool = False


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
                force_detail_fetch=request.force_detail_fetch,
                detail_refetch_hours=request.detail_refetch_hours,
                ignore_error_history=request.ignore_error_history
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
    """すべてのスクレイピング履歴を削除（実行中のタスクを除く）"""
    try:
        # 実行中のタスクのIDを取得
        running_task_ids = db.query(ScrapingTask.task_id).filter(
            ScrapingTask.status.in_(['running', 'paused'])
        ).all()
        running_ids = [task_id[0] for task_id in running_task_ids]
        
        # 実行中のタスクを除いて進捗情報を削除
        if running_ids:
            deleted_progress = db.query(ScrapingTaskProgress).filter(
                ~ScrapingTaskProgress.task_id.in_(running_ids)
            ).delete(synchronize_session=False)
        else:
            deleted_progress = db.query(ScrapingTaskProgress).delete()
        
        # 実行中のタスクを除いてタスク本体を削除
        if running_ids:
            deleted_tasks = db.query(ScrapingTask).filter(
                ~ScrapingTask.task_id.in_(running_ids)
            ).delete(synchronize_session=False)
        else:
            deleted_tasks = db.query(ScrapingTask).delete()
        
        db.commit()
        
        message = "スクレイピング履歴を削除しました"
        if running_ids:
            message += f"（実行中の{len(running_ids)}件を除く）"
        
        return {
            "message": message,
            "deleted_tasks": deleted_tasks,
            "deleted_progress": deleted_progress,
            "skipped_running_tasks": len(running_ids)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"履歴の削除に失敗しました: {str(e)}")


def calculate_final_primary_property(
    db: Session,
    property_id: int,
    excluded_property_id: int = None,
    visited: set = None
) -> int:
    """物件の最終的な統合先を再帰的に計算（チェーン統合対応）"""
    if visited is None:
        visited = set()
    
    current_id = property_id
    
    while current_id not in visited:
        visited.add(current_id)
        
        # この物件が統合されている履歴を検索（除外する統合以外）
        merge_history = db.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.merged_property_id == current_id,
            PropertyMergeHistory.merged_property_id != excluded_property_id
        ).first()
        
        if not merge_history:
            # これ以上統合先がない場合、現在のIDが最終統合先
            return current_id
        
        # 次の統合先へ
        current_id = merge_history.direct_primary_property_id
    
    # 循環参照を検出した場合、現在のIDを返す
    return current_id


def calculate_final_primary_building(db: Session, building_id: int) -> int:
    """
    ハイブリッド方式：建物の最終的な統合先を計算
    direct_primary_building_idをたどって最終的な統合先を見つける
    """
    visited = set()  # 循環参照を防ぐ
    current_id = building_id
    
    while True:
        # 既に訪問済みの場合は循環参照
        if current_id in visited:
            return current_id
        visited.add(current_id)
        
        # この建物が統合されている履歴を検索
        merge_history = db.query(BuildingMergeHistory).filter(
            BuildingMergeHistory.merged_building_id == current_id
        ).first()
        
        if not merge_history:
            # これ以上統合先がない場合、現在のIDが最終統合先
            return current_id
        
        # 次の統合先へ
        current_id = merge_history.direct_primary_building_id


def calculate_final_primary_building_after_revert(
    db: Session, 
    building_id: int, 
    excluded_building_id: int
) -> int:
    """
    取り消し後の最終統合先を計算
    excluded_building_idへの統合は無視する
    """
    visited = set()  # 循環参照を防ぐ
    current_id = building_id
    
    while True:
        # 既に訪問済みの場合は循環参照
        if current_id in visited:
            return current_id
        visited.add(current_id)
        
        # この建物が統合されている履歴を検索（除外する統合以外）
        merge_history = db.query(BuildingMergeHistory).filter(
            BuildingMergeHistory.merged_building_id == current_id,
            BuildingMergeHistory.merged_building_id != excluded_building_id
        ).first()
        
        if not merge_history:
            # これ以上統合先がない場合、現在のIDが最終統合先
            return current_id
        
        # 次の統合先へ
        current_id = merge_history.direct_primary_building_id


@router.post("/revert-building-merge/{history_id}")
def revert_building_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """統合を取り消す（建物を復元）"""
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # 建物が既に存在するかどうかで取り消し済みかを判断
    if history.merge_details:
        for merged_building in history.merge_details.get("merged_buildings", []):
            existing = db.query(Building).filter(Building.id == merged_building["id"]).first()
            if existing:
                raise HTTPException(status_code=400, detail="既に取り消し済みです（建物が既に存在します）")
    
    try:
        # 主建物の存在確認
        primary_building = db.query(Building).filter(
            Building.id == history.primary_building_id
        ).first()
        
        if not primary_building:
            raise HTTPException(status_code=404, detail="主建物が見つかりません")
        
        # 統合時の詳細情報から建物を復元
        restored_count = 0
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            
            # 既に存在するかチェック
            existing = db.query(Building).filter(Building.id == building_id).first()
            if existing:
                print(f"[WARNING] Building {building_id} already exists, skipping restoration")
                continue
            
            # 建物を復元（読み仮名も生成）
            from ..utils.reading_generator import generate_reading
            building = Building(
                id=building_id,
                normalized_name=merged_building["normalized_name"],
                address=merged_building.get("address"),
                reading=generate_reading(merged_building["normalized_name"]),
                total_floors=merged_building.get("total_floors"),
                built_year=merged_building.get("built_year"),
                construction_type=merged_building.get("construction_type")  # structureではなくconstruction_type
            )
            db.add(building)
            
            # この建物に移動された物件を元に戻す
            property_ids = merged_building.get("property_ids", [])
            if property_ids:
                # 統合時に記録した特定の物件IDリストを使用して元の建物に戻す
                # ただし、物件統合で削除された物件は除く
                existing_properties = db.query(MasterProperty).filter(
                    MasterProperty.id.in_(property_ids),
                    MasterProperty.building_id == history.primary_building_id
                ).all()
                
                for prop in existing_properties:
                    prop.building_id = building_id
                    print(f"[INFO] Moved property {prop.id} back to building {building_id}")
                
                # 物件統合で削除された物件を確認
                deleted_property_ids = set(property_ids) - set([p.id for p in existing_properties])
                if deleted_property_ids:
                    # 削除された物件がある場合、物件統合履歴を確認
                    merge_histories = db.query(PropertyMergeHistory).filter(
                        PropertyMergeHistory.merged_property_id.in_(deleted_property_ids)
                    ).all()
                    
                    if merge_histories:
                        print(f"[WARNING] {len(deleted_property_ids)} properties were merged and cannot be automatically restored:")
                        for mh in merge_histories:
                            print(f"  - Property {mh.merged_property_id} was merged into {mh.primary_property_id}")
                        print("[INFO] Please manually revert property merges if needed.")
            elif merged_building.get("properties_moved", 0) > 0:
                # 古い形式の履歴（property_idsがない場合）のフォールバック
                # この場合は正確な復元ができないため警告を出す
                print(f"[WARNING] No property_ids found in merge history. Cannot accurately restore properties.")
                print(f"[WARNING] {merged_building.get('properties_moved', 0)} properties may need manual intervention.")
            
            # BuildingAliasテーブルが存在する場合のみエイリアス処理
            # （現在は使用していないが、将来の互換性のため）
            try:
                from ..models import BuildingAlias
                db.query(BuildingAlias).filter(
                    BuildingAlias.building_id == history.primary_building_id,
                    BuildingAlias.alias_name == merged_building["normalized_name"],
                    BuildingAlias.source == 'MERGE'
                ).delete()
            except Exception:
                # BuildingAliasが存在しない場合は無視
                pass
            
            restored_count += 1
        
        # 統合時に作成された可能性のある除外ペアを削除
        # 主建物と統合された建物間の除外ペアを削除
        merged_building_ids = [b["id"] for b in history.merge_details.get("merged_buildings", [])]
        for building_id in merged_building_ids:
            # 両方向の除外ペアを削除
            db.query(BuildingMergeExclusion).filter(
                or_(
                    and_(
                        BuildingMergeExclusion.building1_id == history.primary_building_id,
                        BuildingMergeExclusion.building2_id == building_id
                    ),
                    and_(
                        BuildingMergeExclusion.building1_id == building_id,
                        BuildingMergeExclusion.building2_id == history.primary_building_id
                    )
                )
            ).delete()
        
        # 多数決による建物名更新（エイリアスが変更されたため）
        from ..utils.majority_vote_updater import MajorityVoteUpdater
        updater = MajorityVoteUpdater(db)
        
        # 主建物の名前を更新（統合時に追加されたエイリアスが削除されたため）
        if primary_building:
            updater.update_building_name_by_majority(primary_building.id)
        
        # 復元された建物の名前も更新
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            # 復元された建物が存在する場合
            restored_building = db.query(Building).filter(Building.id == building_id).first()
            if restored_building:
                updater.update_building_name_by_majority(building_id)
        
        # この統合に依存する履歴を再計算（削除前に実行）
        # final_primary_building_idがこの統合の主建物を指している履歴を検索
        dependent_histories = db.query(BuildingMergeHistory).filter(
            BuildingMergeHistory.final_primary_building_id == history.final_primary_building_id,
            BuildingMergeHistory.merged_building_id != history.merged_building_id  # 自分自身は除外
        ).all()
        
        for dep_history in dependent_histories:
            # この統合の取り消しにより、依存する履歴の最終統合先を再計算
            if dep_history.direct_primary_building_id == history.merged_building_id:
                # この履歴の直接統合先が、取り消される建物の場合
                # 元の建物に戻す必要がある
                dep_history.final_primary_building_id = dep_history.merged_building_id
                dep_history.primary_building_id = dep_history.merged_building_id  # 互換性のため
                dep_history.merge_depth = 0
            else:
                # 新しい最終統合先を計算
                new_final_primary = calculate_final_primary_building_after_revert(
                    db, 
                    dep_history.merged_building_id,
                    history.merged_building_id  # 削除される統合を除外
                )
                dep_history.final_primary_building_id = new_final_primary
                dep_history.primary_building_id = new_final_primary  # 互換性のため
                dep_history.merge_depth = max(0, dep_history.merge_depth - 1)  # 深さを減らす
        
        # 履歴レコードを削除
        db.delete(history)
        
        db.commit()
        
        # キャッシュをクリア（建物復元により建物リストが変更されたため）
        global _duplicate_buildings_cache, _duplicate_buildings_cache_time
        _duplicate_buildings_cache = {}
        _duplicate_buildings_cache_time = 0
        logger.info("[DEBUG] Cleared duplicate buildings cache after merge revert")
        
        print(f"[INFO] Merge revert completed: restored {restored_count} buildings")
        
        # 警告メッセージを生成
        warning_message = ""
        for merged_building in history.merge_details.get("merged_buildings", []):
            property_ids = merged_building.get("property_ids", [])
            if property_ids:
                existing_count = db.query(MasterProperty).filter(
                    MasterProperty.id.in_(property_ids)
                ).count()
                if existing_count < len(property_ids):
                    warning_message += f"\n※ 建物{merged_building['id']}の一部物件が物件統合で削除されているため復元できませんでした。"
        
        message = f"統合を取り消しました。{restored_count}件の建物を復元しました。{warning_message}"
        
        return {
            "success": True, 
            "message": message,
            "restored_count": restored_count
        }
        
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERROR] Merge revert failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"取り消し中にエラーが発生しました: {str(e)}")


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
    
    try:
        # 主物件の存在確認（ハイブリッド方式ではfinal_primary_property_idを使用）
        primary_property_id = history.final_primary_property_id or history.primary_property_id
        primary_property = db.query(MasterProperty).filter(
            MasterProperty.id == primary_property_id
        ).first()
        
        if not primary_property:
            raise HTTPException(status_code=404, detail="主物件が見つかりません")
        
        # 副物件を復元
        secondary_data = history.merge_details.get("secondary_property", {})
        secondary_property_id = secondary_data["id"]  # 復元する副物件のID
        
        secondary_property = MasterProperty(
            id=secondary_property_id,
            building_id=secondary_data["building_id"],
            room_number=secondary_data.get("room_number"),
            floor_number=secondary_data.get("floor_number"),
            area=secondary_data.get("area"),
            balcony_area=secondary_data.get("balcony_area"),
            layout=secondary_data.get("layout"),
            direction=secondary_data.get("direction"),
            property_hash=secondary_data.get("property_hash"),
            management_fee=secondary_data.get("management_fee"),
            repair_fund=secondary_data.get("repair_fund"),
            station_info=secondary_data.get("station_info"),
            parking_info=secondary_data.get("parking_info"),
            display_building_name=secondary_data.get("display_building_name")
        )
        db.add(secondary_property)
        
        # 移動された掲載情報を元に戻す
        moved_listings = history.merge_details.get("moved_listings", [])
        restored_count = 0
        
        for listing_info in moved_listings:
            listing = db.query(PropertyListing).filter(
                PropertyListing.id == listing_info["listing_id"]
            ).first()
            
            # ハイブリッド方式: final_primary_property_idを考慮
            if listing and listing.master_property_id == primary_property_id:
                # 掲載情報を復元した副物件に戻す
                listing.master_property_id = secondary_property_id
                restored_count += 1
        
        # 主物件の更新を元に戻す（必要に応じて）
        primary_updates = history.merge_details.get("primary_updates", {})
        if primary_updates:
            # 更新された項目を確認し、副物件の値で上書きされていた場合は元に戻す
            # ただし、その後別の更新があった可能性もあるため、慎重に処理
            pass
        
        # ハイブリッド方式：この統合に依存する履歴を再計算（削除前に実行）
        # final_primary_property_idがこの統合の主物件を指している履歴を検索
        dependent_histories = db.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.final_primary_property_id == history.final_primary_property_id,
            PropertyMergeHistory.merged_property_id != history.merged_property_id  # 自分自身は除外
        ).all()
        
        for dep_history in dependent_histories:
            # 最終統合先を再計算
            new_final_id = calculate_final_primary_property(
                db, 
                dep_history.merged_property_id,
                excluded_property_id=history.merged_property_id
            )
            dep_history.final_primary_property_id = new_final_id
            # 深さも再計算
            depth = 0
            current_id = dep_history.merged_property_id
            visited = set()
            while current_id != new_final_id and current_id not in visited:
                visited.add(current_id)
                merge = db.query(PropertyMergeHistory).filter(
                    PropertyMergeHistory.merged_property_id == current_id,
                    PropertyMergeHistory.merged_property_id != history.merged_property_id
                ).first()
                if merge:
                    current_id = merge.direct_primary_property_id
                    depth += 1
                else:
                    break
            dep_history.merge_depth = depth
        
        # 履歴を削除（取り消し時に履歴を削除する仕様）
        db.delete(history)
        
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


class ExcludeBuildingsRequest(BaseModel):
    """建物除外リクエスト"""
    building1_id: int
    building2_id: int
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
    from backend.app.utils.datetime_utils import to_jst_string
    
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
        
        # 物件1の価格を取得
        prop1_price = None
        if prop1:
            active_listing1 = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop1.id,
                PropertyListing.is_active == True
            ).first()
            if active_listing1:
                prop1_price = active_listing1.current_price
        
        # 物件2の価格を取得
        prop2_price = None
        if prop2:
            active_listing2 = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop2.id,
                PropertyListing.is_active == True
            ).first()
            if active_listing2:
                prop2_price = active_listing2.current_price
        
        if prop1 and prop1.building:
            info_parts = [prop1.building.normalized_name]
            if prop1.room_number:
                info_parts.append(prop1.room_number)
            if prop1.floor_number:
                info_parts.append(f"{prop1.floor_number}階")
            if prop1.area:
                info_parts.append(f"{prop1.area}㎡")
            if prop1.direction:
                info_parts.append(prop1.direction)
            if prop1_price:
                info_parts.append(f"{prop1_price:,}万円")
            prop1_info = " / ".join(info_parts)
        else:
            prop1_info = f"物件ID: {exclusion.property1_id}"
            
        if prop2 and prop2.building:
            info_parts = [prop2.building.normalized_name]
            if prop2.room_number:
                info_parts.append(prop2.room_number)
            if prop2.floor_number:
                info_parts.append(f"{prop2.floor_number}階")
            if prop2.area:
                info_parts.append(f"{prop2.area}㎡")
            if prop2.direction:
                info_parts.append(prop2.direction)
            if prop2_price:
                info_parts.append(f"{prop2_price:,}万円")
            prop2_info = " / ".join(info_parts)
        else:
            prop2_info = f"物件ID: {exclusion.property2_id}"
        
        result.append({
            "id": exclusion.id,
            "property1": {
                "id": exclusion.property1_id,
                "info": prop1_info,
                "building_name": prop1.building.normalized_name if prop1 and prop1.building else None,
                "room_number": prop1.room_number if prop1 else None,
                "floor_number": prop1.floor_number if prop1 else None,
                "area": prop1.area if prop1 else None,
                "direction": prop1.direction if prop1 else None,
                "price": prop1_price
            },
            "property2": {
                "id": exclusion.property2_id,
                "info": prop2_info,
                "building_name": prop2.building.normalized_name if prop2 and prop2.building else None,
                "room_number": prop2.room_number if prop2 else None,
                "floor_number": prop2.floor_number if prop2 else None,
                "area": prop2.area if prop2 else None,
                "direction": prop2.direction if prop2 else None,
                "price": prop2_price
            },
            "reason": exclusion.reason,
            "excluded_by": exclusion.excluded_by,
            "created_at": to_jst_string(exclusion.created_at)
        })
    
    return {"exclusions": result, "total": len(result)}


class ExcludeBuildingsRequest(BaseModel):
    building1_id: int
    building2_id: int
    reason: Optional[str] = None


@router.post("/exclude-buildings")
def exclude_buildings(
    request: ExcludeBuildingsRequest,
    db: Session = Depends(get_db)
):
    """建物ペアを統合候補から除外"""
    building1_id = request.building1_id
    building2_id = request.building2_id
    reason = request.reason
    
    # 既に除外されているかチェック
    existing = db.query(BuildingMergeExclusion).filter(
        or_(
            and_(
                BuildingMergeExclusion.building1_id == building1_id,
                BuildingMergeExclusion.building2_id == building2_id
            ),
            and_(
                BuildingMergeExclusion.building1_id == building2_id,
                BuildingMergeExclusion.building2_id == building1_id
            )
        )
    ).first()
    
    if existing:
        return {"success": False, "message": "既に除外済みです"}
    
    # 小さいIDを building1_id として保存（一貫性のため）
    if building1_id > building2_id:
        building1_id, building2_id = building2_id, building1_id
    
    exclusion = BuildingMergeExclusion(
        building1_id=building1_id,
        building2_id=building2_id,
        reason=reason,
        excluded_by="admin"  # TODO: 実際のユーザー名を設定
    )
    db.add(exclusion)
    db.commit()
    
    # キャッシュをクリア（除外リストが変更されたため）
    global _duplicate_buildings_cache, _duplicate_buildings_cache_time
    _duplicate_buildings_cache = {}
    _duplicate_buildings_cache_time = 0
    logger.info("[DEBUG] Cleared duplicate buildings cache after building exclusion")
    
    return {"success": True, "exclusion_id": exclusion.id}


@router.delete("/exclude-buildings/{exclusion_id}")
def remove_building_exclusion(
    exclusion_id: int,
    db: Session = Depends(get_db)
):
    """建物除外を取り消す"""
    exclusion = db.query(BuildingMergeExclusion).filter(
        BuildingMergeExclusion.id == exclusion_id
    ).first()
    
    if not exclusion:
        raise HTTPException(status_code=404, detail="除外記録が見つかりません")
    
    db.delete(exclusion)
    db.commit()
    
    # キャッシュをクリア（除外リストが変更されたため）
    global _duplicate_buildings_cache, _duplicate_buildings_cache_time
    _duplicate_buildings_cache = {}
    _duplicate_buildings_cache_time = 0
    logger.info("[DEBUG] Cleared duplicate buildings cache after removing building exclusion")
    
    return {"success": True}


@router.get("/building-exclusions")
def get_building_exclusions(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """建物除外リストを取得"""
    from backend.app.utils.datetime_utils import to_jst_string
    
    exclusions = db.query(BuildingMergeExclusion).order_by(
        BuildingMergeExclusion.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for exclusion in exclusions:
        # 建物情報を取得
        building1 = db.query(Building).filter(
            Building.id == exclusion.building1_id
        ).first()
        building2 = db.query(Building).filter(
            Building.id == exclusion.building2_id
        ).first()
        
        # 物件数を取得
        count1 = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.building_id == exclusion.building1_id
        ).scalar() or 0
        count2 = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.building_id == exclusion.building2_id
        ).scalar() or 0
        
        result.append({
            "id": exclusion.id,
            "building1": {
                "id": exclusion.building1_id,
                "normalized_name": building1.normalized_name if building1 else "削除済み",
                "address": building1.address if building1 else "-",
                "property_count": count1
            },
            "building2": {
                "id": exclusion.building2_id,
                "normalized_name": building2.normalized_name if building2 else "削除済み",
                "address": building2.address if building2 else "-",
                "property_count": count2
            },
            "reason": exclusion.reason,
            "excluded_by": exclusion.excluded_by,
            "created_at": to_jst_string(exclusion.created_at)
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


@router.get("/scraper-alerts")
def get_scraper_alerts(
    db: Session = Depends(get_db),
    include_resolved: bool = False
):
    """スクレイパーのアラートを取得"""
    try:
        from ..models import ScraperAlert
        
        # アラートを取得
        query = db.query(ScraperAlert)
        
        if not include_resolved:
            query = query.filter(ScraperAlert.is_active == True)
        
        alerts_objs = query.order_by(ScraperAlert.created_at.desc()).limit(100 if include_resolved else 50).all()
        
        alerts = []
        for alert in alerts_objs:
            alert_dict = {
                "id": alert.id,
                "source_site": alert.source_site,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "details": alert.details,
                "is_active": alert.is_active,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "updated_at": alert.updated_at.isoformat() if alert.updated_at else None
            }
            alerts.append(alert_dict)
        
        return {"alerts": alerts}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アラート取得エラー: {str(e)}")


@router.put("/scraper-alerts/{alert_id}/resolve")
def resolve_scraper_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """スクレイパーアラートを解決済みにする"""
    try:
        from ..models import ScraperAlert
        
        alert = db.query(ScraperAlert).filter(ScraperAlert.id == alert_id).first()
        
        if not alert:
            raise HTTPException(status_code=404, detail="アラートが見つかりません")
        
        alert.is_active = False
        alert.resolved_at = datetime.now()
        db.commit()
        
        return {"message": "アラートを解決済みにしました", "alert_id": alert_id}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"アラート更新エラー: {str(e)}")

