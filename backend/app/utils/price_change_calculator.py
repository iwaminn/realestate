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
        物件の価格改定履歴を計算（改善版）
        
        主な改善点：
        1. 連続した日付範囲を生成して、記録がない日も含める
        2. すべての掲載を対象とする（非掲載も含む）
        3. 最新の状態（今日）も含めて価格変更を検出
        
        Args:
            master_property_id: 物件ID
            start_date: 計算開始日（Noneの場合は最初の掲載日から）
            
        Returns:
            価格改定履歴のリスト
        """
        # まず対象物件の掲載期間を取得
        period_query = text("""
            SELECT 
                MIN(DATE(COALESCE(
                    (SELECT MIN(recorded_at) FROM listing_price_history
                     WHERE property_listing_id = pl.id),
                    pl.first_seen_at,
                    pl.created_at
                ))) as start_date,
                CURRENT_DATE as end_date
            FROM property_listings pl
            WHERE pl.master_property_id = :master_property_id
        """)
        
        period = self.db.execute(period_query, {'master_property_id': master_property_id}).fetchone()
        
        if not period or not period[0]:
            logger.warning(f"物件ID {master_property_id} の有効な掲載が見つかりません")
            return []
        
        calc_start_date = start_date or period[0]
        calc_end_date = period[1]
        
        # 改善されたSQL クエリ
        query = text("""
            WITH date_range AS (
                -- 連続した日付範囲を生成（記録がない日も含める）
                SELECT generate_series(
                    CAST(:start_date AS date),
                    CAST(:end_date AS date),
                    '1 day'::interval
                )::date as price_date
            ),
            all_listings AS (
                -- すべての掲載を対象とする（非掲載も含む）
                SELECT * FROM property_listings
                WHERE master_property_id = :master_property_id
            ),
            listing_prices_expanded AS (
                -- 各掲載の価格を日付ごとに展開（掲載の有効期間のみ）
                SELECT DISTINCT
                    al.master_property_id,
                    al.id as listing_id,
                    dr.price_date,
                    COALESCE(
                        -- その日の価格履歴
                        (SELECT price FROM listing_price_history
                         WHERE property_listing_id = al.id
                           AND DATE(recorded_at) = dr.price_date
                         ORDER BY recorded_at DESC
                         LIMIT 1),
                        -- なければ直前の価格
                        (SELECT price FROM listing_price_history
                         WHERE property_listing_id = al.id
                           AND DATE(recorded_at) < dr.price_date
                         ORDER BY recorded_at DESC
                         LIMIT 1),
                        -- それもなければ現在価格（最新の状態）
                        al.current_price
                    ) as price
                FROM all_listings al
                CROSS JOIN date_range dr
                WHERE 
                    -- 掲載の有効期間内のみ
                    dr.price_date >= DATE(COALESCE(al.first_published_at, al.first_seen_at, al.created_at))
                    AND (
                        al.is_active = true  -- アクティブな掲載は現在まで有効
                        OR dr.price_date <= DATE(COALESCE(al.delisted_at, al.last_confirmed_at))  -- 非アクティブな掲載は終了日まで
                    )
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
                ORDER BY price_date, vote_count DESC, price ASC  -- 同票の場合は最低価格
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
            'start_date': calc_start_date,
            'end_date': calc_end_date
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
        
        logger.info(f"物件ID {master_property_id}: {len(changes)}件の価格変更を検出")
        
        return changes
    
    def save_price_changes(self, master_property_id: int, changes: List[Dict]) -> int:
        """
        価格改定履歴をデータベースに保存
        
        重要な改善：
        - 指定物件の既存の履歴をすべて削除してから新規作成
        - これにより誤った日付の履歴も適切に削除される
        
        Args:
            master_property_id: 物件ID
            changes: 価格改定履歴のリスト
            
        Returns:
            保存された件数
        """
        try:
            # 既存のデータをすべて削除（誤った履歴も含めて完全にリセット）
            self.db.query(PropertyPriceChange).filter(
                PropertyPriceChange.master_property_id == master_property_id
            ).delete(synchronize_session=False)
            
            if not changes:
                self.db.commit()
                return 0
            
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
            logger.info(f"物件ID {master_property_id}: {len(changes)}件の価格改定履歴を保存（既存履歴は削除）")
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