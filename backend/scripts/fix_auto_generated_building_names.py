#!/usr/bin/env python3
"""
自動生成された建物名を修正するスクリプト

「建物_」や「地域名建物_」という形式で自動生成された建物名を、
実際の掲載情報から取得した建物名に修正します。
"""

import sys
import os

# Dockerコンテナ内のパスを追加
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/backend')

from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty, PropertyListing
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_auto_generated_building_names():
    """自動生成された建物名を修正"""
    
    session = SessionLocal()
    
    try:
        logger.info("=" * 60)
        logger.info("自動生成された建物名の修正処理")
        logger.info("=" * 60)
        
        # 自動生成された建物名を持つ建物を検索
        auto_generated_buildings = session.query(Building).filter(
            Building.normalized_name.like('%建物_%')
        ).all()
        
        logger.info(f"\n自動生成された建物名を持つ建物: {len(auto_generated_buildings)}件")
        
        fixed_count = 0
        
        for building in auto_generated_buildings:
            logger.info(f"\n建物ID {building.id}: {building.normalized_name}")
            
            # この建物に紐付く物件の掲載情報から建物名を取得
            listing_names = session.query(
                PropertyListing.listing_building_name,
                func.count(PropertyListing.id).label('count')
            ).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building.id,
                PropertyListing.is_active == True,
                PropertyListing.listing_building_name.isnot(None)
            ).group_by(
                PropertyListing.listing_building_name
            ).order_by(
                func.count(PropertyListing.id).desc()
            ).all()
            
            if listing_names:
                # 最も多く出現する建物名を使用
                most_common_name = listing_names[0][0]
                count = listing_names[0][1]
                
                logger.info(f"  掲載情報から取得した建物名: {most_common_name} (出現回数: {count})")
                
                # 建物名を更新
                old_name = building.normalized_name
                building.normalized_name = most_common_name
                
                # canonical_nameも更新
                from backend.app.scrapers.data_normalizer import canonicalize_building_name
                building.canonical_name = canonicalize_building_name(most_common_name)
                
                logger.info(f"  建物名を更新: {old_name} → {most_common_name}")
                fixed_count += 1
            else:
                logger.info(f"  掲載情報から建物名を取得できませんでした")
        
        # コミット
        if fixed_count > 0:
            session.commit()
            logger.info(f"\n{fixed_count}件の建物名を修正しました")
        else:
            logger.info("\n修正対象の建物はありませんでした")
        
        logger.info("\n" + "=" * 60)
        logger.info("処理完了")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    fix_auto_generated_building_names()