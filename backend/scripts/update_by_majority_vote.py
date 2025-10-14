#!/usr/bin/env python3
"""
物件情報と建物情報を多数決で更新するスクリプト

MajorityVoteUpdaterクラスを使用して、各物件・建物の属性を
紐づけられた掲載情報から多数決で決定します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty
from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def update_all_properties(session, limit=None):
    """
    全物件の情報を多数決で更新（属性と物件レベルの建物名）

    Args:
        session: データベースセッション
        limit: 処理する物件数の上限（Noneの場合は全件）

    Returns:
        更新された物件数
    """
    logger.info("=== 物件情報の多数決更新開始 ===")

    updater = MajorityVoteUpdater(session)

    # 全物件を取得
    query = session.query(MasterProperty)
    if limit:
        query = query.limit(limit)

    properties = query.all()
    total = len(properties)
    updated_count = 0
    building_name_updated_count = 0

    logger.info(f"処理対象物件数: {total}件")

    for i, prop in enumerate(properties, 1):
        try:
            # 多数決で物件属性を更新
            if updater.update_master_property_by_majority(prop):
                updated_count += 1

            # 多数決で物件レベルの建物名を更新
            if updater.update_property_building_name_by_majority(prop.id):
                building_name_updated_count += 1

            # 進捗表示（100件ごと）
            if i % 100 == 0:
                logger.info(f"進捗: {i}/{total}件処理完了 (属性更新: {updated_count}件, 建物名更新: {building_name_updated_count}件)")

        except Exception as e:
            logger.error(f"物件ID {prop.id} の更新に失敗: {e}")
            continue

    logger.info(f"物件情報の更新完了: 属性更新 {updated_count}/{total}件, 建物名更新 {building_name_updated_count}/{total}件")
    return updated_count


def update_all_buildings(session, limit=None):
    """
    全建物の情報を多数決で更新（建物名を含む）

    注意：update_building_name_by_majorityは事前に更新された各物件の
    display_building_nameを元に建物の建物名を決定します（真の2段階投票）。
    物件のdisplay_building_nameはupdate_all_propertiesで更新されている必要があります。

    Args:
        session: データベースセッション
        limit: 処理する建物数の上限（Noneの場合は全件）

    Returns:
        更新された建物数
    """
    logger.info("=== 建物情報の多数決更新開始 ===")

    updater = MajorityVoteUpdater(session)

    # 全建物を取得
    query = session.query(Building)
    if limit:
        query = query.limit(limit)

    buildings = query.all()
    total = len(buildings)
    updated_count = 0

    logger.info(f"処理対象建物数: {total}件")

    for i, building in enumerate(buildings, 1):
        try:
            # 多数決で建物情報を更新（建物名を含む）
            if updater.update_building_by_majority(building):
                updated_count += 1

            # 進捗表示（100件ごと）
            if i % 100 == 0:
                logger.info(f"進捗: {i}/{total}件処理完了 (更新: {updated_count}件)")

        except Exception as e:
            logger.error(f"建物ID {building.id} の更新に失敗: {e}")
            continue

    logger.info(f"建物情報の更新完了: {updated_count}/{total}件を更新")
    return updated_count


def update_single_property(session, property_id):
    """
    特定の物件を多数決で更新

    Args:
        session: データベースセッション
        property_id: 物件ID

    Returns:
        更新された場合True
    """
    logger.info(f"=== 物件ID {property_id} の多数決更新 ===")

    updater = MajorityVoteUpdater(session)

    prop = session.query(MasterProperty).filter(MasterProperty.id == property_id).first()
    if not prop:
        logger.error(f"物件ID {property_id} が見つかりません")
        return False

    logger.info(f"更新前: current_price={prop.current_price}, sold_at={prop.sold_at}, display_building_name={prop.display_building_name}")

    updated = False
    
    # 物件属性の更新
    if updater.update_master_property_by_majority(prop):
        updated = True
        logger.info("物件属性を更新しました")
    
    # 物件レベルの建物名の更新
    if updater.update_property_building_name_by_majority(property_id):
        updated = True
        logger.info("物件レベルの建物名を更新しました")
    
    if updated:
        logger.info(f"更新後: current_price={prop.current_price}, sold_at={prop.sold_at}, display_building_name={prop.display_building_name}")
        logger.info("更新成功")
        return True
    else:
        logger.info("更新なし")
        return False


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='物件・建物情報を多数決で更新')
    parser.add_argument('--target', choices=['property', 'building', 'both'],
                       default='both', help='更新対象（デフォルト: both）')
    parser.add_argument('--property-id', type=int, help='特定の物件IDのみ更新')
    parser.add_argument('--limit', type=int, help='処理件数の上限')
    parser.add_argument('--dry-run', action='store_true', help='ドライラン（実際にはコミットしない）')

    args = parser.parse_args()

    session = SessionLocal()

    try:
        # 特定の物件のみ更新
        if args.property_id:
            updated = update_single_property(session, args.property_id)
            if not args.dry_run and updated:
                session.commit()
                logger.info("変更をコミットしました")
            elif args.dry_run:
                session.rollback()
                logger.info("ドライラン: 変更をロールバックしました")
            return

        # 全体の更新（物件→建物の順で実行）
        property_updates = 0
        building_updates = 0

        # 物件を先に更新（物件レベルの建物名を含む）
        if args.target in ['property', 'both']:
            property_updates = update_all_properties(session, args.limit)

        # 建物を更新（事前更新済みの物件建物名から建物名を決定）
        if args.target in ['building', 'both']:
            building_updates = update_all_buildings(session, args.limit)

        if not args.dry_run:
            session.commit()
            logger.info("=" * 50)
            logger.info("すべての変更をコミットしました")
            logger.info(f"物件更新: {property_updates}件")
            logger.info(f"建物更新: {building_updates}件")
        else:
            session.rollback()
            logger.info("=" * 50)
            logger.info("ドライラン: すべての変更をロールバックしました")
            logger.info(f"物件更新（試算）: {property_updates}件")
            logger.info(f"建物更新（試算）: {building_updates}件")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
