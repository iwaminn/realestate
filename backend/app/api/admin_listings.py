"""
管理者用掲載情報管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, Integer
from typing import Any, Dict, Optional
from datetime import datetime
import logging

from ..database import get_db
from ..models import PropertyListing, MasterProperty, Building, ListingPriceHistory

router = APIRouter(prefix="/api/admin", tags=["admin-listings"])


@router.get("/listings")
async def get_listings(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    listing_id: Optional[int] = None,  # 掲載ID検索を追加
    source_site: Optional[str] = None,
    building_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    ward: Optional[str] = None,
    sort_by: str = Query("id", regex="^(id|source_site|building_name|floor_number|area|current_price|is_active|last_confirmed_at|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """掲載情報一覧を取得（管理者用）"""
    # ベースクエリ
    query = db.query(PropertyListing).options(
        joinedload(PropertyListing.master_property).joinedload(MasterProperty.building)
    )
    
    # フィルタリング
    if listing_id:
        # 掲載IDで直接検索
        query = query.filter(PropertyListing.id == listing_id)
    
    if source_site:
        query = query.filter(PropertyListing.source_site == source_site)
    
    # 建物名または区でフィルタする場合はJOINを追加
    if building_name or ward:
        query = query.join(MasterProperty).join(Building)
    
    if building_name:
        # 建物名で検索（スペース区切りでAND検索）
        building_terms = building_name.strip().split()
        for term in building_terms:
            if term:  # 空文字列をスキップ
                query = query.filter(
                    or_(
                        Building.normalized_name.ilike(f"%{term}%"),
                        PropertyListing.listing_building_name.ilike(f"%{term}%")
                    )
                )
    
    if is_active is not None:
        query = query.filter(PropertyListing.is_active == is_active)
    
    if ward:
        # 区で検索（スペース区切りでAND検索）
        ward_terms = ward.strip().split()
        for term in ward_terms:
            if term:  # 空文字列をスキップ
                query = query.filter(Building.address.ilike(f"%{term}%"))
    
    # ソート
    if sort_by == "current_price":
        order_column = PropertyListing.current_price
    elif sort_by == "source_site":
        order_column = PropertyListing.source_site
    elif sort_by == "building_name":
        # 建物名でソートする場合はJOINが必要
        if not (building_name or ward):
            query = query.join(MasterProperty).join(Building)
        order_column = Building.normalized_name
    elif sort_by == "floor_number":
        # 階数でソートする場合はJOINが必要
        if not (building_name or ward):
            query = query.join(MasterProperty)
        order_column = MasterProperty.floor_number
    elif sort_by == "area":
        # 面積でソートする場合はJOINが必要
        if not (building_name or ward):
            query = query.join(MasterProperty)
        order_column = MasterProperty.area
    elif sort_by == "is_active":
        order_column = PropertyListing.is_active
    elif sort_by == "last_confirmed_at":
        order_column = PropertyListing.last_confirmed_at
    elif sort_by == "created_at":
        order_column = PropertyListing.created_at
    elif sort_by == "updated_at":
        order_column = PropertyListing.updated_at
    else:
        order_column = PropertyListing.id
    
    if sort_order == "desc":
        query = query.order_by(order_column.desc())
    else:
        query = query.order_by(order_column.asc())
    
    # 総件数を取得
    total = query.count()
    
    # ページネーション
    offset = (page - 1) * per_page
    listings = query.offset(offset).limit(per_page).all()
    
    # レスポンスの構築
    listings_data = []
    for listing in listings:
        building = listing.master_property.building if listing.master_property else None
        listing_data = {
            'id': listing.id,
            'source_site': listing.source_site,
            'site_property_id': listing.site_property_id,
            'url': listing.url,
            'title': listing.title,
            'listing_building_name': listing.listing_building_name,
            'current_price': listing.current_price,
            'is_active': listing.is_active,
            'master_property_id': listing.master_property_id,
            'building_id': building.id if building else None,
            'building_name': building.normalized_name if building else None,
            'address': building.address if building else None,
            'floor_number': listing.master_property.floor_number if listing.master_property else None,
            'area': listing.master_property.area if listing.master_property else None,
            'layout': listing.master_property.layout if listing.master_property else None,
            'station_info': listing.station_info,
            'first_seen_at': listing.first_seen_at.isoformat() if listing.first_seen_at else None,
            'last_confirmed_at': listing.last_confirmed_at.isoformat() if listing.last_confirmed_at else None,
            'delisted_at': listing.delisted_at.isoformat() if listing.delisted_at else None,
            'detail_fetched_at': listing.detail_fetched_at.isoformat() if listing.detail_fetched_at else None,
            'created_at': listing.created_at.isoformat() if listing.created_at else None,
            'updated_at': listing.updated_at.isoformat() if listing.updated_at else None,
        }
        listings_data.append(listing_data)
    
    # 統計情報を集計
    stats_query = db.query(
        func.count(PropertyListing.id).label('total_listings'),
        func.count(func.distinct(PropertyListing.master_property_id)).label('unique_properties'),
        func.sum(func.cast(PropertyListing.is_active, Integer)).label('active_listings'),
        func.sum(func.cast(PropertyListing.detail_fetched_at.isnot(None), Integer)).label('with_details')
    )
    
    # フィルタも適用
    if source_site:
        stats_query = stats_query.filter(PropertyListing.source_site == source_site)
    if is_active is not None:
        stats_query = stats_query.filter(PropertyListing.is_active == is_active)
    
    stats = stats_query.first()
    
    return {
        'listings': listings_data,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'stats': {
            'total_listings': stats.total_listings or 0,
            'unique_properties': stats.unique_properties or 0,
            'active_listings': stats.active_listings or 0,
            'with_details': stats.with_details or 0,
        } if stats else None
    }


@router.get("/listings/{listing_id}")
async def get_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db)
):
    """掲載情報の詳細を取得（管理者用）"""
    listing = db.query(PropertyListing).options(
        joinedload(PropertyListing.master_property).joinedload(MasterProperty.building),
        joinedload(PropertyListing.price_history)
    ).filter(PropertyListing.id == listing_id).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="掲載情報が見つかりません")
    
    # 価格履歴を整形
    price_history = [
        {
            'id': h.id,
            'price': h.price,
            'recorded_at': h.recorded_at.isoformat() if h.recorded_at else None,
            'management_fee': h.management_fee,
            'repair_fund': h.repair_fund
        }
        for h in listing.price_history
    ]
    price_history.sort(key=lambda x: x['recorded_at'] or '')
    
    building = listing.master_property.building if listing.master_property else None
    
    return {
        'id': listing.id,
        'source_site': listing.source_site,
        'site_property_id': listing.site_property_id,
        'url': listing.url,
        'title': listing.title,
        'listing_building_name': listing.listing_building_name,
        'listing_address': listing.listing_address,
        'current_price': listing.current_price,
        'is_active': listing.is_active,
        'master_property_id': listing.master_property_id,
        'building_id': building.id if building else None,
        'building_name': building.normalized_name if building else None,
        'address': building.address if building else None,
        'master_property': {
            'id': listing.master_property.id,
            'room_number': listing.master_property.room_number,
            'floor_number': listing.master_property.floor_number,
            'area': listing.master_property.area,
            'balcony_area': listing.master_property.balcony_area,
            'layout': listing.master_property.layout,
            'direction': listing.master_property.direction,
            'display_building_name': listing.master_property.display_building_name,
        } if listing.master_property else None,
        'building': {
            'id': building.id,
            'normalized_name': building.normalized_name,
            'address': building.address,
            'total_floors': building.total_floors,
            'total_units': building.total_units,
            'built_year': building.built_year,
        } if building else None,
        'listing_floor_number': listing.listing_floor_number,
        'listing_area': listing.listing_area,
        'listing_balcony_area': listing.listing_balcony_area,
        'listing_layout': listing.listing_layout,
        'listing_direction': listing.listing_direction,
        'listing_total_floors': listing.listing_total_floors,
        'listing_total_units': listing.listing_total_units,
        'listing_built_year': listing.listing_built_year,
        'listing_built_month': listing.listing_built_month,
        'management_fee': listing.management_fee,
        'repair_fund': listing.repair_fund,
        'agency_name': listing.agency_name,
        'agency_tel': listing.agency_tel,
        'station_info': listing.station_info,
        'remarks': listing.remarks,

        'first_seen_at': listing.first_seen_at.isoformat() if listing.first_seen_at else None,
        'first_published_at': listing.first_published_at.isoformat() if listing.first_published_at else None,
        'published_at': listing.published_at.isoformat() if listing.published_at else None,
        'last_confirmed_at': listing.last_confirmed_at.isoformat() if listing.last_confirmed_at else None,
        'delisted_at': listing.delisted_at.isoformat() if listing.delisted_at else None,
        'detail_fetched_at': listing.detail_fetched_at.isoformat() if listing.detail_fetched_at else None,
        'created_at': listing.created_at.isoformat() if listing.created_at else None,
        'updated_at': listing.updated_at.isoformat() if listing.updated_at else None,
        'price_history': price_history,
        'detail_info': listing.detail_info,
    }


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
):
    """掲載情報分離時の候補物件を取得（管理者用）"""
    try:
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
        listing_room = current_property.room_number  # PropertyListingには部屋番号フィールドがない
        
        # 掲載情報から適切な建物を検索（スクレイピング時と同じロジック）
        from ..models import BuildingListingName, Building
        from ..utils.building_name_normalizer import canonicalize_building_name
        from ..utils.address_normalizer import AddressNormalizer
        
        suggested_building_ids = set()
        
        # 掲載情報の属性を取得
        listing_building_name = listing.listing_building_name
        listing_address = listing.listing_address
        listing_total_floors = listing.listing_total_floors
        listing_total_units = listing.listing_total_units
        listing_built_year = listing.listing_built_year
        
        if listing_building_name:
            # 建物名を正規化して検索
            canonical_name = canonicalize_building_name(listing_building_name)
            
            # 1. BuildingListingNameテーブルから建物名で候補を検索
            name_matching_buildings = db.query(BuildingListingName.building_id).filter(
                BuildingListingName.canonical_name == canonical_name
            ).distinct().all()
            
            # 2. 各候補建物を住所・属性でスコアリング
            if name_matching_buildings:
                addr_normalizer = AddressNormalizer() if listing_address else None
                normalized_address = addr_normalizer.normalize_for_comparison(listing_address) if listing_address else None
                
                for (building_id,) in name_matching_buildings:
                    building = db.query(Building).filter(Building.id == building_id).first()
                    if building:
                        score = 0
                        
                        # 住所の一致度を評価
                        if normalized_address and building.normalized_address:
                            if building.normalized_address == normalized_address:
                                score += 50  # 住所完全一致
                            elif normalized_address in building.normalized_address or building.normalized_address in normalized_address:
                                score += 20  # 住所部分一致
                        
                        # 総階数の一致度を評価
                        if listing_total_floors and building.total_floors:
                            if building.total_floors == listing_total_floors:
                                score += 20  # 総階数完全一致
                            elif abs(building.total_floors - listing_total_floors) <= 1:
                                score += 10  # 総階数±1階以内
                        
                        # 総戸数の一致度を評価
                        if listing_total_units and building.total_units:
                            if building.total_units == listing_total_units:
                                score += 15  # 総戸数完全一致
                            elif abs(building.total_units - listing_total_units) <= 5:
                                score += 5  # 総戸数±5戸以内
                        
                        # 築年の一致度を評価
                        if listing_built_year and building.built_year:
                            if building.built_year == listing_built_year:
                                score += 15  # 築年完全一致
                            elif abs(building.built_year - listing_built_year) <= 1:
                                score += 5  # 築年±1年以内
                        
                        # 高スコアの建物を候補に追加（閾値を設定）
                        if score >= 20:  # 最低限のスコアを持つ建物のみ
                            suggested_building_ids.add(building_id)
        
        # 候補物件を検索
        candidates = []
        
        # すべての物件を検索（現在の物件を除外）
        all_properties_query = db.query(MasterProperty).join(
            Building, MasterProperty.building_id == Building.id
        ).filter(
            MasterProperty.id != current_property.id
        )
        
        # 条件に合う物件を検索
        for prop in all_properties_query.all():
            score = 0
            match_details = []
            
            # 建物名マッチによる加点（掲載情報の建物名と一致する建物内の物件）
            if prop.building_id in suggested_building_ids:
                score += 10  # 建物名が一致する場合は高得点
                match_details.append("建物名一致")
            
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
            'candidates': candidates[:20],  # 上位20件まで（より多くの候補を表示）
            'new_property_defaults': new_property_defaults,
            'can_create_new': True
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"候補検索中にエラーが発生しました: {str(e)}")


@router.post("/listings/{listing_id}/attach-to-property")
async def attach_listing_to_property(
    listing_id: int,
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """掲載情報を指定された物件に紐付け（管理者用）"""
    import logging
    logger = logging.getLogger(__name__)
    
    # リクエストパラメータを取得
    target_property_id = request.get('property_id')
    create_new = request.get('create_new', False)
    delete_original = request.get('delete_original', False)  # 元の物件を削除するかどうか
    
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
    
    # 元の物件に残る掲載情報の数を確認
    remaining_listings_count = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == current_property.id,
        PropertyListing.id != listing_id
    ).count()
    
    if create_new:
        # 新しい物件を作成
        new_property = MasterProperty(
            building_id=current_property.building_id,
            room_number=request.get('room_number') or current_property.room_number,
            floor_number=request.get('floor_number') or listing.listing_floor_number or current_property.floor_number,
            area=request.get('area') or listing.listing_area or current_property.area,
            layout=request.get('layout') or listing.listing_layout or current_property.layout,
            direction=request.get('direction') or listing.listing_direction or current_property.direction,
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
    
    # 元の物件を削除する前に必要な情報を保存
    original_property_id = current_property.id
    original_building_id = current_property.building_id
    
    # 多数決処理を実行（元の物件と移動先の物件の両方）
    from ..utils.majority_vote_updater import MajorityVoteUpdater
    from ..utils.building_listing_name_manager import BuildingListingNameManager
    updater = MajorityVoteUpdater(db)
    listing_name_manager = BuildingListingNameManager(db)
    
    # データベースに変更を反映（掲載情報の紐付けを先に確定）
    db.flush()
    
    # 移動先の物件を更新（削除前に実行）
    new_property_obj = db.query(MasterProperty).filter(MasterProperty.id == new_property_id).first()
    if new_property_obj:
        updater.update_master_property_by_majority(new_property_obj)
        # 最初の掲載日を更新
        from ..utils.property_utils import update_earliest_listing_date, update_latest_price_change
        update_earliest_listing_date(db, new_property_id)
        update_latest_price_change(db, new_property_id)
    
    # 元の物件を削除（必要な場合）
    original_deleted = False
    if delete_original and remaining_listings_count == 0:
        # 元の物件に掲載情報が残らない場合のみ削除
        # SQLAlchemyのセッションから切り離して削除
        db.expire(listing)  # 掲載情報をセッションから切り離す
        db.flush()  # 確実に反映
        db.delete(current_property)
        db.flush()  # 削除を確実に反映
        original_deleted = True
        message += "（元の物件は削除されました）"
        # 元の物件が削除された場合も、建物の掲載名を更新
        listing_name_manager.refresh_building_names(original_building_id)
        logger.info(f"[DEBUG] Refreshed listing names for building {original_building_id} after property deletion")
    else:
        # 元の物件が削除されない場合は更新
        original_property_obj = db.query(MasterProperty).filter(MasterProperty.id == original_property_id).first()
        if original_property_obj:
            updater.update_master_property_by_majority(original_property_obj)
            # 元の物件の最初の掲載日と価格改定日も更新
            update_earliest_listing_date(db, original_property_id)
            update_latest_price_change(db, original_property_id)
    
    # BuildingListingNameテーブルを更新
    # 掲載情報の移動後、その掲載情報の建物名を反映
    listing_name_manager.update_from_listing(listing)
    
    # 物件が異なる建物に移動する場合、物件分離として処理
    if create_new:
        # 新規物件作成の場合
        if original_building_id != new_property.building_id:
            listing_name_manager.update_from_property_split(
                original_property_id=original_property_id,
                new_property_id=new_property.id,
                new_building_id=new_property.building_id
            )
    else:
        # 既存物件に紐付ける場合
        target_property = db.query(MasterProperty).filter(
            MasterProperty.id == target_property_id
        ).first()
        if target_property and original_building_id != target_property.building_id:
            # 異なる建物への移動の場合、掲載情報の建物名を新しい建物にも登録
            listing_name_manager.refresh_building_names(target_property.building_id)
            # 重要: 元の建物の掲載名も再計算
            listing_name_manager.refresh_building_names(original_building_id)
    
    try:
        db.commit()
        return {
            "success": True,
            "message": message,
            "original_property_id": original_property_id,
            "new_property_id": new_property_id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"掲載情報紐付けエラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"紐付け処理に失敗しました: {str(e)}")


@router.post("/listings/{listing_id}/refresh-detail")
async def refresh_listing_detail(
    listing_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """掲載情報の詳細を再取得（管理者用）- 簡易版"""
    # 対象の掲載情報を取得
    listing = db.query(PropertyListing).filter(
        PropertyListing.id == listing_id
    ).first()
    
    if not listing:
        raise HTTPException(status_code=404, detail="掲載情報が見つかりません")
    
    if not listing.is_active:
        raise HTTPException(status_code=400, detail="掲載終了した物件の詳細は再取得できません")
    
    # バックグラウンドでシンプルな詳細取得を実行（タスク作成なし）
    background_tasks.add_task(
        refresh_single_listing_detail,
        listing_id=listing_id,
        url=listing.url,
        source_site=listing.source_site
    )
    
    return {
        "success": True,
        "message": "詳細情報の再取得を開始しました",
        "listing_id": listing_id,
        "url": listing.url,
        "source_site": listing.source_site
    }


def refresh_single_listing_detail(
    listing_id: int,
    url: str,
    source_site: str
):
    """単一の掲載情報の詳細を再取得（シンプル版）"""
    import logging
    from datetime import datetime
    from ..database import SessionLocal
    from ..utils.scraper_utils import fetch_property_detail, update_listing_from_detail
    
    logger = logging.getLogger(__name__)
    logger.info(f"詳細再取得開始（簡易版）: listing_id={listing_id}, url={url}")
    
    db = SessionLocal()
    try:
        # 既存の掲載情報を取得
        listing = db.query(PropertyListing).filter(
            PropertyListing.id == listing_id
        ).first()
        
        if not listing:
            logger.error(f"掲載情報が見つかりません: listing_id={listing_id}")
            return False
        
        # 詳細情報を取得（ユーティリティ関数を使用）
        # source_siteはそのまま使用（スクレイパーが小文字を期待）
        detail_info = fetch_property_detail(url, source_site)
        
        if not detail_info:
            logger.error(f"詳細情報解析失敗: {url}")
            return False
        
        # datetime型を文字列に変換（JSON対応）
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime(item) for item in obj]
            return obj
        
        detail_info = convert_datetime(detail_info)
        
        # 掲載情報を更新
        listing.detail_info = detail_info
        listing.detail_fetched_at = datetime.now()
        listing.updated_at = datetime.now()
        
        # 詳細情報から各フィールドを更新（ユーティリティ関数を使用）
        update_listing_from_detail(listing, detail_info)
        
        # 多数決処理を実行して物件情報と建物情報を更新
        from ..utils.majority_vote_updater import MajorityVoteUpdater
        
        if listing.master_property:
            logger.info(f"物件の多数決処理を実行: master_property_id={listing.master_property.id}")
            updater = MajorityVoteUpdater(db)
            updater.update_master_property_by_majority(listing.master_property)
            
            if listing.master_property.building:
                logger.info(f"建物の多数決処理を実行: building_id={listing.master_property.building.id}")
                updater.update_building_by_majority(listing.master_property.building)
        
        db.commit()
        logger.info(f"詳細情報更新完了: listing_id={listing_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"詳細取得エラー: {e}", exc_info=True)
        return False
    finally:
        db.close()

