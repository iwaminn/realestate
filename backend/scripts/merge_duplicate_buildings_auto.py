#!/usr/bin/env python3
"""
重複建物を自動統合するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Building, MasterProperty, BuildingAlias
from app.utils.building_normalizer import BuildingNameNormalizer
from app.database import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def merge_shirogane_the_sky():
    """白金ザスカイE棟の重複を統合"""
    session = SessionLocal()
    normalizer = BuildingNameNormalizer()
    
    try:
        # 白金ザスカイE棟関連の建物を検索
        buildings = session.query(Building).filter(
            Building.normalized_name.like('%白金%スカイ%E%')
        ).all()
        
        logger.info(f"白金ザスカイE棟関連の建物: {len(buildings)}件")
        for b in buildings:
            logger.info(f"  - {b.normalized_name} (ID: {b.id})")
        
        if len(buildings) <= 1:
            logger.info("統合の必要はありません")
            return
        
        # 正規化して同じものをグループ化
        normalized_groups = {}
        for building in buildings:
            normalized = normalizer.normalize(building.normalized_name)
            if normalized not in normalized_groups:
                normalized_groups[normalized] = []
            normalized_groups[normalized].append(building)
        
        # 統合実行
        for normalized_name, group in normalized_groups.items():
            if len(group) <= 1:
                continue
                
            logger.info(f"\n統合グループ: {normalized_name}")
            
            # 主建物を選択（情報が充実しているもの）
            primary = max(group, key=lambda b: (
                bool(b.address),
                b.built_year is not None,
                b.total_floors is not None,
                -b.id
            ))
            
            logger.info(f"主建物: {primary.normalized_name} (ID: {primary.id})")
            
            # 他の建物を統合
            for building in group:
                if building.id == primary.id:
                    continue
                    
                logger.info(f"  統合元: {building.normalized_name} (ID: {building.id})")
                
                # 情報をマージ
                if not primary.address and building.address:
                    primary.address = building.address
                if not primary.built_year and building.built_year:
                    primary.built_year = building.built_year
                if not primary.total_floors and building.total_floors:
                    primary.total_floors = building.total_floors
                
                # エイリアスを移動（削除前に確実に処理）
                aliases = session.query(BuildingAlias).filter_by(building_id=building.id).all()
                for alias in aliases:
                    existing = session.query(BuildingAlias).filter_by(
                        building_id=primary.id,
                        alias_name=alias.alias_name
                    ).first()
                    if not existing:
                        # 新しいエイリアスを作成して既存のものは削除
                        new_alias = BuildingAlias(
                            building_id=primary.id,
                            alias_name=alias.alias_name,
                            source=alias.source
                        )
                        session.add(new_alias)
                        session.delete(alias)
                    else:
                        # 重複するエイリアスは削除
                        session.delete(alias)
                
                # 元の建物名をエイリアスとして追加
                if building.normalized_name != primary.normalized_name:
                    existing = session.query(BuildingAlias).filter_by(
                        building_id=primary.id,
                        alias_name=building.normalized_name
                    ).first()
                    if not existing:
                        new_alias = BuildingAlias(
                            building_id=primary.id,
                            alias_name=building.normalized_name,
                            source='MERGE'
                        )
                        session.add(new_alias)
                
                # マスター物件を移動
                count = session.query(MasterProperty).filter_by(
                    building_id=building.id
                ).update({MasterProperty.building_id: primary.id})
                logger.info(f"    {count}件のマスター物件を移動")
                
                # 建物を削除
                session.delete(building)
            
            session.commit()
            logger.info("統合完了")
    
    except Exception as e:
        logger.error(f"エラー: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    merge_shirogane_the_sky()