#!/usr/bin/env python3
"""
建物属性が異なる物件を検出し、適切な建物に再紐付けするスクリプト

築年月、総階数、総戸数のうち2つ以上が異なる物件を検出し、
現在の自動紐付けロジックに従って適切な建物を探すか、新規作成します。
"""

import sys
import os
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
from datetime import datetime

# Dockerコンテナ内のパスを追加
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/backend')

from backend.app.database import SessionLocal
from backend.app.models import (
    Building, MasterProperty, PropertyListing, 
    BuildingListingName, PropertyMergeHistory
)
from backend.app.utils.address_normalizer import AddressNormalizer
from backend.app.scrapers.suumo_scraper import SuumoScraper
from sqlalchemy import func, and_, or_, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PropertyRealigner:
    """物件の再紐付け処理を行うクラス"""
    
    def __init__(self, session):
        self.session = session
        self.addr_normalizer = AddressNormalizer()
        # SuumoScraperのインスタンスを利用して建物検索メソッドを使用
        self.scraper = SuumoScraper()
        self.scraper.session = session
        self.scraper.logger = logger
        
    def check_attribute_mismatch(self, building: Building, property_listing: PropertyListing) -> Tuple[bool, List[str], int]:
        """
        建物と物件の属性を比較し、2つ以上異なるかチェック
        
        Returns:
            (is_mismatch, mismatched_attributes, mismatch_count): 
            2つ以上異なる場合True、異なる属性のリスト、不一致数
        """
        mismatched = []
        comparable_count = 0
        mismatch_count = 0
        
        # 総階数の比較
        if (building.total_floors is not None and 
            property_listing.listing_total_floors is not None):
            comparable_count += 1
            if building.total_floors != property_listing.listing_total_floors:
                mismatched.append(f"総階数: 建物={building.total_floors}, 物件={property_listing.listing_total_floors}")
                mismatch_count += 1
        
        # 築年月の比較
        if (building.built_year is not None and 
            property_listing.listing_built_year is not None):
            comparable_count += 1
            if building.built_year != property_listing.listing_built_year:
                mismatched.append(f"築年: 建物={building.built_year}, 物件={property_listing.listing_built_year}")
                mismatch_count += 1
            # 年が一致している場合のみ月も比較
            elif (building.built_month is not None and 
                  property_listing.listing_built_month is not None and
                  building.built_month != property_listing.listing_built_month):
                mismatched.append(f"築月: 建物={building.built_month}月, 物件={property_listing.listing_built_month}月")
                # 築月の不一致は築年と別カウントしない（築年月で1つの属性）
        
        # 総戸数の比較
        if (building.total_units is not None and 
            property_listing.listing_total_units is not None):
            comparable_count += 1
            if building.total_units != property_listing.listing_total_units:
                mismatched.append(f"総戸数: 建物={building.total_units}, 物件={property_listing.listing_total_units}")
                mismatch_count += 1
        
        # 2つ以上の属性が比較可能で、そのうち2つ以上が異なる場合
        is_mismatch = comparable_count >= 2 and mismatch_count >= 2
        
        return is_mismatch, mismatched, mismatch_count
    
    def find_mismatched_properties(self, area_filter: str = None) -> List[Dict]:
        """属性が異なる物件を検出"""
        
        logger.info("属性が異なる物件を検索中...")
        
        # 建物を取得（エリアフィルター適用）
        query = self.session.query(Building)
        if area_filter:
            query = query.filter(Building.address.like(f'%{area_filter}%'))
        
        buildings = query.all()
        logger.info(f"対象建物数: {len(buildings)}件")
        
        mismatched_properties = []
        checked_count = 0
        
        for building in buildings:
            # この建物に紐付く物件を取得
            properties = self.session.query(MasterProperty).filter(
                MasterProperty.building_id == building.id
            ).all()
            
            for property in properties:
                checked_count += 1
                if checked_count % 100 == 0:
                    logger.info(f"  {checked_count}件チェック済み...")
                
                # 各物件の掲載情報を取得（アクティブなもののみ）
                listings = self.session.query(PropertyListing).filter(
                    PropertyListing.master_property_id == property.id,
                    PropertyListing.is_active == True
                ).all()
                
                # 各掲載情報の属性をチェック
                for listing in listings:
                    is_mismatch, mismatched_attrs, mismatch_count = self.check_attribute_mismatch(building, listing)
                    
                    if is_mismatch:
                        mismatched_properties.append({
                            'property': property,
                            'building': building,
                            'listing': listing,
                            'mismatched_attributes': mismatched_attrs,
                            'mismatch_count': mismatch_count
                        })
                        break  # 1つの掲載で不一致が見つかれば十分
        
        logger.info(f"属性が異なる物件数: {len(mismatched_properties)}件")
        return mismatched_properties
    
    def find_suitable_building(self, listing: PropertyListing) -> Optional[Building]:
        """
        物件に適した既存建物を探す（現在の自動紐付けロジックを使用）
        """
        # 建物名と住所を取得
        building_name = listing.listing_building_name or ""
        address = listing.listing_address
        
        # 駅情報などの無効な建物名をスキップ
        station_patterns = ['駅', '徒歩', '分歩', 'バス', '線']
        if any(pattern in building_name for pattern in station_patterns):
            building_name = f"物件_{listing.master_property_id}_建物"
        
        # BaseScraperのget_or_create_buildingメソッドを使用
        # ただし、新規作成はせずに既存建物の検索のみ行う
        try:
            # find_existing_building_by_keyメソッドを使用
            from backend.app.scrapers.data_normalizer import DataNormalizer
            normalizer = DataNormalizer()
            clean_building_name, _ = normalizer.extract_room_number(building_name)
            search_key = self.scraper.get_search_key_for_building(clean_building_name)
            
            # 既存建物を検索
            existing_building = self.scraper.find_existing_building_by_key(
                search_key=search_key,
                address=address,
                total_floors=listing.listing_total_floors,
                built_year=listing.listing_built_year,
                built_month=listing.listing_built_month,
                total_units=listing.listing_total_units
            )
            
            return existing_building
            
        except Exception as e:
            logger.debug(f"既存建物の検索中にエラー: {e}")
            return None
    
    def create_new_building(self, property: MasterProperty, listing: PropertyListing) -> Building:
        """物件用の新しい建物を作成"""
        
        # 建物名を取得（駅情報でもそのまま使用）
        building_name = listing.listing_building_name
        
        # 建物名が全くない場合のみログを出力
        if not building_name:
            logger.warning(f"物件ID {property.id} の建物名が取得できていません")
        
        # 正規化された住所
        normalized_addr = None
        if listing.listing_address:
            normalized_addr = self.addr_normalizer.normalize_for_comparison(listing.listing_address)
        
        # 検索キーを生成
        search_key = self.scraper.get_search_key_for_building(building_name)
        
        # 新しい建物を作成
        new_building = Building(
            normalized_name=building_name,
            canonical_name=search_key,
            address=listing.listing_address,
            normalized_address=normalized_addr,
            built_year=listing.listing_built_year,
            built_month=listing.listing_built_month,
            total_floors=listing.listing_total_floors,
            total_units=listing.listing_total_units,
            construction_type=listing.listing_building_structure
        )
        
        self.session.add(new_building)
        self.session.flush()
        
        logger.info(f"  新規建物作成: ID={new_building.id}, 名前={new_building.normalized_name}")
        
        # BuildingListingNameに登録（駅情報でない場合のみ）
        if listing.listing_building_name and not any(
            pattern in listing.listing_building_name 
            for pattern in station_patterns
        ):
            from backend.app.scrapers.data_normalizer import canonicalize_building_name
            
            listing_name_entry = BuildingListingName(
                building_id=new_building.id,
                listing_name=listing.listing_building_name,
                canonical_name=canonicalize_building_name(listing.listing_building_name),
                source_sites=listing.source_site,
                occurrence_count=1,
                first_seen_at=datetime.now(),
                last_seen_at=datetime.now()
            )
            self.session.add(listing_name_entry)
        
        return new_building
    
    def realign_property(self, property_info: Dict) -> int:
        """物件を適切な建物に再紐付け"""
        
        property = property_info['property']
        old_building = property_info['building']
        listing = property_info['listing']
        mismatched_attrs = property_info['mismatched_attributes']
        
        logger.info(f"\n物件ID {property.id} を再紐付け中...")
        logger.info(f"  現在の建物: ID={old_building.id}, {old_building.normalized_name}")
        logger.info(f"  属性の不一致: {', '.join(mismatched_attrs)}")
        
        # 適切な既存建物を探す
        suitable_building = self.find_suitable_building(listing)
        
        if suitable_building:
            # 既存の適切な建物が見つかった
            logger.info(f"  適切な既存建物を発見: ID={suitable_building.id}, {suitable_building.normalized_name}")
            new_building = suitable_building
        else:
            # 適切な建物が見つからないので新規作成
            logger.info(f"  適切な既存建物が見つからないため新規作成")
            new_building = self.create_new_building(property, listing)
        
        # 物件の建物IDを更新
        old_building_id = property.building_id
        property.building_id = new_building.id
        
        # 再紐付けの履歴を記録（PropertyMergeHistoryは物件統合用なので、別の方法で記録）
        # ログに詳細を記録
        import json
        realign_details = {
            'property_id': property.id,
            'old_building_id': old_building_id,
            'old_building_name': old_building.normalized_name,
            'new_building_id': new_building.id,
            'new_building_name': new_building.normalized_name,
            'reason': '建物属性の不一致による再紐付け',
            'mismatched_attributes': mismatched_attrs,
            'realigned_to': 'existing_building' if suitable_building else 'new_building',
            'timestamp': datetime.now().isoformat()
        }
        logger.info(f"  再紐付け詳細: {json.dumps(realign_details, ensure_ascii=False)}")
        
        logger.info(f"  物件を建物に再紐付け: 建物ID {old_building_id} → {new_building.id}")
        
        return old_building_id
    
    def update_building_attributes(self, building_id: int):
        """建物の属性を多数決で再計算"""
        
        logger.info(f"\n建物ID {building_id} の属性を再計算中...")
        
        # 建物に紐付く全物件の掲載情報から属性を集計
        result = self.session.query(
            func.mode().within_group(PropertyListing.listing_total_floors).label('total_floors'),
            func.mode().within_group(PropertyListing.listing_built_year).label('built_year'),
            func.mode().within_group(PropertyListing.listing_built_month).label('built_month'),
            func.mode().within_group(PropertyListing.listing_total_units).label('total_units')
        ).select_from(PropertyListing).join(
            MasterProperty
        ).filter(
            MasterProperty.building_id == building_id,
            PropertyListing.is_active == True
        ).first()
        
        if result:
            building = self.session.query(Building).get(building_id)
            if building:
                # 属性を更新
                updated = []
                
                if result.total_floors and building.total_floors != result.total_floors:
                    old_value = building.total_floors
                    building.total_floors = result.total_floors
                    updated.append(f"総階数: {old_value} → {result.total_floors}")
                
                if result.built_year and building.built_year != result.built_year:
                    old_value = building.built_year
                    building.built_year = result.built_year
                    updated.append(f"築年: {old_value} → {result.built_year}")
                
                if result.built_month and building.built_month != result.built_month:
                    old_value = building.built_month
                    building.built_month = result.built_month
                    updated.append(f"築月: {old_value} → {result.built_month}")
                
                if result.total_units and building.total_units != result.total_units:
                    old_value = building.total_units
                    building.total_units = result.total_units
                    updated.append(f"総戸数: {old_value} → {result.total_units}")
                
                if updated:
                    logger.info(f"  更新内容: {', '.join(updated)}")
                else:
                    logger.info(f"  更新なし（属性に変更なし）")

