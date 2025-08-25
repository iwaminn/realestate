#!/usr/bin/env python3
"""
誤った建物に紐付いている物件を修正するスクリプト

処理内容：
1. 掲載情報の多数決値と建物属性が2つ以上異なる物件を特定
2. これらの物件を現在の建物から分離
3. 正しい建物を探して再紐付け（属性がすべて一致する建物）
4. 見つからない場合は新規建物を作成
5. 建物属性を多数決で更新
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text, func, and_, or_
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import (
    Building, MasterProperty, PropertyListing,
    BuildingListingName
)
from backend.app.utils.address_normalizer import AddressNormalizer
from backend.app.scrapers.data_normalizer import DataNormalizer, canonicalize_building_name

# ロガーの設定
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PropertyBuildingFixer:
    """誤った建物紐付けを修正するクラス"""
    
    def __init__(self, session: Session):
        self.session = session
        self.address_normalizer = AddressNormalizer()
        self.data_normalizer = DataNormalizer()
        self.stats = {
            'total_mismatched': 0,
            'separated': 0,
            'relinked': 0,
            'new_buildings_created': 0,
            'buildings_updated': 0,
            'errors': 0
        }
        
    def find_mismatched_properties(self) -> List[Dict]:
        """2つ以上の属性が異なる物件を検出"""
        logger.info("誤った紐付けの物件を検出中...")
        
        query = text("""
            WITH property_majority AS (
                SELECT 
                    mp.id as property_id,
                    mp.building_id,
                    mp.floor_number,
                    mp.room_number,
                    mp.area,
                    mp.layout,
                    mp.direction,
                    b.normalized_name as building_name,
                    b.address,
                    b.total_floors as building_total_floors,
                    b.total_units as building_total_units,
                    b.built_year as building_built_year,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_total_floors) as majority_total_floors,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_total_units) as majority_total_units,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_built_year) as majority_built_year,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_building_name) as majority_building_name,
                    COUNT(DISTINCT pl.id) as listing_count
                FROM master_properties mp
                INNER JOIN buildings b ON b.id = mp.building_id
                INNER JOIN property_listings pl ON pl.master_property_id = mp.id
                WHERE pl.is_active = true
                GROUP BY mp.id, mp.building_id, mp.floor_number, mp.room_number, 
                         mp.area, mp.layout, mp.direction,
                         b.normalized_name, b.address, 
                         b.total_floors, b.total_units, b.built_year
            ),
            mismatches AS (
                SELECT 
                    *,
                    CASE 
                        WHEN building_total_floors IS NOT NULL AND majority_total_floors IS NOT NULL 
                             AND building_total_floors != majority_total_floors THEN 1
                        ELSE 0
                    END as floor_mismatch,
                    CASE 
                        WHEN building_total_units IS NOT NULL AND majority_total_units IS NOT NULL 
                             AND building_total_units != majority_total_units THEN 1
                        ELSE 0
                    END as unit_mismatch,
                    CASE 
                        WHEN building_built_year IS NOT NULL AND majority_built_year IS NOT NULL 
                             AND building_built_year != majority_built_year THEN 1
                        ELSE 0
                    END as year_mismatch
                FROM property_majority
            )
            SELECT 
                property_id,
                building_id,
                floor_number,
                room_number,
                area,
                layout,
                direction,
                building_name,
                address,
                building_total_floors,
                building_total_units,
                building_built_year,
                majority_total_floors,
                majority_total_units,
                majority_built_year,
                majority_building_name,
                listing_count,
                (floor_mismatch + unit_mismatch + year_mismatch) as mismatch_count
            FROM mismatches
            WHERE (floor_mismatch + unit_mismatch + year_mismatch) >= 2
            ORDER BY building_id, property_id
        """)
        
        result = self.session.execute(query)
        properties = [row._asdict() for row in result]
        
        logger.info(f"検出された誤った紐付け物件: {len(properties)}件")
        self.stats['total_mismatched'] = len(properties)
        
        return properties
    
    def find_correct_building(self, property_info: Dict) -> Optional[Building]:
        """正しい建物を探す（属性がすべて一致する建物）"""
        
        # 多数決で決定された建物名と属性
        majority_name = property_info['majority_building_name']
        majority_floors = property_info['majority_total_floors']
        majority_units = property_info['majority_total_units']
        majority_year = property_info['majority_built_year']
        
        if not majority_name:
            return None
        
        # 正規化された建物名を生成
        canonical_name = canonicalize_building_name(majority_name)
        
        # 既存の建物から検索（属性がすべて一致）
        query = self.session.query(Building).filter(
            Building.canonical_name == canonical_name
        )
        
        # 属性がすべて揃っている必要がある
        if majority_floors is not None and majority_units is not None and majority_year is not None:
            query = query.filter(
                Building.total_floors == majority_floors,
                Building.total_units == majority_units,
                Building.built_year == majority_year
            )
        else:
            # 属性が不完全な場合は自動紐付けしない
            return None
        
        buildings = query.all()
        
        # 複数候補がある場合は住所でフィルタリング
        if len(buildings) > 1 and property_info.get('address'):
            normalized_addr = self.address_normalizer.normalize_for_comparison(property_info['address'])
            for building in buildings:
                if building.address:
                    building_addr = self.address_normalizer.normalize_for_comparison(building.address)
                    if building_addr == normalized_addr or \
                       building_addr.startswith(normalized_addr) or \
                       normalized_addr.startswith(building_addr):
                        return building
        
        return buildings[0] if buildings else None
    
    def create_new_building(self, property_info: Dict) -> Building:
        """新規建物を作成"""
        
        majority_name = property_info['majority_building_name'] or property_info['building_name']
        canonical_name = canonicalize_building_name(majority_name)
        
        # 住所の正規化
        normalized_addr = None
        if property_info.get('address'):
            normalized_addr = self.address_normalizer.normalize_for_comparison(property_info['address'])
        
        building = Building(
            normalized_name=majority_name,
            canonical_name=canonical_name,
            address=property_info.get('address'),
            normalized_address=normalized_addr,
            total_floors=property_info['majority_total_floors'],
            total_units=property_info['majority_total_units'],
            built_year=property_info['majority_built_year']
        )
        
        self.session.add(building)
        self.session.flush()
        
        logger.info(f"新規建物を作成: ID={building.id}, 名前={building.normalized_name}")
        self.stats['new_buildings_created'] += 1
        
        return building
    
    def update_building_attributes(self, building_id: int):
        """建物属性を多数決で更新"""
        
        # 建物に紐付く物件の掲載情報から多数決を取る
        result = self.session.execute(text("""
            SELECT 
                MODE() WITHIN GROUP (ORDER BY pl.listing_total_floors) as majority_floors,
                MODE() WITHIN GROUP (ORDER BY pl.listing_total_units) as majority_units,
                MODE() WITHIN GROUP (ORDER BY pl.listing_built_year) as majority_year,
                MODE() WITHIN GROUP (ORDER BY pl.listing_built_month) as majority_month
            FROM master_properties mp
            INNER JOIN property_listings pl ON pl.master_property_id = mp.id
            WHERE mp.building_id = :building_id
                AND pl.is_active = true
        """), {'building_id': building_id}).first()
        
        if not result:
            return
        
        building = self.session.query(Building).get(building_id)
        if not building:
            return
        
        updated = False
        
        # 属性を更新（NULLでない場合のみ）
        if result.majority_floors and building.total_floors != result.majority_floors:
            logger.info(f"建物ID {building_id}: 総階数を {building.total_floors} → {result.majority_floors} に更新")
            building.total_floors = result.majority_floors
            updated = True
        
        if result.majority_units and building.total_units != result.majority_units:
            logger.info(f"建物ID {building_id}: 総戸数を {building.total_units} → {result.majority_units} に更新")
            building.total_units = result.majority_units
            updated = True
        
        if result.majority_year and building.built_year != result.majority_year:
            logger.info(f"建物ID {building_id}: 築年を {building.built_year} → {result.majority_year} に更新")
            building.built_year = result.majority_year
            updated = True
        
        if result.majority_month and not building.built_month:
            building.built_month = result.majority_month
            updated = True
        
        if updated:
            self.session.flush()
            self.stats['buildings_updated'] += 1
    
    def process_property(self, property_info: Dict) -> bool:
        """1つの物件を処理"""
        
        property_id = property_info['property_id']
        old_building_id = property_info['building_id']
        
        try:
            # 1. 正しい建物を探す
            correct_building = self.find_correct_building(property_info)
            
            if not correct_building:
                # 2. 見つからない場合は新規建物を作成
                correct_building = self.create_new_building(property_info)
            
            # 3. 物件を新しい建物に紐付け直す
            property_obj = self.session.query(MasterProperty).get(property_id)
            if property_obj:
                logger.info(f"物件ID {property_id}: 建物ID {old_building_id} → {correct_building.id} に再紐付け")
                property_obj.building_id = correct_building.id
                self.session.flush()
                self.stats['relinked'] += 1
                
                # 4. 新旧両方の建物属性を多数決で更新
                self.update_building_attributes(old_building_id)
                self.update_building_attributes(correct_building.id)
                
                return True
            
        except Exception as e:
            logger.error(f"物件ID {property_id} の処理中にエラー: {e}")
            self.stats['errors'] += 1
            return False
        
        return False
    
    def run(self, dry_run: bool = False):
        """修正処理を実行"""
        
        logger.info("=" * 80)
        logger.info("誤った建物紐付け修正処理を開始")
        logger.info("=" * 80)
        
        # 誤った紐付けの物件を検出
        mismatched_properties = self.find_mismatched_properties()
        
        if not mismatched_properties:
            logger.info("修正対象の物件が見つかりませんでした")
            return
        
        # 建物ごとにグループ化
        properties_by_building = defaultdict(list)
        for prop in mismatched_properties:
            properties_by_building[prop['building_id']].append(prop)
        
        logger.info(f"影響を受ける建物数: {len(properties_by_building)}")
        
        if dry_run:
            logger.info("=== ドライラン（実際の変更は行いません） ===")
            for building_id, properties in properties_by_building.items():
                building_name = properties[0]['building_name']
                logger.info(f"\n建物ID {building_id} ({building_name}): {len(properties)}件の物件")
                for prop in properties[:3]:  # 最初の3件だけ表示
                    logger.info(f"  - 物件ID {prop['property_id']}: "
                              f"建物属性({prop['building_total_floors']}F/"
                              f"{prop['building_total_units']}戸/"
                              f"{prop['building_built_year']}年) → "
                              f"多数決({prop['majority_total_floors']}F/"
                              f"{prop['majority_total_units']}戸/"
                              f"{prop['majority_built_year']}年)")
            return
        
        # 実際の処理を実行
        logger.info("\n処理を開始します...")
        processed = 0
        
        for building_id, properties in properties_by_building.items():
            building_name = properties[0]['building_name']
            logger.info(f"\n建物ID {building_id} ({building_name}) の物件を処理中...")
            
            for prop in properties:
                if self.process_property(prop):
                    processed += 1
                    self.stats['separated'] += 1
                
                # 10件ごとにコミット
                if processed % 10 == 0:
                    self.session.commit()
                    logger.info(f"進捗: {processed}/{len(mismatched_properties)} 件処理済み")
        
        # 最終コミット
        self.session.commit()
        
        # 統計を表示
        logger.info("\n" + "=" * 80)
        logger.info("処理完了")
        logger.info("=" * 80)
        logger.info(f"対象物件数: {self.stats['total_mismatched']}")
        logger.info(f"分離済み: {self.stats['separated']}")
        logger.info(f"再紐付け済み: {self.stats['relinked']}")
        logger.info(f"新規建物作成: {self.stats['new_buildings_created']}")
        logger.info(f"建物属性更新: {self.stats['buildings_updated']}")
        logger.info(f"エラー: {self.stats['errors']}")


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='誤った建物紐付けを修正')
    parser.add_argument('--dry-run', action='store_true', help='実際の変更を行わずに確認のみ')
    parser.add_argument('--limit', type=int, help='処理する物件数の上限')
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        fixer = PropertyBuildingFixer(session)
        fixer.run(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"処理中にエラーが発生: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()