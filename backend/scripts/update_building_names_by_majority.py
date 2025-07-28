#!/usr/bin/env python3
"""
全ての建物名を多数決で更新するバッチスクリプト
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_all_building_names():
    """全ての建物名を多数決で更新"""
    session = SessionLocal()
    updater = MajorityVoteUpdater(session)
    
    try:
        # 全建物を取得
        buildings = session.query(Building).all()
        total_buildings = len(buildings)
        updated_count = 0
        
        print(f"建物名の多数決更新を開始します。対象建物数: {total_buildings}")
        
        for i, building in enumerate(buildings, 1):
            if i % 100 == 0:
                print(f"進行状況: {i}/{total_buildings}")
                session.commit()  # 定期的にコミット
            
            # 建物名を多数決で更新
            if updater.update_building_name_by_majority(building.id):
                updated_count += 1
        
        # 最終コミット
        session.commit()
        
        print(f"\n更新完了:")
        print(f"- 対象建物数: {total_buildings}")
        print(f"- 更新された建物数: {updated_count}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def update_specific_building(building_id: int):
    """特定の建物の名前を多数決で更新"""
    session = SessionLocal()
    updater = MajorityVoteUpdater(session)
    
    try:
        building = session.query(Building).filter_by(id=building_id).first()
        if not building:
            print(f"建物ID {building_id} が見つかりません。")
            return
        
        print(f"建物情報:")
        print(f"- ID: {building.id}")
        print(f"- 現在の名前: {building.normalized_name}")
        print(f"- 住所: {building.address or '未設定'}")
        
        # 建物名を多数決で更新
        if updater.update_building_name_by_majority(building.id):
            session.commit()
            # 更新後の情報を再取得
            building = session.query(Building).filter_by(id=building_id).first()
            print(f"\n更新後の名前: {building.normalized_name}")
        else:
            print("\n更新は不要でした。")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="建物名を多数決で更新")
    parser.add_argument(
        "--building-id", 
        type=int, 
        help="特定の建物IDのみ更新"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="実行をシミュレート（実際には更新しない）"
    )
    
    args = parser.parse_args()
    
    if args.building_id:
        update_specific_building(args.building_id)
    else:
        confirm = input("全ての建物名を多数決で更新しますか？ (yes/no): ")
        if confirm.lower() == "yes":
            update_all_building_names()
        else:
            print("キャンセルされました。")