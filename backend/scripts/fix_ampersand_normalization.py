#!/usr/bin/env python3
"""
既存の建物名に含まれる＆記号を正規化するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
from app.utils.building_name_normalizer import normalize_building_name
from sqlalchemy import or_

def fix_ampersand_in_building_names():
    """＆を含む建物名を再正規化"""
    db = SessionLocal()
    
    try:
        # ＆（全角・半角）を含む建物を検索
        buildings = db.query(Building).filter(
            or_(
                Building.normalized_name.like('%＆%'),
                Building.normalized_name.like('%&%'),
                Building.normalized_name.like('%　%')  # 全角スペースも含む
            )
        ).all()
        
        print(f"見つかった建物: {len(buildings)}件")
        print("-" * 60)
        
        updated_count = 0
        for building in buildings:
            old_name = building.normalized_name
            new_name = normalize_building_name(old_name)
            
            if old_name != new_name:
                print(f"建物ID: {building.id}")
                print(f"  変更前: {old_name}")
                print(f"  変更後: {new_name}")
                print()
                
                building.normalized_name = new_name
                updated_count += 1
            else:
                print(f"建物ID {building.id}: 変更なし ({old_name})")
        
        if updated_count > 0:
            db.commit()
            print("-" * 60)
            print(f"✅ {updated_count}件の建物名を更新しました")
        else:
            print("更新が必要な建物はありませんでした")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    fix_ampersand_in_building_names()