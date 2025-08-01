#!/usr/bin/env python3
"""
canonical_nameを正しく再生成するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.scrapers.suumo_scraper import SuumoScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_canonical_names():
    """すべての建物のcanonical_nameを再生成"""
    session = SessionLocal()
    scraper = SuumoScraper()  # 具体的なスクレイパーを使用（メソッドは共通）
    
    try:
        # すべての建物を取得
        buildings = session.query(Building).all()
        total = len(buildings)
        logger.info(f"建物総数: {total}")
        
        updated_count = 0
        for i, building in enumerate(buildings, 1):
            if i % 100 == 0:
                logger.info(f"進捗: {i}/{total}")
            
            # canonical_nameを再生成
            new_canonical_name = scraper.get_search_key_for_building(building.normalized_name)
            
            # 変更が必要な場合のみ更新
            if building.canonical_name != new_canonical_name:
                old_value = building.canonical_name
                building.canonical_name = new_canonical_name
                updated_count += 1
                
                if updated_count <= 10:  # 最初の10件は詳細表示
                    logger.info(f"更新: {building.normalized_name}")
                    logger.info(f"  旧: {old_value}")
                    logger.info(f"  新: {new_canonical_name}")
        
        session.commit()
        logger.info(f"更新完了: {updated_count}件のcanonical_nameを修正")
        
    except Exception as e:
        logger.error(f"エラー: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    fix_canonical_names()