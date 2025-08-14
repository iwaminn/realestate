#!/usr/bin/env python3
"""
既存の建物名正規化データを新しい正規化ルール（大文字統一）で更新するスクリプト

実行方法:
    docker exec realestate-backend poetry run python /app/backend/scripts/update_normalized_names.py [--dry-run]
"""

import sys
import argparse
from typing import List, Tuple
import logging
from datetime import datetime

# パス設定
sys.path.append('/app/backend')

from app.database import SessionLocal
from app.models import Building, MasterProperty, PropertyListing
from app.scrapers.suumo_scraper import SuumoScraper
from sqlalchemy import func

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_normalization_changes(session, scraper) -> List[Tuple[str, str, int]]:
    """
    正規化ルールの変更による影響を分析
    
    Returns:
        [(現在の正規化名, 新しい正規化名, 影響を受ける建物数)]
    """
    logger.info("正規化ルールの変更による影響を分析中...")
    
    # 建物テーブルの全ての normalized_name を取得
    buildings = session.query(
        Building.normalized_name,
        func.count(Building.id).label('count')
    ).group_by(
        Building.normalized_name
    ).all()
    
    changes = []
    for current_name, count in buildings:
        if current_name:
            # 新しい正規化ルールを適用
            new_name = scraper.normalize_building_name(current_name)
            
            # 変更がある場合のみ記録
            if current_name != new_name:
                changes.append((current_name, new_name, count))
    
    return changes


def analyze_canonical_name_changes(session, scraper) -> List[Tuple[str, str, int]]:
    """
    canonical_name（検索キー）の変更による影響を分析
    
    Returns:
        [(現在のcanonical_name, 新しいcanonical_name, 影響を受ける建物数)]
    """
    logger.info("canonical_name の変更による影響を分析中...")
    
    # 建物テーブルの全ての canonical_name を取得
    buildings = session.query(
        Building.canonical_name,
        func.count(Building.id).label('count')
    ).filter(
        Building.canonical_name.isnot(None)
    ).group_by(
        Building.canonical_name
    ).all()
    
    changes = []
    for current_key, count in buildings:
        # 一度正規化してから検索キーを生成
        # canonical_nameは既に処理済みの値なので、元の建物名が必要
        # ここでは簡易的に、現在のcanonical_nameから逆算
        
        # 実際の建物を1つ取得して、その建物名から新しいキーを生成
        sample_building = session.query(Building).filter(
            Building.canonical_name == current_key
        ).first()
        
        if sample_building and sample_building.normalized_name:
            new_key = scraper.get_search_key_for_building(sample_building.normalized_name)
            
            # 変更がある場合のみ記録
            if current_key != new_key:
                changes.append((current_key, new_key, count))
    
    return changes


def update_building_names(session, scraper, dry_run=False):
    """
    建物名の正規化を更新
    """
    logger.info(f"建物名の正規化を更新中... (dry_run={dry_run})")
    
    # すべての建物を取得
    buildings = session.query(Building).all()
    
    updated_count = 0
    merged_buildings = {}  # 新しい正規化名 -> 建物IDリスト
    
    for building in buildings:
        if building.normalized_name:
            # 新しい正規化ルールを適用
            old_normalized = building.normalized_name
            new_normalized = scraper.normalize_building_name(old_normalized)
            
            # canonical_name も更新
            old_canonical = building.canonical_name
            new_canonical = scraper.get_search_key_for_building(new_normalized)
            
            if old_normalized != new_normalized or old_canonical != new_canonical:
                logger.info(
                    f"建物 ID={building.id}: "
                    f"normalized_name: '{old_normalized}' → '{new_normalized}', "
                    f"canonical_name: '{old_canonical}' → '{new_canonical}'"
                )
                
                if not dry_run:
                    building.normalized_name = new_normalized
                    building.canonical_name = new_canonical
                    updated_count += 1
                
                # 同じ正規化名になる建物を記録（統合候補）
                if new_canonical not in merged_buildings:
                    merged_buildings[new_canonical] = []
                merged_buildings[new_canonical].append({
                    'id': building.id,
                    'old_name': old_normalized,
                    'new_name': new_normalized,
                    'address': building.address
                })
    
    # 統合候補を報告
    logger.info("\n=== 統合候補の建物 ===")
    for canonical_name, buildings_list in merged_buildings.items():
        if len(buildings_list) > 1:
            logger.warning(f"\n同じcanonical_name '{canonical_name}' になる建物:")
            for b in buildings_list:
                logger.warning(
                    f"  - ID={b['id']}: '{b['old_name']}' → '{b['new_name']}' "
                    f"(住所: {b['address']})"
                )
    
    if not dry_run:
        session.commit()
        logger.info(f"✅ {updated_count} 件の建物を更新しました")
    else:
        logger.info(f"[DRY RUN] {updated_count} 件の建物が更新対象です")
    
    return updated_count


