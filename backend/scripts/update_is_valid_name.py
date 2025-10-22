#!/usr/bin/env python3
"""
広告文のみの建物名に対してis_valid_nameをFalseに設定するスクリプト

使用方法:
    # ドライラン（更新しない）
    poetry run python backend/scripts/update_is_valid_name.py --dry-run

    # 実際に更新
    poetry run python backend/scripts/update_is_valid_name.py

    # 本番環境での実行（Dockerコンテナ内）
    docker exec realestate-backend poetry run python backend/scripts/update_is_valid_name.py
"""

import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.utils.building_name_normalizer import remove_ad_text_from_building_name


def update_is_valid_name(dry_run: bool = False) -> dict:
    """
    広告文除去処理を使用してis_valid_nameフラグを更新

    Args:
        dry_run: Trueの場合、実際には更新せずに対象のみを表示

    Returns:
        更新結果の統計情報
    """
    db = SessionLocal()
    stats = {
        'total_buildings': 0,
        'checked_buildings': 0,
        'updated_to_false': 0,
        'updated_to_true': 0,
        'skipped': 0,
        'updated_buildings': []
    }

    try:
        # 全建物を取得
        buildings = db.query(Building).all()
        stats['total_buildings'] = len(buildings)

        print(f"チェック対象の建物数: {stats['total_buildings']}")
        if dry_run:
            print("【ドライランモード】実際の更新は行いません\n")
        else:
            print()

        for building in buildings:
            stats['checked_buildings'] += 1

            # 広告文除去処理を実行
            normalized_name = remove_ad_text_from_building_name(building.normalized_name)

            # 広告文除去後に空文字 = 広告文のみと判定
            is_ad_only = not normalized_name or normalized_name.strip() == ''

            # 期待されるis_valid_name
            expected_is_valid_name = not is_ad_only

            # 現在の値と異なる場合のみ更新
            if building.is_valid_name != expected_is_valid_name:
                if is_ad_only:
                    # 広告文のみの建物
                    action = "→ False (広告文のみ)"
                    print(f"建物ID {building.id}: '{building.normalized_name}' {action}")
                    stats['updated_to_false'] += 1
                else:
                    # 有効な建物名
                    action = "→ True (有効な建物名)"
                    print(f"建物ID {building.id}: '{building.normalized_name}' {action}")
                    stats['updated_to_true'] += 1

                stats['updated_buildings'].append({
                    'id': building.id,
                    'name': building.normalized_name,
                    'old_value': building.is_valid_name,
                    'new_value': expected_is_valid_name,
                    'is_ad_only': is_ad_only
                })

                if not dry_run:
                    building.is_valid_name = expected_is_valid_name
            else:
                stats['skipped'] += 1

        if not dry_run and (stats['updated_to_false'] > 0 or stats['updated_to_true'] > 0):
            db.commit()
            print(f"\n✅ 合計 {stats['updated_to_false'] + stats['updated_to_true']} 件の建物を更新しました")
        elif dry_run and (stats['updated_to_false'] > 0 or stats['updated_to_true'] > 0):
            print(f"\n【ドライラン】更新対象: {stats['updated_to_false'] + stats['updated_to_true']} 件")
        else:
            print("\n更新が必要な建物はありませんでした")

        # 統計情報の表示
        print("\n=== 統計情報 ===")
        print(f"全建物数: {stats['total_buildings']}")
        print(f"チェック済み: {stats['checked_buildings']}")
        print(f"False に更新: {stats['updated_to_false']}")
        print(f"True に更新: {stats['updated_to_true']}")
        print(f"スキップ（変更なし）: {stats['skipped']}")

        return stats

    except Exception as e:
        print(f"エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='広告文のみの建物名に対してis_valid_nameを更新',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='ドライランモード（実際には更新しない）'
    )

    args = parser.parse_args()

    try:
        stats = update_is_valid_name(dry_run=args.dry_run)

        # 終了コード
        if stats['updated_to_false'] > 0 or stats['updated_to_true'] > 0:
            if args.dry_run:
                sys.exit(1)  # ドライランで更新対象がある場合は1
            else:
                sys.exit(0)  # 更新成功
        else:
            sys.exit(0)  # 更新不要

    except KeyboardInterrupt:
        print("\n中断されました")
        sys.exit(130)
    except Exception as e:
        print(f"\n予期しないエラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
