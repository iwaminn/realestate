#!/usr/bin/env python3
"""
全建物の交通情報を再計算（路線名正規化対応）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.utils.majority_vote_updater import MajorityVoteUpdater
from app.models import Building

db = SessionLocal()
try:
    # 交通情報を持つすべての建物を取得
    buildings = db.query(Building).filter(
        Building.station_info.isnot(None),
        Building.station_info != ''
    ).order_by(Building.id).all()

    print(f"交通情報を持つ建物: {len(buildings)}件")
    print("=" * 80)
    print()

    updater = MajorityVoteUpdater(db)
    updated_count = 0

    for i, building in enumerate(buildings, 1):
        old_station_info = building.station_info

        # 多数決で更新
        updated = updater.update_building_by_majority(building)

        if updated:
            updated_count += 1
            new_station_info = building.station_info

            # 変更があった場合のみ表示
            if old_station_info != new_station_info:
                print(f"[{i}/{len(buildings)}] 建物ID {building.id}: {building.normalized_name}")
                print(f"  更新前: {old_station_info.replace(chr(10), ' / ')}")
                print(f"  更新後: {new_station_info.replace(chr(10), ' / ')}")
                print()

        # 100件ごとにコミット
        if i % 100 == 0:
            db.commit()
            print(f"進捗: {i}/{len(buildings)}件処理完了")

    # 最終コミット
    db.commit()

    print("=" * 80)
    print(f"✅ 処理完了: {len(buildings)}件中{updated_count}件の建物を更新しました")

finally:
    db.close()
