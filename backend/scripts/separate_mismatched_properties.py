#!/usr/bin/env python3
"""
品川区・目黒区の物件で建物属性が異なるものを分離するスクリプト

建物の築年月、総階数、総戸数のうち2つ以上が異なる物件を検出し、
新規建物を作成して分離します。
"""

import sys
import os
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# Dockerコンテナ内のパスを追加
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/backend')

from backend.app.database import SessionLocal
from backend.app.models import (
    Building, MasterProperty, PropertyListing, 
    BuildingListingName, PropertyMergeHistory
)
from backend.app.utils.address_normalizer import AddressNormalizer
from backend.app.utils.building_name_aggregator import BuildingNameAggregator
from backend.app.utils.building_attribute_aggregator import BuildingAttributeAggregator
from sqlalchemy import func, and_, or_
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_attribute_mismatch(building: Building, property_listing: PropertyListing) -> Tuple[bool, List[str]]:
    """
    建物と物件の属性を比較し、2つ以上異なるかチェック
    
    Returns:
        (is_mismatch, mismatched_attributes): 2つ以上異なる場合True、異なる属性のリスト
    """
    mismatched = []
    
    # 総階数の比較
    if (building.total_floors is not None and 
        property_listing.listing_total_floors is not None and
        building.total_floors != property_listing.listing_total_floors):
        mismatched.append(f"総階数: 建物={building.total_floors}, 物件={property_listing.listing_total_floors}")
    
    # 築年月の比較（年と月の両方）
    if (building.built_year is not None and 
        property_listing.listing_built_year is not None):
        
        # 年の比較
        if building.built_year != property_listing.listing_built_year:
            mismatched.append(f"築年: 建物={building.built_year}, 物件={property_listing.listing_built_year}")
        # 年が一致している場合のみ月も比較
        elif (building.built_month is not None and 
              property_listing.listing_built_month is not None and
              building.built_month != property_listing.listing_built_month):
            mismatched.append(f"築月: 建物={building.built_month}月, 物件={property_listing.listing_built_month}月")
    
    # 総戸数の比較
    if (building.total_units is not None and 
        property_listing.listing_total_units is not None and
        building.total_units != property_listing.listing_total_units):
        mismatched.append(f"総戸数: 建物={building.total_units}, 物件={property_listing.listing_total_units}")
    
    return len(mismatched) >= 2, mismatched

def find_mismatched_properties(session):
    """品川区・目黒区の属性が異なる物件を検出"""
    
    logger.info("品川区・目黒区の物件を検索中...")
    
    # 品川区・目黒区の建物を取得
    buildings = session.query(Building).filter(
        or_(
            Building.address.like('%品川区%'),
            Building.address.like('%目黒区%')
        )
    ).all()
    
    logger.info(f"対象建物数: {len(buildings)}件")
    
    mismatched_properties = []
    
    for building in buildings:
        # この建物に紐付く物件を取得
        properties = session.query(MasterProperty).filter(
            MasterProperty.building_id == building.id
        ).all()
        
        for property in properties:
            # 各物件の掲載情報を取得（アクティブなもののみ）
            listings = session.query(PropertyListing).filter(
                PropertyListing.master_property_id == property.id,
                PropertyListing.is_active == True
            ).all()
            
            # 各掲載情報の属性をチェック
            for listing in listings:
                is_mismatch, mismatched_attrs = check_attribute_mismatch(building, listing)
                
                if is_mismatch:
                    mismatched_properties.append({
                        'property': property,
                        'building': building,
                        'listing': listing,
                        'mismatched_attributes': mismatched_attrs
                    })
    
    logger.info(f"属性が異なる物件数: {len(mismatched_properties)}件")
    return mismatched_properties

def create_new_building_for_property(session, property: MasterProperty, listing: PropertyListing) -> Building:
    """物件用の新しい建物を作成"""
    
    addr_normalizer = AddressNormalizer()
    
    # 建物名を取得（駅情報でもそのまま使用）
    building_name = listing.listing_building_name
    if not building_name:
        logger.warning(f"物件ID {property.id} の建物名が取得できていません")
    if property.room_number:
        building_name = f"{building_name}_{property.room_number}号室分離"
    
    # 正規化された住所
    normalized_addr = None
    if listing.listing_address:
        normalized_addr = addr_normalizer.normalize_for_comparison(listing.listing_address)
    
    # 新しい建物を作成
    new_building = Building(
        normalized_name=building_name,
        address=listing.listing_address,
        normalized_address=normalized_addr,
        built_year=listing.listing_built_year,
        built_month=listing.listing_built_month,
        total_floors=listing.listing_total_floors,
        total_units=listing.listing_total_units,
        construction_type=listing.listing_building_structure
    )
    
    session.add(new_building)
    session.flush()
    
    logger.info(f"  新規建物作成: ID={new_building.id}, 名前={new_building.normalized_name}")
    
    # BuildingListingNameに登録
    if listing.listing_building_name and not any(
        pattern in listing.listing_building_name 
        for pattern in ['駅', '徒歩', '分歩', 'バス', '線']
    ):
        from backend.app.scrapers.data_normalizer import canonicalize_building_name
        
        listing_name_entry = BuildingListingName(
            building_id=new_building.id,
            listing_name=listing.listing_building_name,
            canonical_name=canonicalize_building_name(listing.listing_building_name),
            source_sites=listing.source_site,
            occurrence_count=1
        )
        session.add(listing_name_entry)
    
    return new_building

