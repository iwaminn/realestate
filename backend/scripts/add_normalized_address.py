#!/usr/bin/env python3
"""
normalized_addressカラムの追加と既存データの正規化
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.utils.address_normalizer import AddressNormalizer
from sqlalchemy import text
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_normalized_address_column(session):
    """normalized_addressカラムを追加"""
    try:
        # カラムの存在確認
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'buildings' AND column_name = 'normalized_address'
        """))
        
        if result.fetchone() is None:
            # カラムを追加
            logger.info("normalized_addressカラムを追加します...")
            session.execute(text("""
                ALTER TABLE buildings 
                ADD COLUMN normalized_address VARCHAR(500)
            """))
            session.commit()
            logger.info("✓ カラムを追加しました")
            
            # インデックスを追加
            logger.info("インデックスを追加します...")
            session.execute(text("""
                CREATE INDEX idx_buildings_normalized_address 
                ON buildings(normalized_address)
            """))
            session.execute(text("""
                CREATE INDEX idx_buildings_canonical_normalized_addr 
                ON buildings(canonical_name, normalized_address)
            """))
            session.commit()
            logger.info("✓ インデックスを追加しました")
        else:
            logger.info("normalized_addressカラムは既に存在します")
            
    except Exception as e:
        logger.error(f"カラム追加エラー: {e}")
        session.rollback()
        raise


def normalize_existing_addresses(session):
    """既存の住所を正規化"""
    normalizer = AddressNormalizer()
    
    # 住所があってnormalized_addressが未設定の建物を取得
    buildings = session.query(Building).filter(
        Building.address.isnot(None),
        Building.address != '',
        Building.normalized_address.is_(None)
    ).all()
    
    logger.info(f"{len(buildings)}件の建物の住所を正規化します...")
    
    updated_count = 0
    for i, building in enumerate(buildings, 1):
        try:
            normalized = normalizer.normalize_for_comparison(building.address)
            building.normalized_address = normalized
            
            if i % 100 == 0:
                session.commit()
                logger.info(f"  {i}/{len(buildings)}件処理済み...")
                
            updated_count += 1
            
        except Exception as e:
            logger.error(f"エラー (建物ID: {building.id}): {e}")
            continue
    
    # 最後のコミット
    session.commit()
    logger.info(f"✓ {updated_count}件の住所を正規化しました")


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 1. カラムを追加
        add_normalized_address_column(session)
        
        # 2. 既存データを正規化
        normalize_existing_addresses(session)
        
        # 3. 統計情報を表示
        total_buildings = session.query(Building).count()
        with_address = session.query(Building).filter(
            Building.address.isnot(None), 
            Building.address != ''
        ).count()
        normalized = session.query(Building).filter(
            Building.normalized_address.isnot(None)
        ).count()
        
        logger.info("\n=== 統計情報 ===")
        logger.info(f"総建物数: {total_buildings}")
        logger.info(f"住所あり: {with_address}")
        logger.info(f"正規化済み: {normalized}")
        
    except Exception as e:
        logger.error(f"処理エラー: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()