def main():
    """メイン処理"""
    
    session = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("建物属性不一致物件の再紐付け処理")
        logger.info("=" * 60)
        
        # 処理対象エリアの選択
        logger.info("\n処理対象を選択してください:")
        logger.info("1. 全エリア")
        logger.info("2. 品川区のみ")
        logger.info("3. 目黒区のみ")
        logger.info("4. 品川区と目黒区")
        
        # Docker環境では自動的に品川区と目黒区
        if os.environ.get('DOCKER_ENV'):
            choice = '4'
            logger.info("選択: 4 (Docker環境)")
        else:
            choice = input("選択 (1-4): ").strip()
        
        area_filter = None
        if choice == '2':
            area_filter = '品川区'
        elif choice == '3':
            area_filter = '目黒区'
        elif choice == '4':
            # 品川区と目黒区を別々に処理
            pass  # 後で特別処理
        
        realigner = PropertyRealigner(session)
        
        # 属性が異なる物件を検出
        if choice == '4':
            # 品川区と目黒区
            mismatched_properties = []
            for area in ['品川区', '目黒区']:
                logger.info(f"\n{area}の物件を検索中...")
                area_properties = realigner.find_mismatched_properties(area)
                mismatched_properties.extend(area_properties)
        else:
            mismatched_properties = realigner.find_mismatched_properties(area_filter)
        
        if not mismatched_properties:
            logger.info("属性が異なる物件は見つかりませんでした。")
            return
        
        # 不一致の度合いでソート（不一致が多いものから処理）
        mismatched_properties.sort(key=lambda x: x['mismatch_count'], reverse=True)
        
        # 確認メッセージ
        logger.info(f"\n{len(mismatched_properties)}件の物件を再紐付けします。")
        logger.info("処理を続行しますか？ (yes/no): ")
        
        # Docker環境では自動的にyes
        if os.environ.get('DOCKER_ENV'):
            response = 'yes'
            logger.info("yes (Docker環境)")
        else:
            response = input().strip().lower()
        
        if response != 'yes':
            logger.info("処理をキャンセルしました。")
            return
        
        # 各物件を再紐付け
        affected_buildings = set()
        
        for i, property_info in enumerate(mismatched_properties):
            logger.info(f"\n進捗: {i+1}/{len(mismatched_properties)}")
            old_building_id = realigner.realign_property(property_info)
            affected_buildings.add(old_building_id)
            
            # 定期的にコミット
            if (i + 1) % 10 == 0:
                session.commit()
                logger.info(f"  {i+1}件処理済み、中間コミット実行")
        
        # 影響を受けた建物の属性を再計算
        logger.info("\n" + "=" * 60)
        logger.info("建物属性の再計算")
        logger.info("=" * 60)
        
        for building_id in affected_buildings:
            realigner.update_building_attributes(building_id)
        
        # 最終コミット
        session.commit()
        
        logger.info("\n" + "=" * 60)
        logger.info("処理完了")
        logger.info(f"再紐付けした物件数: {len(mismatched_properties)}件")
        logger.info(f"更新した建物数: {len(affected_buildings)}件")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    # Docker環境フラグを設定
    os.environ['DOCKER_ENV'] = '1'
    main()