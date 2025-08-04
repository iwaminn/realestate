#!/usr/bin/env python3
"""
建物エイリアステーブルを追加するマイグレーションスクリプト
"""

import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime
import logging

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)


def create_building_aliases_table():
    """建物エイリアステーブルを作成"""
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS building_aliases (
        id SERIAL PRIMARY KEY,
        building_id INTEGER NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
        alias_name VARCHAR(200) NOT NULL,
        alias_type VARCHAR(50),
        source_site VARCHAR(50),
        is_primary BOOLEAN DEFAULT FALSE,
        confidence_score FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        CONSTRAINT unique_building_alias UNIQUE (building_id, alias_name)
    );
    
    -- インデックスの作成
    CREATE INDEX IF NOT EXISTS idx_building_aliases_name ON building_aliases(alias_name);
    CREATE INDEX IF NOT EXISTS idx_building_aliases_building ON building_aliases(building_id);
    CREATE INDEX IF NOT EXISTS idx_building_aliases_type ON building_aliases(alias_type);
    
    -- 更新日時の自動更新トリガー
    CREATE OR REPLACE FUNCTION update_building_aliases_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS update_building_aliases_updated_at ON building_aliases;
    CREATE TRIGGER update_building_aliases_updated_at
        BEFORE UPDATE ON building_aliases
        FOR EACH ROW
        EXECUTE FUNCTION update_building_aliases_updated_at();
    """
    
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()
        logger.info("building_aliasesテーブルを作成しました")


def populate_initial_aliases():
    """既存の建物名からエイリアスを生成"""
    
    populate_sql = """
    -- 既存の建物名からエイリアスを抽出
    WITH building_names AS (
        SELECT DISTINCT
            b.id as building_id,
            pl.listing_building_name as name,
            pl.source_site,
            COUNT(*) as occurrence_count
        FROM buildings b
        JOIN master_properties mp ON b.id = mp.building_id
        JOIN property_listings pl ON mp.id = pl.master_property_id
        WHERE pl.listing_building_name IS NOT NULL
        AND pl.listing_building_name != ''
        GROUP BY b.id, pl.listing_building_name, pl.source_site
    )
    INSERT INTO building_aliases (building_id, alias_name, alias_type, source_site, confidence_score)
    SELECT 
        building_id,
        name,
        CASE 
            WHEN name ~ '^[A-Za-z0-9\s\-]+$' THEN 'english'
            WHEN name ~ '[ァ-ヴー]' THEN 'katakana'
            ELSE 'kanji'
        END as alias_type,
        source_site,
        LEAST(occurrence_count::float / 10, 1.0) as confidence_score
    FROM building_names
    WHERE name != (SELECT normalized_name FROM buildings WHERE id = building_names.building_id)
    ON CONFLICT (building_id, alias_name) DO UPDATE
    SET 
        source_site = EXCLUDED.source_site,
        confidence_score = GREATEST(building_aliases.confidence_score, EXCLUDED.confidence_score),
        updated_at = CURRENT_TIMESTAMP;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(populate_sql))
        conn.commit()
        logger.info(f"初期エイリアスを{result.rowcount}件追加しました")


def identify_high_confidence_matches():
    """住所・総階数・築年月が一致する建物を特定"""
    
    query = """
    WITH building_matches AS (
        SELECT 
            b1.id as building1_id,
            b1.normalized_name as building1_name,
            b2.id as building2_id,
            b2.normalized_name as building2_name,
            b1.address,
            b1.total_floors,
            b1.built_year,
            b1.built_month
        FROM buildings b1
        JOIN buildings b2 ON 
            b1.id < b2.id  -- 重複を避けるため
            AND b1.address = b2.address
            AND b1.address IS NOT NULL
            AND b1.total_floors = b2.total_floors
            AND b1.total_floors IS NOT NULL
            AND b1.built_year = b2.built_year
            AND b1.built_year IS NOT NULL
            AND (
                (b1.built_month = b2.built_month)
                OR (b1.built_month IS NULL AND b2.built_month IS NULL)
            )
        WHERE NOT EXISTS (
            -- 既に統合済みまたは除外済みでない
            SELECT 1 FROM building_merge_history 
            WHERE (primary_building_id = b1.id AND merged_building_id = b2.id)
               OR (primary_building_id = b2.id AND merged_building_id = b1.id)
        )
        AND NOT EXISTS (
            SELECT 1 FROM building_merge_exclusions
            WHERE (building1_id = b1.id AND building2_id = b2.id)
               OR (building1_id = b2.id AND building2_id = b1.id)
        )
    )
    SELECT 
        bm.*,
        (SELECT COUNT(*) FROM master_properties WHERE building_id = bm.building1_id) as property_count1,
        (SELECT COUNT(*) FROM master_properties WHERE building_id = bm.building2_id) as property_count2
    FROM building_matches bm
    ORDER BY bm.address, bm.building1_name;
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        matches = result.fetchall()
        
        if matches:
            logger.info(f"\n住所・総階数・築年月が一致する建物ペアを{len(matches)}件発見しました：")
            for match in matches[:10]:  # 最初の10件を表示
                logger.info(f"  - {match.building1_name} (ID: {match.building1_id}, 物件数: {match.property_count1})")
                logger.info(f"    {match.building2_name} (ID: {match.building2_id}, 物件数: {match.property_count2})")
                logger.info(f"    住所: {match.address}")
                logger.info(f"    総階数: {match.total_floors}階, 築年月: {match.built_year}年{match.built_month or ''}月")
                logger.info("")
        
        return matches


def add_cross_reference_aliases(matches):
    """高信頼度のマッチングから相互エイリアスを追加"""
    
    added_count = 0
    
    with engine.connect() as conn:
        for match in matches:
            # 建物1の名前を建物2のエイリアスとして追加
            sql1 = """
            INSERT INTO building_aliases (building_id, alias_name, alias_type, confidence_score)
            VALUES (:building_id, :alias_name, 'cross_reference', 0.9)
            ON CONFLICT (building_id, alias_name) DO UPDATE
            SET confidence_score = GREATEST(building_aliases.confidence_score, 0.9),
                updated_at = CURRENT_TIMESTAMP;
            """
            
            conn.execute(text(sql1), {
                'building_id': match.building2_id,
                'alias_name': match.building1_name
            })
            
            # 建物2の名前を建物1のエイリアスとして追加
            conn.execute(text(sql1), {
                'building_id': match.building1_id,
                'alias_name': match.building2_name
            })
            
            added_count += 2
        
        conn.commit()
    
    logger.info(f"相互参照エイリアスを{added_count}件追加しました")


def main():
    """メイン処理"""
    try:
        # テーブル作成
        create_building_aliases_table()
        
        # 初期データ投入
        populate_initial_aliases()
        
        # 高信頼度マッチングを検出
        matches = identify_high_confidence_matches()
        
        if matches:
            # ユーザーに確認
            response = input(f"\n{len(matches)}件の高信頼度マッチングが見つかりました。相互エイリアスを追加しますか？ (y/n): ")
            if response.lower() == 'y':
                add_cross_reference_aliases(matches)
        
        logger.info("\n処理が完了しました")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    main()