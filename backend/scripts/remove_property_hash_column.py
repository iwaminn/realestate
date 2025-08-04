#!/usr/bin/env python3
"""
property_hashカラムを削除するマイグレーションスクリプト

このスクリプトは以下の処理を行います：
1. property_hashカラムの使用状況を確認
2. property_hashカラムを削除
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import MasterProperty
from sqlalchemy import text, func
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_property_hash_usage(session):
    """property_hashカラムの使用状況を確認"""
    logger.info("=== property_hashカラムの使用状況確認 ===")
    
    # NULL値の件数を確認
    null_count = session.query(func.count(MasterProperty.id)).filter(
        MasterProperty.property_hash.is_(None)
    ).scalar()
    
    # 非NULL値の件数を確認
    not_null_count = session.query(func.count(MasterProperty.id)).filter(
        MasterProperty.property_hash.isnot(None)
    ).scalar()
    
    total_count = null_count + not_null_count
    
    logger.info(f"総物件数: {total_count}")
    logger.info(f"property_hashがNULL: {null_count}")
    logger.info(f"property_hashが非NULL: {not_null_count}")
    
    if not_null_count > 0:
        logger.warning(f"まだ{not_null_count}件の物件にproperty_hashが設定されています")
        
        # サンプルを表示
        samples = session.query(MasterProperty).filter(
            MasterProperty.property_hash.isnot(None)
        ).limit(5).all()
        
        for prop in samples:
            logger.info(
                f"  - ID: {prop.id}, "
                f"建物ID: {prop.building_id}, "
                f"階: {prop.floor_number}, "
                f"面積: {prop.area}, "
                f"ハッシュ: {prop.property_hash[:8]}..."
            )
    
    return null_count, not_null_count


def remove_property_hash_column(session):
    """property_hashカラムを削除"""
    logger.info("=== property_hashカラムの削除 ===")
    
    try:
        # カラムを削除
        drop_column_sql = text("""
            ALTER TABLE master_properties 
            DROP COLUMN IF EXISTS property_hash
        """)
        
        session.execute(drop_column_sql)
        session.commit()
        logger.info("✓ property_hashカラムを削除しました")
        
    except Exception as e:
        logger.error(f"カラム削除エラー: {e}")
        session.rollback()
        raise


def verify_removal(session):
    """削除が成功したか確認"""
    logger.info("=== 削除の確認 ===")
    
    try:
        # カラムが存在するか確認
        check_sql = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'master_properties' 
            AND column_name = 'property_hash'
        """)
        
        result = session.execute(check_sql).fetchone()
        
        if result:
            logger.error("property_hashカラムがまだ存在します")
            return False
        else:
            logger.info("✓ property_hashカラムが正常に削除されました")
            return True
            
    except Exception as e:
        logger.error(f"確認エラー: {e}")
        return False


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 1. 使用状況を確認
        null_count, not_null_count = check_property_hash_usage(session)
        
        # 2. 確認
        print("\n" + "="*60)
        print("property_hashカラムを削除します。")
        print("この操作は元に戻すことができません。")
        print("="*60)
        
        if not_null_count > 0:
            print(f"\n警告: まだ{not_null_count}件の物件にproperty_hashが設定されています。")
            print("これらの値は失われます。")
        
        response = input("\n続行しますか？ (y/N): ")
        if response.lower() != 'y':
            logger.info("処理を中止しました")
            return
        
        # 3. カラムを削除
        remove_property_hash_column(session)
        
        # 4. 削除を確認
        if verify_removal(session):
            logger.info("\n=== 完了 ===")
            logger.info("property_hashカラムの削除が完了しました。")
            logger.info("次のステップ：")
            logger.info("1. models.pyからproperty_hashの定義を削除")
            logger.info("2. 管理画面でFuzzyPropertyMatcherベースの物件重複検出を実装")
        else:
            logger.error("削除の確認に失敗しました")
        
    except Exception as e:
        logger.error(f"処理エラー: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()