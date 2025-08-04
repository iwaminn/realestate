#!/usr/bin/env python3
"""
すべての建物の正規化された住所を再生成
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
from app.utils.address_normalizer import AddressNormalizer
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_normalized_addresses():
    """すべての建物の正規化された住所を更新"""
    session = SessionLocal()
    normalizer = AddressNormalizer()
    
    try:
        # すべての建物を取得
        buildings = session.query(Building).filter(Building.address.isnot(None)).all()
        logger.info(f"{len(buildings)}件の建物の住所を正規化します...")
        
        updated_count = 0
        for i, building in enumerate(buildings, 1):
            try:
                new_normalized = normalizer.normalize_for_comparison(building.address)
                
                # 変更があった場合のみ更新
                if building.normalized_address != new_normalized:
                    old_normalized = building.normalized_address
                    building.normalized_address = new_normalized
                    updated_count += 1
                    
                    # デバッグ出力（最初の10件と「六」を含む住所）
                    if updated_count <= 10 or '六' in building.address:
                        logger.info(f"ID {building.id}: {building.normalized_name}")
                        logger.info(f"  Address: {building.address}")
                        logger.info(f"  Old: {old_normalized}")
                        logger.info(f"  New: {new_normalized}")
                
                # 100件ごとにコミット
                if i % 100 == 0:
                    session.commit()
                    logger.info(f"進捗: {i}/{len(buildings)} ({updated_count}件更新)")
                    
            except Exception as e:
                logger.error(f"建物ID {building.id} の処理中にエラー: {e}")
                continue
        
        # 最終コミット
        session.commit()
        
        logger.info(f"\n=== 完了 ===")
        logger.info(f"総建物数: {len(buildings)}")
        logger.info(f"更新件数: {updated_count}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    update_normalized_addresses()