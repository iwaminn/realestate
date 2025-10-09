#!/usr/bin/env python3
"""
buildingsテーブルにgecoding_failed_atカラムを追加するマイグレーションスクリプト

目的:
- ジオコーディング失敗時の日時を記録
- 失敗から一定期間は再試行しないようにする
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal, engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_geocoding_failed_at_column():
    """buildingsテーブルにgecoding_failed_atカラムを追加"""

    session = SessionLocal()

    try:
        # カラムが既に存在するかチェック
        result = session.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'buildings'
            AND column_name = 'geocoding_failed_at'
        """))

        if result.fetchone():
            logger.info("geocoding_failed_atカラムは既に存在します")
            return

        # カラムを追加
        logger.info("geocoding_failed_atカラムを追加しています...")
        session.execute(text("""
            ALTER TABLE buildings
            ADD COLUMN geocoding_failed_at TIMESTAMP
        """))
        session.commit()
        logger.info("✓ geocoding_failed_atカラムを追加しました")

        # 確認
        result = session.execute(text("""
            SELECT COUNT(*) as total
            FROM buildings
        """))
        total = result.fetchone()[0]
        logger.info(f"✓ マイグレーション完了（建物数: {total}件）")

    except Exception as e:
        logger.error(f"マイグレーションに失敗しました: {e}", exc_info=True)
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    logger.info("=== buildingsテーブルマイグレーション開始 ===")

    add_geocoding_failed_at_column()

    logger.info("=== マイグレーション完了 ===")


if __name__ == "__main__":
    main()
