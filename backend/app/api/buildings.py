"""建物関連のAPIエンドポイント"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, distinct, case, asc, desc

from ..database import get_db
from ..models import Building, MasterProperty, PropertyListing
from ..schemas.building import BuildingSchema

router = APIRouter(prefix="/api", tags=["buildings"])

@router.get("/areas", response_model=List[Dict[str, Any]])
async def get_areas(db: Session = Depends(get_db)):
    """物件が存在する区の一覧を取得"""
    # 住所から区名を抽出し、物件数をカウント
    query = db.query(
        func.substring(Building.address, r'東京都([^区]+区)').label('ward'),
        func.count(distinct(MasterProperty.id)).label('property_count')
    ).join(
        MasterProperty, Building.id == MasterProperty.building_id
    ).filter(
        Building.address.like('東京都%'),
        Building.address.isnot(None)
    ).group_by(
        func.substring(Building.address, r'東京都([^区]+区)')
    ).having(
        func.substring(Building.address, r'東京都([^区]+区)').isnot(None)
    ).order_by(
        'ward'
    )
    
    results = query.all()
    
    # area_config.pyの定義も含めて返す
    from ..scrapers.area_config import TOKYO_AREA_CODES
    
    # 地価順の並び（辞書の順序を保持するため、Python 3.7+で有効）
    area_order = list(TOKYO_AREA_CODES.keys())
    
    area_list = []
    for ward, property_count in results:
        if ward:
            # 区コードを取得
            area_code = TOKYO_AREA_CODES.get(ward, None)
            area_list.append({
                "name": ward,
                "code": area_code,
                "property_count": property_count
            })
    
    # 地価順でソート（TOKYO_AREA_CODESの定義順）
    area_list.sort(key=lambda x: area_order.index(x["name"]) if x["name"] in area_order else 999)
    
    return area_list

@router.get("/buildings", response_model=Dict[str, Any])
async def get_buildings(
    wards: Optional[List[str]] = Query(None, description="区名リスト（例: 港区、中央区）"),
    search: Optional[str] = Query(None, description="建物名検索"),
    min_price: Optional[int] = Query(None, description="最低価格（万円）"),
    max_price: Optional[int] = Query(None, description="最高価格（万円）"),
    max_building_age: Optional[int] = Query(None, description="築年数以内"),
    min_total_floors: Optional[int] = Query(None, description="最低階数"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(20, ge=1, le=100, description="1ページあたりの件数"),
    sort_by: str = Query("property_count", description="ソート項目"),
    sort_order: str = Query("desc", description="ソート順序"),
    db: Session = Depends(get_db)
):
    """建物一覧を取得（物件集計情報付き）"""
    
    # 各建物の物件統計を取得するサブクエリ
    property_stats = db.query(
        MasterProperty.building_id,
        func.count(distinct(MasterProperty.id)).label('property_count'),
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.avg(PropertyListing.current_price).label('avg_price'),
        func.count(distinct(PropertyListing.id)).label('total_listings'),
        func.sum(case((PropertyListing.is_active == True, 1), else_=0)).label('active_listings')
    ).join(
        PropertyListing, MasterProperty.id == PropertyListing.master_property_id
    ).filter(
        PropertyListing.is_active == True  # アクティブな掲載のみ
    ).group_by(
        MasterProperty.building_id
    ).subquery()
    
    # メインクエリ
    query = db.query(
        Building,
        property_stats.c.property_count,
        property_stats.c.min_price,
        property_stats.c.max_price,
        property_stats.c.avg_price,
        property_stats.c.total_listings,
        property_stats.c.active_listings
    ).outerjoin(
        property_stats, Building.id == property_stats.c.building_id
    )
    
    # アクティブな物件がある建物のみ表示
    query = query.filter(property_stats.c.property_count > 0)
    
    # フィルター条件
    if wards:
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.like(f'%{ward}%'))
        query = query.filter(or_(*ward_conditions))
    
    if search:
        # ひらがなをカタカナに変換してから検索
        from ..utils.search_normalizer import normalize_search_text, create_search_patterns
        from ..models import BuildingListingName
        from ..scrapers.data_normalizer import canonicalize_building_name
        
        # 検索語を正規化（ひらがな→カタカナ変換）
        normalized_search = normalize_search_text(search)
        search_terms = normalized_search.split()
        
        # canonicalで検索
        canonical_search = canonicalize_building_name(search)
        
        # BuildingListingNameから該当する建物IDを取得
        listing_building_ids = db.query(BuildingListingName.building_id).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_search}%")
        ).distinct().subquery()
        
        # 検索パターンを生成
        search_patterns = create_search_patterns(search)
        
        # 複数のパターンで検索
        search_conditions = []
        for pattern in search_patterns[:3]:  # 最初の3パターンを使用
            search_conditions.append(Building.normalized_name.ilike(f"%{pattern}%"))
        
        # BuildingListingNameの建物IDも含める
        search_conditions.append(Building.id.in_(listing_building_ids))
        
        query = query.filter(or_(*search_conditions))
    
    if min_price:
        query = query.filter(property_stats.c.min_price >= min_price)
    
    if max_price:
        query = query.filter(property_stats.c.max_price <= max_price)
    
    if max_building_age:
        min_year = datetime.now().year - max_building_age
        query = query.filter(Building.built_year >= min_year)
    
    if min_total_floors:
        query = query.filter(Building.total_floors >= min_total_floors)
    
    # ソート
    if sort_by == "property_count":
        order_column = property_stats.c.property_count
    elif sort_by == "min_price":
        order_column = property_stats.c.min_price
    elif sort_by == "max_price":
        order_column = property_stats.c.max_price
    elif sort_by == "built_year":
        order_column = Building.built_year
    elif sort_by == "total_floors":
        order_column = Building.total_floors
    elif sort_by == "name":
        order_column = Building.normalized_name
    else:
        order_column = property_stats.c.property_count
    
    if sort_order == "asc":
        query = query.order_by(asc(order_column))
    else:
        query = query.order_by(desc(order_column))
    
    # ページネーション
    total = query.count()
    offset = (page - 1) * per_page
    buildings = query.offset(offset).limit(per_page).all()
    
    # レスポンス形式に変換
    result = []
    for building, property_count, min_price, max_price, avg_price, total_listings, active_listings in buildings:
        result.append({
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "built_year": building.built_year,
            "built_month": building.built_month,
            "construction_type": building.construction_type,
            "station_info": building.station_info,
            "property_count": property_count or 0,
            "active_listings": active_listings or 0,
            "price_range": {
                "min": min_price,
                "max": max_price,
                "avg": int(avg_price) if avg_price else None
            },
            "building_age": datetime.now().year - building.built_year if building.built_year else None
        })
    
    return {
        "buildings": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }

@router.get("/buildings/{building_id}/properties", response_model=Dict[str, Any])
async def get_building_properties(
    building_id: int,
    include_inactive: bool = Query(False, description="削除済み物件も含む"),
    db: Session = Depends(get_db)
):
    """特定の建物内の物件一覧を取得"""
    
    # 建物が存在するか確認
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="建物が見つかりません")
    
    # 価格の多数決を計算するサブクエリ
    from ..utils.price_queries import create_majority_price_subquery, create_price_stats_subquery, get_sold_property_final_price
    
    majority_price_query = create_majority_price_subquery(db, include_inactive)
    price_subquery = create_price_stats_subquery(db, majority_price_query, include_inactive)
    
    # 物件取得クエリ
    query = db.query(
        MasterProperty,
        price_subquery.c.min_price,
        price_subquery.c.max_price,
        price_subquery.c.majority_price,
        price_subquery.c.listing_count,
        price_subquery.c.source_sites,
        price_subquery.c.has_active_listing,
        price_subquery.c.last_confirmed_at,
        price_subquery.c.delisted_at,
        price_subquery.c.station_info,
        price_subquery.c.earliest_published_at
    ).filter(
        MasterProperty.building_id == building_id
    ).outerjoin(
        price_subquery, MasterProperty.id == price_subquery.c.master_property_id
    )
    
    # アクティブフィルタ
    if not include_inactive:
        query = query.filter(MasterProperty.sold_at.is_(None))
        query = query.filter(price_subquery.c.master_property_id.isnot(None))
    
    # 階数でソート
    query = query.order_by(
        MasterProperty.floor_number.desc().nullslast(),
        MasterProperty.room_number.asc().nullslast()
    )
    
    results = query.all()
    
    # 結果を整形
    properties = []
    for mp, min_price, max_price, majority_price, listing_count, source_sites, has_active, last_confirmed, delisted, station_info, earliest_published_at in results:
        # 販売終了物件の価格を計算
        if mp.sold_at:
            final_price = get_sold_property_final_price(db, mp)
            display_price = final_price
        else:
            display_price = majority_price
            final_price = None
        
        properties.append({
            "id": mp.id,
            "room_number": mp.room_number,
            "floor_number": mp.floor_number,
            "area": mp.area,
            "balcony_area": mp.balcony_area,
            "layout": mp.layout,
            "direction": mp.direction,
            "min_price": min_price if not mp.sold_at else display_price,
            "max_price": max_price if not mp.sold_at else display_price,
            "majority_price": display_price,
            "listing_count": listing_count,
            "source_sites": source_sites.split(',') if source_sites else [],
            "has_active_listing": has_active,
            "last_confirmed_at": str(last_confirmed) if last_confirmed else None,
            "delisted_at": str(delisted) if delisted else None,
            "station_info": mp.station_info if mp.station_info else station_info,
            "management_fee": mp.management_fee,
            "repair_fund": mp.repair_fund,
            "earliest_published_at": earliest_published_at,
            "sold_at": mp.sold_at.isoformat() if mp.sold_at else None,
            "final_price": mp.final_price
        })
    
    return {
        "building": {
            "id": building.id,
            "normalized_name": building.normalized_name,
            "address": building.address,
            "total_floors": building.total_floors,
            "total_units": building.total_units,  # 総戸数を追加
            "built_year": building.built_year,
            "built_month": building.built_month,
            "construction_type": building.construction_type,
            "station_info": building.station_info
        },
        "properties": properties,
        "total": len(properties)
    }

@router.get("/buildings/suggest")
async def suggest_buildings(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(10, ge=1, le=50, description="最大候補数"),
    db: Session = Depends(get_db)
):
    """建物名のサジェスト（インクリメンタルサーチ）- 掲載情報ベース"""
    from typing import Dict, List, Union
    from ..models import BuildingListingName
    
    if len(q) < 1:
        return []
    
    # 結果を格納する辞書（building_id -> 情報）
    building_info: Dict[int, Dict[str, Union[str, List[str]]]] = {}
    
    # スペース区切りでAND検索対応（ひらがな→カタカナ変換）
    from ..utils.search_normalizer import normalize_search_text
    from ..scrapers.data_normalizer import canonicalize_building_name
    
    # 検索語を正規化（ひらがな→カタカナ変換）
    normalized_q = normalize_search_text(q)
    search_terms = normalized_q.split()
    
    # canonical形式も生成
    canonical_q = canonicalize_building_name(q)
    
    # 1. 建物名で直接検索（AND条件）
    query = db.query(Building)
    for term in search_terms:
        if term:  # 空文字列をスキップ
            query = query.filter(Building.normalized_name.ilike(f"%{term}%"))
    direct_matches = query.all()
    
    for building in direct_matches:
        building_info[building.id] = {
            "name": building.normalized_name,
            "matched_by": "name"
        }
    
    # 2. 読み仮名で検索（AND条件）
    query = db.query(Building)
    for term in search_terms:
        if term:  # 空文字列をスキップ
            query = query.filter(Building.reading.ilike(f"%{term}%"))
    reading_matches = query.all()
    
    for building in reading_matches:
        if building.id not in building_info:
            building_info[building.id] = {
                "name": building.normalized_name,
                "matched_by": "reading"
            }
    
    # 3. 掲載情報の建物名から検索（各掲載名に対して全検索語がAND条件で含まれるものを検索）
    listing_matches = []
    
    if len(search_terms) > 1:
        # 複数の検索語がある場合：各掲載名に全ての検索語が含まれるものを探す
        # canonical形式の検索語リストを作成
        canonical_terms = [canonicalize_building_name(term) for term in search_terms if term]
        
        # まず最初の検索語で絞り込み
        first_term = search_terms[0]
        first_canonical = canonical_terms[0]
        query = db.query(
            BuildingListingName.building_id,
            BuildingListingName.listing_name,
            BuildingListingName.canonical_name,
            func.max(BuildingListingName.occurrence_count).label('max_count')
        ).filter(
            or_(
                BuildingListingName.listing_name.ilike(f"%{first_term}%"),
                BuildingListingName.canonical_name.ilike(f"%{first_canonical}%")
            )
        ).group_by(
            BuildingListingName.building_id,
            BuildingListingName.listing_name,
            BuildingListingName.canonical_name
        )
        
        candidates = query.all()
        
        # 残りの検索語でフィルタリング
        for listing in candidates:
            listing_name_lower = listing.listing_name.lower() if listing.listing_name else ""
            canonical_name = listing.canonical_name if listing.canonical_name else ""
            
            # 全ての検索語が含まれているかチェック
            all_terms_match = True
            for i, term in enumerate(search_terms[1:], 1):  # 2番目以降の検索語
                if term:  # 空文字列をスキップ
                    term_lower = term.lower()
                    canonical_term = canonical_terms[i]
                    # 通常の名前またはcanonical名のいずれかで各検索語がマッチするか
                    if not (term_lower in listing_name_lower or canonical_term in canonical_name):
                        all_terms_match = False
                        break
            
            if all_terms_match:
                listing_matches.append(listing)
    else:
        # 単一の検索語の場合：従来通りの検索
        canonical_q = canonicalize_building_name(q)
        query = db.query(
            BuildingListingName.building_id,
            BuildingListingName.listing_name,
            func.max(BuildingListingName.occurrence_count).label('max_count')
        ).filter(
            or_(
                BuildingListingName.listing_name.ilike(f"%{q}%"),
                BuildingListingName.canonical_name.ilike(f"%{canonical_q}%")
            )
        ).group_by(
            BuildingListingName.building_id,
            BuildingListingName.listing_name
        )
        listing_matches = query.all()
    
    # 掲載名でマッチした建物の情報を取得
    for listing_match in listing_matches:
        building = db.query(Building).filter(
            Building.id == listing_match.building_id
        ).first()
        
        if building:
            if building.id not in building_info:
                building_info[building.id] = {
                    "name": building.normalized_name,
                    "matched_by": "listing",
                    "listing_name": listing_match.listing_name
                }
            elif building_info[building.id].get("matched_by") != "name":
                # 既に他の方法でマッチしていて、かつ名前マッチではない場合は掲載名情報を追加
                building_info[building.id]["listing_name"] = listing_match.listing_name
    
    # 建物名でグループ化して重複をチェック
    name_groups = {}
    for building_id, info in building_info.items():
        name = info["name"]
        if name not in name_groups:
            name_groups[name] = []
        name_groups[name].append((building_id, info))
    
    # 結果をリスト形式に変換（同名の建物は1つだけ表示）
    results = []
    seen_names = set()  # 既に追加した建物名を記録
    
    for name, buildings_list in name_groups.items():
        # 同名の建物がある場合も、最初の1つだけを採用
        building_id, info = buildings_list[0]
        if name not in seen_names:
            result_item = {
                "value": info["name"],
                "label": info["name"]
            }
            
            # 掲載名でマッチした場合でも、括弧内表示は不要
            # 既に正規化された建物名で表示しているため
            
            results.append(result_item)
            seen_names.add(name)
    
    # スコアリング関数：検索語の連結との一致度を計算
    def calculate_score(item):
        name = item["value"].lower()
        score = 0
        
        # 1. 検索語を連結した文字列との一致度をチェック
        # 例：「パーク タワー」→「パークタワー」
        if len(search_terms) > 1:
            # スペースを除去した検索語
            concatenated = ''.join(search_terms).lower()
            # 建物名からもスペースを除去
            name_no_space = name.replace(' ', '').replace('　', '')
            
            # 完全一致（最高スコア）
            if concatenated == name_no_space:
                score += 1000
            # 連結語での前方一致
            elif name_no_space.startswith(concatenated):
                score += 800
            # 連結語が含まれる
            elif concatenated in name_no_space:
                score += 600
                
        # 2. 元の検索文字列での前方一致
        if name.startswith(q.lower()):
            score += 500
            
        # 3. 最初の検索語での前方一致
        first_term = search_terms[0] if search_terms else q
        if name.startswith(first_term.lower()):
            score += 400
            
        # 4. すべての検索語が順番通りに出現するかチェック
        if len(search_terms) > 1:
            last_pos = -1
            all_in_order = True
            for term in search_terms:
                pos = name.find(term.lower())
                if pos == -1 or pos < last_pos:
                    all_in_order = False
                    break
                last_pos = pos
            if all_in_order:
                score += 300
                
        # 5. 文字列の長さによるペナルティ（短い方が優先）
        score -= len(name) * 0.1
        
        return score
    
    # スコアでソート（降順）
    results.sort(key=lambda item: calculate_score(item), reverse=True)
    
    # レガシー対応: 文字列のリストも返せるようにする
    # フロントエンドが新しい形式に対応するまでの暫定措置
    if limit <= 10:  # デフォルトの呼び出しの場合は新形式
        return results[:limit]
    else:  # 明示的に大きな limit が指定された場合は旧形式
        return [r["value"] for r in results[:limit]]