"""
BuildingListingNameテーブルの管理ユーティリティ

このモジュールは、建物に紐づく掲載建物名を透過的に管理します。
スクレイピング時の新規登録、物件・建物の統合・分離時の更新を一元管理します。
"""

import logging
from typing import Optional, List, Set, Dict
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from ..models import (
    Building,
    MasterProperty,
    PropertyListing,
    BuildingListingName
)
from ..scrapers.data_normalizer import normalize_building_name, canonicalize_building_name

logger = logging.getLogger(__name__)


class BuildingListingNameManager:
    """BuildingListingNameテーブルの管理クラス"""
    
    def __init__(self, db: Session):
        """
        初期化
        
        Args:
            db: データベースセッション
        """
        self.db = db
        
    def update_from_listing(self, listing: PropertyListing) -> None:
        """
        掲載情報から建物名を更新（スクレイピング時に使用）
        
        Args:
            listing: 掲載情報オブジェクト
        """
        if not listing.listing_building_name or not listing.master_property_id:
            return
            
        # マスター物件から建物IDを取得
        master_property = self.db.query(MasterProperty).filter(
            MasterProperty.id == listing.master_property_id
        ).first()
        
        if not master_property or not master_property.building_id:
            return
            
        # 建物名を更新
        self._update_building_name(
            building_id=master_property.building_id,
            listing_name=listing.listing_building_name,
            source_site=listing.source_site
        )
    
    def update_from_property_merge(
        self,
        primary_property_id: int,
        secondary_property_id: int
    ) -> None:
        """
        物件統合時に掲載建物名を移動
        
        Args:
            primary_property_id: 統合先の物件ID
            secondary_property_id: 統合元の物件ID
        """
        # 両方の物件の建物IDを取得
        primary_property = self.db.query(MasterProperty).filter(
            MasterProperty.id == primary_property_id
        ).first()
        
        secondary_property = self.db.query(MasterProperty).filter(
            MasterProperty.id == secondary_property_id
        ).first()
        
        if not primary_property or not secondary_property:
            logger.warning(f"物件が見つかりません: primary={primary_property_id}, secondary={secondary_property_id}")
            return
            
        # 建物が異なる場合のみ処理
        if primary_property.building_id != secondary_property.building_id:
            # 統合元の建物の掲載名を統合先に移動
            self._migrate_building_names(
                from_building_id=secondary_property.building_id,
                to_building_id=primary_property.building_id
            )
    
    def update_from_building_merge(
        self,
        primary_building_id: int,
        secondary_building_id: int
    ) -> None:
        """
        建物統合時に掲載建物名を移動
        
        Args:
            primary_building_id: 統合先の建物ID
            secondary_building_id: 統合元の建物ID
        """
        # 統合元の建物の掲載名を統合先に移動
        self._migrate_building_names(
            from_building_id=secondary_building_id,
            to_building_id=primary_building_id
        )
    
    def update_from_property_split(
        self,
        original_property_id: int,
        new_property_id: int,
        new_building_id: Optional[int] = None
    ) -> None:
        """
        物件分離時に掲載建物名を分割
        
        Args:
            original_property_id: 元の物件ID
            new_property_id: 新しく作成された物件ID
            new_building_id: 新しい建物ID（異なる建物に分離する場合）
        """
        if not new_building_id:
            # 同じ建物内での分離の場合は何もしない
            return
            
        # 元の物件の建物IDを取得
        original_property = self.db.query(MasterProperty).filter(
            MasterProperty.id == original_property_id
        ).first()
        
        if not original_property or not original_property.building_id:
            return
            
        # 元の建物の掲載名を新しい建物にもコピー
        self._copy_building_names(
            from_building_id=original_property.building_id,
            to_building_id=new_building_id
        )
    
    def update_from_building_split(
        self,
        original_building_id: int,
        new_building_id: int,
        property_ids_to_move: List[int]
    ) -> None:
        """
        建物分離時に掲載建物名を分割
        
        Args:
            original_building_id: 元の建物ID
            new_building_id: 新しく作成された建物ID
            property_ids_to_move: 新しい建物に移動する物件IDのリスト
        """
        # 移動する物件に紐づく掲載情報から建物名を収集
        listing_names = self.db.query(
            PropertyListing.listing_building_name,
            PropertyListing.source_site
        ).join(
            MasterProperty,
            PropertyListing.master_property_id == MasterProperty.id
        ).filter(
            MasterProperty.id.in_(property_ids_to_move),
            PropertyListing.listing_building_name.isnot(None)
        ).distinct().all()
        
        # 新しい建物に掲載名を登録
        for listing_name, source_site in listing_names:
            self._update_building_name(
                building_id=new_building_id,
                listing_name=listing_name,
                source_site=source_site
            )
    
    def refresh_building_names(self, building_id: int) -> None:
        """
        指定された建物の掲載名を再集計
        
        Args:
            building_id: 建物ID
        """
        # 既存のエントリを削除
        self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == building_id
        ).delete()
        
        # 建物に紐づく掲載情報から建物名を再集計
        listing_names = self.db.query(
            PropertyListing.listing_building_name,
            PropertyListing.source_site,
            func.count(PropertyListing.id).label('count'),
            func.min(PropertyListing.first_seen_at).label('first_seen'),
            func.max(PropertyListing.last_scraped_at).label('last_seen')
        ).join(
            MasterProperty,
            PropertyListing.master_property_id == MasterProperty.id
        ).filter(
            MasterProperty.building_id == building_id,
            PropertyListing.listing_building_name.isnot(None),
            PropertyListing.listing_building_name != ''
        ).group_by(
            PropertyListing.listing_building_name,
            PropertyListing.source_site
        ).all()
        
        # 正規化後の名前で集約
        canonical_aggregation = defaultdict(lambda: {
            'listing_names': {},  # {name: count} の辞書
            'sites': set(),
            'total_count': 0,
            'first_seen': None,
            'last_seen': None
        })
        
        for name, site, count, first_seen, last_seen in listing_names:
            canonical_name = canonicalize_building_name(name)
            agg = canonical_aggregation[canonical_name]
            
            # 元の表記とその出現回数を記録
            if name in agg['listing_names']:
                agg['listing_names'][name] += count
            else:
                agg['listing_names'][name] = count
            
            agg['sites'].add(site)
            agg['total_count'] += count
            
            if agg['first_seen'] is None or (first_seen and first_seen < agg['first_seen']):
                agg['first_seen'] = first_seen
                
            if agg['last_seen'] is None or (last_seen and last_seen > agg['last_seen']):
                agg['last_seen'] = last_seen
        
        # BuildingListingNameに保存
        for canonical_name, agg_data in canonical_aggregation.items():
            # 最も出現回数が多い表記を代表名とする
            most_common_name = max(agg_data['listing_names'].items(), key=lambda x: x[1])[0]
            
            new_entry = BuildingListingName(
                building_id=building_id,
                listing_name=most_common_name,  # 最も一般的な表記を使用
                canonical_name=canonical_name,
                source_sites=','.join(sorted(agg_data['sites'])),
                occurrence_count=agg_data['total_count'],
                first_seen_at=agg_data['first_seen'] or datetime.now(),
                last_seen_at=agg_data['last_seen'] or datetime.now()
            )
            self.db.add(new_entry)
        
        self.db.commit()
    
    def _update_building_name(
        self,
        building_id: int,
        listing_name: str,
        source_site: str
    ) -> None:
        """
        建物名を更新（内部メソッド）
        
        Args:
            building_id: 建物ID
            listing_name: 掲載建物名
            source_site: 掲載サイト
        """
        if not listing_name:
            return
            
        # canonical_nameはスペース・記号を完全に削除
        canonical_name = canonicalize_building_name(listing_name)
        
        # 正規化後の名前で既存レコードを確認
        existing = self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == building_id,
            BuildingListingName.canonical_name == canonical_name
        ).first()
        
        if existing:
            # 更新
            # 元のlisting_nameと異なる場合、最も一般的な表記を保持（出現回数が多い方を優先）
            # 例：「白金ザ・スカイ　西棟」と「白金ザ・スカイ 西棟」のうち、より多く使われている方を代表名とする
            existing.occurrence_count += 1
            existing.last_seen_at = datetime.now()
            
            # サイト情報を更新
            sites = set(existing.source_sites.split(',')) if existing.source_sites else set()
            sites.add(source_site)
            existing.source_sites = ','.join(sorted(sites))
        else:
            # 新規作成
            new_entry = BuildingListingName(
                building_id=building_id,
                listing_name=listing_name,
                canonical_name=canonical_name,
                source_sites=source_site,
                occurrence_count=1,
                first_seen_at=datetime.now(),
                last_seen_at=datetime.now()
            )
            self.db.add(new_entry)
        
        # 自動コミットはしない（呼び出し元でコミット）
    
    def _migrate_building_names(
        self,
        from_building_id: int,
        to_building_id: int
    ) -> None:
        """
        建物名を別の建物に移動（内部メソッド）
        
        Args:
            from_building_id: 移動元の建物ID
            to_building_id: 移動先の建物ID
        """
        # 移動元の建物名を取得
        source_names = self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == from_building_id
        ).all()
        
        for source_name in source_names:
            # 移動先に同じ正規化名があるか確認（canonical_nameで判定）
            target_name = self.db.query(BuildingListingName).filter(
                BuildingListingName.building_id == to_building_id,
                BuildingListingName.canonical_name == source_name.canonical_name
            ).first()
            
            if target_name:
                # 既存レコードを更新
                target_name.occurrence_count += source_name.occurrence_count
                
                # より出現回数が多い表記を保持
                if source_name.occurrence_count > target_name.occurrence_count:
                    target_name.listing_name = source_name.listing_name
                
                # サイト情報をマージ
                source_sites = set(source_name.source_sites.split(',')) if source_name.source_sites else set()
                target_sites = set(target_name.source_sites.split(',')) if target_name.source_sites else set()
                target_name.source_sites = ','.join(sorted(source_sites | target_sites))
                
                # 日付を更新
                if source_name.first_seen_at < target_name.first_seen_at:
                    target_name.first_seen_at = source_name.first_seen_at
                if source_name.last_seen_at > target_name.last_seen_at:
                    target_name.last_seen_at = source_name.last_seen_at
                
                # 移動元のレコードを削除
                self.db.delete(source_name)
            else:
                # 建物IDを変更して移動
                source_name.building_id = to_building_id
    
    def _copy_building_names(
        self,
        from_building_id: int,
        to_building_id: int
    ) -> None:
        """
        建物名を別の建物にコピー（内部メソッド）
        
        Args:
            from_building_id: コピー元の建物ID
            to_building_id: コピー先の建物ID
        """
        # コピー元の建物名を取得
        source_names = self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == from_building_id
        ).all()
        
        for source_name in source_names:
            # コピー先に同じ正規化名があるか確認（canonical_nameで判定）
            existing = self.db.query(BuildingListingName).filter(
                BuildingListingName.building_id == to_building_id,
                BuildingListingName.canonical_name == source_name.canonical_name
            ).first()
            
            if existing:
                # 既存レコードを更新（出現回数を加算）
                existing.occurrence_count += source_name.occurrence_count
                
                # より出現回数が多い表記を保持
                if source_name.occurrence_count > existing.occurrence_count:
                    existing.listing_name = source_name.listing_name
                
                # サイト情報をマージ
                source_sites = set(source_name.source_sites.split(',')) if source_name.source_sites else set()
                existing_sites = set(existing.source_sites.split(',')) if existing.source_sites else set()
                existing.source_sites = ','.join(sorted(source_sites | existing_sites))
                
                # 日付を更新
                if source_name.first_seen_at < existing.first_seen_at:
                    existing.first_seen_at = source_name.first_seen_at
                if source_name.last_seen_at > existing.last_seen_at:
                    existing.last_seen_at = source_name.last_seen_at
            else:
                # 新規作成（コピー）
                new_entry = BuildingListingName(
                    building_id=to_building_id,
                    listing_name=source_name.listing_name,
                    canonical_name=source_name.canonical_name,
                    source_sites=source_name.source_sites,
                    occurrence_count=source_name.occurrence_count,
                    first_seen_at=source_name.first_seen_at,
                    last_seen_at=source_name.last_seen_at
                )
                self.db.add(new_entry)
    
    def get_building_names(self, building_id: int) -> List[Dict]:
        """
        指定された建物の掲載名一覧を取得
        
        Args:
            building_id: 建物ID
            
        Returns:
            掲載名情報のリスト
        """
        names = self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == building_id
        ).order_by(
            BuildingListingName.occurrence_count.desc()
        ).all()
        
        return [
            {
                'listing_name': name.listing_name,
                'canonical_name': name.canonical_name,
                'source_sites': name.source_sites.split(',') if name.source_sites else [],
                'occurrence_count': name.occurrence_count,
                'first_seen_at': name.first_seen_at,
                'last_seen_at': name.last_seen_at
            }
            for name in names
        ]
    
    def search_buildings_by_name(self, search_term: str) -> List[int]:
        """
        建物名で建物IDを検索
        
        Args:
            search_term: 検索語
            
        Returns:
            マッチした建物IDのリスト
        """
        building_ids = self.db.query(
            BuildingListingName.building_id
        ).filter(
            or_(
                BuildingListingName.listing_name.ilike(f"%{search_term}%"),
                BuildingListingName.canonical_name.ilike(f"%{search_term}%")
            )
        ).distinct().all()
        
        return [bid[0] for bid in building_ids]