"""
BuildingListingNameテーブルの管理ユーティリティ

このモジュールは、建物に紐づく掲載建物名を透過的に管理します。
スクレイピング時の新規登録、物件・建物の統合・分離時の更新を一元管理します。
"""

import logging
from typing import Optional, List, Set, Dict
from datetime import datetime
from collections import defaultdict
import time
import random
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from sqlalchemy.exc import OperationalError

from ..models import (
    Building,
    MasterProperty,
    PropertyListing,
    BuildingListingName
)
from .building_name_normalizer import canonicalize_building_name
from .building_name_normalizer import normalize_building_name

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
            
        # 元の建物IDを保存
        original_building_id = original_property.building_id
            
        # 元の建物の掲載名を新しい建物にもコピー
        self._copy_building_names(
            from_building_id=original_building_id,
            to_building_id=new_building_id
        )
        
        # 重要: 元の建物の掲載名を再計算
        # 物件が移動したので、元の建物に残っている物件の掲載情報から再構築
        self.refresh_building_names(original_building_id)
    
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
        logger.info(f"refresh_building_names called for building_id={building_id}")
        
        # 建物が存在することを確認
        building = self.db.query(Building).filter(Building.id == building_id).first()
        if not building:
            logger.error(f"Building {building_id} does not exist. Skipping refresh_building_names.")
            return
        
        # 既存のエントリを削除
        deleted_count = self.db.query(BuildingListingName).filter(
            BuildingListingName.building_id == building_id
        ).delete()
        self.db.flush()  # 削除を確実に実行
        logger.info(f"Deleted {deleted_count} existing entries for building_id={building_id}")
        
        # 建物に紐づく掲載情報から建物名を取得（集計なし、生データ）
        listing_data = self.db.query(
            PropertyListing.listing_building_name,
            PropertyListing.source_site,
            PropertyListing.first_seen_at,
            PropertyListing.last_scraped_at
        ).join(
            MasterProperty,
            PropertyListing.master_property_id == MasterProperty.id
        ).filter(
            MasterProperty.building_id == building_id,
            PropertyListing.listing_building_name.isnot(None),
            PropertyListing.listing_building_name != ''
        ).all()
        
        logger.info(f"Found {len(listing_data)} listings for building_id={building_id}")
        
        # canonical_nameでグループ化して集約
        from collections import defaultdict
        canonical_groups = defaultdict(lambda: {
            'names': {},  # {name: count}
            'sites': set(),
            'first_seen': None,
            'last_seen': None
        })
        
        for name, site, first_seen, last_seen in listing_data:
            canonical_name = canonicalize_building_name(name)
            group = canonical_groups[canonical_name]
            
            # 名前の出現回数をカウント
            if name not in group['names']:
                group['names'][name] = 0
            group['names'][name] += 1
            
            # サイトを追加
            group['sites'].add(site)
            
            # 日付の更新
            if group['first_seen'] is None or (first_seen and first_seen < group['first_seen']):
                group['first_seen'] = first_seen
            if group['last_seen'] is None or (last_seen and last_seen > group['last_seen']):
                group['last_seen'] = last_seen
        
        logger.info(f"Grouped into {len(canonical_groups)} canonical names")
        for canonical_name in canonical_groups:
            logger.debug(f"  {canonical_name}: {canonical_groups[canonical_name]['names']}")
        
        # 各canonical_nameグループに対して1つのレコードを作成
        for canonical_name, group_data in canonical_groups.items():
            # 最も頻出する表記を選択
            most_common_name = max(group_data['names'].items(), key=lambda x: x[1])[0]
            normalized_name = normalize_building_name(most_common_name)
            total_count = sum(group_data['names'].values())
            
            logger.debug(f"Creating entry: building_id={building_id}, canonical_name={canonical_name}, listing_name={most_common_name}")
            
            # 既存のエントリがないことを再確認
            existing = self.db.query(BuildingListingName).filter(
                BuildingListingName.building_id == building_id,
                BuildingListingName.canonical_name == canonical_name
            ).first()
            
            if existing:
                logger.warning(f"Entry already exists for building_id={building_id}, canonical_name={canonical_name}. Updating instead.")
                existing.normalized_name = normalized_name
                existing.source_sites = ','.join(sorted(group_data['sites']))
                existing.occurrence_count = total_count
                existing.last_seen_at = group_data['last_seen'] or datetime.now()
            else:
                # 新しいエントリを作成（直接INSERT文を実行して確実性を高める）
                from sqlalchemy import text
                insert_sql = text("""
                    INSERT INTO building_listing_names 
                    (building_id, normalized_name, canonical_name, source_sites, occurrence_count, first_seen_at, last_seen_at)
                    VALUES 
                    (:building_id, :normalized_name, :canonical_name, :source_sites, :occurrence_count, :first_seen_at, :last_seen_at)
                    ON CONFLICT (building_id, canonical_name) 
                    DO UPDATE SET
                        normalized_name = EXCLUDED.normalized_name,
                        source_sites = EXCLUDED.source_sites,
                        occurrence_count = EXCLUDED.occurrence_count,
                        last_seen_at = EXCLUDED.last_seen_at
                """)
                
                try:
                    logger.info(f"Inserting BuildingListingName: building_id={building_id}, canonical_name={canonical_name}")
                    self.db.execute(insert_sql, {
                        'building_id': building_id,
                        'normalized_name': normalized_name,
                        'canonical_name': canonical_name,
                        'source_sites': ','.join(sorted(group_data['sites'])),
                        'occurrence_count': total_count,
                        'first_seen_at': group_data['first_seen'] or datetime.now(),
                        'last_seen_at': group_data['last_seen'] or datetime.now()
                    })
                    self.db.flush()
                except Exception as e:
                    logger.error(f"Failed to insert/update entry for building_id={building_id}, canonical_name={canonical_name}: {e}")
                    raise
        
        logger.info(f"refresh_building_names completed for building_id={building_id}")
    
    def _update_building_name(
        self,
        building_id: int,
        listing_name: str,
        source_site: str,
        max_retries: int = 3
    ) -> None:
        """
        建物名を更新（内部メソッド）
        デッドロック回避のためリトライロジック付き
        
        Args:
            building_id: 建物ID
            listing_name: 掲載建物名
            source_site: 掲載サイト
            max_retries: 最大リトライ回数
        """
        if not listing_name:
            return
            
        # 建物が存在することを確認
        building = self.db.query(Building).filter(Building.id == building_id).first()
        if not building:
            logger.error(f"Building {building_id} does not exist. Skipping _update_building_name for '{listing_name}'.")
            return
            
        # 駅情報のパターンをチェック（建物名として無効なものを除外）
        station_patterns = ['駅', '徒歩', '分歩', 'バス', '線', 'ライン', 'Line']
        if any(pattern in listing_name for pattern in station_patterns):
            logger.warning(
                f"駅情報のため建物名として登録をスキップ: '{listing_name}' "
                f"(building_id={building_id}, source={source_site})"
            )
            return
            
        # normalized_nameは表示用に軽く正規化（スペース統一など）
        normalized_name = normalize_building_name(listing_name)
        # canonical_nameはスペース・記号を完全に削除
        canonical_name = canonicalize_building_name(listing_name)
        
        # リトライロジック
        for attempt in range(max_retries):
            try:
                # 正規化後の名前で既存レコードを確認
                existing = self.db.query(BuildingListingName).filter(
                    BuildingListingName.building_id == building_id,
                    BuildingListingName.canonical_name == canonical_name
                ).first()  # ロックを使わずに楽観的並行制御を使用
                
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
                    # 新規作成（ON CONFLICTで安全に挿入）
                    from sqlalchemy import text
                    insert_sql = text("""
                        INSERT INTO building_listing_names 
                        (building_id, normalized_name, canonical_name, source_sites, occurrence_count, first_seen_at, last_seen_at)
                        VALUES 
                        (:building_id, :normalized_name, :canonical_name, :source_sites, :occurrence_count, :first_seen_at, :last_seen_at)
                        ON CONFLICT (building_id, canonical_name) 
                        DO UPDATE SET
                            occurrence_count = building_listing_names.occurrence_count + 1,
                            source_sites = CASE 
                                WHEN position(:source_sites IN building_listing_names.source_sites) = 0
                                THEN building_listing_names.source_sites || ',' || :source_sites
                                ELSE building_listing_names.source_sites
                            END,
                            last_seen_at = EXCLUDED.last_seen_at
                    """)
                    
                    current_time = datetime.now()
                    self.db.execute(insert_sql, {
                        'building_id': building_id,
                        'normalized_name': normalized_name,
                        'canonical_name': canonical_name,
                        'source_sites': source_site,
                        'occurrence_count': 1,
                        'first_seen_at': current_time,
                        'last_seen_at': current_time
                    })
                
                # 成功したら終了
                break
                
            except OperationalError as e:
                if "deadlock detected" in str(e).lower():
                    logger.warning(
                        f"デッドロック検出 (attempt {attempt + 1}/{max_retries}): "
                        f"building_id={building_id}, listing_name={listing_name}"
                    )
                    if attempt < max_retries - 1:
                        # ロールバックして少し待機してからリトライ
                        self.db.rollback()
                        wait_time = (0.1 + random.random() * 0.5) * (2 ** attempt)  # 指数バックオフ
                        time.sleep(wait_time)
                    else:
                        # 最後の試行でも失敗した場合はエラーを再発生
                        logger.error(
                            f"デッドロック解決失敗: building_id={building_id}, "
                            f"listing_name={listing_name}"
                        )
                        raise
                else:
                    # デッドロック以外のエラーは即座に再発生
                    raise
        
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
                    target_name.normalized_name = source_name.normalized_name
                
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
                # 新規作成（コピー）- ON CONFLICTで安全に挿入
                from sqlalchemy import text
                insert_sql = text("""
                    INSERT INTO building_listing_names 
                    (building_id, normalized_name, canonical_name, source_sites, occurrence_count, first_seen_at, last_seen_at)
                    VALUES 
                    (:building_id, :normalized_name, :canonical_name, :source_sites, :occurrence_count, :first_seen_at, :last_seen_at)
                    ON CONFLICT (building_id, canonical_name) 
                    DO UPDATE SET
                        normalized_name = EXCLUDED.normalized_name,
                        source_sites = EXCLUDED.source_sites,
                        occurrence_count = EXCLUDED.occurrence_count,
                        last_seen_at = EXCLUDED.last_seen_at
                """)
                
                self.db.execute(insert_sql, {
                    'building_id': to_building_id,
                    'normalized_name': source_name.normalized_name,
                    'canonical_name': source_name.canonical_name,
                    'source_sites': source_name.source_sites,
                    'occurrence_count': source_name.occurrence_count,
                    'first_seen_at': source_name.first_seen_at,
                    'last_seen_at': source_name.last_seen_at
                })
    
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
                'normalized_name': name.normalized_name,
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
        # canonical_nameで検索
        canonical_search_term = canonicalize_building_name(search_term)
        building_ids = self.db.query(
            BuildingListingName.building_id
        ).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_search_term}%")
        ).distinct().all()
        
        return [bid[0] for bid in building_ids]