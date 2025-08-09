"""
管理者用建物管理API
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, Integer
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing, BuildingExternalId
from ..auth import verify_admin_credentials

router = APIRouter(tags=["admin-buildings"])


@router.get("/buildings")
async def get_buildings(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    name: Optional[str] = None,
    address: Optional[str] = None,
    min_built_year: Optional[int] = None,
    max_built_year: Optional[int] = None,
    min_total_floors: Optional[int] = None,
    max_total_floors: Optional[int] = None,
    has_active_listings: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物一覧を取得（管理者用）"""
    query = db.query(Building)
    
    # フィルタリング
    if name:
        query = query.filter(Building.normalized_name.ilike(f"%{name}%"))
    
    if address:
        query = query.filter(Building.address.ilike(f"%{address}%"))
    
    if min_built_year is not None:
        query = query.filter(Building.built_year >= min_built_year)
    
    if max_built_year is not None:
        query = query.filter(Building.built_year <= max_built_year)
    
    if min_total_floors is not None:
        query = query.filter(Building.total_floors >= min_total_floors)
    
    if max_total_floors is not None:
        query = query.filter(Building.total_floors <= max_total_floors)
    
    # 掲載状態でフィルタ
    if has_active_listings is not None:
        active_building_subquery = db.query(MasterProperty.building_id).join(
            PropertyListing
        ).filter(
            PropertyListing.is_active == True
        ).distinct().subquery()
        
        if has_active_listings:
            query = query.filter(Building.id.in_(active_building_subquery))
        else:
            query = query.filter(~Building.id.in_(active_building_subquery))
    
    # 総件数を取得
    total = query.count()
    
    # ページネーション
    buildings = query.offset(offset).limit(limit).all()
    
    # 各建物の統計情報を取得
    building_ids = [b.id for b in buildings]
    
    # 物件数と掲載情報の集計
    stats = db.query(
        MasterProperty.building_id,
        func.count(func.distinct(MasterProperty.id)).label('property_count'),
        func.count(func.distinct(PropertyListing.id)).filter(PropertyListing.is_active == True).label('active_listing_count'),
        func.min(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('min_price'),
        func.max(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('max_price')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id, isouter=True
    ).filter(
        MasterProperty.building_id.in_(building_ids)
    ).group_by(MasterProperty.building_id).all()
    
    stats_dict = {
        stat.building_id: {
            'property_count': stat.property_count or 0,
            'active_listing_count': stat.active_listing_count or 0,
            'min_price': stat.min_price,
            'max_price': stat.max_price
        }
        for stat in stats
    }
    
    # レスポンスの構築
    items = []
    for building in buildings:
        building_stats = stats_dict.get(building.id, {
            'property_count': 0,
            'active_listing_count': 0,
            'min_price': None,
            'max_price': None
        })
        
        items.append({
            'id': building.id,
            'normalized_name': building.normalized_name,
            'address': building.address,
            'total_floors': building.total_floors,
            'total_units': building.total_units,  # 総戸数を追加
            'built_year': building.built_year,
            'created_at': building.created_at.isoformat() if building.created_at else None,
            'updated_at': building.updated_at.isoformat() if building.updated_at else None,
            **building_stats
        })
    
    return {
        'items': items,
        'total': total,
        'offset': offset,
        'limit': limit
    }


@router.get("/buildings/search")
async def search_buildings_for_merge(
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    credentials: Any = Depends(verify_admin_credentials)
):
    """建物検索（統合用）"""
    from ..utils.search_normalizer import create_search_patterns, normalize_search_text
    from ..models import BuildingMergeHistory
    
    # 検索文字列を正規化してAND検索用に分割
    normalized_search = normalize_search_text(query)
    search_terms = normalized_search.split()
    
    # まず統合履歴（エイリアス）から検索
    alias_matches = db.query(
        BuildingMergeHistory.primary_building_id,
        BuildingMergeHistory.merged_building_name.label('alias_name')
    ).filter(
        or_(
            BuildingMergeHistory.merged_building_name.ilike(f"%{query}%"),
            BuildingMergeHistory.canonical_merged_name.ilike(f"%{normalized_search}%")
        )
    ).distinct().all()
    
    # エイリアスにマッチした建物IDのリスト
    alias_building_ids = [match.primary_building_id for match in alias_matches]
    
    # クエリ構築
    name_query = db.query(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors,
        func.count(MasterProperty.id).label('property_count')
    ).outerjoin(
        MasterProperty, Building.id == MasterProperty.building_id
    )
    
    # 複数の検索語がある場合はAND検索
    if len(search_terms) > 1:
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                term_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
            if term_conditions:
                # 各検索語について、いずれかのパターンにマッチ
                and_conditions.append(or_(*term_conditions))
        
        if and_conditions:
            # 全ての検索語を含む（AND条件）、またはエイリアスにマッチした建物
            if alias_building_ids:
                name_query = name_query.filter(
                    or_(
                        and_(*and_conditions),
                        Building.id.in_(alias_building_ids)
                    )
                )
            else:
                name_query = name_query.filter(and_(*and_conditions))
    else:
        # 単一の検索語の場合
        search_patterns = create_search_patterns(query)
        search_conditions = []
        for pattern in search_patterns:
            search_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
        
        # エイリアスマッチも含める
        if alias_building_ids:
            search_conditions.append(Building.id.in_(alias_building_ids))
        
        if search_conditions:
            name_query = name_query.filter(or_(*search_conditions))
    
    # グループ化と並び替え
    buildings = name_query.group_by(
        Building.id,
        Building.normalized_name,
        Building.address,
        Building.total_floors
    ).order_by(
        func.count(MasterProperty.id).desc()
    ).limit(limit).all()
    
    # 各建物のエイリアス情報を取得
    building_ids_for_alias = [b.id for b in buildings]
    aliases_dict = {}
    if building_ids_for_alias:
        aliases = db.query(
            BuildingMergeHistory.primary_building_id,
            func.string_agg(
                BuildingMergeHistory.merged_building_name, 
                ', '
            ).label('aliases')
        ).filter(
            BuildingMergeHistory.primary_building_id.in_(building_ids_for_alias)
        ).group_by(
            BuildingMergeHistory.primary_building_id
        ).all()
        
        aliases_dict = {alias.primary_building_id: alias.aliases for alias in aliases}
    
    result = []
    for building in buildings:
        building_data = {
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "property_count": building.property_count
        }
        
        # エイリアス情報があれば追加
        if building.id in aliases_dict:
            building_data["aliases"] = aliases_dict[building.id]
        
        # エイリアス検索でマッチした場合、どのエイリアスでマッチしたか表示
        for match in alias_matches:
            if match.primary_building_id == building.id:
                building_data["matched_alias"] = match.alias_name
                break
        
        result.append(building_data)
    
    return {
        "buildings": result,
        "total": len(result)
    }


@router.get("/buildings/{building_id}")
async def get_building_detail(
    building_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物詳細を取得（管理者用）"""
    from ..models import BuildingMergeHistory
    
    building = db.query(Building).filter(Building.id == building_id).first()
    
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 物件一覧を取得
    properties = db.query(
        MasterProperty.id,
        MasterProperty.room_number,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction,
        MasterProperty.display_building_name,  # 物件毎の建物名を追加
        func.count(PropertyListing.id).filter(PropertyListing.is_active == True).label('active_listing_count'),
        func.min(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('min_price'),
        func.max(PropertyListing.current_price).filter(PropertyListing.is_active == True).label('max_price')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id, isouter=True
    ).filter(
        MasterProperty.building_id == building_id
    ).group_by(
        MasterProperty.id,
        MasterProperty.room_number,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction,
        MasterProperty.display_building_name
    ).order_by(
        MasterProperty.floor_number.nullslast(),
        MasterProperty.room_number.nullslast()
    ).all()
    
    # 外部建物IDを取得
    external_ids = db.query(BuildingExternalId).filter(
        BuildingExternalId.building_id == building_id
    ).all()
    
    # エイリアス（統合された建物名）を取得
    aliases = db.query(
        BuildingMergeHistory.id,
        BuildingMergeHistory.merged_building_name,
        BuildingMergeHistory.merged_at,
        BuildingMergeHistory.merged_by,
        BuildingMergeHistory.property_count,  # 統合時の物件数を追加
        BuildingMergeHistory.merge_details  # 統合詳細を追加
    ).filter(
        BuildingMergeHistory.primary_building_id == building_id
    ).order_by(
        BuildingMergeHistory.merged_at.desc()
    ).all()
    
    # 重複を除去してユニークなエイリアスリストを作成
    unique_aliases = []
    seen_names = set()
    for alias in aliases:
        if alias.merged_building_name and alias.merged_building_name not in seen_names:
            seen_names.add(alias.merged_building_name)
            
            # merge_detailsから物件数を取得（新しい形式の場合）
            property_count = alias.property_count
            if property_count is None and alias.merge_details:
                # merge_detailsがJSONオブジェクトでproperty_idsを含む場合
                if isinstance(alias.merge_details, dict) and 'property_ids' in alias.merge_details:
                    property_count = len(alias.merge_details['property_ids'])
                # merge_detailsがプロパティIDのリストの場合
                elif isinstance(alias.merge_details, list):
                    property_count = len(alias.merge_details)
            
            unique_aliases.append({
                'id': alias.id,  # 統合履歴IDを追加
                'name': alias.merged_building_name,
                'merged_at': alias.merged_at.isoformat() if alias.merged_at else None,
                'merged_by': alias.merged_by,
                'property_count': property_count or 0  # 統合時の物件数を追加
            })
    
    # 統計情報を計算
    property_count = len(properties)
    active_listing_count = sum(1 for p in properties if p.active_listing_count > 0)
    all_prices = [p.min_price for p in properties if p.min_price] + [p.max_price for p in properties if p.max_price]
    min_price = min(all_prices) if all_prices else None
    max_price = max(all_prices) if all_prices else None
    
    return {
        'id': building.id,
        'normalized_name': building.normalized_name,
        'address': building.address,
        'total_floors': building.total_floors,
        'total_units': building.total_units,  # 総戸数を追加
        'built_year': building.built_year,
        'created_at': building.created_at.isoformat() if building.created_at else None,
        'updated_at': building.updated_at.isoformat() if building.updated_at else None,
        'property_count': property_count,
        'active_listing_count': active_listing_count,
        'min_price': min_price,
        'max_price': max_price,
        'aliases': unique_aliases,  # エイリアス情報を追加
        'external_ids': [
            {
                'source_site': ext_id.source_site,
                'external_id': ext_id.external_id,
                'created_at': ext_id.created_at.isoformat() if ext_id.created_at else None
            }
            for ext_id in external_ids
        ],
        'properties': [
            {
                'id': p.id,
                'room_number': p.room_number,
                'floor_number': p.floor_number,
                'area': p.area,
                'layout': p.layout,
                'direction': p.direction,
                'display_building_name': p.display_building_name,  # 物件毎の建物名を追加
                'active_listing_count': p.active_listing_count or 0,
                'min_price': p.min_price,
                'max_price': p.max_price
            }
            for p in properties
        ]
    }


@router.patch("/buildings/{building_id}")
async def update_building(
    building_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """建物情報を更新（管理者用）"""
    building = db.query(Building).filter(Building.id == building_id).first()
    
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 更新可能なフィールドのみ更新
    updatable_fields = [
        'normalized_name', 'address', 
        'total_floors', 'total_units', 'built_year'
    ]
    
    for field in updatable_fields:
        if field in data:
            setattr(building, field, data[field])
    
    building.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(building)
        return {"message": "建物情報を更新しました", "building_id": building.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新に失敗しました: {str(e)}")


@router.post("/properties/{property_id}/detach-from-building")
async def detach_property_from_building(
    property_id: int,
    db: Session = Depends(get_db),
    _: Any = Depends(verify_admin_credentials)
):
    """物件を建物から分離して、適切な建物に再紐付け（管理者用）"""
    from ..utils.search_normalizer import normalize_search_text
    import logging
    
    logger = logging.getLogger(__name__)
    
    # 対象物件を取得
    property = db.query(MasterProperty).filter(
        MasterProperty.id == property_id
    ).first()
    
    if not property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    current_building_id = property.building_id
    
    # 物件に紐付く掲載情報から建物名を取得（多数決）
    listings = db.query(
        PropertyListing.listing_building_name,
        func.count(PropertyListing.id).label('count')
    ).filter(
        PropertyListing.master_property_id == property_id,
        PropertyListing.listing_building_name.isnot(None)
    ).group_by(
        PropertyListing.listing_building_name
    ).order_by(
        func.count(PropertyListing.id).desc()
    ).all()
    
    if not listings:
        raise HTTPException(
            status_code=400, 
            detail="この物件には掲載情報がないため、分離できません"
        )
    
    # 最も多く掲載されている建物名を取得
    most_common_building_name = listings[0].listing_building_name
    normalized_name = normalize_search_text(most_common_building_name)
    
    logger.info(f"物件 {property_id} の最頻出建物名: {most_common_building_name} (正規化: {normalized_name})")
    
    # 現在の建物を取得して比較
    current_building = db.query(Building).filter(Building.id == current_building_id).first()
    logger.info(f"現在の建物: ID={current_building_id}, 名前={current_building.normalized_name}")
    
    # 正規化した名前が同じかチェック
    if current_building.normalized_name == normalized_name:
        logger.warning(f"分離しようとしている建物名 '{normalized_name}' は現在の建物名と同じです")
        raise HTTPException(
            status_code=400,
            detail=f"分離後も同じ建物名「{normalized_name}」になるため、分離できません"
        )
    
    # 物件の詳細情報を取得（住所、築年、総階数）
    property_listings = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == property_id
    ).all()
    
    # 物件情報から建物の属性を集計（最頻値を使用）
    property_address = None
    property_built_year = None
    property_total_floors = None
    
    # 住所の集計
    address_counts = {}
    for listing in property_listings:
        if listing.listing_address:
            addr = listing.listing_address
            address_counts[addr] = address_counts.get(addr, 0) + 1
    if address_counts:
        property_address = max(address_counts, key=address_counts.get)
        # 住所を正規化
        property_address = normalize_search_text(property_address)
    
    # 築年の集計
    built_year_counts = {}
    for listing in property_listings:
        if listing.listing_built_year:
            year = listing.listing_built_year
            built_year_counts[year] = built_year_counts.get(year, 0) + 1
    if built_year_counts:
        property_built_year = max(built_year_counts, key=built_year_counts.get)
    
    # 総階数の集計
    total_floors_counts = {}
    for listing in property_listings:
        if listing.listing_total_floors:
            floors = listing.listing_total_floors
            total_floors_counts[floors] = total_floors_counts.get(floors, 0) + 1
    if total_floors_counts:
        property_total_floors = max(total_floors_counts, key=total_floors_counts.get)
    
    logger.info(f"物件属性: 住所={property_address}, 築年={property_built_year}, 総階数={property_total_floors}")
    
    # 既存の建物を検索（建物名＋住所＋築年＋総階数で判定）
    building_candidates = []
    
    # 1. 正規化名で直接検索
    query = db.query(Building).filter(
        Building.normalized_name == normalized_name,
        Building.id != current_building_id  # 現在の建物は除外
    )
    
    for building in query.all():
        score = 0
        match_details = []
        
        # 建物名の一致（必須）
        score += 10
        match_details.append("建物名一致")
        
        # 住所の比較（前方一致も含む）
        if property_address and building.address:
            normalized_building_address = normalize_search_text(building.address)
            if normalized_building_address == property_address:
                score += 5
                match_details.append("住所完全一致")
            elif normalized_building_address.startswith(property_address) or property_address.startswith(normalized_building_address):
                score += 3
                match_details.append("住所部分一致")
        
        # 築年の比較
        if property_built_year and building.built_year:
            if building.built_year == property_built_year:
                score += 5
                match_details.append("築年一致")
        
        # 総階数の比較
        if property_total_floors and building.total_floors:
            if building.total_floors == property_total_floors:
                score += 5
                match_details.append("総階数一致")
        
        building_candidates.append({
            'building': building,
            'score': score,
            'match_details': match_details
        })
    
    # 最高スコアの建物を選択
    if building_candidates:
        best_candidate = max(building_candidates, key=lambda x: x['score'])
        existing_building = best_candidate['building']
        logger.info(f"建物候補発見: ID={existing_building.id}, スコア={best_candidate['score']}, 詳細={best_candidate['match_details']}")
    else:
        existing_building = None
    
    # 見つからない場合は、統合履歴（エイリアス）から検索
    if not existing_building:
        from ..models import BuildingMergeHistory
        
        # エイリアスから検索（正規化して比較）
        merge_histories = db.query(BuildingMergeHistory).filter(
            or_(
                BuildingMergeHistory.merged_building_name == most_common_building_name,
                BuildingMergeHistory.merged_building_name == most_common_building_name.replace(' ', '　'),  # 全角スペース版も試す
                BuildingMergeHistory.canonical_merged_name == normalized_name,
                func.replace(BuildingMergeHistory.merged_building_name, '　', ' ') == most_common_building_name  # DBの全角スペースを半角に変換して比較
            )
        ).all()
        
        # エイリアスの統合先建物も同様にスコアリング
        for merge_history in merge_histories:
            # 統合先の建物を取得
            building = db.query(Building).filter(
                Building.id == merge_history.primary_building_id,
                Building.id != current_building_id  # 現在の建物は除外
            ).first()
            
            if building:
                score = 0
                match_details = []
                
                # エイリアス名の一致（必須）
                score += 10
                match_details.append(f"エイリアス名一致({merge_history.merged_building_name})")
                
                # 住所の比較（前方一致も含む）
                if property_address and building.address:
                    normalized_building_address = normalize_search_text(building.address)
                    if normalized_building_address == property_address:
                        score += 5
                        match_details.append("住所完全一致")
                    elif normalized_building_address.startswith(property_address) or property_address.startswith(normalized_building_address):
                        score += 3
                        match_details.append("住所部分一致")
                
                # 築年の比較
                if property_built_year and building.built_year:
                    if building.built_year == property_built_year:
                        score += 5
                        match_details.append("築年一致")
                
                # 総階数の比較
                if property_total_floors and building.total_floors:
                    if building.total_floors == property_total_floors:
                        score += 5
                        match_details.append("総階数一致")
                
                building_candidates.append({
                    'building': building,
                    'score': score,
                    'match_details': match_details,
                    'is_alias': True,
                    'alias_name': merge_history.merged_building_name
                })
        
        # 全候補（直接一致＋エイリアス）から最高スコアの建物を選択
        if building_candidates:
            best_candidate = max(building_candidates, key=lambda x: x['score'])
            existing_building = best_candidate['building']
            
            if best_candidate.get('is_alias'):
                logger.info(f"エイリアス '{best_candidate['alias_name']}' から統合先建物を発見: ID={existing_building.id}, 名前={existing_building.normalized_name}, スコア={best_candidate['score']}, 詳細={best_candidate['match_details']}")
            else:
                logger.info(f"建物候補発見: ID={existing_building.id}, スコア={best_candidate['score']}, 詳細={best_candidate['match_details']}")
    
    if existing_building:
        # 既存の建物が見つかった場合
        logger.info(f"既存の建物が見つかりました: ID={existing_building.id}, 名前={existing_building.normalized_name}")
        
        # この建物に紐付けた場合、再度同じ建物に戻るかチェック
        # （同じ正規化名を持つ建物が統合されている可能性がある）
        if existing_building.id == current_building_id:
            raise HTTPException(
                status_code=400,
                detail="分離後も同じ建物に紐付くため、分離できません"
            )
        
        # 物件を既存の建物に紐付け
        property.building_id = existing_building.id
        property.display_building_name = most_common_building_name
        
        message = f"物件を既存の建物「{existing_building.normalized_name}」に紐付けました"
        new_building_id = existing_building.id
        
    else:
        # 新しい建物を作成
        logger.info(f"新しい建物を作成します: {normalized_name}")
        
        # 物件情報から取得した属性を使用
        new_building = Building(
            normalized_name=normalized_name,
            address=property_address if property_address else None,  # 集計した住所を使用
            built_year=property_built_year,  # 集計した築年を使用
            total_floors=property_total_floors,  # 集計した総階数を使用
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        logger.info(f"新建物の属性: 住所={new_building.address}, 築年={new_building.built_year}, 総階数={new_building.total_floors}")
        
        db.add(new_building)
        db.flush()  # IDを取得するため
        
        # 物件を新しい建物に紐付け
        property.building_id = new_building.id
        property.display_building_name = most_common_building_name
        
        message = f"新しい建物「{normalized_name}」を作成し、物件を紐付けました"
        new_building_id = new_building.id
    
    # 更新日時を設定
    property.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        return {
            "success": True,
            "message": message,
            "original_building_id": current_building_id,
            "new_building_id": new_building_id,
            "new_building_name": normalized_name
        }
    except Exception as e:
        db.rollback()
        logger.error(f"物件分離エラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分離処理に失敗しました: {str(e)}")

