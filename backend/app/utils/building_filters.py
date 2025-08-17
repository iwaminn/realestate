"""建物検索の共通フィルタユーティリティ"""
from sqlalchemy.orm import Session, Query
from sqlalchemy import or_, and_
from typing import Optional, List
from datetime import datetime
from ..models import Building, BuildingMergeHistory, MasterProperty

def apply_building_name_filter(
    query: Query, 
    db: Session,
    building_name: Optional[str],
    building_table = Building
) -> Query:
    """
    建物名フィルタを適用（掲載情報の建物名を検索）
    
    Args:
        query: ベースクエリ
        db: データベースセッション
        building_name: 検索する建物名
        building_table: 建物テーブル（デフォルト: Building）
    
    Returns:
        フィルタ適用済みのクエリ
    """
    if not building_name:
        return query
    
    from ..models import BuildingListingName
    from ..scrapers.data_normalizer import canonicalize_building_name
    
    terms = building_name.split()
    for term in terms:
        # 検索語をcanonical形式に変換（ひらがな→カタカナ、記号除去、小文字化）
        canonical_term = canonicalize_building_name(term)
        
        # BuildingListingNameテーブルから該当する建物IDを取得
        # canonical_nameを使用して検索（ひらがな入力でも検索可能）
        listing_building_ids = db.query(
            BuildingListingName.building_id
        ).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_term}%")
        ).distinct().subquery()
        
        # Building.normalized_name または 掲載建物名でマッチ
        # normalized_nameに対してもcanonical化した検索語で検索
        from ..utils.search_normalizer import normalize_search_text
        normalized_term = normalize_search_text(term)
        
        query = query.filter(
            or_(
                building_table.normalized_name.ilike(f"%{normalized_term}%"),
                building_table.id.in_(listing_building_ids)
            )
        )
    
    return query

def apply_building_filters(
    query: Query,
    wards: Optional[List[str]] = None,
    max_building_age: Optional[int] = None,
    min_total_floors: Optional[int] = None,
    address: Optional[str] = None
) -> Query:
    """
    建物の基本的なフィルタを適用
    
    Args:
        query: ベースクエリ
        wards: 区名リスト
        max_building_age: 最大築年数
        min_total_floors: 最低階数
        address: 住所
    
    Returns:
        フィルタ適用済みのクエリ
    """
    if wards:
        ward_conditions = []
        for ward in wards:
            ward_conditions.append(Building.address.ilike(f"%{ward}%"))
        query = query.filter(or_(*ward_conditions))
    
    if max_building_age:
        min_year = datetime.now().year - max_building_age
        query = query.filter(Building.built_year >= min_year)
    
    if min_total_floors:
        query = query.filter(Building.total_floors >= min_total_floors)
    
    if address:
        query = query.filter(Building.address.ilike(f"%{address}%"))
    
    return query

def apply_property_filters(
    query: Query,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    layouts: Optional[List[str]] = None
) -> Query:
    """
    物件の基本的なフィルタを適用
    
    Args:
        query: ベースクエリ
        min_area: 最小面積
        max_area: 最大面積
        layouts: 間取りリスト
    
    Returns:
        フィルタ適用済みのクエリ
    """
    if min_area:
        query = query.filter(MasterProperty.area >= min_area)
    if max_area:
        query = query.filter(MasterProperty.area <= max_area)
    if layouts:
        query = query.filter(MasterProperty.layout.in_(layouts))
    
    return query