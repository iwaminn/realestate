#!/usr/bin/env python3
"""
販売中物件の現在価格を多数決で更新するスクリプト

アクティブな掲載情報から多数決により現在価格を決定し、
MasterProperty.current_priceカラムを更新します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.utils.majority_vote_updater import MajorityVoteUpdater
from app.models import MasterProperty, PropertyListing
import argparse
import logging
from sqlalchemy import and_

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='販売中物件の現在価格を多数決で更新')
    parser.add_argument(
        '--property-id',
        type=int,
        help='特定の物件IDのみ更新（指定しない場合は全件）'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際の更新を行わずに結果のみ表示'
    )

    args = parser.parse_args()

    db = SessionLocal()
    try:
        updater = MajorityVoteUpdater(db)

        if args.property_id:
            # 特定の物件のみ更新
            logger.info(f"物件ID {args.property_id} の価格を確認中...")

            property = db.query(MasterProperty).filter(
                MasterProperty.id == args.property_id,
                MasterProperty.sold_at.is_(None)
            ).first()

            if not property:
                logger.error(f"物件ID {args.property_id} は存在しないか販売終了しています")
                return

            # アクティブな掲載の価格を取得
            active_listings = db.query(PropertyListing).filter(
                and_(
                    PropertyListing.master_property_id == args.property_id,
                    PropertyListing.is_active == True
                )
            ).all()

            if active_listings:
                prices = [listing.current_price for listing in active_listings]
                logger.info(f"アクティブな掲載の価格: {prices}")

                majority_price = updater.get_majority_price(prices, property.current_price)
                logger.info(f"多数決による価格: {majority_price}万円")
                logger.info(f"現在のcurrent_price: {property.current_price}万円")

                if not args.dry_run and majority_price != property.current_price:
                    property.current_price = majority_price
                    db.commit()
                    logger.info(f"価格を更新しました: {property.current_price}万円 -> {majority_price}万円")
                elif args.dry_run and majority_price != property.current_price:
                    logger.info(f"[DRY RUN] 価格を更新します: {property.current_price}万円 -> {majority_price}万円")
            else:
                logger.warning(f"アクティブな掲載が見つかりません")

        else:
            # 全件更新
            logger.info("全販売中物件の価格を確認中...")

            active_properties = db.query(MasterProperty).filter(
                MasterProperty.sold_at.is_(None)
            ).all()

            updates_needed = []
            updates_done = 0

            for property in active_properties:
                # アクティブな掲載の価格を取得
                active_listings = db.query(PropertyListing).filter(
                    and_(
                        PropertyListing.master_property_id == property.id,
                        PropertyListing.is_active == True
                    )
                ).all()

                if active_listings:
                    prices = [listing.current_price for listing in active_listings]
                    majority_price = updater.get_majority_price(prices, property.current_price)

                    if majority_price != property.current_price:
                        if args.dry_run:
                            updates_needed.append((
                                property.id,
                                property.current_price,
                                majority_price,
                                prices
                            ))
                        else:
                            property.current_price = majority_price
                            updates_done += 1

            if args.dry_run:
                logger.info(f"[DRY RUN] 更新対象: {len(updates_needed)}件")
                for prop_id, old_price, new_price, prices in updates_needed[:10]:
                    logger.info(f"  物件ID {prop_id}: {old_price}万円 -> {new_price}万円 (掲載価格: {prices})")

                if len(updates_needed) > 10:
                    logger.info(f"  ... 他 {len(updates_needed) - 10}件")
            else:
                db.commit()
                logger.info(f"更新完了: {updates_done}件の物件価格を更新しました")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
