#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全てのcanonical_nameを更新するスクリプト
中点を削除する修正版canonicalize_building_name関数を使用
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_context
from app.models import Building, BuildingListingName
from app.utils.building_name_normalizer import canonicalize_building_name
from datetime import datetime

def update_canonical_names():
    with get_db_context() as db:
        print("canonical_name更新開始...")

        # Buildings テーブル
        print("Buildingsテーブルの更新...")
        buildings = db.query(Building).all()
        building_updated = 0

        for building in buildings:
            new_canonical = canonicalize_building_name(building.normalized_name)
            if building.canonical_name != new_canonical:
                print(f"  更新: {building.normalized_name}: {building.canonical_name} -> {new_canonical}")
                building.canonical_name = new_canonical
                building.updated_at = datetime.now()
                building_updated += 1

                # 1件ずつコミットして重複エラーを回避
                try:
                    db.commit()
                except Exception as e:
                    print(f"    エラー: {e}")
                    db.rollback()

        print(f"Buildings: {building_updated}/{len(buildings)}件を更新")

        # BuildingListingNames テーブル
        print("\nBuildingListingNamesテーブルの更新...")

        # 建物ごとに処理
        building_ids = db.query(BuildingListingName.building_id).distinct().all()
        total_updated = 0
        total_deleted = 0

        for (building_id,) in building_ids:
            listings = db.query(BuildingListingName).filter(
                BuildingListingName.building_id == building_id
            ).all()

            canonical_map = {}  # canonical_name -> 最初のレコード

            for listing in listings:
                new_canonical = canonicalize_building_name(listing.normalized_name)

                if new_canonical in canonical_map:
                    # 重複する場合は削除
                    print(f"  重複削除: building_id={building_id}, {listing.normalized_name}")
                    db.delete(listing)
                    total_deleted += 1
                else:
                    # 新規または最初のレコード
                    canonical_map[new_canonical] = listing

                    if listing.canonical_name != new_canonical:
                        print(f"  更新: {listing.normalized_name}: {listing.canonical_name} -> {new_canonical}")
                        listing.canonical_name = new_canonical
                        listing.updated_at = datetime.now()
                        total_updated += 1

            # 建物ごとにコミット
            try:
                db.commit()
            except Exception as e:
                print(f"  建物ID {building_id} でエラー: {e}")
                db.rollback()

        print(f"\nBuildingListingNames:")
        print(f"  {total_updated}件を更新")
        print(f"  {total_deleted}件を重複削除")

        print("\n完了")

if __name__ == "__main__":
    update_canonical_names()