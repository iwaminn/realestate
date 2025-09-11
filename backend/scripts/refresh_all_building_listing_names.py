#!/usr/bin/env python3
"""
すべての建物のbuilding_listing_namesを再生成するスクリプト
BuildingListingNameManager.refresh_building_names()を使用
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
from app.utils.building_listing_name_manager import BuildingListingNameManager
import time


def refresh_all_building_listing_names():
    """すべての建物のbuilding_listing_namesを再生成"""
    db = SessionLocal()
    
    try:
        # すべての建物を取得
        buildings = db.query(Building).all()
        total_count = len(buildings)
        
        print(f"==================================================")
        print(f"すべての建物のbuilding_listing_namesを再生成")
        print(f"対象建物数: {total_count}件")
        print(f"==================================================\n")
        
        if total_count == 0:
            print("処理対象の建物がありません")
            return
        
        # BuildingListingNameManagerを作成
        manager = BuildingListingNameManager(db)
        
        success_count = 0
        error_count = 0
        start_time = time.time()
        
        for i, building in enumerate(buildings, 1):
            # 進捗表示
            if i % 100 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (total_count - i) / rate if rate > 0 else 0
                print(f"[{i:4d}/{total_count}] 処理中... (速度: {rate:.1f}件/秒, 残り: {remaining:.0f}秒)")
            elif i % 10 == 0:
                print(f"[{i:4d}/{total_count}] 建物ID {building.id}: {building.normalized_name[:30]}...")
            
            try:
                # refresh_building_namesで再生成
                manager.refresh_building_names(building.id)
                success_count += 1
                
                # 1000件ごとにコミット（メモリ節約）
                if i % 1000 == 0:
                    db.commit()
                    print(f"  → {i}件までコミット完了")
                    
            except Exception as e:
                error_count += 1
                print(f"  ✗ 建物ID {building.id} ({building.normalized_name}): エラー - {e}")
                db.rollback()
                # エラーがあっても処理を継続
                continue
        
        # 最終コミット
        if success_count > 0:
            db.commit()
        
        # 処理時間の計算
        total_time = time.time() - start_time
        
        print(f"\n==================================================")
        print(f"処理完了")
        print(f"--------------------------------------------------")
        print(f"  成功: {success_count}件")
        print(f"  失敗: {error_count}件")
        print(f"  処理時間: {total_time:.1f}秒 ({total_time/60:.1f}分)")
        print(f"  平均処理速度: {total_count/total_time:.1f}件/秒")
        print(f"==================================================")
        
    except Exception as e:
        print(f"\n❌ 致命的エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    refresh_all_building_listing_names()