#!/usr/bin/env python3
"""
property_listingsのlisting_building_nameを再生成するスクリプト

既存のtitleカラムから、新しいextract_building_name_from_ad_textメソッドを使って
listing_building_nameを再生成します。
"""

import sys
import os
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.scrapers.base_scraper import extract_building_name_from_ad_text
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def get_total_listings():
    """総レコード数を取得"""
    session = Session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM property_listings WHERE title IS NOT NULL"))
        return result.scalar()
    finally:
        session.close()


def regenerate_listing_building_names(dry_run=True, batch_size=1000):
    """
    listing_building_nameを再生成

    Args:
        dry_run: Trueの場合、実際の更新は行わず変更内容のみ表示
        batch_size: バッチ処理のサイズ
    """
    session = Session()

    try:
        logger.info("=" * 80)
        logger.info("listing_building_name 再生成処理")
        logger.info("=" * 80)
        logger.info(f"モード: {'ドライラン（変更なし）' if dry_run else '実際に更新'}")
        logger.info("")

        # 総レコード数を取得
        total = get_total_listings()
        logger.info(f"処理対象レコード数: {total:,}件")
        logger.info("")

        # 統計情報
        stats = {
            'total': 0,
            'changed': 0,
            'unchanged': 0,
            'empty_to_value': 0,
            'value_to_empty': 0,
            'value_to_value': 0,
        }

        # サンプル表示用（最初の10件の変更を表示）
        sample_changes = []

        # バッチ処理でデータを取得・更新
        offset = 0
        processed = 0

        while True:
            # バッチでデータを取得
            query = text("""
                SELECT id, title, listing_building_name, source_site
                FROM property_listings
                WHERE title IS NOT NULL
                ORDER BY id
                LIMIT :limit OFFSET :offset
            """)

            result = session.execute(query, {"limit": batch_size, "offset": offset})
            rows = result.fetchall()

            if not rows:
                break

            # バッチ内の各レコードを処理
            for row in rows:
                listing_id, title, old_building_name, source_site = row

                # titleが空の場合は、既存のlisting_building_nameを使用
                effective_title = title if title and title.strip() else old_building_name

                # 新しいメソッドで建物名を抽出
                new_building_name = extract_building_name_from_ad_text(effective_title)

                # 統計を更新
                stats['total'] += 1
                processed += 1

                # 進捗表示（1000件ごと）
                if processed % 1000 == 0:
                    logger.info(f"処理中: {processed:,} / {total:,} 件 ({processed/total*100:.1f}%)")

                if old_building_name != new_building_name:
                    stats['changed'] += 1

                    # 変更のタイプを分類
                    if not old_building_name or old_building_name == '':
                        stats['empty_to_value'] += 1
                    elif not new_building_name or new_building_name == '':
                        stats['value_to_empty'] += 1
                    else:
                        stats['value_to_value'] += 1

                    # サンプル収集（最初の10件）
                    if len(sample_changes) < 10:
                        sample_changes.append({
                            'id': listing_id,
                            'source': source_site,
                            'title': title,
                            'old': old_building_name,
                            'new': new_building_name
                        })

                    # 実際に更新（dry_runでない場合）
                    if not dry_run:
                        update_query = text("""
                            UPDATE property_listings
                            SET listing_building_name = :new_name
                            WHERE id = :id
                        """)
                        session.execute(update_query, {
                            "new_name": new_building_name,
                            "id": listing_id
                        })
                else:
                    stats['unchanged'] += 1

            # バッチごとにコミット
            if not dry_run:
                session.commit()

            offset += batch_size

        # 結果を表示
        logger.info("")
        logger.info("=" * 80)
        logger.info("処理結果サマリー")
        logger.info("=" * 80)
        logger.info(f"総レコード数: {stats['total']:,}件")
        logger.info(f"変更あり: {stats['changed']:,}件 ({stats['changed']/stats['total']*100:.2f}%)")
        logger.info(f"変更なし: {stats['unchanged']:,}件 ({stats['unchanged']/stats['total']*100:.2f}%)")
        logger.info("")
        logger.info("変更内訳:")
        logger.info(f"  空 → 値: {stats['empty_to_value']:,}件")
        logger.info(f"  値 → 空: {stats['value_to_empty']:,}件")
        logger.info(f"  値 → 値: {stats['value_to_value']:,}件")
        logger.info("")

        # サンプル変更を表示
        if sample_changes:
            logger.info("=" * 80)
            logger.info("変更サンプル（最初の10件）")
            logger.info("=" * 80)
            for i, change in enumerate(sample_changes, 1):
                logger.info(f"\n{i}. ID: {change['id']} [{change['source']}]")
                logger.info(f"   タイトル: {change['title']}")
                logger.info(f"   旧: {change['old'] or '（空）'}")
                logger.info(f"   新: {change['new'] or '（空）'}")

        logger.info("")
        logger.info("=" * 80)

        if dry_run:
            logger.info("⚠️  ドライランモードのため、実際の更新は行われていません")
            logger.info("実際に更新するには --execute オプションを付けて実行してください")
        else:
            logger.info("✅ 更新が完了しました")
            logger.info("")
            logger.info("次のステップ: 多数決処理を実行して物件・建物の表示名を更新してください")
            logger.info("コマンド: poetry run python backend/scripts/update_display_names_from_majority.py")

        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        raise
    finally:
        session.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='listing_building_nameを再生成')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='実際に更新を実行（指定しない場合はドライラン）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='バッチ処理のサイズ（デフォルト: 1000）'
    )

    args = parser.parse_args()

    # 確認
    if args.execute:
        logger.warning("")
        logger.warning("⚠️  実際に更新を実行します")
        logger.warning("")
        response = input("続行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            logger.info("処理を中止しました")
            return
        logger.info("")

    # 実行
    regenerate_listing_building_names(
        dry_run=not args.execute,
        batch_size=args.batch_size
    )


if __name__ == "__main__":
    main()
