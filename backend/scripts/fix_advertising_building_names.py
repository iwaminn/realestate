#!/usr/bin/env python3
"""
広告文を含む建物名を修正するスクリプト
"""

import os
import sys
import re
from datetime import datetime

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import MasterProperty, PropertyListing, Building
from app.utils.majority_vote_updater import MajorityVoteUpdater
from app.utils.building_name_normalizer import normalize_building_name
from sqlalchemy import or_


def clean_advertising_text(building_name: str) -> str:
    """建物名から広告文を除去"""
    if not building_name:
        return ""
    
    cleaned = building_name
    
    # 【】で囲まれた広告文を除去
    cleaned = re.sub(r'【[^】]+】', '', cleaned)
    
    # 《》で囲まれた広告文を除去
    cleaned = re.sub(r'《[^》]+》', '', cleaned)
    
    # ◆◇■□などの記号を除去
    cleaned = re.sub(r'[◆◇■□▼▲●○★☆※]', '', cleaned)
    
    # ×以降のリノベ表記などを除去（ただし建物名の一部である可能性もあるので慎重に）
    # 「×フルリノベ」「×リフォーム済」などのパターンのみ除去
    cleaned = re.sub(r'×(フルリノベ|リノベ|リフォーム|新規内装).*$', '', cleaned)
    
    # 先頭末尾の記号を除去
    cleaned = re.sub(r'^[・、。！？]+|[・、。！？]+$', '', cleaned)
    
    # スペースの正規化
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def fix_property_building_names(session, dry_run=False):
    """広告文を含む建物名を修正"""
    
    # 問題のある物件を検索
    properties = session.query(MasterProperty).filter(
        or_(
            MasterProperty.display_building_name.like('%【%'),
            MasterProperty.display_building_name.like('%】%'),
            MasterProperty.display_building_name.like('%×フルリノベ%'),
            MasterProperty.display_building_name.like('%×リノベ%'),
            MasterProperty.display_building_name.like('%×リフォーム%'),
            MasterProperty.display_building_name == '',
            MasterProperty.display_building_name == None
        )
    ).all()
    
    print(f"修正対象: {len(properties)}件の物件")
    
    updater = MajorityVoteUpdater(session)
    fixed_count = 0
    
    for prop in properties:
        print(f"\n物件ID {prop.id}:")
        print(f"  現在の建物名: '{prop.display_building_name}'")
        
        # 掲載情報から建物名を取得
        listings = session.query(PropertyListing).filter(
            PropertyListing.master_property_id == prop.id,
            PropertyListing.is_active == True
        ).all()
        
        if listings:
            # 各掲載の建物名をクリーンアップ
            cleaned_names = {}
            for listing in listings:
                if listing.listing_building_name:
                    cleaned = clean_advertising_text(listing.listing_building_name)
                    if cleaned:
                        normalized = normalize_building_name(cleaned)
                        if normalized not in cleaned_names:
                            cleaned_names[normalized] = []
                        cleaned_names[normalized].append({
                            'source_site': listing.source_site,
                            'original': listing.listing_building_name
                        })
            
            if cleaned_names:
                # 最も多く出現する建物名を選択
                best_name = max(cleaned_names.keys(), key=lambda k: len(cleaned_names[k]))
                print(f"  クリーンアップ後: '{best_name}'")
                
                if not dry_run:
                    prop.display_building_name = best_name
                    prop.updated_at = datetime.utcnow()
                    fixed_count += 1
            else:
                # 建物マスターから取得
                building = session.query(Building).filter(
                    Building.id == prop.building_id
                ).first()
                
                if building and building.normalized_name:
                    cleaned = clean_advertising_text(building.normalized_name)
                    if cleaned:
                        print(f"  建物マスターから: '{cleaned}'")
                        if not dry_run:
                            prop.display_building_name = normalize_building_name(cleaned)
                            prop.updated_at = datetime.utcnow()
                            fixed_count += 1
        else:
            # 掲載情報がない場合は建物マスターから
            building = session.query(Building).filter(
                Building.id == prop.building_id
            ).first()
            
            if building and building.normalized_name:
                cleaned = clean_advertising_text(building.normalized_name)
                if cleaned:
                    print(f"  建物マスターから: '{cleaned}'")
                    if not dry_run:
                        prop.display_building_name = normalize_building_name(cleaned)
                        prop.updated_at = datetime.utcnow()
                        fixed_count += 1
    
    return fixed_count


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='広告文を含む建物名を修正')
    parser.add_argument('--dry-run', action='store_true', help='実際に修正せず、対象を表示するのみ')
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        if args.dry_run:
            print("【ドライランモード】実際の修正は行いません。\n")
        
        fixed_count = fix_property_building_names(session, args.dry_run)
        
        if not args.dry_run and fixed_count > 0:
            print(f"\n{fixed_count}件の物件の建物名を修正しています...")
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