def separate_property(session, property_info: Dict):
    """物件を新しい建物に分離"""
    
    property = property_info['property']
    old_building = property_info['building']
    listing = property_info['listing']
    mismatched_attrs = property_info['mismatched_attributes']
    
    logger.info(f"\n物件ID {property.id} を分離中...")
    logger.info(f"  元の建物: ID={old_building.id}, {old_building.normalized_name}")
    logger.info(f"  属性の不一致: {', '.join(mismatched_attrs)}")
    
    # 新しい建物を作成
    new_building = create_new_building_for_property(session, property, listing)
    
    # 物件の建物IDを更新
    old_building_id = property.building_id
    property.building_id = new_building.id
    
    # 物件分離履歴を記録
    history_entry = PropertyMergeHistory(
        action='split',
        source_property_ids=[property.id],
        target_property_id=property.id,
        old_building_id=old_building_id,
        new_building_id=new_building.id,
        details={
            'reason': '建物属性の不一致による分離',
            'mismatched_attributes': mismatched_attrs
        }
    )
    session.add(history_entry)
    
    logger.info(f"  物件を新建物に移動: 建物ID {old_building_id} → {new_building.id}")
    
    return old_building_id

def update_building_attributes(session, building_id: int):
    """建物の属性を多数決で再計算"""
    
    logger.info(f"\n建物ID {building_id} の属性を再計算中...")
    
    # BuildingAttributeAggregatorを使用して属性を集計
    aggregator = BuildingAttributeAggregator(session)
    
    # 建物に紐付く全物件の掲載情報から属性を集計
    attributes = aggregator.aggregate_building_attributes(building_id)
    
    if attributes:
        building = session.query(Building).get(building_id)
        if building:
            # 属性を更新
            updated = []
            
            if attributes.get('total_floors') and building.total_floors != attributes['total_floors']:
                old_value = building.total_floors
                building.total_floors = attributes['total_floors']
                updated.append(f"総階数: {old_value} → {attributes['total_floors']}")
            
            if attributes.get('built_year') and building.built_year != attributes['built_year']:
                old_value = building.built_year
                building.built_year = attributes['built_year']
                updated.append(f"築年: {old_value} → {attributes['built_year']}")
            
            if attributes.get('built_month') and building.built_month != attributes['built_month']:
                old_value = building.built_month
                building.built_month = attributes['built_month']
                updated.append(f"築月: {old_value} → {attributes['built_month']}")
            
            if attributes.get('total_units') and building.total_units != attributes['total_units']:
                old_value = building.total_units
                building.total_units = attributes['total_units']
                updated.append(f"総戸数: {old_value} → {attributes['total_units']}")
            
            if updated:
                logger.info(f"  更新内容: {', '.join(updated)}")
            else:
                logger.info(f"  更新なし（属性に変更なし）")
    
    # 建物名も多数決で再計算
    name_aggregator = BuildingNameAggregator(session)
    new_name = name_aggregator.get_majority_building_name(building_id)
    
    if new_name:
        building = session.query(Building).get(building_id)
        if building and building.normalized_name != new_name:
            old_name = building.normalized_name
            building.normalized_name = new_name
            logger.info(f"  建物名更新: {old_name} → {new_name}")

def main():
    """メイン処理"""
    
    session = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("品川区・目黒区の属性不一致物件の分離処理")
        logger.info("=" * 60)
        
        # 1. 属性が異なる物件を検出
        mismatched_properties = find_mismatched_properties(session)
        
        if not mismatched_properties:
            logger.info("属性が異なる物件は見つかりませんでした。")
            return
        
        # 確認メッセージ
        logger.info(f"\n{len(mismatched_properties)}件の物件を分離します。")
        logger.info("処理を続行しますか？ (yes/no): ", end="")
        
        # Docker環境では自動的にyes
        if os.environ.get('DOCKER_ENV'):
            response = 'yes'
            logger.info("yes (Docker環境)")
        else:
            response = input().strip().lower()
        
        if response != 'yes':
            logger.info("処理をキャンセルしました。")
            return
        
        # 2. 各物件を分離
        affected_buildings = set()
        
        for property_info in mismatched_properties:
            old_building_id = separate_property(session, property_info)
            affected_buildings.add(old_building_id)
        
        # 3. 影響を受けた建物の属性を再計算
        logger.info("\n" + "=" * 60)
        logger.info("建物属性の再計算")
        logger.info("=" * 60)
        
        for building_id in affected_buildings:
            update_building_attributes(session, building_id)
        
        # コミット
        session.commit()
        
        logger.info("\n" + "=" * 60)
        logger.info("処理完了")
        logger.info(f"分離した物件数: {len(mismatched_properties)}件")
        logger.info(f"更新した建物数: {len(affected_buildings)}件")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    # Docker環境フラグを設定
    os.environ['DOCKER_ENV'] = '1'
    main()