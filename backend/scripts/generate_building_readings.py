#!/usr/bin/env python3
"""既存の建物データに読み仮名を生成して追加するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building
from app.utils.reading_generator import generate_reading

def generate_building_readings():
    """既存の建物に読み仮名を生成"""
    
    session = SessionLocal()
    
    try:
        # 読み仮名がない建物を取得
        buildings = session.query(Building).filter(
            Building.reading == None
        ).all()
        
        print(f"{len(buildings)}件の建物に読み仮名を生成します...")
        
        updated_count = 0
        failed_count = 0
        
        for building in buildings:
            reading = generate_reading(building.normalized_name)
            
            if reading:
                building.reading = reading
                updated_count += 1
                print(f"✓ {building.normalized_name} → {reading}")
            else:
                failed_count += 1
                print(f"× {building.normalized_name} → 生成できませんでした")
        
        # 変更を保存
        session.commit()
        
        print(f"\n完了:")
        print(f"  成功: {updated_count}件")
        print(f"  失敗: {failed_count}件")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    generate_building_readings()