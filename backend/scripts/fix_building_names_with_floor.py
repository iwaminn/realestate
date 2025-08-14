#!/usr/bin/env python3
"""
階数を含む建物名を修正するスクリプト

問題例：
- "SAION SAKURAZAKA 14階" → "SAION SAKURAZAKA"
- "5階の3方向角住戸〜ブランズ赤坂〜" → "ブランズ赤坂"
"""

import os
import sys
import re
from datetime import datetime

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, MasterProperty, PropertyListing
from app.utils.majority_vote_updater import MajorityVoteUpdater
from sqlalchemy import func


def extract_clean_building_name(building_name: str) -> str:
    """建物名から階数や広告的な表現を除去"""
    if not building_name:
        return building_name
    
    cleaned = building_name
    
    # パターン1: 「地下○階」を除去（「地下」まで含めて除去）
    cleaned = re.sub(r'\s*地下\d+階$', '', cleaned)
    
    # パターン2: 末尾の「○階」を除去
    cleaned = re.sub(r'\s*\d+階$', '', cleaned)
    
    # パターン3: 「〜...〜」の装飾を除去（ブランズ赤坂を抽出）
    match = re.search(r'〜([^〜]+)〜', cleaned)
    if match:
        cleaned = match.group(1)
    
    # パターン4: 「○階の...」「○階部分」などの前置詞を除去
    cleaned = re.sub(r'^\d+階の[^〜]+〜', '', cleaned)
    cleaned = re.sub(r'\s*\d+階部分$', '', cleaned)
    
    # パターン5: 「×○階」のパターンを除去
    cleaned = re.sub(r'×\d+階[^×]*', '', cleaned)
    
    # スペースの正規化
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def find_buildings_with_floor_in_name(session):
    """階数を含む建物名を持つ建物を検索"""
    # 階数を含むパターン
    patterns = [
        r'\d+階',  # 「○階」を含む
        r'地下\d+階',  # 「地下○階」を含む
        r'〜.*〜',  # 装飾的な表現
    ]
    
    buildings_to_fix = []
    
    for pattern in patterns:
        buildings = session.query(Building).filter(
            Building.normalized_name.op('~')(pattern)
        ).all()
        
        for building in buildings:
            if building not in buildings_to_fix:
                buildings_to_fix.append(building)
    
    return buildings_to_fix


def fix_building_name(session, building, dry_run=False):
    """建物名を修正"""
    original_name = building.normalized_name
    cleaned_name = extract_clean_building_name(original_name)
    
    # 変更が必要ない場合はスキップ
    if cleaned_name == original_name:
        return False
    
    print(f"\n建物ID {building.id}:")
    print(f"  現在の名前: {original_name}")
    print(f"  修正後の名前: {cleaned_name}")
    
    # ドライランモードでも修正対象としてカウント
    if dry_run:
        return True
    
    if not dry_run:
        # 掲載情報から多数決で正しい建物名を取得
        updater = MajorityVoteUpdater(session)
        
        # この建物に紐づく全掲載情報を取得
        listings = session.query(PropertyListing).join(
            MasterProperty
        ).filter(
            MasterProperty.building_id == building.id,
            PropertyListing.is_active == True
        ).all()
        
        if listings:
            # 掲載情報から建物名を収集
            building_names = {}
            for listing in listings:
                if listing.listing_building_name:
                    # 掲載情報の建物名から階数を除去
                    clean_name = extract_clean_building_name(listing.listing_building_name)
                    if clean_name:
                        site = listing.source_site
                        if clean_name not in building_names:
                            building_names[clean_name] = []
                        building_names[clean_name].append({
                            'source_site': site,
                            'listing_id': listing.id
                        })
            
            # 最も信頼性の高い建物名を選択
            if building_names:
                # 重み付き投票で最適な建物名を選択
                best_name = None
                max_score = 0
                
                for name, sources in building_names.items():
                    score = 0
                    for source in sources:
                        # サイトの優先度で重み付け
                        weight = updater.get_site_priority_weight(source['source_site'])
                        score += weight
                    
                    print(f"    候補: {name} (スコア: {score}, 掲載数: {len(sources)})")
                    
                    if score > max_score:
                        max_score = score
                        best_name = name
                
                if best_name and best_name != original_name:
                    print(f"  → 多数決により「{best_name}」に決定")
                    building.normalized_name = best_name
                    building.updated_at = datetime.utcnow()
                    return True
                elif cleaned_name != original_name:
                    # 多数決で決まらない場合は、単純に階数を除去
                    print(f"  → 階数を除去して「{cleaned_name}」に修正")
                    building.normalized_name = cleaned_name
                    building.updated_at = datetime.utcnow()
                    return True
        else:
            # 掲載情報がない場合は単純に階数を除去
            if cleaned_name != original_name:
                print(f"  → 掲載情報なし。階数を除去して「{cleaned_name}」に修正")
                building.normalized_name = cleaned_name
                building.updated_at = datetime.utcnow()
                return True
    
    return False


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='階数を含む建物名を修正')
    parser.add_argument('--dry-run', action='store_true', help='実際に修正せず、対象を表示するのみ')
    parser.add_argument('--limit', type=int, help='処理する建物数の上限')
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        print("階数を含む建物名を検索中...")
        buildings = find_buildings_with_floor_in_name(session)
        
        if not buildings:
            print("階数を含む建物名は見つかりませんでした。")
            return
        
        print(f"\n{len(buildings)}件の建物が見つかりました。")
        
        if args.limit:
            buildings = buildings[:args.limit]
            print(f"（上限{args.limit}件に制限）")
        
        if args.dry_run:
            print("\n【ドライランモード】実際の修正は行いません。")
        
        fixed_count = 0
        for building in buildings:
            if fix_building_name(session, building, args.dry_run):
                fixed_count += 1
        
        if not args.dry_run and fixed_count > 0:
            print(f"\n{fixed_count}件の建物名を修正しています...")
            session.commit()
            print("修正が完了しました。")
            
            # 物件の建物名も更新
            print("\n関連する物件の建物名を更新中...")
            updater = MajorityVoteUpdater(session)
            
            for building in buildings:
                # この建物の全物件を取得
                properties = session.query(MasterProperty).filter(
                    MasterProperty.building_id == building.id
                ).all()
                
                for prop in properties:
                    # 物件レベルの建物名を更新
                    updater.update_property_building_name_by_majority(prop.id)
            
            session.commit()
            print("物件の建物名更新が完了しました。")
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