def update_property_display_names(session, scraper, dry_run=False):
    """
    物件の表示用建物名を更新
    """
    logger.info(f"物件の表示用建物名を更新中... (dry_run={dry_run})")
    
    # display_building_name が設定されている物件を取得
    properties = session.query(MasterProperty).filter(
        MasterProperty.display_building_name.isnot(None)
    ).all()
    
    updated_count = 0
    
    for property_obj in properties:
        old_name = property_obj.display_building_name
        new_name = scraper.normalize_building_name(old_name)
        
        if old_name != new_name:
            logger.info(
                f"物件 ID={property_obj.id}: "
                f"display_building_name: '{old_name}' → '{new_name}'"
            )
            
            if not dry_run:
                property_obj.display_building_name = new_name
                updated_count += 1
    
    if not dry_run:
        session.commit()
        logger.info(f"✅ {updated_count} 件の物件表示名を更新しました")
    else:
        logger.info(f"[DRY RUN] {updated_count} 件の物件表示名が更新対象です")
    
    return updated_count


def main():
    parser = argparse.ArgumentParser(
        description='既存の建物名正規化データを新しい正規化ルールで更新'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='実際には更新せず、変更内容のみ表示'
    )
    parser.add_argument(
        '--analyze-only',
        action='store_true',
        help='影響分析のみ実行'
    )
    
    args = parser.parse_args()
    
    # データベースセッション作成
    session = SessionLocal()
    
    # スクレイパー（正規化メソッド用）
    scraper = SuumoScraper()
    
    try:
        logger.info("=== 建物名正規化の更新スクリプト ===")
        logger.info(f"開始時刻: {datetime.now()}")
        
        if args.analyze_only or args.dry_run:
            # 影響分析
            logger.info("\n=== 影響分析 ===")
            
            # normalized_name の変更
            norm_changes = analyze_normalization_changes(session, scraper)
            if norm_changes:
                logger.info(f"\nnormalized_name の変更: {len(norm_changes)} パターン")
                for old, new, count in norm_changes[:10]:  # 最初の10件のみ表示
                    logger.info(f"  '{old}' → '{new}' ({count}件)")
                if len(norm_changes) > 10:
                    logger.info(f"  ... 他 {len(norm_changes) - 10} パターン")
            else:
                logger.info("normalized_name に変更はありません")
            
            # canonical_name の変更
            canon_changes = analyze_canonical_name_changes(session, scraper)
            if canon_changes:
                logger.info(f"\ncanonical_name の変更: {len(canon_changes)} パターン")
                for old, new, count in canon_changes[:10]:  # 最初の10件のみ表示
                    logger.info(f"  '{old}' → '{new}' ({count}件)")
                if len(canon_changes) > 10:
                    logger.info(f"  ... 他 {len(canon_changes) - 10} パターン")
            else:
                logger.info("canonical_name に変更はありません")
        
        if not args.analyze_only:
            # 実際の更新（またはdry-run）
            logger.info(f"\n=== 更新処理 (dry_run={args.dry_run}) ===")
            
            # 建物名の更新
            building_count = update_building_names(session, scraper, args.dry_run)
            
            # 物件表示名の更新
            property_count = update_property_display_names(session, scraper, args.dry_run)
            
            logger.info(f"\n=== 完了 ===")
            logger.info(f"更新された建物: {building_count} 件")
            logger.info(f"更新された物件表示名: {property_count} 件")
        
        logger.info(f"終了時刻: {datetime.now()}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()