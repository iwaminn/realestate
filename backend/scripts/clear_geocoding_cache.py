#!/usr/bin/env python3
"""
全建物の座標キャッシュをクリアするスクリプト

目的:
- 既存の座標データをクリアして、次回アクセス時に再取得させる
- geocoding.pyのロジック変更後に使用

使用例:
- 開発環境: docker exec realestate-backend poetry run python /app/backend/scripts/clear_geocoding_cache.py
- 本番環境: docker exec realestate-backend poetry run python /app/backend/scripts/clear_geocoding_cache.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import Building
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def clear_geocoding_cache():
    """全建物の座標キャッシュをクリア"""

    session = SessionLocal()

    try:
        # クリア前の状態を確認
        total_buildings = session.query(Building).count()
        buildings_with_coords = session.query(Building).filter(
            Building.latitude.isnot(None),
            Building.longitude.isnot(None)
        ).count()

        logger.info(f"全建物数: {total_buildings}件")
        logger.info(f"座標が設定されている建物: {buildings_with_coords}件")

        # 座標データをクリア
        logger.info("座標データをクリアしています...")
        session.query(Building).update({
            Building.latitude: None,
            Building.longitude: None,
            Building.geocoded_at: None,
            Building.geocoding_failed_at: None
        })
        session.commit()

        logger.info(f"✓ {total_buildings}件の建物の座標をクリアしました")
        logger.info("✓ 次回のアクセス時に座標が再取得されます")

    except Exception as e:
        logger.error(f"座標のクリアに失敗しました: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    logger.info("=== 座標キャッシュクリア開始 ===")

    # 確認メッセージ
    logger.warning("警告: 全ての建物の座標データがクリアされます")
    logger.info("続行しますか？ [y/N]: ")

    # 環境変数で自動承認できるようにする
    auto_approve = os.environ.get('AUTO_APPROVE', '').lower() == 'true'

    if not auto_approve:
        response = input().strip().lower()
        if response != 'y':
            logger.info("キャンセルしました")
            return
    else:
        logger.info("AUTO_APPROVE=true により自動承認")

    clear_geocoding_cache()

    logger.info("=== 座標キャッシュクリア完了 ===")


if __name__ == "__main__":
    main()
