#!/usr/bin/env python3
"""
BuildingMergeHistoryテーブルにハイブリッド方式用のカラムを追加するマイグレーションスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def add_hybrid_merge_columns():
    """ハイブリッド方式用のカラムを追加"""
    session = Session()
    
    try:
        # 1. 新しいカラムを追加
        logger.info("Adding new columns to building_merge_history table...")
        
        # direct_primary_building_id: 直接の統合先
        session.execute(text("""
            ALTER TABLE building_merge_history 
            ADD COLUMN IF NOT EXISTS direct_primary_building_id INTEGER
        """))
        
        # final_primary_building_id: 最終的な統合先（検索用キャッシュ）
        session.execute(text("""
            ALTER TABLE building_merge_history 
            ADD COLUMN IF NOT EXISTS final_primary_building_id INTEGER
        """))
        
        # merge_depth: 統合の深さ
        session.execute(text("""
            ALTER TABLE building_merge_history 
            ADD COLUMN IF NOT EXISTS merge_depth INTEGER DEFAULT 0
        """))
        
        # is_active: 統合が有効かどうか
        session.execute(text("""
            ALTER TABLE building_merge_history 
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE
        """))
        
        session.commit()
        logger.info("Columns added successfully.")
        
        # 2. 既存データの移行
        logger.info("Migrating existing data...")
        
        # 既存のprimary_building_idをdirect_primary_building_idとfinal_primary_building_idにコピー
        session.execute(text("""
            UPDATE building_merge_history 
            SET direct_primary_building_id = primary_building_id,
                final_primary_building_id = primary_building_id
            WHERE direct_primary_building_id IS NULL
        """))
        
        session.commit()
        logger.info("Data migration completed.")
        
        # 3. インデックスを追加
        logger.info("Adding indexes...")
        
        # final_primary_building_id用のインデックス（検索高速化）
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_building_merge_history_final_primary 
            ON building_merge_history(final_primary_building_id)
        """))
        
        # direct_primary_building_id用のインデックス
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_building_merge_history_direct_primary 
            ON building_merge_history(direct_primary_building_id)
        """))
        
        # is_active用のインデックス
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_building_merge_history_is_active 
            ON building_merge_history(is_active)
        """))
        
        session.commit()
        logger.info("Indexes added successfully.")
        
        # 4. 統計情報を表示
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT primary_building_id) as unique_primary,
                COUNT(DISTINCT merged_building_id) as unique_merged,
                MAX(merge_depth) as max_depth
            FROM building_merge_history
            WHERE is_active = TRUE
        """)).fetchone()
        
        logger.info(f"Migration Statistics:")
        logger.info(f"  Total records: {result.total_records}")
        logger.info(f"  Unique primary buildings: {result.unique_primary}")
        logger.info(f"  Unique merged buildings: {result.unique_merged}")
        logger.info(f"  Maximum merge depth: {result.max_depth or 0}")
        
        # 5. チェーン統合の検出と深さの計算
        logger.info("Calculating merge depths for chain merges...")
        
        # チェーン統合を検出して深さを更新
        session.execute(text("""
            WITH RECURSIVE merge_chain AS (
                -- ベースケース：直接統合されたもの（深さ0）
                SELECT 
                    id,
                    merged_building_id,
                    direct_primary_building_id,
                    final_primary_building_id,
                    0 as depth
                FROM building_merge_history
                WHERE is_active = TRUE
                    AND merged_building_id NOT IN (
                        SELECT direct_primary_building_id 
                        FROM building_merge_history 
                        WHERE is_active = TRUE
                    )
                
                UNION ALL
                
                -- 再帰ケース：他の建物を経由して統合されたもの
                SELECT 
                    h.id,
                    h.merged_building_id,
                    h.direct_primary_building_id,
                    h.final_primary_building_id,
                    mc.depth + 1
                FROM building_merge_history h
                INNER JOIN merge_chain mc 
                    ON h.merged_building_id = mc.direct_primary_building_id
                WHERE h.is_active = TRUE
            )
            UPDATE building_merge_history bmh
            SET merge_depth = mc.depth
            FROM merge_chain mc
            WHERE bmh.id = mc.id
        """))
        
        session.commit()
        logger.info("Merge depths calculated successfully.")
        
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    add_hybrid_merge_columns()