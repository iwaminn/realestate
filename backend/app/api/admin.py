"""
管理画面用APIエンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import asyncio
import threading
import uuid
import time
from concurrent.futures import ThreadPoolExecutor

from ..database import get_db
from ..models import MasterProperty, PropertyListing, Building, ListingPriceHistory, PropertyMergeHistory, PropertyMergeExclusion

router = APIRouter(prefix="/api/admin", tags=["admin"])

# スクレイピングタスクの状態を管理
scraping_tasks: Dict[str, Dict[str, Any]] = {}
executor = ThreadPoolExecutor(max_workers=3)

# タスクの制御フラグを管理
task_cancel_flags: Dict[str, threading.Event] = {}
task_pause_flags: Dict[str, threading.Event] = {}


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
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Successfully merged property {merge_request.secondary_property_id} into {merge_request.primary_property_id}",
            "merged_listings": merged_count,
            "history_id": merge_history.id
        }
        
    except Exception as e:
        db.rollback()
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
    scrapers: List[str]  # ["suumo", "athome", "homes"]
    area_codes: List[str] = ["13103"]  # デフォルト: 港区
    max_properties: int = 100  # 各スクレイパー・各エリアで取得する最大件数


class ScrapingTaskStatus(BaseModel):
    """スクレイピングタスクの状態"""
    task_id: str
    status: str  # "pending", "running", "paused", "completed", "failed", "cancelled"
    scrapers: List[str]
    area_codes: List[str]
    max_properties: int
    started_at: datetime
    completed_at: Optional[datetime]
    progress: Dict[str, Dict[str, Any]]  # 各スクレイパー・エリアの進行状況
    errors: List[str]
    logs: Optional[List[Dict[str, Any]]] = []  # 詳細ログ


def run_scraping_task(task_id: str, scrapers: List[str], area_codes: List[str], max_properties: int):
    """バックグラウンドでスクレイピングを実行"""
    import subprocess
    import json
    
    # タスク状態を更新
    scraping_tasks[task_id]["status"] = "running"
    
    # ローカルでスクレイピングを実行（APIサーバーと同じ環境）
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        from app.scrapers.suumo_scraper import SuumoScraper
        from app.scrapers.homes_scraper import HomesScraper
        from app.scrapers.athome_scraper import AtHomeScraper
        
        scraper_classes = {
            "suumo": SuumoScraper,
            "homes": HomesScraper,
            "athome": AtHomeScraper
        }
        
        # エリア名のマッピング（逆引き用）
        area_names = {code: name for name, code in AREA_CODES.items()}
        
        total_combinations = len(scrapers) * len(area_codes)
        completed_combinations = 0
        
        for scraper_name in scrapers:
            if scraper_name not in scraper_classes:
                error_msg = f"Unknown scraper: {scraper_name}"
                scraping_tasks[task_id]["errors"].append(error_msg)
                continue
                
            for area_code in area_codes:
                # キャンセルチェック
                cancel_flag = task_cancel_flags.get(task_id)
                if cancel_flag and cancel_flag.is_set():
                    scraping_tasks[task_id]["status"] = "cancelled"
                    scraping_tasks[task_id]["completed_at"] = datetime.now()
                    print(f"[{task_id}] Task cancelled by user")
                    return
                
                # 一時停止チェック
                pause_flag = task_pause_flags.get(task_id)
                while pause_flag and pause_flag.is_set():
                    if scraping_tasks[task_id]["status"] != "paused":
                        scraping_tasks[task_id]["status"] = "paused"
                        print(f"[{task_id}] Task paused by user")
                    time.sleep(1)
                    # 一時停止中でもキャンセルをチェック
                    if cancel_flag and cancel_flag.is_set():
                        scraping_tasks[task_id]["status"] = "cancelled"
                        scraping_tasks[task_id]["completed_at"] = datetime.now()
                        print(f"[{task_id}] Task cancelled while paused")
                        return
                
                # 一時停止から再開した場合
                if scraping_tasks[task_id]["status"] == "paused":
                    scraping_tasks[task_id]["status"] = "running"
                    print(f"[{task_id}] Task resumed")
                
                # 進行状況のキーを作成（スクレイパー名_エリアコード）
                progress_key = f"{scraper_name}_{area_code}"
                area_name = area_names.get(area_code, area_code)
                
                try:
                    # スクレイパーの進行状況を初期化
                    scraping_tasks[task_id]["progress"][progress_key] = {
                        "scraper": scraper_name,
                        "area_code": area_code,
                        "area_name": area_name,
                        "status": "running",
                        "properties_scraped": 0,
                        "new_listings": 0,
                        "updated_listings": 0,
                        "started_at": datetime.now().isoformat(),
                        "completed_at": None,
                        "error": None
                    }
                    
                    # スクレイピング実行
                    scraper_class = scraper_classes[scraper_name]
                    print(f"[{task_id}] Starting {scraper_name} scraper for {area_name} ({area_code})")
                    
                    # プログレスを更新する関数を定義
                    def update_progress(count, new_count=0, updated_count=0):
                        scraping_tasks[task_id]["progress"][progress_key]["properties_scraped"] = count
                        scraping_tasks[task_id]["progress"][progress_key]["new_listings"] = new_count
                        scraping_tasks[task_id]["progress"][progress_key]["updated_listings"] = updated_count
                        if count % 10 == 0:
                            print(f"[{task_id}] Progress: {progress_key} - {count}/{max_properties} properties (new: {new_count}, updated: {updated_count})")
                    
                    # カウンターを初期化
                    listing_stats = {
                        "new": 0,
                        "updated": 0,
                        "total": 0
                    }
                    
                    # スクレイパーインスタンスを作成
                    with scraper_class(max_properties=max_properties) as scraper:
                        # ページ取得メソッドをオーバーライド（一時停止チェックを追加）
                        original_fetch_page = scraper.fetch_page
                        
                        def fetch_page_with_pause_check(url):
                            # 一時停止チェック
                            pause_flag = task_pause_flags.get(task_id)
                            while pause_flag and pause_flag.is_set():
                                if scraping_tasks[task_id]["status"] != "paused":
                                    scraping_tasks[task_id]["status"] = "paused"
                                    print(f"[{task_id}] Task paused")
                                time.sleep(0.5)
                                # 一時停止中でもキャンセルをチェック
                                cancel_flag = task_cancel_flags.get(task_id)
                                if cancel_flag and cancel_flag.is_set():
                                    scraping_tasks[task_id]["status"] = "cancelled"
                                    scraping_tasks[task_id]["completed_at"] = datetime.now()
                                    print(f"[{task_id}] Task cancelled while paused")
                                    raise Exception("Task cancelled")
                            
                            # 一時停止から再開した場合
                            if scraping_tasks[task_id]["status"] == "paused":
                                scraping_tasks[task_id]["status"] = "running"
                                print(f"[{task_id}] Task resumed")
                            
                            # キャンセルチェック
                            cancel_flag = task_cancel_flags.get(task_id)
                            if cancel_flag and cancel_flag.is_set():
                                scraping_tasks[task_id]["status"] = "cancelled"
                                scraping_tasks[task_id]["completed_at"] = datetime.now()
                                print(f"[{task_id}] Task cancelled")
                                raise Exception("Task cancelled")
                            
                            return original_fetch_page(url)
                        
                        scraper.fetch_page = fetch_page_with_pause_check
                        
                        # create_or_update_listingメソッドをオーバーライド
                        original_create_or_update = scraper.create_or_update_listing
                        
                        def create_or_update_with_stats(*args, **kwargs):
                            # 簡易的な一時停止・キャンセルチェック
                            pause_flag = task_pause_flags.get(task_id)
                            if pause_flag and pause_flag.is_set():
                                # 一時停止フラグがセットされている場合は例外を投げる
                                # （詳細なチェックはfetch_pageで行う）
                                raise Exception("Task paused")
                            
                            cancel_flag = task_cancel_flags.get(task_id)
                            if cancel_flag and cancel_flag.is_set():
                                raise Exception("Task cancelled")
                            
                            # URLから既存の掲載を確認
                            url = args[1] if len(args) > 1 else kwargs.get('url')
                            existing = scraper.session.query(PropertyListing).filter_by(url=url).first()
                            
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
                            
                            # 統計を更新
                            if not existing:
                                listing_stats["new"] += 1
                                log_entry["message"] = f"新規物件登録: {title} ({price}万円)"
                            else:
                                listing_stats["updated"] += 1
                                if existing.current_price != price:
                                    log_entry["message"] = f"価格更新: {title} ({existing.current_price}万円 → {price}万円)"
                                    log_entry["price_change"] = {"old": existing.current_price, "new": price}
                                else:
                                    log_entry["message"] = f"情報更新: {title} ({price}万円)"
                            
                            listing_stats["total"] += 1
                            
                            # ログを追加（最新50件のみ保持）
                            if "logs" not in scraping_tasks[task_id]:
                                scraping_tasks[task_id]["logs"] = []
                            scraping_tasks[task_id]["logs"].append(log_entry)
                            if len(scraping_tasks[task_id]["logs"]) > 50:
                                scraping_tasks[task_id]["logs"] = scraping_tasks[task_id]["logs"][-50:]
                            
                            # プログレスを更新
                            update_progress(listing_stats["total"], listing_stats["new"], listing_stats["updated"])
                            
                            return result
                        
                        scraper.create_or_update_listing = create_or_update_with_stats
                        
                        
                        # スクレイピング実行（max_pagesを計算）
                        # SUUMOは100件/ページ、他は概ね25件/ページ
                        items_per_page = 100 if scraper_name == 'suumo' else 25
                        max_pages = (max_properties + items_per_page - 1) // items_per_page
                        
                        print(f"[{task_id}] Scraping up to {max_pages} pages for {max_properties} properties")
                        scraper.scrape_area(area_code, max_pages=max_pages)
                    
                    # 完了（実際の取得件数を反映）
                    final_count = scraping_tasks[task_id]["progress"][progress_key]["properties_scraped"]
                    scraping_tasks[task_id]["progress"][progress_key].update({
                        "status": "completed",
                        "completed_at": datetime.now().isoformat()
                    })
                    
                    completed_combinations += 1
                    print(f"[{task_id}] Completed {scraper_name} scraper for {area_name} ({completed_combinations}/{total_combinations})")
                    
                except Exception as e:
                    # キャンセルされた場合は特別な処理
                    if "Task cancelled" in str(e):
                        print(f"[{task_id}] Scraping cancelled for {scraper_name} in {area_name}")
                        scraping_tasks[task_id]["progress"][progress_key].update({
                            "status": "cancelled",
                            "completed_at": datetime.now().isoformat()
                        })
                        # キャンセルされたらループを抜ける
                        return
                    elif "Task paused" in str(e):
                        # 一時停止の場合は、fetch_pageで詳細な処理が行われているので、ここでは何もしない
                        # 例外を再度発生させて上位で処理
                        raise
                    else:
                        error_msg = f"Error in {scraper_name} for {area_name}: {str(e)}"
                        print(f"[{task_id}] {error_msg}")
                        scraping_tasks[task_id]["errors"].append(error_msg)
                        scraping_tasks[task_id]["progress"][progress_key].update({
                            "status": "failed",
                            "error": str(e),
                            "completed_at": datetime.now().isoformat()
                        })
                    completed_combinations += 1
        
        # タスク完了
        if scraping_tasks[task_id]["status"] != "cancelled":
            scraping_tasks[task_id]["status"] = "completed"
            scraping_tasks[task_id]["completed_at"] = datetime.now()
            
    except Exception as e:
        scraping_tasks[task_id]["status"] = "failed"
        scraping_tasks[task_id]["completed_at"] = datetime.now()
        scraping_tasks[task_id]["errors"].append(f"Failed to import scrapers: {str(e)}")
        print(f"[{task_id}] Import Error: {e}")
        return
    
    # 制御フラグをクリーンアップ
    if task_id in task_cancel_flags:
        del task_cancel_flags[task_id]
    if task_id in task_pause_flags:
        del task_pause_flags[task_id]


@router.post("/scraping/start", response_model=ScrapingTaskStatus)
def start_scraping(
    request: ScrapingRequest,
    background_tasks: BackgroundTasks
):
    """スクレイピングを開始"""
    # タスクIDを生成
    task_id = str(uuid.uuid4())
    
    # タスク情報を初期化
    scraping_tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "scrapers": request.scrapers,
        "area_codes": request.area_codes,
        "max_properties": request.max_properties,
        "started_at": datetime.now(),
        "completed_at": None,
        "progress": {},
        "errors": [],
        "logs": []  # 詳細ログを初期化
    }
    
    # 制御フラグを作成
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


@router.get("/scraping/tasks", response_model=List[ScrapingTaskStatus])
def get_all_scraping_tasks():
    """全てのスクレイピングタスクを取得"""
    # 最新10件のみ返す
    sorted_tasks = sorted(
        scraping_tasks.values(),
        key=lambda x: x["started_at"],
        reverse=True
    )[:10]
    
    return [ScrapingTaskStatus(**task) for task in sorted_tasks]


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
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] != "running":
        raise HTTPException(
            status_code=400, 
            detail=f"Task is {scraping_tasks[task_id]['status']}, cannot pause"
        )
    
    # 一時停止フラグをセット
    if task_id in task_pause_flags:
        task_pause_flags[task_id].set()
        return {"success": True, "message": "Pause request sent"}
    else:
        return {"success": False, "message": "Task pause flag not found"}


@router.post("/scraping/resume/{task_id}")
def resume_scraping(task_id: str):
    """スクレイピングタスクを再開"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] != "paused":
        raise HTTPException(
            status_code=400, 
            detail=f"Task is {scraping_tasks[task_id]['status']}, cannot resume"
        )
    
    # 一時停止フラグをクリア
    if task_id in task_pause_flags:
        task_pause_flags[task_id].clear()
        return {"success": True, "message": "Resume request sent"}
    else:
        return {"success": False, "message": "Task pause flag not found"}


@router.post("/scraping/cancel/{task_id}")
def cancel_scraping(task_id: str):
    """スクレイピングタスクをキャンセル"""
    if task_id not in scraping_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if scraping_tasks[task_id]["status"] not in ["pending", "running", "paused"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Task is already {scraping_tasks[task_id]['status']}"
        )
    
    # キャンセルフラグをセット
    if task_id in task_cancel_flags:
        task_cancel_flags[task_id].set()
        return {"success": True, "message": "Cancel request sent"}
    else:
        return {"success": False, "message": "Task cancel flag not found"}


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