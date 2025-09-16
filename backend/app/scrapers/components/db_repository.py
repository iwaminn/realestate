"""
データベースリポジトリコンポーネント

データベース操作を担当
- 物件の保存・更新
- 建物の保存・更新
- トランザクション管理
- 重複チェック
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import hashlib


class DbRepositoryComponent:
    """データベース操作を担当するコンポーネント"""
    
    def __init__(self, session: Session, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            session: SQLAlchemyセッション
            logger: ロガーインスタンス
        """
        self.session = session
        self.logger = logger or logging.getLogger(__name__)
    
    def find_or_create_building(self, building_data: Dict[str, Any]) -> Optional[Any]:
        """
        建物を検索または作成
        
        Args:
            building_data: 建物データ
            
        Returns:
            建物オブジェクト
        """
        from backend.app.models import Building
        
        # 必須フィールドチェック
        if not building_data.get('normalized_name'):
            self.logger.error("建物名が指定されていません")
            return None
        
        # 既存の建物を検索
        building = self.session.query(Building).filter_by(
            normalized_name=building_data['normalized_name'],
            address=building_data.get('address')
        ).first()
        
        if building:
            # 既存の建物を更新
            self._update_building(building, building_data)
            return building
        
        # 新規建物を作成
        try:
            building = Building(**building_data)
            self.session.add(building)
            self.session.flush()
            self.logger.info(f"新規建物を作成: {building_data['normalized_name']}")
            return building
        except Exception as e:
            self.logger.error(f"建物作成エラー: {e}")
            self.session.rollback()
            return None
    
    def _update_building(self, building: Any, data: Dict[str, Any]) -> None:
        """
        建物情報を更新
        
        Args:
            building: 建物オブジェクト
            data: 更新データ
        """
        update_fields = ['total_floors', 'built_year', 'built_month', 'structure']
        
        for field in update_fields:
            if field in data and data[field] is not None:
                if getattr(building, field) != data[field]:
                    setattr(building, field, data[field])
                    self.logger.debug(f"建物{field}を更新: {data[field]}")
    
    def find_master_property(self, property_hash: str) -> Optional[Any]:
        """
        マスター物件を検索
        
        Args:
            property_hash: 物件ハッシュ
            
        Returns:
            マスター物件オブジェクト
        """
        from backend.app.models import MasterProperty
        
        return self.session.query(MasterProperty).filter_by(
            property_hash=property_hash
        ).first()
    
    def create_master_property(self, property_data: Dict[str, Any]) -> Optional[Any]:
        """
        マスター物件を作成
        
        Args:
            property_data: 物件データ
            
        Returns:
            マスター物件オブジェクト
        """
        from backend.app.models import MasterProperty
        
        try:
            master_property = MasterProperty(**property_data)
            self.session.add(master_property)
            self.session.flush()
            self.logger.info(f"新規マスター物件を作成: {property_data.get('property_hash')}")
            return master_property
        except Exception as e:
            self.logger.error(f"マスター物件作成エラー: {e}")
            self.session.rollback()
            return None
    
    def update_master_property(self, master_property: Any, data: Dict[str, Any]) -> None:
        """
        マスター物件を更新
        
        Args:
            master_property: マスター物件オブジェクト
            data: 更新データ
        """
        update_fields = [
            'room_number', 'floor_number', 'area', 'layout',
            'direction', 'display_building_name'
        ]
        
        for field in update_fields:
            if field in data and data[field] is not None:
                current_value = getattr(master_property, field)
                new_value = data[field]
                
                # 値が変更された場合のみ更新
                if current_value != new_value:
                    setattr(master_property, field, new_value)
                    self.logger.debug(f"マスター物件{field}を更新: {current_value} → {new_value}")
    
    def find_or_create_listing(self, 
                              master_property_id: int,
                              source_site: str,
                              source_id: str) -> Tuple[Any, bool]:
        """
        掲載情報を検索または作成
        
        Args:
            master_property_id: マスター物件ID
            source_site: ソースサイト
            source_id: ソースID
            
        Returns:
            (掲載情報オブジェクト, 新規作成フラグ) のタプル
        """
        from backend.app.models import PropertyListing
        from backend.app.utils.datetime_utils import get_utc_now
        
        # 既存の掲載情報を検索
        listing = self.session.query(PropertyListing).filter_by(
            master_property_id=master_property_id,
            source_site=source_site,
            source_id=source_id
        ).first()
        
        if listing:
            return listing, False
        
        # 新規掲載情報を作成
        try:
            listing = PropertyListing(
                master_property_id=master_property_id,
                source_site=source_site,
                source_id=source_id,
                first_seen_at=get_utc_now(),
                last_seen_at=get_utc_now(),
                is_active=True
            )
            self.session.add(listing)
            self.session.flush()
            self.logger.info(f"新規掲載情報を作成: {source_site}/{source_id}")
            return listing, True
        except Exception as e:
            self.logger.error(f"掲載情報作成エラー: {e}")
            self.session.rollback()
            return None, False
    
    def update_listing(self, listing: Any, data: Dict[str, Any]) -> None:
        """
        掲載情報を更新
        
        Args:
            listing: 掲載情報オブジェクト
            data: 更新データ
        """
        from backend.app.utils.datetime_utils import get_utc_now
        
        # 更新可能フィールド
        update_fields = [
            'current_price', 'listing_building_name', 'url',
            'station_info', 'agency_name', 'agency_tel',
            'balcony_area', 'remarks', 'summary_remarks',
            'management_fee', 'repair_fund', 'transaction_mode',
            'floor_plan_url', 'is_active'
        ]
        
        for field in update_fields:
            if field in data and data[field] is not None:
                current_value = getattr(listing, field, None)
                new_value = data[field]
                
                if current_value != new_value:
                    setattr(listing, field, new_value)
                    self.logger.debug(f"掲載{field}を更新: {new_value}")
        
        # 最終確認日時を更新
        listing.last_seen_at = get_utc_now()
    
    def record_price_change(self, listing_id: int, 
                          old_price: Optional[int], 
                          new_price: int) -> None:
        """
        価格変更を記録
        
        Args:
            listing_id: 掲載ID
            old_price: 旧価格
            new_price: 新価格
        """
        from backend.app.models import ListingPriceHistory
        from backend.app.utils.datetime_utils import get_utc_now
        
        if old_price == new_price:
            return
        
        try:
            price_history = ListingPriceHistory(
                property_listing_id=listing_id,
                price=new_price,
                recorded_at=get_utc_now()
            )
            self.session.add(price_history)
            self.session.flush()
            
            self.logger.info(
                f"価格変更を記録: {old_price}万円 → {new_price}万円"
            )
        except Exception as e:
            self.logger.error(f"価格履歴記録エラー: {e}")
    
    def deactivate_missing_listings(self, 
                                   source_site: str,
                                   active_source_ids: List[str]) -> int:
        """
        見つからなかった掲載を非アクティブ化
        
        Args:
            source_site: ソースサイト
            active_source_ids: アクティブなソースIDのリスト
            
        Returns:
            非アクティブ化した件数
        """
        from backend.app.models import PropertyListing
        from backend.app.utils.datetime_utils import get_utc_now
        
        # アクティブだが今回見つからなかった掲載を取得
        missing_listings = self.session.query(PropertyListing).filter(
            and_(
                PropertyListing.source_site == source_site,
                PropertyListing.is_active == True,
                ~PropertyListing.source_id.in_(active_source_ids)
            )
        ).all()
        
        count = 0
        for listing in missing_listings:
            listing.is_active = False
            listing.delisted_at = get_utc_now()
            count += 1
            self.logger.info(f"掲載を非アクティブ化: {listing.source_id}")
        
        if count > 0:
            self.session.flush()
        
        return count
    
    def commit(self) -> bool:
        """
        トランザクションをコミット
        
        Returns:
            成功フラグ
        """
        try:
            self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"コミットエラー: {e}")
            self.session.rollback()
            return False
    
    def rollback(self) -> None:
        """トランザクションをロールバック"""
        self.session.rollback()
    
    def close(self) -> None:
        """セッションを閉じる"""
        self.session.close()