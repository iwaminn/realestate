"""
価格改定履歴の計算と管理
"""

import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Set
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from ..models import (
    PropertyPriceChange,
    PropertyPriceChangeQueue,
    MasterProperty,
    PropertyListing,
    ListingPriceHistory
)

logger = logging.getLogger(__name__)


class PriceChangeCalculator:
    """価格改定履歴を計算・管理するクラス"""
    
    def __init__(self, db: Session):
        self.db = db
        
    def add_to_queue(self, master_property_id: int, reason: str, priority: int = 0) -> bool:
        """
        物件を再計算キューに追加
        
        Args:
            master_property_id: 物件ID
            reason: キューに追加する理由
            priority: 優先度（0が最高）
            
        Returns:
            追加に成功した場合True
        """
        try:
            # 既存のpendingステータスのキューがないか確認
            existing = self.db.query(PropertyPriceChangeQueue).filter(
                PropertyPriceChangeQueue.master_property_id == master_property_id,
                PropertyPriceChangeQueue.status == 'pending'
            ).first()
            
            if existing:
                # 既存のキューがある場合は優先度を更新
                if existing.priority > priority:
                    existing.priority = priority
                    existing.reason = reason
                    existing.updated_at = datetime.now()
                    self.db.commit()
                return True
            
            # 新規追加
            queue_item = PropertyPriceChangeQueue(
                master_property_id=master_property_id,
                reason=reason,
                priority=priority,
                status='pending'
            )
            self.db.add(queue_item)
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"キューへの追加に失敗: {e}")
            self.db.rollback()
            return False
    
    def add_multiple_to_queue(self, master_property_ids: List[int], reason: str, priority: int = 0) -> int:
        """
        複数の物件を再計算キューに追加
        
        Args:
            master_property_ids: 物件IDのリスト
            reason: キューに追加する理由
            priority: 優先度
            
        Returns:
            追加された件数
        """
        count = 0
        for property_id in master_property_ids:
            if self.add_to_queue(property_id, reason, priority):
                count += 1
        return count
    
    def calculate_price_changes(self, master_property_id: int, start_date: Optional[date] = None) -> List[Dict]:
        """
        物件の価格改定履歴を計算
        
        Args:
            master_property_id: 物件ID
            start_date: 計算開始日（Noneの場合は全期間）
            
        Returns:
            価格改定履歴のリスト
        """
        # SQLクエリで多数決ベースの価格変更を計算
        query = text("""
            WITH listing_prices_expanded AS (
                -- 各掲載の価格を日付ごとに展開
                SELECT DISTINCT
                    pl.master_property_id,
                    pl.id as listing_id,
                    dates.price_date,
                    COALESCE(
                        lph_today.price,
                        -- その日の記録がない場合は、直近の価格を使用
                        (SELECT price FROM listing_price_history lph_prev
                         WHERE lph_prev.property_listing_id = pl.id
                           AND DATE(lph_prev.recorded_at) < dates.price_date
                         ORDER BY lph_prev.recorded_at DESC
                         LIMIT 1),
                        pl.current_price
                    ) as price
                FROM property_listings pl
                CROSS JOIN (
                    -- 対象期間内のすべての日付を生成
                    SELECT DISTINCT DATE(lph.recorded_at) as price_date
                    FROM listing_price_history lph
                    JOIN property_listings pl2 ON pl2.id = lph.property_listing_id
                    WHERE pl2.master_property_id = :master_property_id
                      AND (:start_date IS NULL OR DATE(lph.recorded_at) >= :start_date)
                ) dates
                LEFT JOIN listing_price_history lph_today 
                    ON lph_today.property_listing_id = pl.id 
                    AND DATE(lph_today.recorded_at) = dates.price_date
                WHERE pl.master_property_id = :master_property_id
            ),
            daily_majority_prices AS (
                -- 各日付の多数決価格を計算
                SELECT 
                    price_date,
                    price,
                    COUNT(*) as vote_count
                FROM listing_prices_expanded
                WHERE price IS NOT NULL
                GROUP BY price_date, price
            ),
            daily_majority AS (
                -- 各日付の最終的な多数決価格を決定
                SELECT DISTINCT ON (price_date)
                    price_date,
                    price as majority_price,
                    vote_count
                FROM daily_majority_prices
                ORDER BY price_date, vote_count DESC, price ASC
            ),
            price_changes AS (
                -- 価格変動を検出
                SELECT 
                    dm1.price_date as change_date,
                    dm1.majority_price as new_price,
                    dm1.vote_count as new_price_votes,
                    dm2.majority_price as old_price,
                    dm2.vote_count as old_price_votes
                FROM daily_majority dm1
                LEFT JOIN LATERAL (
                    SELECT majority_price, vote_count
                    FROM daily_majority dm2
                    WHERE dm2.price_date < dm1.price_date
                    ORDER BY dm2.price_date DESC
                    LIMIT 1
                ) dm2 ON true
                WHERE dm2.majority_price IS NOT NULL
                  AND dm1.majority_price != dm2.majority_price
            )
            SELECT 
                change_date,
                new_price,
                old_price,
                new_price - old_price as price_diff,
                CASE 
                    WHEN old_price > 0 THEN 
                        ROUND(((new_price - old_price)::numeric / old_price * 100), 2)
                    ELSE 0
                END as price_diff_rate,
                new_price_votes,
                old_price_votes
            FROM price_changes
            ORDER BY change_date
        """)
        
        result = self.db.execute(query, {
            'master_property_id': master_property_id,
            'start_date': start_date
        }).fetchall()
        
        changes = []
        for row in result:
            changes.append({
                'change_date': row[0],
                'new_price': row[1],
                'old_price': row[2],
                'price_diff': row[3],
                'price_diff_rate': row[4],
                'new_price_votes': row[5],
                'old_price_votes': row[6]
            })
        
        return changes
    
    def save_price_changes(self, master_property_id: int, changes: List[Dict]) -> int:
        """
        価格改定履歴をデータベースに保存
        
        Args:
            master_property_id: 物件ID
            changes: 価格改定履歴のリスト
            
        Returns:
            保存された件数
        """
        if not changes:
            return 0
        
        try:
            # 既存のデータを削除（UPSERT的な処理）
            change_dates = [c['change_date'] for c in changes]
            self.db.query(PropertyPriceChange).filter(
                PropertyPriceChange.master_property_id == master_property_id,
                PropertyPriceChange.change_date.in_(change_dates)
            ).delete(synchronize_session=False)
            
            # 新しいデータを挿入
            for change in changes:
                price_change = PropertyPriceChange(
                    master_property_id=master_property_id,
                    change_date=change['change_date'],
                    new_price=change['new_price'],
                    old_price=change['old_price'],
                    price_diff=change['price_diff'],
                    price_diff_rate=change['price_diff_rate'],
                    new_price_votes=change['new_price_votes'],
                    old_price_votes=change['old_price_votes']
                )
                self.db.add(price_change)
            
            self.db.commit()
            return len(changes)
            
        except Exception as e:
            logger.error(f"価格改定履歴の保存に失敗: {e}")
            self.db.rollback()
            return 0
    
    def process_queue(self, limit: int = 100) -> Dict[str, int]:
        """
        キューに入っている物件の価格改定履歴を処理
        
        Args:
            limit: 一度に処理する最大件数
            
        Returns:
            処理結果の統計
        """
        stats = {
            'processed': 0,
            'failed': 0,
            'changes_found': 0
        }
        
        # 優先度順にキューを取得
        queue_items = self.db.query(PropertyPriceChangeQueue).filter(
            PropertyPriceChangeQueue.status == 'pending'
        ).order_by(
            PropertyPriceChangeQueue.priority,
            PropertyPriceChangeQueue.created_at
        ).limit(limit).all()
        
        for item in queue_items:
            try:
                # ステータスを処理中に更新
                item.status = 'processing'
                self.db.commit()
                
                # 価格改定履歴を計算
                changes = self.calculate_price_changes(item.master_property_id)
                
                # 保存
                saved_count = self.save_price_changes(item.master_property_id, changes)
                
                # キューを完了に更新
                item.status = 'completed'
                item.processed_at = datetime.now()
                self.db.commit()
                
                stats['processed'] += 1
                stats['changes_found'] += saved_count
                
            except Exception as e:
                logger.error(f"物件 {item.master_property_id} の処理に失敗: {e}")
                item.status = 'failed'
                item.error_message = str(e)
                self.db.commit()
                stats['failed'] += 1
        
        return stats
    
    def refresh_all_recent_changes(self, days: int = 90) -> Dict[str, int]:
        """
        全物件の最近の価格改定履歴を更新
        
        Args:
            days: 更新対象期間（日数）
            
        Returns:
            処理結果の統計
        """
        start_date = date.today() - timedelta(days=days)
        
        # アクティブな物件を取得
        active_properties = self.db.query(MasterProperty.id).join(
            PropertyListing,
            PropertyListing.master_property_id == MasterProperty.id
        ).filter(
            PropertyListing.is_active == True,
            MasterProperty.sold_at.is_(None)
        ).distinct().all()
        
        stats = {
            'total': len(active_properties),
            'processed': 0,
            'changes_found': 0
        }
        
        for (property_id,) in active_properties:
            try:
                # キューに入っている物件は全期間を再計算
                queued = self.db.query(PropertyPriceChangeQueue).filter(
                    PropertyPriceChangeQueue.master_property_id == property_id,
                    PropertyPriceChangeQueue.status == 'pending'
                ).first()
                
                if queued:
                    # キューに入っている場合は全期間
                    changes = self.calculate_price_changes(property_id)
                else:
                    # キューに入っていない場合は指定期間のみ
                    changes = self.calculate_price_changes(property_id, start_date)
                
                saved_count = self.save_price_changes(property_id, changes)
                
                stats['processed'] += 1
                stats['changes_found'] += saved_count
                
                # キューから削除
                if queued:
                    queued.status = 'completed'
                    queued.processed_at = datetime.now()
                    self.db.commit()
                
            except Exception as e:
                logger.error(f"物件 {property_id} の処理に失敗: {e}")
        
        return stats
    
    def get_recent_changes(self, hours: int = 24, ward: Optional[str] = None) -> List[Dict]:
        """
        最近の価格改定を取得（キャッシュテーブルから）
        
        Args:
            hours: 対象時間
            ward: 区でフィルタリング（オプション）
            
        Returns:
            価格改定のリスト
        """
        cutoff_date = date.today() - timedelta(hours=hours/24)
        
        query = self.db.query(
            PropertyPriceChange,
            MasterProperty,
            func.max(PropertyListing.title).label('title'),
            func.max(PropertyListing.url).label('url'),
            func.max(PropertyListing.source_site).label('source_site')
        ).join(
            MasterProperty,
            MasterProperty.id == PropertyPriceChange.master_property_id
        ).join(
            PropertyListing,
            PropertyListing.master_property_id == MasterProperty.id
        ).filter(
            PropertyPriceChange.change_date >= cutoff_date,
            PropertyListing.is_active == True
        ).group_by(
            PropertyPriceChange.id,
            MasterProperty.id
        )
        
        if ward:
            from ..models import Building
            query = query.join(
                Building,
                Building.id == MasterProperty.building_id
            ).filter(
                Building.address.ilike(f'%{ward}%')
            )
        
        results = query.all()
        
        changes = []
        for price_change, property, title, url, source in results:
            changes.append({
                'id': property.id,
                'change_date': price_change.change_date,
                'new_price': price_change.new_price,
                'old_price': price_change.old_price,
                'price_diff': price_change.price_diff,
                'price_diff_rate': price_change.price_diff_rate,
                'title': title,
                'url': url,
                'source_site': source,
                # その他の必要な属性
            })
        
        return changes