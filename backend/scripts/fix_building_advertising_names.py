#!/usr/bin/env python3
"""
建物名から広告文を除去するスクリプト
"""

import os
import sys
import re
from datetime import datetime

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
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
    
    # スペースの正規化
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def fix_building_names(session, dry_run=False):
    """広告文を含む建物名を修正"""
    
    # 問題のある建物を検索
    buildings = session.query(Building).filter(
        or_(
            Building.normalized_name.like('%【%'),
            Building.normalized_name.like('%】%'),
            Building.normalized_name.like('%《%'),
            Building.normalized_name.like('%》%'),
            Building.normalized_name.like('%◆%'),
            Building.normalized_name.like('%◇%'),
            Building.normalized_name.like('%■%'),
            Building.normalized_name.like('%□%')
        )
    ).all()
    
    print(f"修正対象: {len(buildings)}件の建物")
    
    fixed_count = 0
    
    for building in buildings:
        print(f"\n建物ID {building.id}:")
        print(f"  現在の名前: '{building.normalized_name}'")
        
        # 広告文を除去
        cleaned = clean_advertising_text(building.normalized_name)
        if cleaned and cleaned != building.normalized_name:
            normalized = normalize_building_name(cleaned)
            print(f"  修正後の名前: '{normalized}'")
            
            if not dry_run:
                building.normalized_name = normalized
                building.canonical_name = normalized  # canonical_nameも更新
                building.updated_at = datetime.utcnow()
                fixed_count += 1
        else:
            print(f"  → 変更なし")
    
    return fixed_count


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='建物名から広告文を除去')
    parser.add_argument('--dry-run', action='store_true', help='実際に修正せず、対象を表示するのみ')
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        if args.dry_run:
            print("【ドライランモード】実際の修正は行いません。\n")
        
        fixed_count = fix_building_names(session, args.dry_run)
        
        if not args.dry_run and fixed_count > 0:
            print(f"\n{fixed_count}件の建物名を修正しています...")
            session.commit()
            print("修正が完了しました。")
            
            # 建物名変更後、重複候補を再検索する必要があることを通知
            print("\n※ 建物名を修正したため、建物重複管理画面で重複候補を再確認してください。")
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