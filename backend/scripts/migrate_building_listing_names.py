#!/usr/bin/env python3
"""
建物掲載名テーブルの作成と既存データの移行スクリプト

このスクリプトは以下の処理を行います：
1. building_listing_namesテーブルを作成
2. 既存のproperty_listingsから建物名を集約
3. 検索用に正規化された名前を生成
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import logging
from collections import defaultdict

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal, engine
from backend.app.models import (
    Base, Building, PropertyListing, BuildingListingName, MasterProperty
)
from backend.app.scrapers.data_normalizer import normalize_building_name
from sqlalchemy import text, func
from sqlalchemy.exc import OperationalError

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_table_if_not_exists():
    """building_listing_namesテーブルを作成"""
    try:
        # テーブルが存在するか確認
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'building_listing_names'
                )
            """))
            exists = result.scalar()
            
            if not exists:
                logger.info("building_listing_namesテーブルを作成します...")
                BuildingListingName.__table__.create(engine)
                logger.info("テーブルの作成が完了しました")
            else:
                logger.info("building_listing_namesテーブルは既に存在します")
                
    except Exception as e:
        logger.error(f"テーブル作成中にエラーが発生しました: {e}")
        raise


def normalize_for_search(name: str) -> str:
    """検索用に建物名を正規化"""
    if not name:
        return ""
    
    # data_normalizerの正規化を使用
    normalized = normalize_building_name(name)
    
    # 追加の正規化（検索用）
    # 全角英数字を半角に変換
    import unicodedata
    normalized = unicodedata.normalize('NFKC', normalized)
    
    # 小文字に統一
    normalized = normalized.lower()
    
    # 連続するスペースを1つに
    import re
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def migrate_existing_data():
    """既存のproperty_listingsから建物名を集約"""
    db = SessionLocal()
    try:
        logger.info("既存データの移行を開始します...")
        
        # すべての建物を取得
        buildings = db.query(Building).all()
        total_buildings = len(buildings)
        logger.info(f"{total_buildings}件の建物を処理します")
        
        for idx, building in enumerate(buildings, 1):
            if idx % 100 == 0:
                logger.info(f"進捗: {idx}/{total_buildings} ({idx*100/total_buildings:.1f}%)")
            
            # この建物に紐づく掲載情報から建物名を取得
            listing_names = db.query(
                PropertyListing.listing_building_name,
                PropertyListing.source_site,
                func.count(PropertyListing.id).label('count'),
                func.min(PropertyListing.first_seen_at).label('first_seen'),
                func.max(PropertyListing.last_scraped_at).label('last_seen')
            ).join(
                MasterProperty,
                PropertyListing.master_property_id == MasterProperty.id
            ).filter(
                MasterProperty.building_id == building.id,
                PropertyListing.listing_building_name.isnot(None),
                PropertyListing.listing_building_name != ''
            ).group_by(
                PropertyListing.listing_building_name,
                PropertyListing.source_site
            ).all()
            
            # 建物名ごとに集約
            name_aggregation = defaultdict(lambda: {
                'sites': set(),
                'count': 0,
                'first_seen': None,
                'last_seen': None
            })
            
            for name, site, count, first_seen, last_seen in listing_names:
                if not name:
                    continue
                    
                agg = name_aggregation[name]
                agg['sites'].add(site)
                agg['count'] += count
                
                if agg['first_seen'] is None or (first_seen and first_seen < agg['first_seen']):
                    agg['first_seen'] = first_seen
                    
                if agg['last_seen'] is None or (last_seen and last_seen > agg['last_seen']):
                    agg['last_seen'] = last_seen
            
            # BuildingListingNameに保存
            for listing_name, agg_data in name_aggregation.items():
                canonical_name = normalize_for_search(listing_name)
                
                # 既存レコードを確認
                existing = db.query(BuildingListingName).filter(
                    BuildingListingName.building_id == building.id,
                    BuildingListingName.listing_name == listing_name
                ).first()
                
                if existing:
                    # 更新
                    existing.canonical_name = canonical_name
                    existing.source_sites = ','.join(sorted(agg_data['sites']))
                    existing.occurrence_count = agg_data['count']
                    existing.last_seen_at = agg_data['last_seen'] or datetime.now()
                else:
                    # 新規作成
                    new_entry = BuildingListingName(
                        building_id=building.id,
                        listing_name=listing_name,
                        canonical_name=canonical_name,
                        source_sites=','.join(sorted(agg_data['sites'])),
                        occurrence_count=agg_data['count'],
                        first_seen_at=agg_data['first_seen'] or datetime.now(),
                        last_seen_at=agg_data['last_seen'] or datetime.now()
                    )
                    db.add(new_entry)
            
            # 定期的にコミット
            if idx % 50 == 0:
                db.commit()
        
        # 最終コミット
        db.commit()
        
        # 統計を表示
        total_entries = db.query(func.count(BuildingListingName.id)).scalar()
        unique_names = db.query(func.count(func.distinct(BuildingListingName.listing_name))).scalar()
        
        logger.info(f"""
移行完了:
- 処理した建物数: {total_buildings}
- 作成されたエントリ数: {total_entries}
- ユニークな建物名数: {unique_names}
        """)
        
    except Exception as e:
        logger.error(f"データ移行中にエラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def create_fulltext_index():
    """全文検索用のインデックスを作成（PostgreSQL）"""
    try:
        with engine.connect() as conn:
            # 日本語全文検索用の設定を確認
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'
                )
            """))
            
            if not result.scalar():
                logger.info("pg_trgm拡張をインストールします...")
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                conn.commit()
            
            # trigramインデックスを作成（部分一致検索用）
            logger.info("trigramインデックスを作成します...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_building_listing_names_trgm
                ON building_listing_names 
                USING gin (canonical_name gin_trgm_ops)
            """))
            conn.commit()
            
            logger.info("インデックスの作成が完了しました")
            
    except Exception as e:
        logger.error(f"インデックス作成中にエラーが発生しました: {e}")
        # エラーが発生してもスクリプトは続行


def main():
    """メイン処理"""
    logger.info("建物掲載名の移行処理を開始します")
    
    # 1. テーブル作成
    create_table_if_not_exists()
    
    # 2. 既存データの移行
    migrate_existing_data()
    
    # 3. インデックス作成
    create_fulltext_index()
    
    logger.info("すべての処理が完了しました")


if __name__ == "__main__":
    main()