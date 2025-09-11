#!/usr/bin/env python3
"""
建物の住所を多数決で更新するスクリプト
正規化された住所（半角数字）で統一
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
from app.utils.majority_vote_updater import MajorityVoteUpdater
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def update_building_addresses():
    """建物の住所を多数決で更新"""
    session = SessionLocal()
    updater = MajorityVoteUpdater(session)
    
    try:
        # すべての建物を取得
        buildings = session.query(Building).all()
        total_count = len(buildings)
        updated_count = 0
        
        logger.info(f"=== 建物住所の更新開始 ===")
        logger.info(f"対象建物数: {total_count}")
        
        for i, building in enumerate(buildings, 1):
            if i % 100 == 0:
                logger.info(f"進捗: {i}/{total_count}")
            
            try:
                # 建物に関連する掲載情報から住所を収集
                building_info = updater.collect_building_info_from_listings(building.id)
                
                if building_info['addresses']:
                    # 住所の多数決（正規化あり）
                    majority_address = updater.get_majority_value_with_normalization(
                        building_info['addresses'], 
                        building.address, 
                        value_type='address'
                    )
                    
                    if majority_address and majority_address != building.address:
                        old_address = building.address
                        building.address = majority_address
                        
                        # 正規化住所も更新
                        if hasattr(building, 'normalized_address'):
                            from app.utils.address_normalizer import AddressNormalizer
                            normalizer = AddressNormalizer()
                            building.normalized_address = normalizer.normalize_for_comparison(majority_address)
                        
                        updated_count += 1
                        
                        # 最初の10件は詳細をログ出力
                        if updated_count <= 10:
                            logger.info(f"建物ID {building.id} '{building.normalized_name}':")
                            logger.info(f"  旧住所: {old_address}")
                            logger.info(f"  新住所: {majority_address}")
                
                # 100件ごとにコミット
                if i % 100 == 0:
                    session.commit()
                    
            except Exception as e:
                logger.error(f"建物ID {building.id} の更新エラー: {e}")
                session.rollback()
                continue
        
        # 最終コミット
        session.commit()
        
        logger.info(f"=== 建物住所の更新完了 ===")
        logger.info(f"更新件数: {updated_count}/{total_count}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    update_building_addresses()