#!/usr/bin/env python3
"""
PropertyListingテーブルに物件属性フィールドを追加するマイグレーションスクリプト

各掲載サイトごとの物件情報を保存できるようにし、
多数決による情報統合を可能にします。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_listing_attributes():
    """PropertyListingテーブルに属性フィールドを追加"""
    
    # 追加するカラムのSQL
    alter_statements = [
        # 物件基本情報
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_floor_number INTEGER",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_area FLOAT",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_layout VARCHAR(50)",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_direction VARCHAR(50)",
        
        # 建物情報
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_total_floors INTEGER",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_building_structure VARCHAR(100)",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_built_year INTEGER",
        
        # 追加情報
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_balcony_area FLOAT",
        "ALTER TABLE property_listings ADD COLUMN IF NOT EXISTS listing_address TEXT",
        
        # コメント追加
        "COMMENT ON COLUMN property_listings.listing_floor_number IS 'この掲載での階数情報'",
        "COMMENT ON COLUMN property_listings.listing_area IS 'この掲載での専有面積'",
        "COMMENT ON COLUMN property_listings.listing_layout IS 'この掲載での間取り'",
        "COMMENT ON COLUMN property_listings.listing_direction IS 'この掲載での方角'",
        "COMMENT ON COLUMN property_listings.listing_total_floors IS 'この掲載での総階数'",
        "COMMENT ON COLUMN property_listings.listing_building_structure IS 'この掲載での建物構造'",
        "COMMENT ON COLUMN property_listings.listing_built_year IS 'この掲載での築年'",
        "COMMENT ON COLUMN property_listings.listing_balcony_area IS 'この掲載でのバルコニー面積'",
        "COMMENT ON COLUMN property_listings.listing_address IS 'この掲載での住所'"
    ]
    
    with engine.connect() as conn:
        for statement in alter_statements:
            try:
                conn.execute(text(statement))
                conn.commit()
                logger.info(f"実行成功: {statement[:50]}...")
            except Exception as e:
                logger.error(f"実行失敗: {statement[:50]}... - {e}")
                conn.rollback()


def create_majority_vote_view():
    """多数決で統合された情報を表示するビューを作成"""
    
    view_sql = """
    CREATE OR REPLACE VIEW property_majority_info AS
    WITH listing_counts AS (
        SELECT 
            master_property_id,
            COUNT(*) as total_listings,
            COUNT(DISTINCT source_site) as unique_sites
        FROM property_listings
        WHERE is_active = true
        GROUP BY master_property_id
    ),
    floor_majority AS (
        SELECT 
            master_property_id,
            listing_floor_number,
            source_site,
            COUNT(*) as count,
            ROW_NUMBER() OVER (
                PARTITION BY master_property_id 
                ORDER BY 
                    COUNT(*) DESC,
                    CASE source_site
                        WHEN 'suumo' THEN 1
                        WHEN 'homes' THEN 2
                        WHEN 'rehouse' THEN 3
                        WHEN 'nomu' THEN 4
                        ELSE 5
                    END
            ) as priority
        FROM property_listings
        WHERE is_active = true AND listing_floor_number IS NOT NULL
        GROUP BY master_property_id, listing_floor_number, source_site
    ),
    area_majority AS (
        SELECT 
            master_property_id,
            listing_area,
            source_site,
            COUNT(*) as count,
            ROW_NUMBER() OVER (
                PARTITION BY master_property_id 
                ORDER BY 
                    COUNT(*) DESC,
                    CASE source_site
                        WHEN 'suumo' THEN 1
                        WHEN 'homes' THEN 2
                        WHEN 'rehouse' THEN 3
                        WHEN 'nomu' THEN 4
                        ELSE 5
                    END
            ) as priority
        FROM property_listings
        WHERE is_active = true AND listing_area IS NOT NULL
        GROUP BY master_property_id, listing_area, source_site
    ),
    layout_majority AS (
        SELECT 
            master_property_id,
            listing_layout,
            source_site,
            COUNT(*) as count,
            ROW_NUMBER() OVER (
                PARTITION BY master_property_id 
                ORDER BY 
                    COUNT(*) DESC,
                    CASE source_site
                        WHEN 'suumo' THEN 1
                        WHEN 'homes' THEN 2
                        WHEN 'rehouse' THEN 3
                        WHEN 'nomu' THEN 4
                        ELSE 5
                    END
            ) as priority
        FROM property_listings
        WHERE is_active = true AND listing_layout IS NOT NULL
        GROUP BY master_property_id, listing_layout, source_site
    ),
    direction_majority AS (
        SELECT 
            master_property_id,
            listing_direction,
            source_site,
            COUNT(*) as count,
            ROW_NUMBER() OVER (
                PARTITION BY master_property_id 
                ORDER BY 
                    COUNT(*) DESC,
                    CASE source_site
                        WHEN 'suumo' THEN 1
                        WHEN 'homes' THEN 2
                        WHEN 'rehouse' THEN 3
                        WHEN 'nomu' THEN 4
                        ELSE 5
                    END
            ) as priority
        FROM property_listings
        WHERE is_active = true AND listing_direction IS NOT NULL
        GROUP BY master_property_id, listing_direction, source_site
    )
    SELECT 
        mp.id as master_property_id,
        mp.building_id,
        lc.total_listings,
        lc.unique_sites,
        COALESCE(fm.listing_floor_number, mp.floor_number) as floor_number,
        COALESCE(am.listing_area, mp.area) as area,
        COALESCE(lm.listing_layout, mp.layout) as layout,
        COALESCE(dm.listing_direction, mp.direction) as direction,
        mp.property_hash,
        mp.created_at,
        mp.updated_at
    FROM master_properties mp
    LEFT JOIN listing_counts lc ON mp.id = lc.master_property_id
    LEFT JOIN floor_majority fm ON mp.id = fm.master_property_id AND fm.priority = 1
    LEFT JOIN area_majority am ON mp.id = am.master_property_id AND am.priority = 1
    LEFT JOIN layout_majority lm ON mp.id = lm.master_property_id AND lm.priority = 1
    LEFT JOIN direction_majority dm ON mp.id = dm.master_property_id AND dm.priority = 1;
    
    COMMENT ON VIEW property_majority_info IS '掲載情報の多数決による物件情報統合ビュー';
    """
    
    with engine.connect() as conn:
        try:
            conn.execute(text(view_sql))
            conn.commit()
            logger.info("多数決ビューを作成しました")
        except Exception as e:
            logger.error(f"ビュー作成失敗: {e}")
            conn.rollback()


def main():
    """メイン処理"""
    logger.info("=== PropertyListingテーブルの拡張開始 ===")
    
    # カラム追加
    add_listing_attributes()
    
    # ビュー作成
    create_majority_vote_view()
    
    logger.info("=== 完了 ===")
    logger.info("次のステップ:")
    logger.info("1. backend/app/models.py の PropertyListing モデルに新しいフィールドを追加")
    logger.info("2. 各スクレイパーを更新して listing_* フィールドに値を保存するように修正")
    logger.info("3. update_by_majority_vote.py を実行して既存データを多数決で更新")


if __name__ == "__main__":
    main()