#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
canonical_nameを重複を回避しながら修正するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_context
from app.models import Building, BuildingListingName
from app.utils.building_name_normalizer import canonicalize_building_name
from datetime import datetime
from sqlalchemy.exc import IntegrityError

def fix_canonical_names():
    with get_db_context() as db:
        print("canonical_name修正開始...")

        # BuildingListingName
        listings = db.query(BuildingListingName).all()
        total = len(listings)
        updated = 0
        skipped = 0

        for i, listing in enumerate(listings, 1):
            if i % 100 == 0:
                print(f"処理中... {i}/{total}")

            new_canonical = canonicalize_building_name(listing.normalized_name)

            if listing.canonical_name != new_canonical:
                # 同じbuilding_idで同じcanonical_nameが既に存在するかチェック
                existing = db.query(BuildingListingName).filter(
                    BuildingListingName.building_id == listing.building_id,
                    BuildingListingName.canonical_name == new_canonical,
                    BuildingListingName.id != listing.id
                ).first()

                if existing:
                    # 既存レコードがある場合は削除（重複統合）
                    print(f"  重複統合: {listing.normalized_name} (ID: {listing.id}) -> 既存: {existing.normalized_name} (ID: {existing.id})")
                    db.delete(listing)
                    skipped += 1
                else:
                    old_value = listing.canonical_name
                    listing.canonical_name = new_canonical
                    listing.updated_at = datetime.now()
                    updated += 1

                    if updated <= 10:
                        print(f"  更新: {listing.normalized_name}")
                        print(f"    旧: {old_value}")
                        print(f"    新: {new_canonical}")

        # Building
        buildings = db.query(Building).all()
        building_updated = 0

        for building in buildings:
            new_canonical = canonicalize_building_name(building.normalized_name)
            if building.canonical_name != new_canonical:
                old_value = building.canonical_name
                building.canonical_name = new_canonical
                building.updated_at = datetime.now()
                building_updated += 1

                if building_updated <= 10:
                    print(f"  建物更新: {building.normalized_name}")
                    print(f"    旧: {old_value}")
                    print(f"    新: {new_canonical}")

        db.commit()

        print(f"\n完了:")
        print(f"  BuildingListingName: {updated}件を更新、{skipped}件を重複統合")
        print(f"  Building: {building_updated}/{len(buildings)}件を更新")

if __name__ == "__main__":
    fix_canonical_names()