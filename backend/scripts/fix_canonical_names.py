#!/usr/bin/env python3
"""
Building.canonical_nameを強制的に再計算するスクリプト

問題:
- normalized_nameは正しいが、canonical_nameが古いロジックで誤変換されている
- 多数決処理ではnormalized_nameが変わらない場合、canonical_nameを更新しない

解決:
- normalized_nameからcanonical_nameを強制的に再計算
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import Building
from backend.app.utils.building_name_normalizer import canonicalize_building_name

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    # 誤変換されている建物を取得
    buildings = session.query(Building).filter(
        (Building.canonical_name.like('%3田%')) |
        (Building.canonical_name.like('%6本%')) |
        (Building.canonical_name.like('%5反%'))
    ).all()

    print(f"誤変換されている建物: {len(buildings)}件")

    updated = 0
    for building in buildings:
        old_canonical = building.canonical_name
        # normalized_nameから新しいcanonical_nameを計算
        new_canonical = canonicalize_building_name(building.normalized_name)

        if new_canonical != old_canonical:
            building.canonical_name = new_canonical
            updated += 1
            print(f"Building ID {building.id}: '{old_canonical}' → '{new_canonical}'")

    session.commit()
    print(f"\n更新完了: {updated}/{len(buildings)}件を更新しました")

except Exception as e:
    print(f"エラー: {e}")
    session.rollback()
    raise
finally:
    session.close()
