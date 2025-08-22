"""価格関連の共通クエリユーティリティ"""
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, distinct, String
from typing import Optional
from datetime import timedelta
from ..models import PropertyListing, MasterProperty

def create_majority_price_subquery(db: Session, include_inactive: bool = False):
    """
    価格の多数決を計算するサブクエリを生成
    
    Args:
        db: データベースセッション
        include_inactive: 非アクティブな掲載も含むか
    
    Returns:
        多数決価格を含むサブクエリ
    """
    # 価格の多数決を計算するサブクエリ
    price_vote_query = db.query(
        PropertyListing.master_property_id,
        PropertyListing.current_price,
        func.count(PropertyListing.id).label('vote_count')
    ).filter(
        PropertyListing.is_active == True if not include_inactive else True,
        PropertyListing.current_price.isnot(None)
    ).group_by(
        PropertyListing.master_property_id,
        PropertyListing.current_price
    ).subquery()
    
    # 多数決で最も多い価格を選択
    majority_price_query = db.query(
        price_vote_query.c.master_property_id,
        price_vote_query.c.current_price.label('majority_price'),
        func.row_number().over(
            partition_by=price_vote_query.c.master_property_id,
            order_by=[price_vote_query.c.vote_count.desc(), price_vote_query.c.current_price.asc()]
        ).label('rn')
    ).subquery()
    
    return majority_price_query

def create_price_stats_subquery(db: Session, majority_price_query, include_inactive: bool = False):
    """
    物件の価格統計情報を取得するサブクエリを生成
    
    Args:
        db: データベースセッション
        majority_price_query: 多数決価格のサブクエリ
        include_inactive: 非アクティブな掲載も含むか
    
    Returns:
        価格統計を含むサブクエリ
    """
    price_query = db.query(
        PropertyListing.master_property_id,
        func.min(PropertyListing.current_price).label('min_price'),
        func.max(PropertyListing.current_price).label('max_price'),
        func.max(majority_price_query.c.majority_price).label('majority_price'),
        func.count(distinct(PropertyListing.id)).label('listing_count'),
        func.string_agg(distinct(func.cast(PropertyListing.source_site, String)), ',').label('source_sites'),
        func.bool_or(PropertyListing.is_active).label('has_active_listing'),
        func.max(PropertyListing.last_confirmed_at).label('last_confirmed_at'),
        func.max(PropertyListing.delisted_at).label('delisted_at'),
        func.max(PropertyListing.station_info).label('station_info'),
        func.min(func.coalesce(
            PropertyListing.first_published_at, 
            PropertyListing.published_at, 
            PropertyListing.first_seen_at
        )).label('earliest_published_at'),
        func.coalesce(
            func.max(PropertyListing.price_updated_at),
            func.min(PropertyListing.published_at)
        ).label('latest_price_update'),
        func.bool_or(
            db.query(func.count(distinct(PropertyListing.id)))
            .filter(PropertyListing.master_property_id == PropertyListing.master_property_id)
            .scalar_subquery() > 1
        ).label('has_price_change')
    ).outerjoin(
        majority_price_query,
        and_(
            PropertyListing.master_property_id == majority_price_query.c.master_property_id,
            majority_price_query.c.rn == 1
        )
    )
    
    if not include_inactive:
        price_query = price_query.filter(PropertyListing.is_active == True)
    
    return price_query.group_by(
        PropertyListing.master_property_id,
        majority_price_query.c.majority_price
    ).subquery()

def apply_price_filter(query, price_subquery, min_price: Optional[int], max_price: Optional[int]):
    """
    価格フィルタを適用
    
    Args:
        query: ベースクエリ
        price_subquery: 価格サブクエリ
        min_price: 最低価格
        max_price: 最高価格
    
    Returns:
        フィルタ適用済みのクエリ
    """
    if min_price:
        query = query.filter(
            or_(
                price_subquery.c.min_price >= min_price,
                and_(
                    price_subquery.c.min_price.is_(None),
                    MasterProperty.final_price >= min_price
                )
            )
        )
    if max_price:
        query = query.filter(
            or_(
                price_subquery.c.max_price <= max_price,
                and_(
                    price_subquery.c.max_price.is_(None),
                    MasterProperty.final_price <= max_price
                )
            )
        )
    return query

def calculate_final_price_for_sold_property(db: Session, master_property_id: int) -> Optional[int]:
    """
    販売終了物件の最終価格を計算（販売終了前1週間の価格履歴から多数決）
    
    Args:
        db: データベースセッション
        master_property_id: マスター物件ID
    
    Returns:
        最終価格（万円）、データがない場合はNone
    """
    from datetime import timedelta
    from ..models import ListingPriceHistory
    
    # マスター物件を取得
    master_property = db.query(MasterProperty).filter(
        MasterProperty.id == master_property_id
    ).first()
    
    if not master_property or not master_property.sold_at:
        return None
    
    # 販売終了前1週間の期間を計算
    end_date = master_property.sold_at
    start_date = end_date - timedelta(days=7)
    
    # 期間内の価格履歴を取得（全掲載から）
    price_history = db.query(
        ListingPriceHistory.price,
        func.count(ListingPriceHistory.id).label('count')
    ).join(
        PropertyListing,
        ListingPriceHistory.property_listing_id == PropertyListing.id
    ).filter(
        PropertyListing.master_property_id == master_property_id,
        ListingPriceHistory.recorded_at >= start_date,
        ListingPriceHistory.recorded_at <= end_date,
        ListingPriceHistory.price.isnot(None)
    ).group_by(
        ListingPriceHistory.price
    ).order_by(
        func.count(ListingPriceHistory.id).desc(),
        ListingPriceHistory.price.desc()  # 同数の場合は高い方を優先
    ).first()
    
    if price_history:
        return price_history[0]
    
    # 1週間以内のデータがない場合は、販売終了時点の最新価格を取得
    latest_price = db.query(
        PropertyListing.current_price
    ).filter(
        PropertyListing.master_property_id == master_property_id,
        PropertyListing.current_price.isnot(None)
    ).order_by(
        PropertyListing.updated_at.desc()
    ).first()
    
    if latest_price:
        return latest_price[0]
    
    return None

def get_sold_property_final_price(db: Session, master_property: MasterProperty) -> Optional[int]:
    """
    販売終了物件の最終価格を取得（キャッシュ済みならそれを使用、なければ計算）
    
    Args:
        db: データベースセッション
        master_property: マスター物件オブジェクト
    
    Returns:
        最終価格（万円）
    """
    if not master_property.sold_at:
        return None
    
    # すでに final_price が設定されていればそれを返す
    if master_property.final_price:
        return master_property.final_price
    
    # 計算して更新
    final_price = calculate_final_price_for_sold_property(db, master_property.id)
    if final_price:
        master_property.final_price = final_price
        db.commit()
    
    return final_price
