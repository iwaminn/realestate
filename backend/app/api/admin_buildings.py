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

router = APIRouter(prefix="/api/admin", tags=["admin-buildings"])


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
    db: Session = Depends(get_db)
    # _: Any = Depends(verify_admin_credentials)  # 開発環境では一時的に無効化
):
    """建物一覧を取得（管理者用）"""
    query = db.query(Building)
    
    # フィルタリング
    if name:
        # 共通の建物名検索関数を使用
        from ..utils.building_search import apply_building_name_filter_with_alias
        from ..models import BuildingMergeHistory
        query = apply_building_name_filter_with_alias(
            query,
            name,
            db,
            Building,
            merge_history_table=BuildingMergeHistory,
            search_building_name=True,
            search_property_display_name=False,
            search_aliases=True  # エイリアスも検索対象に含める
        )
    
    if address:
        # スペース区切りでAND検索
        address_terms = address.strip().split()
        for term in address_terms:
            if term:  # 空文字列をスキップ
                query = query.filter(Building.address.ilike(f"%{term}%"))
    
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
    db: Session = Depends(get_db)
    # _: Any = Depends(verify_admin_credentials)  # 開発環境では一時的に無効化
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
    db: Session = Depends(get_db)
    # _: Any = Depends(verify_admin_credentials)  # 開発環境では一時的に無効化
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


