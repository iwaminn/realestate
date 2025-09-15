#!/usr/bin/env python3
"""
BuildingListingNameテーブルの構造更新と既存データの移行スクリプト

このスクリプトは以下の処理を行います：
1. listing_nameカラムをnormalized_nameカラムに移行
2. 既存のデータを正規化して保存
3. 古いカラムの削除（オプション）
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
from backend.app.utils.building_name_normalizer import canonicalize_building_name
from backend.app.utils.building_name_normalizer import normalize_building_name
from sqlalchemy import text, func
from sqlalchemy.exc import OperationalError

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_normalized_name_column():
    """normalized_nameカラムを追加"""
    try:
        with engine.connect() as conn:
            # カラムが存在するか確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'building_listing_names' 
                AND column_name = 'normalized_name'
            """))
            
            if not result.fetchone():
                logger.info("normalized_nameカラムを追加中...")
                conn.execute(text("""
                    ALTER TABLE building_listing_names 
                    ADD COLUMN normalized_name VARCHAR(200)
                """))
                conn.commit()
                logger.info("✅ normalized_nameカラムを追加しました")
            else:
                logger.info("ℹ️ normalized_nameカラムは既に存在します")
                
    except Exception as e:
        logger.warning(f"カラム追加時のエラー（無視可能）: {e}")


def check_listing_name_column():
    """listing_nameカラムの存在を確認"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'building_listing_names' 
                AND column_name = 'listing_name'
            """))
            return result.fetchone() is not None
    except:
        return False


def migrate_existing_data():
    """既存データをnormalized_nameカラムに移行"""
    db = SessionLocal()
    try:
        has_listing_name = check_listing_name_column()
        
        if has_listing_name:
            # listing_nameカラムが存在する場合、データを移行
            logger.info("listing_nameからnormalized_nameへの移行を開始...")
            
            with engine.connect() as conn:
                entries = conn.execute(text("""
                    SELECT id, listing_name 
                    FROM building_listing_names 
                    WHERE listing_name IS NOT NULL 
                    AND (normalized_name IS NULL OR normalized_name = '')
                """)).fetchall()
                
                total_count = len(entries)
                logger.info(f"移行対象: {total_count}件")
                
                if total_count > 0:
                    updated_count = 0
                    for entry_id, listing_name in entries:
                        normalized_name = normalize_building_name(listing_name)
                        conn.execute(text("""
                            UPDATE building_listing_names 
                            SET normalized_name = :normalized_name 
                            WHERE id = :id
                        """), {'normalized_name': normalized_name, 'id': entry_id})
                        
                        updated_count += 1
                        if updated_count % 100 == 0:
                            logger.info(f"  {updated_count}/{total_count} 件完了...")
                            conn.commit()
                    
                    conn.commit()
                    logger.info(f"✅ {updated_count}件のデータを移行しました")
                else:
                    logger.info("ℹ️ 移行するデータはありません")
        else:
            # listing_nameカラムが存在しない場合、property_listingsから再構築
            logger.info("listing_nameカラムが存在しません。property_listingsから再構築します...")
            
            # normalized_nameが空のエントリを取得
            empty_entries = db.query(BuildingListingName).filter(
                BuildingListingName.normalized_name.is_(None)
            ).all()
            
            if empty_entries:
                logger.info(f"再構築対象: {len(empty_entries)}件")
                
                # BuildingListingNameManagerを使用して再構築
                from backend.app.utils.building_listing_name_manager import BuildingListingNameManager
                manager = BuildingListingNameManager(db)
                
                # 建物IDをユニークに取得
                building_ids = set(entry.building_id for entry in empty_entries)
                
                for building_id in building_ids:
                    logger.info(f"建物ID {building_id} の名前を再構築中...")
                    manager.refresh_building_names(building_id)
                
                db.commit()
                logger.info(f"✅ {len(building_ids)}件の建物の名前を再構築しました")
            else:
                logger.info("ℹ️ すべてのエントリにnormalized_nameが設定されています")
        
        # 統計を表示
        total = db.query(BuildingListingName).count()
        with_normalized = db.query(BuildingListingName).filter(
            BuildingListingName.normalized_name.isnot(None)
        ).count()
        
        logger.info(f"\n統計:")
        logger.info(f"- 全レコード数: {total}")
        logger.info(f"- normalized_name設定済み: {with_normalized}")
        
        if total == with_normalized:
            logger.info("✅ すべてのレコードにnormalized_nameが設定されています")
        else:
            logger.warning(f"⚠️ {total - with_normalized}件のレコードにnormalized_nameが未設定です")
        
    except Exception as e:
        logger.error(f"データ移行中にエラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def drop_listing_name_column():
    """listing_nameカラムを削除（オプション）"""
    if not check_listing_name_column():
        logger.info("listing_nameカラムは既に削除されています")
        return
        
    print("\nlisting_nameカラムを削除しますか？")
    print("⚠️ 警告: この操作は元に戻せません")
    
    response = input("削除を実行しますか？ (yes/no): ")
    if response.lower() == 'yes':
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE building_listing_names 
                    DROP COLUMN listing_name
                """))
                conn.commit()
                logger.info("✅ listing_nameカラムを削除しました")
        except Exception as e:
            logger.error(f"❌ カラム削除エラー: {e}")
    else:
        logger.info("カラム削除をキャンセルしました")


def main():
    """メイン処理"""
    logger.info("="*60)
    logger.info("BuildingListingName移行スクリプト")
    logger.info("="*60)
    
    # 1. normalized_nameカラムを追加
    add_normalized_name_column()
    
    # 2. 既存データの移行
    migrate_existing_data()
    
    # 3. listing_nameカラムの削除（オプション）
    drop_listing_name_column()
    
    logger.info("\nすべての処理が完了しました")


if __name__ == "__main__":
    main()