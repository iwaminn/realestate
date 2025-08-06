#!/usr/bin/env python3
"""
PropertyMergeHistoryテーブルにハイブリッド方式用のカラムを追加するマイグレーションスクリプト
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


def add_hybrid_property_merge_columns():
    """ハイブリッド方式用のカラムを追加"""
    session = Session()
    
    try:
        # 1. 新しいカラムを追加
        logger.info("Adding new columns to property_merge_history table...")
        
        # direct_primary_property_id: 直接の統合先
        session.execute(text("""
            ALTER TABLE property_merge_history 
            ADD COLUMN IF NOT EXISTS direct_primary_property_id INTEGER
        """))
        
        # final_primary_property_id: 最終的な統合先（検索用キャッシュ）
        session.execute(text("""
            ALTER TABLE property_merge_history 
            ADD COLUMN IF NOT EXISTS final_primary_property_id INTEGER
        """))
        
        # merge_depth: 統合の深さ
        session.execute(text("""
            ALTER TABLE property_merge_history 
            ADD COLUMN IF NOT EXISTS merge_depth INTEGER DEFAULT 0
        """))
        
        session.commit()
        logger.info("Columns added successfully.")
        
        # 2. 既存データの移行
        logger.info("Migrating existing data...")
        
        # 既存のprimary_property_idをdirect_primary_property_idとfinal_primary_property_idにコピー
        session.execute(text("""
            UPDATE property_merge_history 
            SET direct_primary_property_id = primary_property_id,
                final_primary_property_id = primary_property_id
            WHERE direct_primary_property_id IS NULL
        """))
        
        session.commit()
        logger.info("Data migration completed.")
        
        # 3. 外部キー制約を追加（存在しない場合のみ）
        logger.info("Adding foreign key constraints...")
        
        # 制約が存在するかチェック
        result = session.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'property_merge_history' 
            AND constraint_name = 'property_merge_history_direct_primary_property_id_fkey'
        """)).fetchone()
        
        if not result:
            session.execute(text("""
                ALTER TABLE property_merge_history
                ADD CONSTRAINT property_merge_history_direct_primary_property_id_fkey
                FOREIGN KEY (direct_primary_property_id) REFERENCES master_properties(id)
            """))
            logger.info("Added direct_primary_property_id foreign key constraint.")
        
        result = session.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'property_merge_history' 
            AND constraint_name = 'property_merge_history_final_primary_property_id_fkey'
        """)).fetchone()
        
        if not result:
            session.execute(text("""
                ALTER TABLE property_merge_history
                ADD CONSTRAINT property_merge_history_final_primary_property_id_fkey
                FOREIGN KEY (final_primary_property_id) REFERENCES master_properties(id)
            """))
            logger.info("Added final_primary_property_id foreign key constraint.")
        
        session.commit()
        logger.info("Foreign key constraints added successfully.")
        
        # 4. インデックスを追加
        logger.info("Adding indexes...")
        
        # final_primary_property_id用のインデックス（検索高速化）
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_property_merge_history_final_primary 
            ON property_merge_history(final_primary_property_id)
        """))
        
        # direct_primary_property_id用のインデックス
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_property_merge_history_direct_primary 
            ON property_merge_history(direct_primary_property_id)
        """))
        
        session.commit()
        logger.info("Indexes added successfully.")
        
        # 5. 統計情報を表示
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT primary_property_id) as unique_primary,
                COUNT(DISTINCT merged_property_id) as unique_merged,
                MAX(merge_depth) as max_depth
            FROM property_merge_history
        """)).fetchone()
        
        logger.info(f"Migration Statistics:")
        logger.info(f"  Total records: {result.total_records}")
        logger.info(f"  Unique primary properties: {result.unique_primary}")
        logger.info(f"  Unique merged properties: {result.unique_merged}")
        logger.info(f"  Maximum merge depth: {result.max_depth or 0}")
        
        # 6. チェーン統合の検出と深さの計算
        logger.info("Calculating merge depths for chain merges...")
        
        # チェーン統合を検出して深さを更新
        session.execute(text("""
            WITH RECURSIVE merge_chain AS (
                -- ベースケース：直接統合されたもの（深さ0）
                SELECT 
                    id,
                    merged_property_id,
                    direct_primary_property_id,
                    final_primary_property_id,
                    0 as depth
                FROM property_merge_history
                WHERE merged_property_id NOT IN (
                    SELECT COALESCE(direct_primary_property_id, -1)
                    FROM property_merge_history 
                )
                
                UNION ALL
                
                -- 再帰ケース：他の物件を経由して統合されたもの
                SELECT 
                    h.id,
                    h.merged_property_id,
                    h.direct_primary_property_id,
                    h.final_primary_property_id,
                    mc.depth + 1
                FROM property_merge_history h
                INNER JOIN merge_chain mc 
                    ON h.merged_property_id = mc.direct_primary_property_id
            )
            UPDATE property_merge_history pmh
            SET merge_depth = mc.depth
            FROM merge_chain mc
            WHERE pmh.id = mc.id
        """))
        
        session.commit()
        logger.info("Merge depths calculated successfully.")
        
        # 7. テーブル構造を確認
        logger.info("\nCurrent columns in property_merge_history:")
        columns = session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'property_merge_history'
            ORDER BY ordinal_position
        """)).fetchall()
        
        for col in columns:
            logger.info(f"  - {col.column_name}: {col.data_type} (nullable: {col.is_nullable})")
        
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    add_hybrid_property_merge_columns()