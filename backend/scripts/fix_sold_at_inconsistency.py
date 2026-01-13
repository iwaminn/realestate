#!/usr/bin/env python3
"""
sold_atの不整合を修正するスクリプト

sold_atが全掲載のdelisted_atの最大値と異なる物件を検出し、
正しい値に修正します。

使用方法:
    # 開発環境（Docker内）
    docker exec realestate-backend poetry run python /app/backend/scripts/fix_sold_at_inconsistency.py

    # 本番環境（Docker内）
    docker exec realestate-backend poetry run python /app/backend/scripts/fix_sold_at_inconsistency.py

    # ドライラン（変更を適用せずに確認のみ）
    docker exec realestate-backend poetry run python /app/backend/scripts/fix_sold_at_inconsistency.py --dry-run
"""

import sys
import os
import argparse
from pathlib import Path

# パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import MasterProperty, PropertyListing
from app.utils.price_queries import update_sold_status_and_final_price

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")


def find_inconsistent_properties(db):
    """sold_atが不整合な物件を検出"""
    query = text("""
        SELECT
            mp.id AS property_id,
            mp.sold_at AS current_sold_at,
            MAX(pl.delisted_at) AS correct_sold_at
        FROM master_properties mp
        JOIN property_listings pl ON pl.master_property_id = mp.id
        WHERE mp.sold_at IS NOT NULL
        GROUP BY mp.id, mp.sold_at
        HAVING mp.sold_at != MAX(pl.delisted_at)
        ORDER BY mp.id
    """)

    result = db.execute(query)
    return result.fetchall()


def fix_sold_at_inconsistency(dry_run=False):
    """sold_atの不整合を修正"""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # 不整合な物件を検出
        inconsistent = find_inconsistent_properties(db)
        total = len(inconsistent)

        print("=" * 60)
        print("sold_at不整合修正スクリプト")
        print("=" * 60)
        print(f"\n検出された不整合: {total}件")

        if total == 0:
            print("修正が必要な物件はありません。")
            return

        if dry_run:
            print("\n[ドライラン] 以下の物件が修正対象です:")
            print("-" * 60)
            for row in inconsistent[:20]:  # 最初の20件を表示
                print(f"  物件ID: {row.property_id}")
                print(f"    現在のsold_at: {row.current_sold_at}")
                print(f"    正しいsold_at: {row.correct_sold_at}")
            if total > 20:
                print(f"  ... 他 {total - 20}件")
            print("-" * 60)
            print("\n実際に修正するには --dry-run オプションを外して実行してください。")
            return

        # 修正を実行
        print("\n修正を実行中...")
        fixed_count = 0
        error_count = 0

        for row in inconsistent:
            try:
                result = update_sold_status_and_final_price(db, row.property_id)
                if result["is_sold"]:
                    fixed_count += 1
                    if fixed_count <= 10 or fixed_count % 50 == 0:
                        print(f"  修正: 物件ID={row.property_id}, sold_at={result['sold_at']}")
            except Exception as e:
                error_count += 1
                print(f"  エラー: 物件ID={row.property_id}, {e}")

        # コミット
        db.commit()

        print("\n" + "=" * 60)
        print("修正完了")
        print("=" * 60)
        print(f"  修正件数: {fixed_count}件")
        print(f"  エラー件数: {error_count}件")

        # 修正後の確認
        remaining = find_inconsistent_properties(db)
        print(f"  残りの不整合: {len(remaining)}件")

    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="sold_atの不整合を修正するスクリプト")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を適用せずに確認のみ行う"
    )
    args = parser.parse_args()

    fix_sold_at_inconsistency(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
