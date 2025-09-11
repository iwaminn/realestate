#!/usr/bin/env python3
"""
すべての物件のdisplay_building_nameを再生成するスクリプト
building_name_normalizerの修正を反映
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import MasterProperty, PropertyListing
from app.utils.building_name_normalizer import normalize_building_name
from sqlalchemy import func
import time


def regenerate_property_display_names():
    """すべての物件のdisplay_building_nameを再生成"""
    db = SessionLocal()
    
    try:
        # すべての物件を取得
        properties = db.query(MasterProperty).all()
        total_count = len(properties)
        
        print(f"==================================================")
        print(f"物件のdisplay_building_nameを再生成")
        print(f"対象物件数: {total_count}件")
        print(f"==================================================\n")
        
        if total_count == 0:
            print("処理対象の物件がありません")
            return
        
        success_count = 0
        changed_count = 0
        error_count = 0
        start_time = time.time()
        
        for i, property_obj in enumerate(properties, 1):
            # 進捗表示
            if i % 100 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                remaining = (total_count - i) / rate if rate > 0 else 0
                print(f"[{i:4d}/{total_count}] 処理中... (速度: {rate:.1f}件/秒, 残り: {remaining:.0f}秒)")
            
            try:
                # 物件に紐づく掲載情報から多数決で建物名を決定
                listings = db.query(
                    PropertyListing.listing_building_name,
                    func.count(PropertyListing.id).label('count')
                ).filter(
                    PropertyListing.master_property_id == property_obj.id,
                    PropertyListing.is_active == True,
                    PropertyListing.listing_building_name.isnot(None)
                ).group_by(
                    PropertyListing.listing_building_name
                ).order_by(
                    func.count(PropertyListing.id).desc()
                ).all()
                
                if not listings:
                    # アクティブな掲載がない場合は非アクティブも含めて検索
                    listings = db.query(
                        PropertyListing.listing_building_name,
                        func.count(PropertyListing.id).label('count')
                    ).filter(
                        PropertyListing.master_property_id == property_obj.id,
                        PropertyListing.listing_building_name.isnot(None)
                    ).group_by(
                        PropertyListing.listing_building_name
                    ).order_by(
                        func.count(PropertyListing.id).desc()
                    ).all()
                
                if listings:
                    # 最も多い建物名を採用（正規化はしない、表示用なので）
                    most_common_name = listings[0].listing_building_name
                    
                    # 変更があった場合のみ更新
                    if property_obj.display_building_name != most_common_name:
                        old_name = property_obj.display_building_name
                        property_obj.display_building_name = most_common_name
                        changed_count += 1
                        
                        if i <= 10 or changed_count <= 10:
                            print(f"  物件ID {property_obj.id}: 「{old_name}」→「{most_common_name}」")
                    
                    success_count += 1
                else:
                    # 掲載情報がない場合はスキップ
                    success_count += 1
                    
                # 1000件ごとにコミット（メモリ節約）
                if i % 1000 == 0:
                    db.commit()
                    print(f"  → {i}件までコミット完了")
                    
            except Exception as e:
                error_count += 1
                print(f"  ✗ 物件ID {property_obj.id}: エラー - {e}")
                db.rollback()
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
        print(f"  変更: {changed_count}件")
        print(f"  失敗: {error_count}件")
        print(f"  処理時間: {total_time:.1f}秒 ({total_time/60:.1f}分)")
        print(f"  平均処理速度: {total_count/total_time:.1f}件/秒")
        print(f"==================================================")
        
        return changed_count
        
    except Exception as e:
        print(f"\n❌ 致命的エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    regenerate_property_display_names()