@router.post("/properties/{property_id}/detach-candidates")
async def get_detach_candidates(
    property_id: int,
    db: Session = Depends(get_db)
    # _: Any = Depends(verify_admin_credentials)  # 開発環境では一時的に無効化
):
    """物件分離時の建物候補を取得（管理者用）"""
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
    
    # 物件のdisplay_building_nameを使用（重み付き多数決済みの値）
    most_common_building_name = property.display_building_name
    
    if not most_common_building_name:
        # display_building_nameが設定されていない場合は、掲載情報の有無を確認
        listings_count = db.query(PropertyListing).filter(
            PropertyListing.master_property_id == property_id
        ).count()
        
        if listings_count == 0:
            raise HTTPException(
                status_code=400, 
                detail="この物件には掲載情報がないため、分離できません"
            )
        else:
            # display_building_nameが未設定の場合はエラー
            raise HTTPException(
                status_code=400,
                detail="この物件の建物名が設定されていません。データの整合性を確認してください"
            )
    normalized_name = normalize_search_text(most_common_building_name)
    # canonical_name用のキーも生成
    from ..utils.search_normalizer import get_search_key_for_comparison
    search_key = get_search_key_for_comparison(most_common_building_name)
    
    logger.info(f"物件 {property_id} の最頻出建物名: {most_common_building_name} (正規化: {normalized_name}, 検索キー: {search_key})")
    
    # 現在の建物を取得して比較
    current_building = db.query(Building).filter(Building.id == current_building_id).first()
    logger.info(f"現在の建物: ID={current_building_id}, 名前={current_building.normalized_name}")
    
    # 物件の詳細情報を取得（住所、築年、総階数）
    property_listings = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == property_id
    ).all()
    
    # 物件情報から建物の属性を集計（最頻値を使用）
    property_address = None
    property_built_year = None
    property_built_month = None
    property_total_floors = None
    
    # 住所の集計
    address_counts = {}
    for listing in property_listings:
        if listing.listing_address:
            addr = listing.listing_address
            address_counts[addr] = address_counts.get(addr, 0) + 1
    if address_counts:
        property_address = max(address_counts, key=address_counts.get)
        property_address_normalized = normalize_search_text(property_address)
    else:
        property_address_normalized = None
    
    # 築年の集計
    built_year_counts = {}
    for listing in property_listings:
        if listing.listing_built_year:
            year = listing.listing_built_year
            built_year_counts[year] = built_year_counts.get(year, 0) + 1
    if built_year_counts:
        property_built_year = max(built_year_counts, key=built_year_counts.get)
    
    # 築月の集計
    built_month_counts = {}
    for listing in property_listings:
        if listing.listing_built_month:
            month = listing.listing_built_month
            built_month_counts[month] = built_month_counts.get(month, 0) + 1
    if built_month_counts:
        property_built_month = max(built_month_counts, key=built_month_counts.get)
    
    # 総階数の集計
    total_floors_counts = {}
    for listing in property_listings:
        if listing.listing_total_floors:
            floors = listing.listing_total_floors
            total_floors_counts[floors] = total_floors_counts.get(floors, 0) + 1
    if total_floors_counts:
        property_total_floors = max(total_floors_counts, key=total_floors_counts.get)
    
    logger.info(f"物件属性: 住所={property_address}, 築年={property_built_year}, 総階数={property_total_floors}")
    
    # 建物候補を収集
    building_candidates = []
    
    # 1. 建物名で検索（段階的なマッチング）
    # まずnormalized_name（棟表記含む）での完全一致を最優先
    normalized_match_query = db.query(Building).filter(
        Building.normalized_name == normalized_name,
        Building.id != current_building_id  # 現在の建物は除外
    )
    
    # canonical_name（棟表記除去）での一致も検索
    canonical_match_query = db.query(Building).filter(
        Building.canonical_name == search_key,
        Building.id != current_building_id
    )
    
    # 部分一致も検索（建物名の主要部分を含む）
    # 例：「白金ザ・スカイ 東棟」から「白金ザ・スカイ」を抽出
    base_name = normalized_name.split()[0] if ' ' in normalized_name else normalized_name
    partial_match_query = db.query(Building).filter(
        Building.normalized_name.like(f"%{base_name}%"),
        Building.id != current_building_id
    )
    
    # 両方の結果を統合
    all_buildings = []
    seen_ids = set()
    
    # normalized_name（棟表記含む）での完全一致を最優先
    for building in normalized_match_query.all():
        if building.id not in seen_ids:
            all_buildings.append(building)
            seen_ids.add(building.id)
    
    # canonical_name（棟表記除去）での一致を次に優先
    for building in canonical_match_query.all():
        if building.id not in seen_ids:
            all_buildings.append(building)
            seen_ids.add(building.id)
    
    # 部分一致を追加（上位20件まで）
    for building in partial_match_query.limit(20).all():
        if building.id not in seen_ids:
            all_buildings.append(building)
            seen_ids.add(building.id)
    
    # 各建物をスコアリング
    for building in all_buildings:
        score = 0
        match_details = []
        
        # 建物名の一致度を評価
        # normalized_name（棟表記含む）の完全一致を最優先
        if building.normalized_name == normalized_name:
            score += 15
            match_details.append("建物名完全一致（棟含む）")
        # canonical_name（棟表記除去）の一致は中優先
        elif building.canonical_name == search_key:
            score += 8
            match_details.append("建物群一致（棟違いの可能性）")
        # 部分一致は低優先
        elif base_name in building.normalized_name:
            score += 5
            match_details.append("建物名部分一致")
        
        # 住所の比較（前方一致も含む）
        if property_address_normalized and building.address:
            normalized_building_address = normalize_search_text(building.address)
            if normalized_building_address == property_address_normalized:
                score += 5
                match_details.append("住所完全一致")
            elif normalized_building_address.startswith(property_address_normalized) or property_address_normalized.startswith(normalized_building_address):
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
            'id': building.id,
            'normalized_name': building.normalized_name,
            'address': building.address,
            'built_year': building.built_year,
            'total_floors': building.total_floors,
            'total_units': building.total_units,
            'score': score,
            'match_details': match_details,
            'match_type': 'direct'
        })
    
    # 2. エイリアスから検索
    from ..models import BuildingMergeHistory
    
    merge_histories = db.query(BuildingMergeHistory).filter(
        or_(
            BuildingMergeHistory.canonical_merged_name == search_key,  # canonical_nameでの検索を追加
            BuildingMergeHistory.merged_building_name == most_common_building_name,
            BuildingMergeHistory.merged_building_name == most_common_building_name.replace(' ', '　'),
            BuildingMergeHistory.canonical_merged_name == normalized_name,
            func.replace(BuildingMergeHistory.merged_building_name, '　', ' ') == most_common_building_name
        )
    ).all()
    
    for merge_history in merge_histories:
        building = db.query(Building).filter(
            Building.id == merge_history.primary_building_id,
            Building.id != current_building_id
        ).first()
        
        if building:
            score = 0
            match_details = []
            
            # エイリアス名の一致
            score += 10
            match_details.append(f"エイリアス名一致({merge_history.merged_building_name})")
            
            # 住所の比較
            if property_address_normalized and building.address:
                normalized_building_address = normalize_search_text(building.address)
                if normalized_building_address == property_address_normalized:
                    score += 5
                    match_details.append("住所完全一致")
                elif normalized_building_address.startswith(property_address_normalized) or property_address_normalized.startswith(normalized_building_address):
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
            
            # 重複チェック
            if not any(c['id'] == building.id for c in building_candidates):
                building_candidates.append({
                    'id': building.id,
                    'normalized_name': building.normalized_name,
                    'address': building.address,
                    'built_year': building.built_year,
                    'total_floors': building.total_floors,
                    'total_units': building.total_units,
                    'score': score,
                    'match_details': match_details,
                    'match_type': 'alias',
                    'alias_name': merge_history.merged_building_name
                })
    
    # スコア順にソート
    building_candidates.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        'current_building': {
            'id': current_building.id,
            'normalized_name': current_building.normalized_name,
            'address': current_building.address
        },
        'property_building_name': most_common_building_name,
        'property_attributes': {
            'address': property_address,
            'built_year': property_built_year,
            'built_month': property_built_month,
            'total_floors': property_total_floors
        },
        'candidates': building_candidates[:10],  # 上位10件まで
        'can_create_new': len(building_candidates) == 0 or building_candidates[0]['score'] < 15  # スコアが低い場合は新規作成も推奨
    }


