#!/usr/bin/env python3
"""
建物名の「々」文字が消えている問題を修正するスクリプト

修正内容:
- 「代 木」→「代々木」のように、スペースで分断された建物名を修正
- property_listingsの正しい建物名から再計算
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.app.utils.building_name_normalizer import normalize_building_name, canonicalize_building_name
import os

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def find_buildings_with_missing_々():
    """「々」が欠落している可能性のある建物を検索"""
    session = Session()

    try:
        # スペースを含む建物名を検索（「々」が消えた可能性）
        query = text("""
            SELECT
                b.id,
                b.normalized_name,
                COUNT(DISTINCT pl.listing_building_name) as listing_count,
                STRING_AGG(DISTINCT pl.listing_building_name, ' | ') as listing_names
            FROM buildings b
            JOIN master_properties mp ON mp.building_id = b.id
            JOIN property_listings pl ON pl.master_property_id = mp.id
            WHERE b.normalized_name LIKE '% %'  -- スペースを含む
            AND pl.listing_building_name LIKE '%々%'  -- 掲載情報には々がある
            GROUP BY b.id, b.normalized_name
            ORDER BY b.id
        """)

        results = session.execute(query).fetchall()
        return results
    finally:
        session.close()

def fix_building_name(building_id: int):
    """建物名を修正"""
    session = Session()

    try:
        # 建物の掲載情報から最も多い建物名を取得
        query = text("""
            SELECT pl.listing_building_name, COUNT(*) as count
            FROM property_listings pl
            JOIN master_properties mp ON pl.master_property_id = mp.id
            WHERE mp.building_id = :building_id
            AND pl.listing_building_name IS NOT NULL
            AND pl.listing_building_name != ''
            GROUP BY pl.listing_building_name
            ORDER BY count DESC, pl.listing_building_name
            LIMIT 1
        """)

        result = session.execute(query, {"building_id": building_id}).fetchone()

        if result:
            correct_name = result[0]
            normalized_name = normalize_building_name(correct_name)
            canonical_name = canonicalize_building_name(correct_name)

            # 建物情報を更新
            update_query = text("""
                UPDATE buildings
                SET normalized_name = :normalized_name,
                    canonical_name = :canonical_name
                WHERE id = :building_id
            """)

            session.execute(update_query, {
                "building_id": building_id,
                "normalized_name": normalized_name,
                "canonical_name": canonical_name
            })

            session.commit()
            return correct_name, normalized_name

        return None, None
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def main():
    print("「々」が欠落している可能性のある建物を検索中...")

    buildings = find_buildings_with_missing_々()

    if not buildings:
        print("修正が必要な建物は見つかりませんでした。")
        return

    print(f"\n修正が必要な建物: {len(buildings)}件\n")

    for building in buildings:
        building_id = building[0]
        old_normalized = building[1]
        listing_names = building[3]

        print(f"Building ID: {building_id}")
        print(f"  現在の正規化名: {old_normalized}")
        print(f"  掲載情報の建物名: {listing_names}")

        correct_name, new_normalized = fix_building_name(building_id)

        if correct_name:
            print(f"  ✅ 修正後: {new_normalized}")
        else:
            print(f"  ⚠️ 修正失敗")

        print()

    print(f"完了: {len(buildings)}件の建物名を修正しました。")

if __name__ == "__main__":
    main()