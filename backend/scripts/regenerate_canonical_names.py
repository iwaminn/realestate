#!/usr/bin/env python
"""
全建物のcanonical_nameを現在のロジックで再生成するスクリプト

背景:
- canonical_nameは建物名の正規化ロジックで生成される検索用キー
- 正規化ロジックが更新された場合、古い建物のcanonical_nameは古いロジックのまま
- 多数決処理ではnormalized_nameが変更された場合のみcanonical_nameが更新される
- そのため、古いcanonical_nameが残り続け、重複検出に影響する

使用方法:
    # ドライラン（変更内容の確認のみ）
    docker exec realestate-backend poetry run python /app/backend/scripts/regenerate_canonical_names.py --dry-run

    # 実際に更新
    docker exec realestate-backend poetry run python /app/backend/scripts/regenerate_canonical_names.py
"""

import sys
import os
import argparse

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Building
from app.utils.building_name_normalizer import canonicalize_building_name


def regenerate_canonical_names(dry_run: bool = True):
    """全建物のcanonical_nameを再生成"""

    # データベース接続
    database_url = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 全建物を取得
        buildings = session.query(Building).all()
        total_count = len(buildings)
        updated_count = 0

        print(f"全建物数: {total_count}")
        print(f"モード: {'ドライラン（更新なし）' if dry_run else '実際に更新'}")
        print("-" * 80)

        for building in buildings:
            if not building.normalized_name:
                continue

            # 現在のロジックでcanonical_nameを再生成
            new_canonical_name = canonicalize_building_name(building.normalized_name)

            # 変更があるかチェック
            if building.canonical_name != new_canonical_name:
                updated_count += 1
                print(f"建物ID {building.id}: {building.normalized_name}")
                print(f"  変更前: {building.canonical_name}")
                print(f"  変更後: {new_canonical_name}")
                print()

                if not dry_run:
                    building.canonical_name = new_canonical_name

        print("-" * 80)
        print(f"更新対象: {updated_count}件 / {total_count}件")

        if not dry_run and updated_count > 0:
            session.commit()
            print("データベースを更新しました")
        elif dry_run and updated_count > 0:
            print("ドライランのため、実際の更新は行われませんでした")
            print("実際に更新するには --dry-run オプションを外して実行してください")
        else:
            print("更新対象の建物はありませんでした")

    except Exception as e:
        session.rollback()
        print(f"エラーが発生しました: {e}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description='全建物のcanonical_nameを現在のロジックで再生成'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='ドライラン（変更内容の確認のみ、実際の更新は行わない）'
    )

    args = parser.parse_args()
    regenerate_canonical_names(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
