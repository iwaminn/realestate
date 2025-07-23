#!/usr/bin/env python3
"""
物件ハッシュ再生成スクリプト

部屋番号を使用しない新しいハッシュ生成ロジックで
既存の物件ハッシュを再生成します。
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import MasterProperty
from backend.app.scrapers.base_scraper import BaseScraper
from sqlalchemy import func
import hashlib

def generate_new_hash(building_id: int, floor_number: int = None, area: float = None, 
                     layout: str = None, direction: str = None) -> str:
    """新しいハッシュ生成ロジック（部屋番号を使用しない）"""
    floor_str = f"F{floor_number}" if floor_number else "F?"
    area_str = f"A{area:.1f}" if area else "A?"
    layout_str = layout if layout else "L?"
    direction_str = f"D{direction}" if direction else "D?"
    data = f"{building_id}:{floor_str}_{area_str}_{layout_str}_{direction_str}"
    
    return hashlib.md5(data.encode()).hexdigest()

def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        # 統計情報を収集
        total_properties = session.query(func.count(MasterProperty.id)).scalar()
        properties_with_room = session.query(func.count(MasterProperty.id)).filter(
            MasterProperty.room_number.isnot(None),
            MasterProperty.room_number != ''
        ).scalar()
        
        print(f"=== 物件ハッシュ再生成 ===")
        print(f"総物件数: {total_properties}")
        print(f"部屋番号あり: {properties_with_room}")
        print(f"部屋番号なし: {total_properties - properties_with_room}")
        print()
        
        # 重複が発生する可能性のあるケースを事前チェック
        print("=== 重複チェック ===")
        print("新しいハッシュで重複する可能性のある物件を検出中...")
        
        # 仮のハッシュ辞書を作成
        hash_dict = {}
        duplicate_count = 0
        
        properties = session.query(MasterProperty).all()
        
        for prop in properties:
            new_hash = generate_new_hash(
                prop.building_id,
                prop.floor_number,
                prop.area,
                prop.layout,
                prop.direction
            )
            
            if new_hash in hash_dict:
                duplicate_count += 1
                if duplicate_count <= 10:  # 最初の10件を表示
                    existing = hash_dict[new_hash]
                    print(f"\n重複検出:")
                    print(f"  既存: ID={existing['id']}, 建物ID={existing['building_id']}, "
                          f"部屋={existing['room_number']}, 階={existing['floor_number']}, "
                          f"面積={existing['area']}, 間取り={existing['layout']}")
                    print(f"  新規: ID={prop.id}, 建物ID={prop.building_id}, "
                          f"部屋={prop.room_number}, 階={prop.floor_number}, "
                          f"面積={prop.area}, 間取り={prop.layout}")
            else:
                hash_dict[new_hash] = {
                    'id': prop.id,
                    'building_id': prop.building_id,
                    'room_number': prop.room_number,
                    'floor_number': prop.floor_number,
                    'area': prop.area,
                    'layout': prop.layout
                }
        
        if duplicate_count > 0:
            print(f"\n警告: {duplicate_count}件の重複が検出されました。")
            print("これらの物件は同一物件として扱われることになります。")
            
            response = input("\n続行しますか？ (y/N): ")
            if response.lower() != 'y':
                print("処理を中止しました。")
                return
        else:
            print("\n重複は検出されませんでした。")
        
        # ハッシュを更新
        print("\n=== ハッシュ更新中 ===")
        update_count = 0
        
        for prop in properties:
            old_hash = prop.property_hash
            new_hash = generate_new_hash(
                prop.building_id,
                prop.floor_number,
                prop.area,
                prop.layout,
                prop.direction
            )
            
            if old_hash != new_hash:
                prop.property_hash = new_hash
                update_count += 1
                
                if update_count % 100 == 0:
                    print(f"{update_count}件更新...")
        
        print(f"\n{update_count}件のハッシュを更新しました。")
        
        # コミット
        if update_count > 0:
            response = input("\n変更をコミットしますか？ (y/N): ")
            if response.lower() == 'y':
                session.commit()
                print("変更をコミットしました。")
            else:
                session.rollback()
                print("変更をロールバックしました。")
        
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()