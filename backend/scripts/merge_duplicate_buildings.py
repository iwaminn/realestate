#!/usr/bin/env python3
"""
重複建物を統合するスクリプト
中黒（・）の有無などの表記ゆれで重複登録された建物を統合
"""

import sys
import os
sys.path.insert(0, '/app')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.app.models import Building, MasterProperty, PropertyListing, BuildingAlias, BuildingExternalId, BuildingMergeHistory
from backend.app.utils.building_normalizer import BuildingNameNormalizer
import logging
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def find_duplicate_buildings(session, min_similarity=0.95):
    """高い類似度を持つ建物を見つける"""
    normalizer = BuildingNameNormalizer()
    
    # 全建物を取得
    buildings = session.query(Building).order_by(Building.normalized_name).all()
    logger.info(f"総建物数: {len(buildings)}")
    
    # 重複候補を検出
    duplicate_groups = {}
    processed_ids = set()
    
    for i, building1 in enumerate(buildings):
        if building1.id in processed_ids:
            continue
        
        candidates = []
        
        for j, building2 in enumerate(buildings[i+1:], i+1):
            if building2.id in processed_ids:
                continue
            
            # 類似度計算
            similarity = normalizer.calculate_similarity(
                building1.normalized_name, 
                building2.normalized_name
            )
            
            if similarity >= min_similarity:
                # 住所チェック（同じ区内か）
                same_district = True
                if building1.address and building2.address:
                    if '区' in building1.address and '区' in building2.address:
                        district1 = building1.address.split('区')[0]
                        district2 = building2.address.split('区')[0]
                        same_district = district1 == district2
                
                # 棟が異なる場合は除外
                comp1 = normalizer.extract_building_components(building1.normalized_name)
                comp2 = normalizer.extract_building_components(building2.normalized_name)
                if comp1['unit'] and comp2['unit'] and comp1['unit'] != comp2['unit']:
                    continue
                
                if same_district:
                    candidates.append({
                        'building': building2,
                        'similarity': similarity
                    })
                    processed_ids.add(building2.id)
        
        if candidates:
            # グループのキーとして正規化名を使用
            group_key = building1.normalized_name
            duplicate_groups[group_key] = [building1] + [c['building'] for c in candidates]
            processed_ids.add(building1.id)
    
    return duplicate_groups


