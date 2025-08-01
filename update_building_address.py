#!/usr/bin/env python3
"""
既存の物件情報から建物の住所を更新するスクリプト
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def update_building_addresses():
    """property_listingsのdetail_infoから建物の住所を更新"""
    session = Session()
    
    try:
        # 住所がない建物を取得
        result = session.execute(text("""
            SELECT b.id, b.normalized_name, b.address
            FROM buildings b
            WHERE b.address IS NULL OR b.address = ''
            ORDER BY b.id
        """))
        
        buildings_without_address = result.fetchall()
        print(f"住所がない建物数: {len(buildings_without_address)}")
        
        updated_count = 0
        
        for building in buildings_without_address:
            building_id = building[0]
            building_name = building[1]
            
            # この建物の物件から住所を探す
            address_result = session.execute(text("""
                SELECT DISTINCT pl.detail_info->>'address' as address
                FROM property_listings pl
                JOIN master_properties mp ON pl.master_property_id = mp.id
                WHERE mp.building_id = :building_id
                  AND pl.detail_info->>'address' IS NOT NULL
                  AND pl.detail_info->>'address' != ''
                LIMIT 1
            """), {"building_id": building_id})
            
            address_row = address_result.fetchone()
            
            if address_row and address_row[0]:
                address = address_row[0]
                
                # 建物の住所を更新
                session.execute(text("""
                    UPDATE buildings
                    SET address = :address, updated_at = NOW()
                    WHERE id = :building_id
                """), {"address": address, "building_id": building_id})
                
                updated_count += 1
                print(f"更新: {building_name} -> {address}")
        
        session.commit()
        print(f"\n合計 {updated_count} 件の建物の住所を更新しました")
        
    except Exception as e:
        session.rollback()
        print(f"エラーが発生しました: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    update_building_addresses()