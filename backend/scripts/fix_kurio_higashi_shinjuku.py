#!/usr/bin/env python3
"""
クリオ東新宿壱番館の誤った紐付けを修正するテストスクリプト
"""

import os
import sys
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty, PropertyListing

# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    session = SessionLocal()
    
    try:
        # クリオ東新宿壱番館の状況を確認
        logger.info("クリオ東新宿壱番館の現在の状況を確認...")
        
        result = session.execute(text("""
            SELECT 
                b.id as building_id,
                b.normalized_name,
                b.total_floors,
                b.total_units,
                b.built_year,
                mp.id as property_id,
                mp.floor_number,
                pl.source_site,
                pl.listing_total_floors,
                pl.listing_total_units,
                pl.listing_built_year
            FROM buildings b
            INNER JOIN master_properties mp ON mp.building_id = b.id
            INNER JOIN property_listings pl ON pl.master_property_id = mp.id
            WHERE b.normalized_name = 'クリオ東新宿壱番館'
                AND pl.is_active = true
            ORDER BY b.id, mp.id
        """))
        
        for row in result:
            logger.info(f"建物ID {row.building_id}: {row.total_floors}F/{row.total_units}戸/{row.built_year}年")
            logger.info(f"  物件ID {row.property_id} ({row.floor_number}階): "
                       f"掲載情報 {row.listing_total_floors}F/{row.listing_total_units}戸/"
                       f"{row.listing_built_year}年 ({row.source_site})")
        
        # 建物ID 4062の物件ID 6653を建物ID 4291に移動
        logger.info("\n誤った紐付けを修正...")
        
        # 物件ID 6653を取得
        property_6653 = session.query(MasterProperty).filter_by(id=6653).first()
        if property_6653 and property_6653.building_id == 4062:
            logger.info(f"物件ID 6653を建物ID 4062 → 4291に移動")
            property_6653.building_id = 4291
            session.commit()
            logger.info("移動完了")
        else:
            logger.info("物件ID 6653は既に正しく紐付けられています")
        
        # 建物属性を多数決で更新
        logger.info("\n建物属性を多数決で更新...")
        
        for building_id in [4062, 4291]:
            result = session.execute(text("""
                SELECT 
                    :building_id as building_id,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_total_floors) as majority_floors,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_total_units) as majority_units,
                    MODE() WITHIN GROUP (ORDER BY pl.listing_built_year) as majority_year
                FROM master_properties mp
                INNER JOIN property_listings pl ON pl.master_property_id = mp.id
                WHERE mp.building_id = :building_id
                    AND pl.is_active = true
            """), {'building_id': building_id}).first()
            
            if result:
                building = session.query(Building).get(building_id)
                if building:
                    updated = []
                    if result.majority_floors and building.total_floors != result.majority_floors:
                        updated.append(f"総階数: {building.total_floors} → {result.majority_floors}")
                        building.total_floors = result.majority_floors
                    if result.majority_units and building.total_units != result.majority_units:
                        updated.append(f"総戸数: {building.total_units} → {result.majority_units}")
                        building.total_units = result.majority_units
                    if result.majority_year and building.built_year != result.majority_year:
                        updated.append(f"築年: {building.built_year} → {result.majority_year}")
                        building.built_year = result.majority_year
                    
                    if updated:
                        logger.info(f"建物ID {building_id}: {', '.join(updated)}")
                        session.commit()
                    else:
                        logger.info(f"建物ID {building_id}: 更新不要")
        
        # 修正後の状況を確認
        logger.info("\n修正後の状況を確認...")
        
        result = session.execute(text("""
            SELECT 
                b.id as building_id,
                b.normalized_name,
                b.total_floors,
                b.total_units,
                b.built_year,
                COUNT(DISTINCT mp.id) as property_count,
                STRING_AGG(DISTINCT mp.floor_number::text, ', ' ORDER BY mp.floor_number::text) as floors
            FROM buildings b
            LEFT JOIN master_properties mp ON mp.building_id = b.id
            WHERE b.id IN (4062, 4291)
            GROUP BY b.id, b.normalized_name, b.total_floors, b.total_units, b.built_year
            ORDER BY b.id
        """))
        
        for row in result:
            logger.info(f"建物ID {row.building_id} ({row.normalized_name}): "
                       f"{row.total_floors}F/{row.total_units}戸/{row.built_year}年 "
                       f"- {row.property_count}物件 (階: {row.floors})")
        
        logger.info("\n処理完了")
        
    except Exception as e:
        logger.error(f"エラーが発生: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()