def merge_buildings(session, buildings_to_merge):
    """複数の建物を1つに統合"""
    if len(buildings_to_merge) < 2:
        return None
    
    # 最も情報が充実している建物を主建物として選択
    # 優先順位: address > built_year > total_floors > 作成日時が古い
    primary_building = max(buildings_to_merge, key=lambda b: (
        bool(b.address),
        b.built_year is not None,
        b.total_floors is not None,
        -b.id  # IDが小さい（古い）ものを優先
    ))
    
    logger.info(f"主建物として選択: {primary_building.normalized_name} (ID: {primary_building.id})")
    
    # 他の建物の情報を主建物にマージ
    for building in buildings_to_merge:
        if building.id == primary_building.id:
            continue
            
        logger.info(f"  統合: {building.normalized_name} (ID: {building.id})")
        
        # 住所情報をマージ
        if not primary_building.address and building.address:
            primary_building.address = building.address
            
        # 築年をマージ
        if not primary_building.built_year and building.built_year:
            primary_building.built_year = building.built_year
            
        # 階数をマージ
        if not primary_building.total_floors and building.total_floors:
            primary_building.total_floors = building.total_floors
            
        # エイリアスをマージ
        aliases = session.query(BuildingAlias).filter_by(building_id=building.id).all()
        for alias in aliases:
            # 同じエイリアスが既に存在しない場合のみ追加
            existing = session.query(BuildingAlias).filter_by(
                building_id=primary_building.id,
                alias_name=alias.alias_name
            ).first()
            if not existing:
                # 新しいエイリアスオブジェクトを作成
                new_alias = BuildingAlias(
                    building_id=primary_building.id,
                    alias_name=alias.alias_name,
                    source=alias.source
                )
                session.add(new_alias)
                logger.info(f"    エイリアス移動: {alias.alias_name}")
            # 既存のエイリアスは削除
            session.delete(alias)
        
        # 元の建物名もエイリアスとして追加
        if building.normalized_name != primary_building.normalized_name:
            existing = session.query(BuildingAlias).filter_by(
                building_id=primary_building.id,
                alias_name=building.normalized_name
            ).first()
            if not existing:
                new_alias = BuildingAlias(
                    building_id=primary_building.id,
                    alias_name=building.normalized_name,
                    source='MERGE'
                )
                session.add(new_alias)
                logger.info(f"    新規エイリアス追加: {building.normalized_name}")
        
        # マスター物件の建物IDを更新
        master_properties = session.query(MasterProperty).filter_by(building_id=building.id).all()
        for mp in master_properties:
            mp.building_id = primary_building.id
        logger.info(f"    {len(master_properties)}件のマスター物件を移動")
        
        # セッションをフラッシュして変更を反映
        session.flush()
        
        # 削除対象の建物を削除
        session.delete(building)
    
    session.commit()
    return primary_building


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 重複建物を検索
        logger.info("重複建物を検索中...")
        duplicates = find_duplicate_buildings(session)
        
        if not duplicates:
            logger.info("重複建物は見つかりませんでした")
            return
        
        logger.info(f"{len(duplicates)}グループの重複建物が見つかりました")
        
        # 全ての重複グループを表示（最大20グループ）
        count = 0
        for group_name, buildings in duplicates.items():
            if count >= 20:
                logger.info(f"\n...他{len(duplicates) - 20}グループ")
                break
                
            print(f"\nグループ {count + 1}: {group_name}")
            for b in buildings:
                print(f"  - {b.normalized_name} (ID: {b.id}, 住所: {b.address or '住所なし'})")
            count += 1
        
        # 自動統合モード（確認なし）
        if '--auto' in sys.argv:
            logger.info("\n自動統合モードで実行します...")
            total_merged = 0
            for group_name, buildings in duplicates.items():
                if len(buildings) > 1:
                    logger.info(f"\n統合中: {group_name} ({len(buildings)}件)")
                    merge_buildings(session, buildings)
                    total_merged += len(buildings) - 1
            logger.info(f"\n合計 {total_merged} 件の建物を統合しました")
        else:
            # 対話モード
            response = input(f"\n{len(duplicates)}グループの重複が見つかりました。すべて統合しますか？ (y/n/auto): ")
            if response.lower() == 'auto':
                total_merged = 0
                for group_name, buildings in duplicates.items():
                    if len(buildings) > 1:
                        logger.info(f"\n統合中: {group_name} ({len(buildings)}件)")
                        merge_buildings(session, buildings)
                        total_merged += len(buildings) - 1
                logger.info(f"\n合計 {total_merged} 件の建物を統合しました")
            elif response.lower() == 'y':
                # 個別確認モード
                for group_name, buildings in duplicates.items():
                    logger.info(f"\n統合対象: {group_name}")
                    for b in buildings:
                        logger.info(f"  - {b.normalized_name} (ID: {b.id}, 住所: {b.address or '住所なし'})")
                    
                    response = input("\nこれらの建物を統合しますか？ (y/n): ")
                    if response.lower() == 'y':
                        merge_buildings(session, buildings)
                        logger.info("統合完了")
                    else:
                        logger.info("スキップ")
            else:
                logger.info("統合をキャンセルしました")
    
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    # ヘルプメッセージ
    if '--help' in sys.argv:
        print("""使い方:
    python merge_duplicate_buildings.py          # 対話モード（個別確認）
    python merge_duplicate_buildings.py --auto   # 自動統合モード（確認なし）
        """)
        sys.exit(0)
    
    main()