#!/usr/bin/env python3
"""
物件情報と建物情報を多数決で更新するスクリプト

物件情報：紐づけられた掲載情報の多数決で決定
建物情報：紐づけられた物件情報の多数決で決定
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import Building, MasterProperty, PropertyListing
from sqlalchemy import func
from collections import Counter
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_most_common_value(values, current_value=None):
    """
    最頻値を取得する。同数の場合は現在の値を優先、
    現在の値がない場合は最初に見つかった値を返す
    """
    if not values:
        return None
    
    # Noneや空文字を除外
    valid_values = [v for v in values if v is not None and v != '']
    if not valid_values:
        return current_value
    
    # 値の出現回数をカウント
    counter = Counter(valid_values)
    max_count = max(counter.values())
    
    # 最頻値が複数ある場合
    most_common = [value for value, count in counter.items() if count == max_count]
    
    # 現在の値が最頻値の中にあればそれを優先
    if current_value in most_common:
        return current_value
    
    # そうでなければ最初の最頻値を返す
    return most_common[0]


def update_master_property_by_majority(session, dry_run=True):
    """物件情報を掲載情報の多数決で更新"""
    logger.info("=== 物件情報の多数決更新開始 ===")
    
    # 全物件を取得
    properties = session.query(MasterProperty).all()
    update_count = 0
    
    for prop in properties:
        # この物件の全掲載情報を取得
        listings = session.query(PropertyListing).filter(
            PropertyListing.master_property_id == prop.id,
            PropertyListing.is_active == True
        ).all()
        
        if len(listings) <= 1:
            continue
        
        updates = {}
        
        # 階数の多数決
        floor_numbers = []
        for listing in listings:
            # listingから直接階数情報を取得する方法がないため、
            # 詳細ページから抽出された情報を使用する必要がある
            # ここでは説明欄やタイトルから抽出することを想定
            # 実際のスクレイパーの実装に応じて調整が必要
            pass
        
        # 現時点では、PropertyListingテーブルに階数、面積、間取り、方角の情報が
        # 直接保存されていないため、これらの情報は物件詳細ページの
        # descriptionやremarksから抽出する必要があります
        
        # より実用的なアプローチとして、各スクレイパーが物件情報を保存する際に
        # これらの値も一緒に保存するように拡張することを推奨します
        
        logger.info(f"物件ID {prop.id}: 掲載数 {len(listings)}")
    
    logger.info(f"更新対象: {update_count}件")


def update_building_by_majority(session, dry_run=True):
    """建物情報を物件情報の多数決で更新"""
    logger.info("=== 建物情報の多数決更新開始 ===")
    
    # 全建物を取得
    buildings = session.query(Building).all()
    update_count = 0
    
    for building in buildings:
        # この建物の全物件を取得
        properties = session.query(MasterProperty).filter(
            MasterProperty.building_id == building.id
        ).all()
        
        if len(properties) <= 1:
            continue
        
        updates = {}
        
        # 総階数の多数決
        total_floors_values = [p.floor_number for p in properties if p.floor_number]
        if total_floors_values:
            # 物件の最大階数を建物の総階数として推定
            new_total_floors = max(total_floors_values)
            if building.total_floors != new_total_floors:
                updates['total_floors'] = new_total_floors
                logger.info(f"建物ID {building.id} ({building.normalized_name}): "
                          f"総階数 {building.total_floors} → {new_total_floors}")
        
        # 住所の多数決（通常は変わらないはずだが念のため）
        # PropertyListingから住所情報を取得できる場合のみ
        
        if updates:
            if not dry_run:
                for key, value in updates.items():
                    setattr(building, key, value)
            update_count += 1
    
    logger.info(f"更新対象: {update_count}件")
    
    if not dry_run:
        session.commit()
        logger.info("変更をコミットしました")


def add_listing_property_fields(session):
    """
    PropertyListingテーブルに物件属性フィールドを追加する
    （将来的な拡張案）
    """
    # この関数は、PropertyListingテーブルに以下のフィールドを追加することを提案します：
    # - listing_floor_number: この掲載での階数情報
    # - listing_area: この掲載での面積情報
    # - listing_layout: この掲載での間取り情報
    # - listing_direction: この掲載での方角情報
    # - listing_total_floors: この掲載での総階数情報
    
    # これにより、各サイトごとの情報を保持しつつ、
    # 多数決で最も信頼できる情報を特定できるようになります
    pass


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='物件・建物情報を多数決で更新')
    parser.add_argument('--execute', action='store_true', help='実際に更新を実行（デフォルトはドライラン）')
    parser.add_argument('--target', choices=['property', 'building', 'both'], 
                      default='both', help='更新対象')
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        if args.target in ['property', 'both']:
            update_master_property_by_majority(session, dry_run=not args.execute)
        
        if args.target in ['building', 'both']:
            update_building_by_majority(session, dry_run=not args.execute)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()