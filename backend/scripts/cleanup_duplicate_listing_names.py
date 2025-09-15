#!/usr/bin/env python
"""
BuildingListingNameテーブルの重複エントリをクリーンアップするスクリプト

同じcanonical_name（正規化された名前）を持つエントリを統合し、
最も出現回数が多い表記を代表名として保持します。
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from backend.app.models import BuildingListingName
from backend.app.utils.building_name_normalizer import normalize_building_name, canonicalize_building_name
import logging
import os

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cleanup_duplicate_listing_names(dry_run: bool = True):
    """
    重複する建物名エントリをクリーンアップ
    
    Args:
        dry_run: Trueの場合、実際の削除・更新は行わない
    """
    # データベース接続
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 建物ごとに処理
        building_ids = session.query(
            BuildingListingName.building_id
        ).distinct().all()
        
        total_duplicates = 0
        total_merged = 0
        
        for (building_id,) in building_ids:
            # この建物の全エントリを取得
            entries = session.query(BuildingListingName).filter(
                BuildingListingName.building_id == building_id
            ).all()
            
            if not entries:
                continue
            
            # canonical_nameでグループ化
            canonical_groups = defaultdict(list)
            for entry in entries:
                # canonical_nameが設定されていない場合は正規化
                if not entry.canonical_name:
                    entry.canonical_name = canonicalize_building_name(entry.normalized_name)
                canonical_groups[entry.canonical_name].append(entry)
            
            # 重複があるグループを処理
            for canonical_name, group_entries in canonical_groups.items():
                if len(group_entries) <= 1:
                    continue
                
                total_duplicates += len(group_entries) - 1
                
                # 出現回数が最も多いエントリを見つける
                primary_entry = max(group_entries, key=lambda x: x.occurrence_count)
                
                # 他のエントリの情報をマージ
                for entry in group_entries:
                    if entry.id == primary_entry.id:
                        continue
                    
                    # 出現回数を加算
                    primary_entry.occurrence_count += entry.occurrence_count
                    
                    # サイト情報をマージ
                    primary_sites = set(primary_entry.source_sites.split(',')) if primary_entry.source_sites else set()
                    entry_sites = set(entry.source_sites.split(',')) if entry.source_sites else set()
                    primary_entry.source_sites = ','.join(sorted(primary_sites | entry_sites))
                    
                    # 日付を更新
                    if entry.first_seen_at < primary_entry.first_seen_at:
                        primary_entry.first_seen_at = entry.first_seen_at
                    if entry.last_seen_at > primary_entry.last_seen_at:
                        primary_entry.last_seen_at = entry.last_seen_at
                    
                    logger.info(
                        f"建物ID {building_id}: "
                        f"'{entry.normalized_name}' (出現回数: {entry.occurrence_count}) を "
                        f"'{primary_entry.normalized_name}' (出現回数: {primary_entry.occurrence_count}) に統合"
                    )
                    
                    if not dry_run:
                        session.delete(entry)
                
                total_merged += 1
        
        if not dry_run:
            session.commit()
            logger.info(f"クリーンアップ完了: {total_duplicates}件の重複を{total_merged}グループに統合しました")
        else:
            logger.info(f"[DRY RUN] {total_duplicates}件の重複が{total_merged}グループに統合される予定です")
            logger.info("実際に実行するには --execute オプションを付けて実行してください")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='BuildingListingNameテーブルの重複エントリをクリーンアップ'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='実際にクリーンアップを実行（このオプションなしではドライラン）'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("BuildingListingNameテーブルのクリーンアップを開始")
    logger.info("=" * 60)
    
    cleanup_duplicate_listing_names(dry_run=not args.execute)


if __name__ == "__main__":
    main()