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
    建物名フィルタを適用（エイリアス対応）
    
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
        
    from ..utils.search_normalizer import create_search_patterns
    
    terms = building_name.split()
    for term in terms:
        # エイリアスマッチした建物IDを取得
        alias_building_ids = db.query(
            BuildingMergeHistory.primary_building_id
        ).filter(
            or_(
                BuildingMergeHistory.merged_building_name.ilike(f"%{term}%"),
                BuildingMergeHistory.canonical_merged_name.ilike(f"%{term}%")
            )
        ).distinct().subquery()
        
        # Building.normalized_name または エイリアスでマッチ
        query = query.filter(
            or_(
                building_table.normalized_name.ilike(f"%{term}%"),
                building_table.id.in_(alias_building_ids)
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