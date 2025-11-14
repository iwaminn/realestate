#!/usr/bin/env python
"""
BuildingListingNameテーブルのcanonical_nameを修正するスクリプト

問題:
- コード修正前（2025年9月14日）にrefresh_building_names()が実行された
- 古いロジックで「三田」→「3田」などの誤変換が発生
- コード修正後（2025年11月12日）に再実行が必要だったが未実施

修正内容:
- 全建物に対してrefresh_building_names()を再実行
- property_listingsの最新データから正しいcanonical_nameを再生成
- 古い誤変換エントリは削除される
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.app.models import Building
from backend.app.utils.building_listing_name_manager import BuildingListingNameManager
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fix_building_listing_names(dry_run: bool = False):
    """BuildingListingNameを修正"""

    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 誤変換されているエントリ数を確認
        result = session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN canonical_name LIKE '%3田%' OR
                                   canonical_name LIKE '%6本%' OR
                                   canonical_name LIKE '%5反%' THEN 1 END) as wrong_conversion
            FROM building_listing_names
        """)).fetchone()

        logger.info("=" * 70)
        logger.info(f"BuildingListingName総数: {result.total}件")
        logger.info(f"誤変換エントリ数: {result.wrong_conversion}件")
        logger.info("=" * 70)

        if dry_run:
            logger.info("DRY RUN モード: 実際の更新は行いません")

            # サンプルとして誤変換エントリを表示
            samples = session.execute(text("""
                SELECT building_id, normalized_name, canonical_name
                FROM building_listing_names
                WHERE canonical_name LIKE '%3田%' OR
                      canonical_name LIKE '%6本%' OR
                      canonical_name LIKE '%5反%'
                LIMIT 10
            """)).fetchall()

            logger.info("\n誤変換エントリのサンプル:")
            for sample in samples:
                logger.info(f"  Building ID: {sample.building_id}, "
                          f"normalized_name: {sample.normalized_name}, "
                          f"canonical_name: {sample.canonical_name}")

            return

        # 全建物を取得
        buildings = session.query(Building).all()
        logger.info(f"\n全建物数: {len(buildings)}件")

        # 各建物に対してrefresh_building_namesを実行
        manager = BuildingListingNameManager(session)

        success_count = 0
        error_count = 0

        for i, building in enumerate(buildings, 1):
            try:
                if i % 100 == 0:
                    logger.info(f"進捗: {i}/{len(buildings)} 建物処理完了...")

                manager.refresh_building_names(building.id)
                session.commit()
                success_count += 1

            except Exception as e:
                logger.error(f"Building ID {building.id} の処理でエラー: {e}")
                session.rollback()
                error_count += 1

        logger.info("\n" + "=" * 70)
        logger.info(f"処理完了")
        logger.info(f"  成功: {success_count}件")
        logger.info(f"  エラー: {error_count}件")
        logger.info("=" * 70)

        # 修正後の状態を確認
        result_after = session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN canonical_name LIKE '%3田%' OR
                                   canonical_name LIKE '%6本%' OR
                                   canonical_name LIKE '%5反%' THEN 1 END) as wrong_conversion
            FROM building_listing_names
        """)).fetchone()

        logger.info(f"\n修正後のBuildingListingName総数: {result_after.total}件")
        logger.info(f"修正後の誤変換エントリ数: {result_after.wrong_conversion}件")

        if result_after.wrong_conversion > 0:
            logger.warning(f"\n警告: まだ{result_after.wrong_conversion}件の誤変換エントリが残っています")
            logger.warning("これらは最近スクレイピングされていない古いデータの可能性があります")
        else:
            logger.info("\n✅ すべての誤変換エントリが修正されました！")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='BuildingListingNameのcanonical_nameを修正')
    parser.add_argument('--dry-run', action='store_true',
                       help='実際の更新を行わず、現状確認のみ')
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("BuildingListingName修正スクリプト")
    logger.info("=" * 70)

    fix_building_listing_names(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