@router.post("/properties/{property_id}/attach-to-building")
async def attach_property_to_building(
    property_id: int,
    request: Dict[str, Any],
    db: Session = Depends(get_db)
    # _: Any = Depends(verify_admin_credentials)  # 開発環境では一時的に無効化
):
    """物件を指定された建物に紐付け（管理者用）"""
    from ..utils.search_normalizer import normalize_search_text
    import logging
    
    logger = logging.getLogger(__name__)
    
    # リクエストパラメータを取得
    target_building_id = request.get('building_id')
    create_new = request.get('create_new', False)
    new_building_name = request.get('new_building_name')
    new_building_address = request.get('new_building_address')
    new_building_built_year = request.get('new_building_built_year')
    new_building_built_month = request.get('new_building_built_month')
    new_building_total_floors = request.get('new_building_total_floors')
    
    # 対象物件を取得
    property = db.query(MasterProperty).filter(
        MasterProperty.id == property_id
    ).first()
    
    if not property:
        raise HTTPException(status_code=404, detail="物件が見つかりません")
    
    current_building_id = property.building_id
    
    # 物件のdisplay_building_nameを使用（重み付き多数決済みの値）
    most_common_building_name = property.display_building_name
    
    if create_new:
        # 新しい建物を作成
        if not new_building_name:
            new_building_name = most_common_building_name
        
        if not new_building_name:
            raise HTTPException(status_code=400, detail="新規建物の名前が必要です")
        
        normalized_name = normalize_search_text(new_building_name)
        
        # 同名の建物が既に存在するかチェック
        existing_buildings = db.query(Building).filter(
            Building.normalized_name == normalized_name
        ).all()
        
        if existing_buildings:
            # 完全に重複する建物があるかチェック（名前、住所、総階数、築年月がすべて同じ）
            for existing in existing_buildings:
                is_duplicate = True
                
                # 住所の比較（両方とも設定されている場合のみ比較）
                if new_building_address and existing.address:
                    if existing.address != new_building_address:
                        is_duplicate = False
                
                # 総階数の比較
                if new_building_total_floors and existing.total_floors != new_building_total_floors:
                    is_duplicate = False
                elif not new_building_total_floors and existing.total_floors:
                    is_duplicate = False
                
                # 築年月の比較
                if new_building_built_year and existing.built_year != new_building_built_year:
                    is_duplicate = False
                elif not new_building_built_year and existing.built_year:
                    is_duplicate = False
                elif new_building_built_month and existing.built_month != new_building_built_month:
                    is_duplicate = False
                elif not new_building_built_month and existing.built_month:
                    is_duplicate = False
                
                if is_duplicate:
                    # 完全に同じ建物が存在する
                    raise HTTPException(
                        status_code=400,
                        detail=f"同じ建物が既に存在します（ID: {existing.id}）。"
                               f"名前: {existing.normalized_name}, "
                               f"住所: {existing.address or '未設定'}, "
                               f"総階数: {existing.total_floors or '未設定'}階, "
                               f"築年: {existing.built_year or '未設定'}年"
                    )
            
            # 同名だが別の建物として登録可能
            logger.info(
                f"同名の建物が{len(existing_buildings)}件存在しますが、"
                f"住所・総階数・築年月のいずれかが異なるため新規建物として登録します: {normalized_name}"
            )
        
        new_building = Building(
            normalized_name=normalized_name,
            address=new_building_address,
            built_year=new_building_built_year,
            built_month=new_building_built_month,
            total_floors=new_building_total_floors,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_building)
        db.flush()  # IDを取得するため
        
        # 物件を新しい建物に紐付け
        property.building_id = new_building.id
        property.display_building_name = new_building_name
        property.updated_at = datetime.utcnow()
        
        message = f"新しい建物「{normalized_name}」を作成し、物件を紐付けました"
        new_building_id = new_building.id
        
    else:
        # 既存の建物に紐付け
        if not target_building_id:
            raise HTTPException(status_code=400, detail="紐付け先の建物IDが必要です")
        
        # 指定された建物が存在するか確認
        target_building = db.query(Building).filter(
            Building.id == target_building_id
        ).first()
        
        if not target_building:
            raise HTTPException(status_code=404, detail="指定された建物が見つかりません")
        
        # 現在の建物と同じ場合はエラー
        if target_building_id == current_building_id:
            raise HTTPException(
                status_code=400,
                detail="現在と同じ建物には紐付けできません"
            )
        
        # 物件を既存の建物に紐付け
        property.building_id = target_building_id
        property.display_building_name = most_common_building_name
        property.updated_at = datetime.utcnow()
        
        message = f"物件を建物「{target_building.normalized_name}」に紐付けました"
        new_building_id = target_building_id
    
    # 多数決処理を実行（元の建物と移動先の建物の両方）
    from ..utils.majority_vote_updater import MajorityVoteUpdater
    updater = MajorityVoteUpdater(db)
    
    try:
        # 元の建物の情報を更新（物件が減った場合）
        if current_building_id:
            logger.info(f"[DEBUG] Updating original building {current_building_id} with majority vote after property removal")
            updater.update_building_name_by_majority(current_building_id)
        
        # 移動先の建物の情報を更新（物件が増えた場合）
        logger.info(f"[DEBUG] Updating target building {new_building_id} with majority vote after property addition")
        updater.update_building_name_by_majority(new_building_id)
        
        db.commit()
        
        logger.info(f"物件 {property_id} を建物 {current_building_id} から {new_building_id} に移動し、両建物の多数決処理を完了しました")
        
        return {
            "success": True,
            "message": message,
            "original_building_id": current_building_id,
            "new_building_id": new_building_id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"物件紐付けエラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"紐付け処理に失敗しました: {str(e)}")

