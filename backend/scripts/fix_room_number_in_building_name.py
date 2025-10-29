#!/usr/bin/env python3
"""
建物名に含まれている部屋番号を除去するスクリプト

このスクリプトは、建物名の末尾に部屋番号が含まれている物件・建物データを修正します。
- master_properties.display_building_name
- buildings.normalized_name
- buildings.canonical_name
- property_listings.listing_building_name（今後のスクレイピングで多数決により自動修正されるため対象外）
"""

import sys
import os

# プロジェクトルートをPYTHONPATHに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import MasterProperty, Building
from app.utils.building_name_normalizer import remove_room_number_from_building_name


def fix_property_building_names(session: Session, dry_run: bool = True):
    """
    物件の建物名から部屋番号を除去

    Args:
        session: データベースセッション
        dry_run: Trueの場合は変更をコミットしない
    """
    # 部屋番号があり、建物名に部屋番号が含まれている可能性のある物件を取得
    properties = session.query(MasterProperty).filter(
        MasterProperty.room_number.isnot(None),
        MasterProperty.room_number != ''
    ).all()

    updated_count = 0

    for prop in properties:
        if not prop.display_building_name:
            continue

        # 部屋番号を除去
        fixed_name = remove_room_number_from_building_name(
            prop.display_building_name, prop.room_number
        )

        # 変更があった場合のみ更新
        if fixed_name != prop.display_building_name:
            print(f"物件ID {prop.id}:")
            print(f"  変更前: {prop.display_building_name}")
            print(f"  変更後: {fixed_name}")
            print(f"  部屋番号: {prop.room_number}")

            updated_count += 1
            if not dry_run:
                prop.display_building_name = fixed_name

    if not dry_run:
        session.commit()
        print(f"\n{updated_count}件の物件建物名を更新しました")
    else:
        print(f"\n{updated_count}件の物件建物名が更新対象です（dry-run モード）")

    return updated_count


def fix_building_names(session: Session, dry_run: bool = True):
    """
    建物名から部屋番号を除去

    建物の正規化名とカノニカル名から部屋番号を除去します。
    ただし、建物に紐づく物件の部屋番号を確認する必要があるため、
    物件レベルでの修正を優先します。

    Args:
        session: データベースセッション
        dry_run: Trueの場合は変更をコミットしない
    """
    # すべての建物を取得
    buildings = session.query(Building).all()

    updated_count = 0

    for building in buildings:
        # この建物に属する物件を取得
        properties = session.query(MasterProperty).filter(
            MasterProperty.building_id == building.id
        ).all()

        # 建物に属する物件の部屋番号を収集（重複を除く）
        room_numbers = set()
        for prop in properties:
            if prop.room_number:
                room_numbers.add(prop.room_number)

        # 各部屋番号について建物名をチェック
        fixed_normalized_name = building.normalized_name
        fixed_canonical_name = building.canonical_name

        for room_number in room_numbers:
            fixed_normalized_name = remove_room_number_from_building_name(
                fixed_normalized_name, room_number
            )
            fixed_canonical_name = remove_room_number_from_building_name(
                fixed_canonical_name, room_number
            )

        # 変更があった場合のみ更新
        if (fixed_normalized_name != building.normalized_name or
                fixed_canonical_name != building.canonical_name):
            print(f"建物ID {building.id}:")
            if fixed_normalized_name != building.normalized_name:
                print(f"  正規化名変更前: {building.normalized_name}")
                print(f"  正規化名変更後: {fixed_normalized_name}")
            if fixed_canonical_name != building.canonical_name:
                print(f"  カノニカル名変更前: {building.canonical_name}")
                print(f"  カノニカル名変更後: {fixed_canonical_name}")

            updated_count += 1
            if not dry_run:
                building.normalized_name = fixed_normalized_name
                building.canonical_name = fixed_canonical_name

    if not dry_run:
        session.commit()
        print(f"\n{updated_count}件の建物名を更新しました")
    else:
        print(f"\n{updated_count}件の建物名が更新対象です（dry-run モード）")

    return updated_count


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='建物名から部屋番号を除去')
    parser.add_argument('--execute', action='store_true',
                        help='実際に更新を実行（指定しない場合はdry-runモード）')
    args = parser.parse_args()

    dry_run = not args.execute

    if dry_run:
        print("=== Dry-run モード（変更はコミットされません） ===\n")
    else:
        print("=== 実行モード（変更をコミットします） ===\n")

    session = SessionLocal()

    try:
        print("--- 物件建物名の修正 ---")
        fix_property_building_names(session, dry_run)

        print("\n--- 建物名の修正 ---")
        fix_building_names(session, dry_run)

    finally:
        session.close()

    if dry_run:
        print("\n実際に更新を実行するには --execute オプションを付けて実行してください")


if __name__ == "__main__":
    main()
