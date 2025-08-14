#!/usr/bin/env python3
"""
display_building_nameが未設定の物件を修正するスクリプト
"""

import os
import sys
from datetime import datetime

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import MasterProperty, PropertyListing, Building
from app.utils.majority_vote_updater import MajorityVoteUpdater
from sqlalchemy import or_


def find_properties_with_missing_display_name(session):
    """display_building_nameが未設定の物件を検索"""
    properties = session.query(MasterProperty).filter(
        or_(
            MasterProperty.display_building_name == None,
            MasterProperty.display_building_name == ''
        )
    ).all()
    
    return properties


def fix_display_building_name(session, property_obj, updater, dry_run=False):
    """物件のdisplay_building_nameを修正"""
    # 掲載情報を確認
    listings = session.query(PropertyListing).filter(
        PropertyListing.master_property_id == property_obj.id,
        PropertyListing.is_active == True
    ).all()
    
    # 建物情報を取得
    building = session.query(Building).filter(
        Building.id == property_obj.building_id
    ).first()
    
    print(f"\n物件ID {property_obj.id}:")
    print(f"  建物ID: {property_obj.building_id}")
    print(f"  建物名: {building.normalized_name if building else 'なし'}")
    print(f"  現在のdisplay_building_name: '{property_obj.display_building_name}'")
    print(f"  アクティブな掲載数: {len(listings)}")
    
    if listings:
        # 掲載情報から建物名を表示
        for listing in listings[:3]:  # 最初の3件のみ表示
            print(f"    - {listing.source_site}: {listing.listing_building_name}")
    
    if not dry_run:
        # 多数決で更新
        result = updater.update_property_building_name_by_majority(property_obj.id)
        if result:
            # 更新後の値を再取得
            session.refresh(property_obj)
            print(f"  → 更新後: '{property_obj.display_building_name}'")
            return True
        else:
            print(f"  → 更新失敗（掲載情報なしまたはエラー）")
            # 掲載情報がない場合は建物名を使用
            if building and not listings:
                property_obj.display_building_name = building.normalized_name
                property_obj.updated_at = datetime.utcnow()
                print(f"  → 建物名を使用: '{building.normalized_name}'")
                return True
    else:
        # ドライランモードでは、どのような値になるか予測
        if listings:
            print(f"  → 多数決により更新予定")
        elif building:
            print(f"  → 建物名を使用予定: '{building.normalized_name}'")
        else:
            print(f"  → 更新不可（建物情報なし）")
        return True
    
    return False


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='display_building_nameが未設定の物件を修正')
    parser.add_argument('--dry-run', action='store_true', help='実際に修正せず、対象を表示するのみ')
    parser.add_argument('--limit', type=int, help='処理する物件数の上限')
    args = parser.parse_args()
    
    session = SessionLocal()
    updater = MajorityVoteUpdater(session)
    
    try:
        print("display_building_nameが未設定の物件を検索中...")
        properties = find_properties_with_missing_display_name(session)
        
        if not properties:
            print("display_building_nameが未設定の物件は見つかりませんでした。")
            return
        
        print(f"\n{len(properties)}件の物件が見つかりました。")
        
        if args.limit:
            properties = properties[:args.limit]
            print(f"（上限{args.limit}件に制限）")
        
        if args.dry_run:
            print("\n【ドライランモード】実際の修正は行いません。")
        
        fixed_count = 0
        for property_obj in properties:
            if fix_display_building_name(session, property_obj, updater, args.dry_run):
                fixed_count += 1
        
        if not args.dry_run and fixed_count > 0:
            print(f"\n{fixed_count}件の物件のdisplay_building_nameを修正しています...")
            session.commit()
            print("修正が完了しました。")
        else:
            print(f"\n修正対象: {fixed_count}件")
            if fixed_count > 0 and args.dry_run:
                print("実際に修正するには --dry-run オプションを外して実行してください。")
    
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()