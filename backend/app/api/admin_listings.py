"""
管理者用掲載情報管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict
from datetime import datetime

from ..database import get_db
from ..models import PropertyListing, MasterProperty
from ..auth import verify_admin_credentials

router = APIRouter(tags=["admin-listings"])


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """掲載情報を削除（管理者用）"""
    # 対象の掲載情報を取得
    listing = db.query(PropertyListing).filter(
        PropertyListing.id == listing_id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="掲載情報が見つかりません")
    
    # 掲載情報を削除
    db.delete(listing)
    
    try:
        db.commit()
        return {
            "success": True,
            "message": f"{listing.source_site}の掲載情報を削除しました"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"削除に失敗しました: {str(e)}")


@router.post("/listings/{listing_id}/detach-candidates")
async def get_detach_candidates(
    listing_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """掲載情報分離時の候補物件を取得（管理者用）"""
    import logging
    logger = logging.getLogger(__name__)
    
    # 対象の掲載情報を取得
    listing = db.query(PropertyListing).filter(
        PropertyListing.id == listing_id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="掲載情報が見つかりません")
    
    # 現在の物件情報を取得
    current_property = db.query(MasterProperty).filter(
        MasterProperty.id == listing.master_property_id
    ).first()
    
    if not current_property:
        raise HTTPException(status_code=404, detail="物件情報が見つかりません")
    
    # 掲載情報の詳細から候補物件を検索
    listing_floor = listing.listing_floor_number or current_property.floor_number
    listing_area = listing.listing_area or current_property.area
    listing_layout = listing.listing_layout or current_property.layout
    listing_direction = listing.listing_direction or current_property.direction
    listing_room = listing.listing_room_number or current_property.room_number
    
    # 同じ建物内の候補物件を検索
    candidates = []
    
    # 同じ建物内の物件を検索（現在の物件を除外）
    query = db.query(MasterProperty).filter(
        MasterProperty.building_id == current_property.building_id,
        MasterProperty.id != current_property.id
    )
    
    # 条件に合う物件を検索
    for prop in query.all():
        score = 0
        match_details = []
        
        # 階数の比較
        if prop.floor_number == listing_floor:
            score += 5
            match_details.append("階数一致")
        
        # 面積の比較（±0.5㎡の許容誤差）
        if prop.area and listing_area:
            if abs(prop.area - listing_area) <= 0.5:
                score += 5
                match_details.append("面積一致")
        
        # 間取りの比較
        if prop.layout == listing_layout:
            score += 3
            match_details.append("間取り一致")
        
        # 方角の比較
        if prop.direction == listing_direction:
            score += 3
            match_details.append("方角一致")
        
        # 部屋番号の比較
        if prop.room_number == listing_room:
            score += 2
            match_details.append("部屋番号一致")
        
        if score > 0:
            candidates.append({
                'id': prop.id,
                'room_number': prop.room_number,
                'floor_number': prop.floor_number,
                'area': prop.area,
                'layout': prop.layout,
                'direction': prop.direction,
                'display_building_name': prop.display_building_name,
                'score': score,
                'match_details': match_details
            })
    
    # スコア順にソート
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    # 新規物件作成用のデフォルト値
    new_property_defaults = {
        'room_number': listing_room,
        'floor_number': listing_floor,
        'area': listing_area,
        'layout': listing_layout,
        'direction': listing_direction,
        'display_building_name': listing.listing_building_name
    }
    
    return {
        'current_property': {
            'id': current_property.id,
            'room_number': current_property.room_number,
            'floor_number': current_property.floor_number,
            'area': current_property.area,
            'layout': current_property.layout,
            'direction': current_property.direction
        },
        'listing_info': {
            'id': listing.id,
            'source_site': listing.source_site,
            'url': listing.url,
            'current_price': listing.current_price,
            'building_name': listing.listing_building_name,
            'room_number': listing_room,
            'floor_number': listing_floor,
            'area': listing_area,
            'layout': listing_layout,
            'direction': listing_direction
        },
        'candidates': candidates[:10],  # 上位10件まで
        'new_property_defaults': new_property_defaults,
        'can_create_new': True
    }


@router.post("/listings/{listing_id}/attach-to-property")
async def attach_listing_to_property(
    listing_id: int,
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """掲載情報を指定された物件に紐付け（管理者用）"""
    import logging
    logger = logging.getLogger(__name__)
    
    # リクエストパラメータを取得
    target_property_id = request.get('property_id')
    create_new = request.get('create_new', False)
    
    # 対象の掲載情報を取得
    listing = db.query(PropertyListing).filter(
        PropertyListing.id == listing_id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="掲載情報が見つかりません")
    
    # 現在の物件情報を取得
    current_property = db.query(MasterProperty).filter(
        MasterProperty.id == listing.master_property_id
    ).first()
    
    if not current_property:
        raise HTTPException(status_code=404, detail="物件情報が見つかりません")
    
    if create_new:
        # 新しい物件を作成
        new_property = MasterProperty(
            building_id=current_property.building_id,
            room_number=request.get('room_number') or listing.listing_room_number or current_property.room_number,
            floor_number=request.get('floor_number') or listing.listing_floor_number or current_property.floor_number,
            area=request.get('area') or listing.listing_area or current_property.area,
            layout=request.get('layout') or listing.listing_layout or current_property.layout,
            direction=request.get('direction') or listing.listing_direction or current_property.direction,
            property_hash=f"detached_{listing_id}_{datetime.utcnow().timestamp()}",  # ユニークなハッシュ
            display_building_name=request.get('display_building_name') or listing.listing_building_name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_property)
        db.flush()  # IDを取得
        
        # 掲載情報を新しい物件に紐付け
        listing.master_property_id = new_property.id
        listing.updated_at = datetime.utcnow()
        
        message = f"{listing.source_site}の掲載情報を新規物件として分離しました"
        new_property_id = new_property.id
    else:
        # 既存の物件に紐付け
        if not target_property_id:
            raise HTTPException(status_code=400, detail="紐付け先の物件IDが必要です")
        
        # 指定された物件が存在するか確認
        target_property = db.query(MasterProperty).filter(
            MasterProperty.id == target_property_id
        ).first()
        
        if not target_property:
            raise HTTPException(status_code=404, detail="指定された物件が見つかりません")
        
        # 同じ物件の場合はエラー
        if target_property_id == current_property.id:
            raise HTTPException(status_code=400, detail="現在と同じ物件には紐付けできません")
        
        # 掲載情報を既存の物件に紐付け
        listing.master_property_id = target_property_id
        listing.updated_at = datetime.utcnow()
        
        message = f"{listing.source_site}の掲載情報を物件ID {target_property_id} に紐付けました"
        new_property_id = target_property_id
    
    try:
        db.commit()
        return {
            "success": True,
            "message": message,
            "original_property_id": current_property.id,
            "new_property_id": new_property_id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"掲載情報紐付けエラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"紐付け処理に失敗しました: {str(e)}")