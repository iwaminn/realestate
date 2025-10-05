#!/usr/bin/env python3
"""
販売終了物件の価格を多数決で更新するスクリプト

販売終了日から過去1週間の価格履歴を分析し、
最も多く掲載されていた価格を最終価格として設定します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.utils.majority_vote_updater import MajorityVoteUpdater
from app.models import MasterProperty
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='販売終了物件の価格を多数決で更新')
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
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='販売終了前の何日間の価格を対象とするか（デフォルト: 7日）'
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        updater = MajorityVoteUpdater(db)
        
        if args.property_id:
            # 特定の物件のみ更新
            logger.info(f"物件ID {args.property_id} の価格を確認中...")
            
            # 最初に価格の投票状況を表示
            property = db.query(MasterProperty).filter(
                MasterProperty.id == args.property_id,
                MasterProperty.sold_at.isnot(None)
            ).first()
            
            if property:
                price_votes = updater.get_price_votes_for_sold_property(
                    property.id,
                    property.sold_at,
                    args.days
                )
                
                if price_votes:
                    logger.info(f"価格の投票状況: {price_votes}")
                    # 辞書を価格のリストに変換（出現回数分だけ繰り返す）
                    prices = []
                    for price, count in price_votes.items():
                        prices.extend([price] * count)
                    majority_price = updater.get_majority_price(prices, None)
                    logger.info(f"多数決による価格: {majority_price}万円")
                    logger.info(f"現在の最終価格: {property.last_sale_price}万円")
                    
                    if not args.dry_run and majority_price != property.last_sale_price:
                        result = updater.update_sold_property_price(args.property_id)
                        if result:
                            logger.info(f"価格を更新しました: {result[0]}万円 -> {result[1]}万円")
                        db.commit()
                    elif args.dry_run and majority_price != property.last_sale_price:
                        logger.info(f"[DRY RUN] 価格を更新します: {property.last_sale_price}万円 -> {majority_price}万円")
                else:
                    logger.warning(f"販売終了前{args.days}日間の価格履歴が見つかりません")
            else:
                logger.error(f"物件ID {args.property_id} は存在しないか販売終了していません")
        
        else:
            # 全件更新
            logger.info("全販売終了物件の価格を確認中...")
            
            if args.dry_run:
                # ドライランモード：更新対象を表示
                sold_properties = db.query(MasterProperty).filter(
                    MasterProperty.sold_at.isnot(None)
                ).all()
                
                updates_needed = []
                for property in sold_properties:
                    price_votes = updater.get_price_votes_for_sold_property(
                        property.id,
                        property.sold_at,
                        args.days
                    )
                    
                    if price_votes:
                        # 辞書を価格のリストに変換（出現回数分だけ繰り返す）
                        prices = []
                        for price, count in price_votes.items():
                            prices.extend([price] * count)
                        majority_price = updater.get_majority_price(prices, None)
                        if majority_price and majority_price != property.last_sale_price:
                            updates_needed.append((
                                property.id,
                                property.last_sale_price,
                                majority_price,
                                price_votes
                            ))
                
                logger.info(f"[DRY RUN] 更新対象: {len(updates_needed)}件")
                for prop_id, old_price, new_price, votes in updates_needed[:10]:
                    logger.info(f"  物件ID {prop_id}: {old_price}万円 -> {new_price}万円 (投票: {votes})")
                
                if len(updates_needed) > 10:
                    logger.info(f"  ... 他 {len(updates_needed) - 10}件")
            
            else:
                # 実際に更新
                updates = updater.update_all_sold_property_prices()
                db.commit()
                
                logger.info(f"更新完了: {len(updates)}件の物件価格を更新しました")
                if updates:
                    logger.info("更新された物件（最初の10件）:")
                    for prop_id, old_price, new_price in updates[:10]:
                        logger.info(f"  物件ID {prop_id}: {old_price}万円 -> {new_price}万円")
                    
                    if len(updates) > 10:
                        logger.info(f"  ... 他 {len(updates) - 10}件")
    
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()