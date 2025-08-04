#!/usr/bin/env python3
"""
property_hashから複合ユニークインデックスへの移行スクリプト

このスクリプトは以下の処理を行います：
1. 重複する物件を事前チェック
2. 複合ユニークインデックスの作成
3. property_hash関連の制約を削除
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import MasterProperty, Building
from sqlalchemy import text, func, and_
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_duplicates(session):
    """複合キーで重複する物件をチェック"""
    logger.info("=== 重複チェック開始 ===")
    
    # 複合キーで重複する物件を検出
    duplicates = session.query(
        MasterProperty.building_id,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction,
        func.count(MasterProperty.id).label('count')
    ).group_by(
        MasterProperty.building_id,
        MasterProperty.floor_number,
        MasterProperty.area,
        MasterProperty.layout,
        MasterProperty.direction
    ).having(
        func.count(MasterProperty.id) > 1
    ).all()
    
    if duplicates:
        logger.warning(f"重複する物件グループが{len(duplicates)}件見つかりました")
        
        # 詳細を表示
        for dup in duplicates[:10]:  # 最初の10件のみ表示
            building = session.query(Building).filter(Building.id == dup.building_id).first()
            logger.warning(
                f"建物: {building.normalized_name if building else '不明'} "
                f"({dup.building_id}), "
                f"階: {dup.floor_number}, "
                f"面積: {dup.area}, "
                f"間取り: {dup.layout}, "
                f"方角: {dup.direction} "
                f"=> {dup.count}件"
            )
            
            # 該当する物件を表示
            properties = session.query(MasterProperty).filter(
                and_(
                    MasterProperty.building_id == dup.building_id,
                    MasterProperty.floor_number == dup.floor_number,
                    MasterProperty.area == dup.area,
                    MasterProperty.layout == dup.layout,
                    MasterProperty.direction == dup.direction
                )
            ).all()
            
            for prop in properties:
                logger.info(
                    f"  - ID: {prop.id}, "
                    f"部屋番号: {prop.room_number}, "
                    f"ハッシュ: {prop.property_hash[:8]}..."
                )
        
        return False
    else:
        logger.info("重複する物件はありません")
        return True


def create_composite_unique_index(session):
    """複合ユニークインデックスを作成"""
    logger.info("=== 複合ユニークインデックスの作成 ===")
    
    try:
        # 既存のインデックスを確認
        check_sql = text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'master_properties' 
            AND indexname = 'idx_property_composite_unique'
        """)
        
        existing = session.execute(check_sql).fetchone()
        
        if existing:
            logger.info("複合ユニークインデックスは既に存在します")
        else:
            # 複合ユニークインデックスを作成
            # 部屋番号がNULLの場合のみユニーク制約を適用
            create_index_sql = text("""
                CREATE UNIQUE INDEX idx_property_composite_unique 
                ON master_properties(building_id, floor_number, area, layout, direction)
                WHERE room_number IS NULL
            """)
            
            session.execute(create_index_sql)
            session.commit()
            logger.info("✓ 複合ユニークインデックスを作成しました")
            
            # 部屋番号がある場合の通常インデックスも作成
            create_normal_index_sql = text("""
                CREATE INDEX IF NOT EXISTS idx_property_composite 
                ON master_properties(building_id, floor_number, area, layout, direction)
            """)
            
            session.execute(create_normal_index_sql)
            session.commit()
            logger.info("✓ 通常の複合インデックスも作成しました")
            
    except Exception as e:
        logger.error(f"インデックス作成エラー: {e}")
        session.rollback()
        raise


def remove_property_hash_constraints(session):
    """property_hash関連の制約を削除"""
    logger.info("=== property_hash制約の削除 ===")
    
    try:
        # UNIQUEキー制約を削除
        drop_unique_sql = text("""
            ALTER TABLE master_properties 
            DROP CONSTRAINT IF EXISTS master_properties_property_hash_key
        """)
        
        session.execute(drop_unique_sql)
        logger.info("✓ UNIQUEキー制約を削除しました")
        
        # インデックスを削除
        drop_index_sql = text("""
            DROP INDEX IF EXISTS idx_master_properties_property_hash
        """)
        
        session.execute(drop_index_sql)
        logger.info("✓ property_hashインデックスを削除しました")
        
        # NOT NULL制約を削除（カラムはまだ残す）
        alter_column_sql = text("""
            ALTER TABLE master_properties 
            ALTER COLUMN property_hash DROP NOT NULL
        """)
        
        session.execute(alter_column_sql)
        logger.info("✓ property_hashのNOT NULL制約を削除しました")
        
        session.commit()
        
    except Exception as e:
        logger.error(f"制約削除エラー: {e}")
        session.rollback()
        raise


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 1. 重複チェック
        if not check_duplicates(session):
            logger.error("\n重複する物件が存在するため、処理を中止します。")
            logger.error("重複する物件を手動で統合してから再実行してください。")
            return
        
        # 2. 確認
        response = input("\n複合ユニークインデックスを作成し、property_hash制約を削除します。続行しますか？ (y/N): ")
        if response.lower() != 'y':
            logger.info("処理を中止しました")
            return
        
        # 3. 複合ユニークインデックスを作成
        create_composite_unique_index(session)
        
        # 4. property_hash制約を削除
        remove_property_hash_constraints(session)
        
        # 5. 統計情報を表示
        total_properties = session.query(func.count(MasterProperty.id)).scalar()
        properties_with_room = session.query(func.count(MasterProperty.id)).filter(
            MasterProperty.room_number.isnot(None)
        ).scalar()
        
        logger.info("\n=== 完了 ===")
        logger.info(f"総物件数: {total_properties}")
        logger.info(f"部屋番号あり: {properties_with_room}")
        logger.info(f"部屋番号なし（ユニーク制約対象）: {total_properties - properties_with_room}")
        logger.info("\nproperty_hashから複合インデックスへの移行が完了しました。")
        logger.info("次のステップ：")
        logger.info("1. base_scraper.pyのproperty_hash生成処理を削除")
        logger.info("2. FuzzyPropertyMatcherを使った重複検出の実装")
        logger.info("3. 最終的にproperty_hashカラムを削除")
        
    except Exception as e:
        logger.error(f"処理エラー: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()