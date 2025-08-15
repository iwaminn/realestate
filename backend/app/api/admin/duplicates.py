"""
重複管理API（建物・物件）
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from ...database import get_db
from ...models import (
    Building, MasterProperty, PropertyListing,
    BuildingMergeHistory, PropertyMergeHistory,
    BuildingMergeExclusion, PropertyMergeExclusion,
    BuildingExternalId
)
from ...utils.enhanced_building_matcher import EnhancedBuildingMatcher
from ...utils.majority_vote_updater import MajorityVoteUpdater

router = APIRouter(tags=["admin-duplicates"])

# キャッシュ用のグローバル変数
_duplicate_buildings_cache = {}
_duplicate_buildings_cache_time = 0
CACHE_DURATION = 300  # 5分

def clear_duplicate_buildings_cache():
    """重複建物キャッシュをクリア"""
    global _duplicate_buildings_cache, _duplicate_buildings_cache_time
    _duplicate_buildings_cache = {}
    _duplicate_buildings_cache_time = 0


class DuplicateCandidate(BaseModel):
    """重複候補の物件ペア"""
    property1_id: int
    property2_id: int
    building_name: str
    floor_number: Optional[int]
    area: Optional[float]
    layout: Optional[str]
    similarity_score: Optional[float]


class BuildingMergeRequest(BaseModel):
    """建物統合リクエスト"""
    primary_building_id: int
    secondary_building_id: int


class BuildingMergeBatchRequest(BaseModel):
    """複数建物統合リクエスト"""
    primary_id: int
    secondary_ids: List[int]


class PropertyMergeRequest(BaseModel):
    """物件統合リクエスト"""
    primary_property_id: int
    secondary_property_id: int


@router.get("/duplicate-buildings")
async def get_duplicate_buildings(
    search: Optional[str] = Query(None, description="検索キーワード"),
    min_similarity: float = Query(0.7, description="類似度の閾値"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """建物の重複候補を取得（改善版）"""
    global _duplicate_buildings_cache, _duplicate_buildings_cache_time
    import re
    import time
    from backend.app.utils.enhanced_building_matcher import EnhancedBuildingMatcher
    
    # キャッシュキーの作成
    cache_key = f"{search}_{min_similarity}_{limit}"
    current_time = time.time()
    
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
        
        # 優先度1: 同じ建物名または類似した建物名を持つ建物（最も重複の可能性が高い）
        # まず完全一致する建物名のグループを取得
        exact_match_subquery = db.query(
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
                db.query(exact_match_subquery.c.normalized_name)
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
            # normalized_addressの前半部分を使用（番地より前の部分）
            attribute_groups = db.query(
                func.substring(Building.normalized_address, 1, 10).label('address_prefix'),  # 正規化済み住所の前半部分
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
                func.substring(Building.normalized_address, 1, 10),
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
                    Building.normalized_address.like(f"{group.address_prefix}%"),
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



@router.get("/duplicate-properties")
def get_duplicate_properties(
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
        from ...utils.search_normalizer import normalize_search_text
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
    
    if building_filter is not None:
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
        additional_query = db.query(
            MasterProperty.building_id,
            MasterProperty.floor_number,
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
            additional_query = additional_query.filter(MasterProperty.building_id.in_(
                db.query(Building.id).filter(building_filter)
            ))
        
        additional_groups = additional_query.group_by(
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
            
            # 除外ペアのチェック
            property_ids = [p[0].id for p in properties_query]
            
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
                # 同じ面積の物件をグループ化
                area_groups = {}
                for prop in properties_query:
                    area = prop[0].area
                    if area not in area_groups:
                        area_groups[area] = []
                    area_groups[area].append(prop)
                
                # 各面積グループで2つ以上の物件があるものを追加
                for area, props in area_groups.items():
                    if len(props) >= 2:
                        duplicate_groups.append({
                            "group_id": f"group_{len(duplicate_groups) + 1}",
                            "property_count": len(props),
                            "building_name": props[0].building_name,
                            "floor_number": group.floor_number,
                            "layout": group.layout,
                            "area": area,
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
                                for prop in props
                            ], key=lambda x: (-x["listing_count"], x["id"]))
                        })
                        
                        if len(duplicate_groups) >= limit:
                            break
    
    # 物件数の多い順にソート
    duplicate_groups.sort(key=lambda x: x["property_count"], reverse=True)
    
    # ページング
    total = len(duplicate_groups)
    paginated_groups = duplicate_groups[offset:offset + limit]
    
    return {
        "groups": paginated_groups,
        "total": total,
        "offset": offset,
        "limit": limit
    }



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
    from ...utils.search_normalizer import create_search_patterns, normalize_search_text
    
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
    
    return {"properties": results, "total": len(results)}


@router.post("/move-property-to-building")
def move_property_to_building(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """物件を別の建物に移動"""
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
            # 掲載情報を既存の物件に移動
            db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_id
            ).update({
                "master_property_id": existing_property.id
            })
            
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
        updater = MajorityVoteUpdater(db)
        
        # 元の建物の情報を更新（物件が減ったため）
        if original_building_id:
            updater.update_building_name_by_majority(original_building_id)
        
        # 移動先の建物の情報を更新（物件が増えたため）
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
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/merge-buildings")
async def merge_buildings(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """複数の建物を統合（admin_old.pyと互換性のある実装）"""
    
    # リクエストの形式を判定
    if "primary_id" in request and "secondary_ids" in request:
        # 複数建物の統合（旧形式）
        primary_id = request.get("primary_id")
        secondary_ids = request.get("secondary_ids", [])
        
        if not primary_id or not secondary_ids:
            raise HTTPException(status_code=400, detail="primary_id and secondary_ids are required")
        
        # 主建物を取得
        primary = db.query(Building).filter(Building.id == primary_id).first()
        if not primary:
            raise HTTPException(status_code=404, detail="Primary building not found")
        
        # 副建物を取得
        secondary_buildings = db.query(Building).filter(Building.id.in_(secondary_ids)).all()
        if len(secondary_buildings) != len(secondary_ids):
            found_ids = [b.id for b in secondary_buildings]
            missing_ids = [sid for sid in secondary_ids if sid not in found_ids]
            raise HTTPException(
                status_code=404, 
                detail=f"One or more secondary buildings not found. Missing IDs: {missing_ids}"
            )
    elif "primary_building_id" in request and "secondary_building_id" in request:
        # 単一建物の統合（新形式）
        primary_id = request.get("primary_building_id")
        secondary_id = request.get("secondary_building_id")
        
        primary = db.query(Building).filter(Building.id == primary_id).first()
        secondary = db.query(Building).filter(Building.id == secondary_id).first()
        
        if not primary or not secondary:
            raise HTTPException(status_code=404, detail="Building not found")
        
        secondary_buildings = [secondary]
    else:
        raise HTTPException(status_code=400, detail="Invalid request format")
    
    # 複数の建物を統合
    try:
        merged_count = 0
        moved_properties = 0
        building_infos = []
        
        for secondary_building in secondary_buildings:
            # 統合履歴を記録（詳細情報を含む）
            merge_details = {
                "merged_buildings": [{
                    "id": secondary_building.id,
                    "normalized_name": secondary_building.normalized_name,
                    "address": secondary_building.address,
                    "total_floors": secondary_building.total_floors,
                    "built_year": secondary_building.built_year,
                    "construction_type": secondary_building.construction_type if hasattr(secondary_building, 'construction_type') else None,
                    "property_ids": [],  # 後で追加
                    "properties_moved": 0  # 後で更新
                }]
            }
            
            merge_history = BuildingMergeHistory(
                primary_building_id=primary_id,
                merged_building_id=secondary_building.id,
                merged_building_name=secondary_building.normalized_name,
                canonical_merged_name=secondary_building.canonical_name,
                merge_details=merge_details,  # 詳細情報を保存
                merged_at=datetime.now(),
                merged_by="admin"
            )
            db.add(merge_history)
            
            # 物件を移動
            properties_to_move = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary_building.id
            ).all()
            
            property_ids_moved = []
            for prop in properties_to_move:
                # PropertyMergeHistoryの参照を更新
                db.query(PropertyMergeHistory).filter(
                    or_(
                        PropertyMergeHistory.primary_property_id == prop.id,
                        PropertyMergeHistory.merged_property_id == prop.id
                    )
                ).update({
                    "primary_property_id": prop.id if PropertyMergeHistory.primary_property_id == prop.id else PropertyMergeHistory.primary_property_id,
                    "merged_property_id": prop.id if PropertyMergeHistory.merged_property_id == prop.id else PropertyMergeHistory.merged_property_id
                })
                
                prop.building_id = primary_id
                moved_properties += 1
                property_ids_moved.append(prop.id)
            
            # merge_detailsに物件IDを記録
            merge_history.merge_details["merged_buildings"][0]["property_ids"] = property_ids_moved
            merge_history.merge_details["merged_buildings"][0]["properties_moved"] = len(property_ids_moved)
            
            # 外部IDを移動（重複がある場合は削除）
            external_ids_to_move = db.query(BuildingExternalId).filter(
                BuildingExternalId.building_id == secondary_building.id
            ).all()
            
            for ext_id in external_ids_to_move:
                # 同じ外部IDが既に主建物に存在するか確認
                existing = db.query(BuildingExternalId).filter(
                    BuildingExternalId.building_id == primary_id,
                    BuildingExternalId.source_site == ext_id.source_site,
                    BuildingExternalId.external_id == ext_id.external_id
                ).first()
                
                if existing:
                    # 重複する場合は削除
                    db.delete(ext_id)
                else:
                    # 重複しない場合は移動
                    ext_id.building_id = primary_id
            
            # 変更をフラッシュ（物件と外部IDの移動を確実に反映）
            db.flush()
            
            # 建物情報を保存（レスポンス用）
            building_infos.append({
                "id": secondary_building.id,
                "name": secondary_building.normalized_name,
                "properties_moved": len(properties_to_move)
            })
            
            # 既存の統合履歴の参照を更新（この建物が他の統合履歴で参照されている場合）
            db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.primary_building_id == secondary_building.id
            ).update({
                "primary_building_id": primary_id
            })
            
            # 建物を削除
            db.delete(secondary_building)
            merged_count += 1
        
        # 多数決で建物情報を更新
        updater = MajorityVoteUpdater(db)
        updater.update_building_name_by_majority(primary_id)
        
        db.commit()
        
        return {
            "merged_count": merged_count,
            "moved_properties": moved_properties,
            "primary_building": {
                "id": primary.id,
                "normalized_name": primary.normalized_name,
                "address": primary.address if hasattr(primary, 'address') else None,
                "property_count": db.query(MasterProperty).filter(
                    MasterProperty.building_id == primary_id
                ).count()
            },
            "message": f"{merged_count}件の建物を統合し、{moved_properties}件の物件を処理しました。重複物件は自動的に統合されました。",
            "merged_buildings": building_infos
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/revert-building-merge/{history_id}")
async def revert_building_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """統合を取り消す（建物を復元）"""
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # merge_detailsがない場合は基本情報から復元
    if not history.merge_details:
        # 旧形式の履歴の場合、最小限の情報で復元を試みる
        # merged_building_idが存在するか確認
        if not history.merged_building_id:
            raise HTTPException(
                status_code=400,
                detail="統合履歴に必要な情報がないため、取り消しできません。"
            )
        
        # 簡易的なmerge_detailsを作成
        history.merge_details = {
            "merged_buildings": [{
                "id": history.merged_building_id,
                "normalized_name": history.merged_building_name or f"建物{history.merged_building_id}",
                "address": None,
                "total_floors": None,
                "built_year": None,
                "construction_type": None,
                "property_ids": [],
                "properties_moved": 0
            }]
        }
    
    # 建物が既に存在するかどうかで取り消し済みかを判断
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
                continue
            
            # 建物を復元（読み仮名も生成）
            from ...utils.reading_generator import generate_reading
            building = Building(
                id=building_id,
                normalized_name=merged_building["normalized_name"],
                address=merged_building.get("address"),
                reading=generate_reading(merged_building["normalized_name"]),
                total_floors=merged_building.get("total_floors"),
                built_year=merged_building.get("built_year"),
                construction_type=merged_building.get("construction_type")
            )
            db.add(building)
            
            # この建物に移動された物件を元に戻す
            property_ids = merged_building.get("property_ids", [])
            if property_ids:
                existing_properties = db.query(MasterProperty).filter(
                    MasterProperty.id.in_(property_ids),
                    MasterProperty.building_id == history.primary_building_id
                ).all()
                
                for prop in existing_properties:
                    prop.building_id = building_id
            
            restored_count += 1
        
        # 統合時に作成された可能性のある除外ペアを削除
        merged_building_ids = [b["id"] for b in history.merge_details.get("merged_buildings", [])]
        for building_id in merged_building_ids:
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
        
        # 多数決による建物名更新
        updater = MajorityVoteUpdater(db)
        
        # 主建物の名前を更新
        if primary_building:
            updater.update_building_name_by_majority(primary_building.id)
        
        # 復元された建物の名前も更新
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            restored_building = db.query(Building).filter(Building.id == building_id).first()
            if restored_building:
                updater.update_building_name_by_majority(building_id)
        
        # 履歴レコードを削除
        db.delete(history)
        
        db.commit()
        
        message = f"統合を取り消しました。{restored_count}件の建物を復元しました。"
        
        return {
            "success": True,
            "message": message,
            "restored_count": restored_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"取り消し中にエラーが発生しました: {str(e)}")


@router.post("/merge-properties")
async def merge_properties(
    request: PropertyMergeRequest,
    db: Session = Depends(get_db)
):
    """2つの物件を統合"""
    
    # 物件の存在確認
    primary = db.query(MasterProperty).filter(
        MasterProperty.id == request.primary_property_id
    ).first()
    secondary = db.query(MasterProperty).filter(
        MasterProperty.id == request.secondary_property_id
    ).first()
    
    if not primary and not secondary:
        raise HTTPException(
            status_code=404, 
            detail=f"Both properties not found: primary_id={request.primary_property_id}, secondary_id={request.secondary_property_id}"
        )
    elif not primary:
        raise HTTPException(
            status_code=404, 
            detail=f"Primary property not found: id={request.primary_property_id}"
        )
    elif not secondary:
        # 既に統合済みかチェック
        merge_history = db.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.merged_property_id == request.secondary_property_id
        ).first()
        
        if merge_history:
            raise HTTPException(
                status_code=400,
                detail=f"Secondary property (id={request.secondary_property_id}) has already been merged into property id={merge_history.primary_property_id}"
            )
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"Secondary property not found: id={request.secondary_property_id}"
            )
    
    # 二次物件の情報をバックアップ（取り消し用）
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
        "display_building_name": secondary.display_building_name,
        "created_at": secondary.created_at.isoformat() if secondary.created_at else None,
        "updated_at": secondary.updated_at.isoformat() if secondary.updated_at else None
    }
    
    # 掲載情報を移動
    listings_to_move = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == request.secondary_property_id
    ).all()
    
    moved_count = 0
    moved_listings_info = []
    for listing in listings_to_move:
        # 移動前の情報を記録
        moved_listings_info.append({
            "listing_id": listing.id,
            "source_site": listing.source_site,
            "url": listing.url
        })
        listing.master_property_id = request.primary_property_id
        moved_count += 1
    
    # 統合履歴を記録（詳細情報を含む）
    merge_history = PropertyMergeHistory(
        primary_property_id=request.primary_property_id,
        merged_property_id=request.secondary_property_id,
        merge_details={
            "secondary_property": secondary_backup,
            "moved_listings": moved_listings_info
        },
        merged_at=datetime.now(),
        merged_by="admin"
    )
    db.add(merge_history)
    
    # 変更を確実に反映させる
    db.flush()
    
    # 二次物件を削除
    db.delete(secondary)
    
    # 多数決で物件情報を更新
    updater = MajorityVoteUpdater(db)
    primary_property = db.query(MasterProperty).filter(
        MasterProperty.id == request.primary_property_id
    ).first()
    if primary_property:
        updater.update_master_property_by_majority(primary_property)
    
    db.commit()
    
    return {
        "message": "Properties merged successfully",
        "moved_listings": moved_count,
        "primary_property": {
            "id": primary.id,
            "building_id": primary.building_id,
            "floor": primary.floor_number,
            "layout": primary.layout
        }
    }


@router.post("/exclude-building-merge")
async def exclude_building_merge(
    building1_id: int,
    building2_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """建物の統合を除外設定に追加"""
    
    # 既存の除外設定をチェック
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
        raise HTTPException(status_code=400, detail="Exclusion already exists")
    
    # 除外設定を追加
    exclusion = BuildingMergeExclusion(
        building1_id=min(building1_id, building2_id),
        building2_id=max(building1_id, building2_id),
        reason=reason,
        created_at=datetime.now(),
        created_by="admin"
    )
    db.add(exclusion)
    db.commit()
    
    return {"message": "Exclusion added successfully"}


@router.post("/exclude-property-merge")
async def exclude_property_merge(
    property1_id: int,
    property2_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """物件の統合を除外設定に追加"""
    
    # 既存の除外設定をチェック
    existing = db.query(PropertyMergeExclusion).filter(
        or_(
            and_(
                PropertyMergeExclusion.property1_id == property1_id,
                PropertyMergeExclusion.property2_id == property2_id
            ),
            and_(
                PropertyMergeExclusion.property1_id == property2_id,
                PropertyMergeExclusion.property2_id == property1_id
            )
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Exclusion already exists")
    
    # 除外設定を追加
    exclusion = PropertyMergeExclusion(
        property1_id=min(property1_id, property2_id),
        property2_id=max(property1_id, property2_id),
        reason=reason,
        created_at=datetime.now(),
        created_by="admin"
    )
    db.add(exclusion)
    db.commit()
    
    return {"message": "Exclusion added successfully"}