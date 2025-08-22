"""
物件関連のユーティリティ関数
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.models import MasterProperty, PropertyListing
import logging

logger = logging.getLogger(__name__)

def update_earliest_listing_date(db: Session, master_property_id: int):
    """
    指定された物件の最初の掲載日を更新
    
    Args:
        db: データベースセッション
        master_property_id: 更新する物件のID
    """
    try:
        # すべての掲載情報の中で最も古い掲載日を取得
        # first_published_at > published_at > first_seen_at > created_at の優先順位で最も古い日付を選択
        from sqlalchemy import case
        
        # 各掲載の最も信頼できる日付を取得
        effective_date = case(
            (PropertyListing.first_published_at.isnot(None), PropertyListing.first_published_at),
            (PropertyListing.published_at.isnot(None), PropertyListing.published_at),
            (PropertyListing.first_seen_at.isnot(None), PropertyListing.first_seen_at),
            else_=PropertyListing.created_at
        )
        
        # 最も古い日付を取得
        earliest_date = db.query(func.min(effective_date))\
            .filter(PropertyListing.master_property_id == master_property_id)\
            .scalar()
        
        # MasterPropertyを更新
        master_property = db.query(MasterProperty).filter(MasterProperty.id == master_property_id).first()
        if master_property:
            master_property.earliest_listing_date = earliest_date
            logger.debug(f"Updated earliest_listing_date for property {master_property_id}: {earliest_date}")
        
    except Exception as e:
        logger.error(f"Error updating earliest_listing_date for property {master_property_id}: {e}")
        # エラーが発生しても処理を継続（最適化機能なので致命的ではない）

def update_latest_price_change(db: Session, master_property_id: int):
    """
    指定された物件の最新価格改定日を更新
    いずれかの掲載で価格変更があった最新日時を記録（概算値）
    
    Args:
        db: データベースセッション
        master_property_id: 更新する物件のID
    """
    try:
        from sqlalchemy import text
        
        # アクティブな掲載の価格履歴から最新の価格変更日を取得
        query = text("""
            SELECT MAX(lph.recorded_at) as latest_change
            FROM listing_price_history lph
            JOIN property_listings pl ON pl.id = lph.property_listing_id
            WHERE pl.master_property_id = :property_id
            AND pl.is_active = true
            AND EXISTS (
                SELECT 1 FROM listing_price_history prev
                WHERE prev.property_listing_id = lph.property_listing_id
                AND prev.recorded_at < lph.recorded_at
                AND prev.price != lph.price
            )
        """)
        
        latest_change = db.execute(query, {'property_id': master_property_id}).scalar()
        
        # MasterPropertyを更新
        master_property = db.query(MasterProperty).filter(MasterProperty.id == master_property_id).first()
        if master_property:
            master_property.latest_price_change_at = latest_change
            logger.debug(f"Updated latest_price_change_at for property {master_property_id}: {latest_change}")
        
    except Exception as e:
        logger.error(f"Error updating latest_price_change for property {master_property_id}: {e}")
        # エラーが発生しても処理を継続（最適化機能なので致命的ではない）