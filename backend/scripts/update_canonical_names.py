#!/usr/bin/env python
"""
BuildingListingNameテーブルのcanonical_nameを正しい形式に更新するスクリプト

現在: canonical_name = "白金ザ スカイ"（スペースあり）
修正: canonical_name = "白金ザスカイ"（スペース・記号なし、ひらがな→カタカナ）
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import BuildingListingName, Building
from backend.app.scrapers.data_normalizer import canonicalize_building_name
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_canonical_names():
    """canonical_nameを正しい形式に更新"""
    
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # すべてのBuildingListingNameエントリを取得
        entries = session.query(BuildingListingName).all()
        
        logger.info(f"更新対象: {len(entries)}件")
        
        updated_count = 0
        for entry in entries:
            # 新しいcanonical_nameを計算
            new_canonical = canonicalize_building_name(entry.listing_name)
            
            # 変更が必要な場合のみ更新
            if entry.canonical_name != new_canonical:
                old_canonical = entry.canonical_name
                entry.canonical_name = new_canonical
                updated_count += 1
                
                if updated_count <= 10:  # 最初の10件だけログ出力
                    logger.info(f"更新: {entry.listing_name}")
                    logger.info(f"  旧: {old_canonical}")
                    logger.info(f"  新: {new_canonical}")
        
        # 建物のnormalized_nameも更新
        buildings = session.query(Building).all()
        logger.info(f"\n建物normalized_name更新対象: {len(buildings)}件")
        
        building_updated = 0
        for building in buildings:
            # canonical形式も生成しておく（検索用）
            new_canonical = canonicalize_building_name(building.normalized_name)
            # ここではnormalized_nameは変更しない（表示用なので）
            # 必要に応じて別カラムを追加することも検討
            
        session.commit()
        logger.info(f"\n更新完了: {updated_count}件のcanonical_nameを更新しました")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    logger.info("=" * 60)
    logger.info("canonical_nameの更新を開始")
    logger.info("=" * 60)
    
    update_canonical_names()


if __name__ == "__main__":
    main()