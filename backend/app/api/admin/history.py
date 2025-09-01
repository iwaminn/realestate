"""
統合履歴管理API（建物・物件の統合履歴の管理と復元）
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
import logging

from ...database import get_db
from ...models import (
    Building, MasterProperty, PropertyListing,
    BuildingMergeHistory, PropertyMergeHistory,
    BuildingMergeExclusion, BuildingListingName
)
from ...utils.majority_vote_updater import MajorityVoteUpdater
from ...utils.building_listing_name_manager import BuildingListingNameManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-history"])


class BuildingMergeHistoryResponse(BaseModel):
    """建物統合履歴レスポンス"""
    id: int
    primary_building_id: int
    primary_building_name: Optional[str]
    merged_building_id: int
    merged_building_name: str
    canonical_merged_name: Optional[str]
    merged_at: datetime
    merged_by: Optional[str]
    property_count: int


class PropertyMergeHistoryResponse(BaseModel):
    """物件統合履歴レスポンス"""
    id: int
    primary_property_id: int
    merged_property_id: int
    primary_building_name: Optional[str]
    primary_floor: Optional[int]
    primary_layout: Optional[str]
    merged_building_name: Optional[str]
    merged_floor: Optional[int]
    merged_layout: Optional[str]
    merged_at: datetime
    merged_by: Optional[str]
    merge_reason: Optional[str]


@router.get("/building-merge-history")
async def get_building_merge_history(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """建物統合履歴を取得"""
    
    # 全体の件数を取得
    total_count = db.query(BuildingMergeHistory).count()
    
    histories = db.query(BuildingMergeHistory).order_by(
        BuildingMergeHistory.merged_at.desc()
    ).offset(offset).limit(limit).all()
    
    results = []
    for history in histories:
        # 主建物の情報を取得
        primary_building = db.query(Building).filter(
            Building.id == history.primary_building_id
        ).first()
        
        # 統合された建物に関連していた物件数を取得
        property_count = db.query(MasterProperty).filter(
            MasterProperty.building_id == history.primary_building_id
        ).count()
        
        results.append({
            "id": history.id,
            "primary_building": {
                "id": history.primary_building_id,
                "normalized_name": primary_building.normalized_name if primary_building else None
            },
            "secondary_building": {
                "id": history.merged_building_id,
                "normalized_name": history.merged_building_name,
                "properties_moved": property_count
            },
            "moved_properties": property_count,
            "merge_details": {},
            "created_at": history.merged_at.isoformat() if history.merged_at else None
        })
    
    return {"histories": results, "total": total_count}


@router.get("/property-merge-history")
async def get_property_merge_history(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """物件統合履歴を取得"""
    
    # 全体の件数を取得
    total_count = db.query(PropertyMergeHistory).count()
    
    histories = db.query(PropertyMergeHistory).order_by(
        PropertyMergeHistory.merged_at.desc()
    ).offset(offset).limit(limit).all()
    
    results = []
    for history in histories:
        # 主物件の情報を取得
        primary = db.query(MasterProperty).options(
            joinedload(MasterProperty.building)
        ).filter(
            MasterProperty.id == history.primary_property_id
        ).first()
        
        # 統合先物件の詳細情報
        primary_data = None
        if primary:
            primary_data = {
                "id": primary.id,
                "building_name": primary.building.normalized_name if primary.building else None,
                "room_number": primary.room_number,
                "floor_number": primary.floor_number,
                "area": primary.area,
                "layout": primary.layout
            }
        
        # 統合された物件の情報（削除済みのため履歴から復元）
        secondary_data = {
            "id": history.merged_property_id,
            "building_name": None,
            "room_number": None,
            "floor_number": None,
            "area": None,
            "layout": None
        }
        
        # merge_detailsから統合元物件の情報を取得
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
        
        # 移動した掲載数を取得
        moved_listings = db.query(PropertyListing).filter(
            PropertyListing.master_property_id == history.primary_property_id
        ).count()
        
        results.append({
            "id": history.id,
            "primary_property": primary_data,
            "secondary_property": secondary_data,
            "moved_listings": history.moved_listings or moved_listings,
            "merge_details": history.merge_details or {},
            "merged_by": history.merged_by or "admin",
            "merged_at": history.merged_at.isoformat() if history.merged_at else None
        })
    
    return {"histories": results, "total": total_count}


@router.post("/revert-building-merge/{history_id}")
async def revert_building_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """建物統合を元に戻す"""
    
    # Phase 1: 建物を復元（独立したトランザクション）
    restored_building_id = None
    restored_building_name = None
    
    # 統合履歴を取得
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # 主建物の存在確認
    primary_building = db.query(Building).filter(
        Building.id == history.primary_building_id
    ).first()
    
    if not primary_building:
        raise HTTPException(status_code=404, detail="主建物が見つかりません")
    
    # まず建物が既に存在しないか確認
    existing_building = db.query(Building).filter(
        Building.normalized_name == history.merged_building_name
    ).first()
    
    if not existing_building:
        # 元の建物を復元
        restored_building = Building(
            normalized_name=history.merged_building_name,
            canonical_name=history.canonical_merged_name or history.merged_building_name,
            address=primary_building.address,  # 主建物と同じ住所を使用
            total_floors=primary_building.total_floors,
            built_year=primary_building.built_year,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(restored_building)
        db.flush()
        
        # 建物のIDを確実に取得するため、ここでコミット（重要：エラーハンドリングの外）
        db.commit()
        
        # 建物を再取得
        restored_building = db.query(Building).filter(
            Building.normalized_name == history.merged_building_name
        ).order_by(Building.id.desc()).first()
    else:
        restored_building = existing_building
        logger.info(f"Building already exists: ID={existing_building.id}, Name={existing_building.normalized_name}")
    
    if not restored_building:
        raise HTTPException(status_code=500, detail=f"建物の復元に失敗しました: {history.merged_building_name}")
    
    restored_building_id = restored_building.id
    restored_building_name = restored_building.normalized_name
    logger.info(f"Restored building ID: {restored_building_id}, Name: {restored_building_name}")
    
    # Phase 2: 物件の移動とその他の処理（別トランザクション）
    try:
        # 物件を分析して適切な物件を移動
        # ここでは簡単のため、統合履歴に記録された物件を移動
        # 実際の実装では、より詳細な分析が必要
        properties_to_move = []
        
        # 統合時期以降に追加された物件を特定
        properties = db.query(MasterProperty).filter(
            MasterProperty.building_id == history.primary_building_id,
            MasterProperty.created_at >= history.merged_at
        ).all()
        
        # 建物名から判断して移動
        for prop in properties:
            # 各掲載情報から建物名を確認
            listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop.id
            ).all()
            
            should_move = False
            for listing in listings:
                if listing.listing_building_name and history.merged_building_name in listing.listing_building_name:
                    should_move = True
                    break
            
            if should_move:
                properties_to_move.append(prop)
        
        # 物件を移動
        moved_count = 0
        for prop in properties_to_move:
            prop.building_id = restored_building_id
            moved_count += 1
        
        # 先にデータベースの変更をフラッシュして確定
        db.flush()
        
        # BuildingListingNameテーブルを再構築（多数決更新の前に実行）
        # 復元された建物のBuildingListingNameを更新
        try:
            # BuildingListingNameManagerを使用して適切に更新
            from ...utils.building_listing_name_manager import BuildingListingNameManager
            listing_name_manager = BuildingListingNameManager(db)
            
            # トランザクション内で安全に実行するため、個別にtry-exceptでラップ
            try:
                # 復元された建物のBuildingListingNameを再構築
                logger.info(f"Calling refresh_building_names with restored_building_id={restored_building_id}")
                listing_name_manager.refresh_building_names(restored_building_id)
            except Exception as e:
                logger.warning(f"復元された建物のBuildingListingName再構築中にエラー（継続）: {e}")
                # エラーが発生した場合は手動で削除だけ実行
                db.query(BuildingListingName).filter(
                    BuildingListingName.building_id == restored_building_id
                ).delete()
                db.flush()
            
            try:
                # 主建物のBuildingListingNameも再構築（物件が移動したため）
                listing_name_manager.refresh_building_names(history.primary_building_id)
            except Exception as e:
                logger.warning(f"主建物のBuildingListingName再構築中にエラー（継続）: {e}")
                
        except Exception as e:
            logger.error(f"BuildingListingName再構築中にエラー: {e}")
            # エラーが発生してもプロセスを続行
        
        # 多数決で両建物の情報を更新
        updater = MajorityVoteUpdater(db)
        # 主建物の全属性を更新（建物名含む）
        primary_building = db.query(Building).filter(Building.id == history.primary_building_id).first()
        if primary_building:
            updater.update_building_by_majority(primary_building)
        # 復元された建物の全属性も更新（建物名含む）
        restored_building_for_update = db.query(Building).filter(Building.id == restored_building_id).first()
        if restored_building_for_update:
            updater.update_building_by_majority(restored_building_for_update)
        
        # 統合履歴を削除
        db.delete(history)
        
        # 除外設定を追加（再統合を防ぐ）
        exclusion = BuildingMergeExclusion(
            building1_id=min(history.primary_building_id, restored_building_id),
            building2_id=max(history.primary_building_id, restored_building_id),
            reason=f"統合取り消し（履歴ID: {history_id}）",
            created_at=datetime.now(),
            created_by="admin"
        )
        db.add(exclusion)
        
        db.commit()
        
        return {
            "message": "建物統合を取り消しました",
            "restored_building_id": restored_building_id,
            "restored_building_name": restored_building_name,
            "moved_properties": moved_count
        }
    except Exception as e:
        db.rollback()
        # 建物は既に作成済みなので、エラーメッセージに含める
        error_msg = f"取り消し中にエラーが発生しました（建物ID {restored_building_id} は作成済み）: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/revert-property-merge/{history_id}")
async def revert_property_merge(
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
        
        # merge_detailsが存在しない場合は従来の復元方法を使用
        if not history.merge_details or "secondary_property" not in history.merge_details:
            # 従来の簡易復元方法
            restored_property = MasterProperty(
                building_id=primary_property.building_id,
                room_number=primary_property.room_number,
                floor_number=primary_property.floor_number,
                area=primary_property.area,
                layout=primary_property.layout,
                direction=primary_property.direction,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(restored_property)
            db.flush()
            
            # 統合時期以降の掲載を移動
            listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == primary_property_id
            ).all()
            
            moved_count = 0
            for listing in listings:
                if listing.created_at >= history.merged_at:
                    listing.master_property_id = restored_property.id
                    moved_count += 1
        else:
            # merge_detailsからの詳細な復元
            secondary_data = history.merge_details.get("secondary_property", {})
            secondary_property_id = secondary_data["id"]  # 復元する副物件のID
            
            # 既存の物件が存在しないことを確認
            existing = db.query(MasterProperty).filter(
                MasterProperty.id == secondary_property_id
            ).first()
            
            if existing:
                # 既に存在する場合はエラー
                raise HTTPException(
                    status_code=400,
                    detail=f"物件ID {secondary_property_id} は既に存在します。この統合は既に取り消されている可能性があります。"
                )
            
            # 副物件を復元（元のIDを使用）
            restored_property = MasterProperty(
                id=secondary_property_id,
                building_id=secondary_data["building_id"],
                room_number=secondary_data.get("room_number"),
                floor_number=secondary_data.get("floor_number"),
                area=secondary_data.get("area"),
                balcony_area=secondary_data.get("balcony_area"),
                layout=secondary_data.get("layout"),
                direction=secondary_data.get("direction"),
                management_fee=secondary_data.get("management_fee"),
                repair_fund=secondary_data.get("repair_fund"),
                station_info=secondary_data.get("station_info"),
                parking_info=secondary_data.get("parking_info"),
                display_building_name=secondary_data.get("display_building_name"),
                created_at=datetime.fromisoformat(secondary_data["created_at"]) if secondary_data.get("created_at") else datetime.now(),
                updated_at=datetime.now()
            )
            db.add(restored_property)
            db.flush()  # IDを確定させる
            
            # 移動された掲載情報を元に戻す
            moved_listings = history.merge_details.get("moved_listings", [])
            moved_count = 0
            
            for listing_info in moved_listings:
                listing = db.query(PropertyListing).filter(
                    PropertyListing.id == listing_info["listing_id"]
                ).first()
                if listing:
                    listing.master_property_id = secondary_property_id
                    moved_count += 1
        
        # BuildingListingNameテーブルを更新（物件分離）
        listing_name_manager = BuildingListingNameManager(db)
        # 復元された物件が異なる建物の場合のみ更新
        if restored_property.building_id != primary_property.building_id:
            listing_name_manager.update_from_property_split(
                original_property_id=primary_property_id,
                new_property_id=restored_property.id,
                new_building_id=restored_property.building_id
            )
        
        # 多数決で両物件の情報を更新
        updater = MajorityVoteUpdater(db)
        updater.update_master_property_by_majority(primary_property)
        updater.update_master_property_by_majority(restored_property)
        
        # 最初の掲載日を更新
        from ...utils.property_utils import update_earliest_listing_date
        update_earliest_listing_date(db, primary_property_id)
        update_earliest_listing_date(db, restored_property.id)
        
        # 統合履歴を削除
        db.delete(history)
        
        db.commit()
        
        return {
            "success": True,
            "message": "物件統合を取り消しました",
            "restored_property_id": restored_property.id,
            "moved_listings": moved_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"取り消し中にエラーが発生しました: {str(e)}")


@router.delete("/building-merge-history/{history_id}")
async def delete_building_merge_history(
    history_id: int,
    db: Session = Depends(get_db)
):
    """建物統合履歴を削除（履歴のみ削除、統合は維持）"""
    
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # 履歴を削除
    db.delete(history)
    db.commit()
    
    return {"success": True, "message": "統合履歴を削除しました"}


@router.delete("/property-merge-history/{history_id}")
async def delete_property_merge_history(
    history_id: int,
    db: Session = Depends(get_db)
):
    """物件統合履歴を削除（履歴のみ削除、統合は維持）"""
    
    history = db.query(PropertyMergeHistory).filter(
        PropertyMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # 履歴を削除
    db.delete(history)
    db.commit()
    
    return {"success": True, "message": "統合履歴を削除しました"}


@router.delete("/building-merge-history/bulk")
async def bulk_delete_building_merge_history(
    db: Session = Depends(get_db)
):
    """建物統合履歴を一括削除"""
    
    # すべての履歴を削除
    count = db.query(BuildingMergeHistory).count()
    db.query(BuildingMergeHistory).delete()
    db.commit()
    
    return {"success": True, "message": f"{count}件の建物統合履歴を削除しました", "deleted_count": count}


@router.delete("/property-merge-history/bulk")
async def bulk_delete_property_merge_history(
    db: Session = Depends(get_db)
):
    """物件統合履歴を一括削除"""
    
    # すべての履歴を削除
    count = db.query(PropertyMergeHistory).count()
    db.query(PropertyMergeHistory).delete()
    db.commit()
    
    return {"success": True, "message": f"{count}件の物件統合履歴を削除しました", "deleted_count": count}