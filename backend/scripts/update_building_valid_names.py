#!/usr/bin/env python3
"""
既存建物のis_valid_nameフラグを判定・更新するスクリプト
広告文のみの建物名を検出してフラグを更新する
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.scrapers.base_scraper import extract_building_name_from_ad_text
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_building_valid_names():
    """建物のis_valid_nameフラグを更新"""
    
    db = SessionLocal()
    
    try:
        # すべての建物を取得
        buildings = db.query(Building).all()
        
        logger.info(f"全{len(buildings)}件の建物を確認します...")
        
        invalid_count = 0
        already_invalid_count = 0
        valid_count = 0
        updated_count = 0
        
        for building in buildings:
            # normalized_nameから広告文を除去
            extracted_name = extract_building_name_from_ad_text(building.normalized_name)
            
            if not extracted_name:
                # 広告文のみの建物名
                if building.is_valid_name:
                    # フラグをfalseに更新
                    building.is_valid_name = False
                    updated_count += 1
                    logger.info(f"  広告文建物を検出: ID={building.id}, 名前='{building.normalized_name}'")
                else:
                    already_invalid_count += 1
                invalid_count += 1
            else:
                # 有効な建物名
                if not building.is_valid_name:
                    # フラグをtrueに更新（多数決処理等で正しい名前に更新された建物）
                    building.is_valid_name = True
                    updated_count += 1
                    logger.info(f"  有効な建物名に修正済み: ID={building.id}, 名前='{building.normalized_name}'")
                valid_count += 1
        
        # コミット
        db.commit()
        
        logger.info(f"\n処理完了:")
        logger.info(f"  有効な建物名: {valid_count}件")
        logger.info(f"  無効な建物名（広告文）: {invalid_count}件")
        logger.info(f"    うち既に無効フラグ設定済み: {already_invalid_count}件")
        logger.info(f"  フラグを更新: {updated_count}件")
        
        # 無効な建物名の例を表示
        if invalid_count > 0:
            logger.info(f"\n無効な建物名の例（最大10件）:")
            invalid_buildings = db.query(Building).filter(
                Building.is_valid_name == False
            ).limit(10).all()
            
            for building in invalid_buildings:
                property_count = len(building.properties)
                logger.info(f"  - ID={building.id}: '{building.normalized_name}' (物件数: {property_count})")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    update_building_valid_names()