#!/usr/bin/env python3
"""
既存の全物件のdisplay_building_nameを更新するスクリプト
listing_building_nameから多数決で決定
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import MasterProperty, PropertyListing
from backend.app.utils.majority_vote_updater import MajorityVoteUpdater
from sqlalchemy import func
import time

def main():
    db = SessionLocal()
    updater = MajorityVoteUpdater(db)
    
    try:
        # display_building_nameがNULLの物件数を確認
        null_count = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.display_building_name == None
        ).scalar()
        
        print(f"display_building_nameがNULLの物件数: {null_count}")
        
        if null_count == 0:
            print("更新対象の物件はありません")
            return
        
        # 全物件を取得
        properties = db.query(MasterProperty).filter(
            MasterProperty.display_building_name == None
        ).all()
        
        print(f"\n{len(properties)}件の物件を更新します...")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for i, property in enumerate(properties):
            if i % 100 == 0 and i > 0:
                print(f"  処理中... {i}/{len(properties)}件完了")
                db.commit()  # 定期的にコミット
            
            try:
                # 物件の表示用建物名を多数決で更新
                if updater.update_property_building_name_by_majority(property.id):
                    updated_count += 1
                else:
                    # 更新されなかった（掲載情報がないか、建物名が取得できない）
                    skipped_count += 1
                    
            except Exception as e:
                error_count += 1
                print(f"  エラー: 物件ID {property.id} - {e}")
                db.rollback()
                continue
            
            # 負荷軽減のため少し待機
            if i % 50 == 0:
                time.sleep(0.1)
        
        # 最終コミット
        db.commit()
        
        print(f"\n処理完了:")
        print(f"  更新成功: {updated_count}件")
        print(f"  スキップ: {skipped_count}件（掲載情報なし等）")
        print(f"  エラー: {error_count}件")
        
        # 結果を確認
        updated_total = db.query(func.count(MasterProperty.id)).filter(
            MasterProperty.display_building_name != None
        ).scalar()
        
        print(f"\ndisplay_building_nameが設定されている物件数: {updated_total}")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()