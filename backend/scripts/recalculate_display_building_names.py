#!/usr/bin/env python3
"""
display_building_nameを多数決で再計算するスクリプト
（誤って正規化してしまったものを修正）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import MasterProperty
from app.utils.majority_vote_updater import MajorityVoteUpdater


def recalculate_display_building_names():
    """すべての物件のdisplay_building_nameを再計算"""
    db = SessionLocal()
    
    try:
        # 誤って正規化してしまった物件を取得
        # （＆や全角スペースが含まれていないものが対象）
        properties = db.query(MasterProperty).filter(
            MasterProperty.display_building_name.isnot(None)
        ).all()
        
        print(f"処理対象: {len(properties)}件の物件")
        print("-" * 60)
        
        # MajorityVoteUpdaterを使用して再計算
        updater = MajorityVoteUpdater(db)
        
        updated_count = 0
        for i, prop in enumerate(properties, 1):
            if i % 100 == 0:
                print(f"処理中: {i}/{len(properties)}件...")
            
            old_name = prop.display_building_name
            
            # 多数決で再計算
            updated = updater.update_property_building_name_by_majority(prop.id)
            
            if updated:
                new_name = db.query(MasterProperty).filter_by(id=prop.id).first().display_building_name
                if old_name != new_name:
                    print(f"物件ID {prop.id}: {old_name} → {new_name}")
                    updated_count += 1
        
        if updated_count > 0:
            db.commit()
            print("-" * 60)
            print(f"✅ {updated_count}件のdisplay_building_nameを修正しました")
        else:
            print("更新が必要な物件はありませんでした")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    recalculate_display_building_names()