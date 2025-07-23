#!/usr/bin/env python3
"""
販売終了した物件を検出してsold_atを更新するスクリプト

スクレイピング後に実行して、is_active=Falseになった物件の販売終了日を記録します。
"""

import sys
import os
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.models import PropertyListing

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def update_sold_properties():
    """販売終了した物件のsold_atを更新"""
    
    session = Session()
    
    try:
        # is_active=Falseでsold_atがNULLの物件を検索
        sold_listings = session.query(PropertyListing).filter(
            PropertyListing.is_active == False,
            PropertyListing.sold_at == None
        ).all()
        
        if sold_listings:
            print(f"販売終了した物件を{len(sold_listings)}件検出しました")
            
            # sold_atを現在時刻で更新
            for listing in sold_listings:
                listing.sold_at = datetime.now()
                print(f"  - {listing.title} (URL: {listing.url})")
            
            session.commit()
            print(f"{len(sold_listings)}件の販売終了日を記録しました")
        else:
            print("新たに販売終了した物件はありません")
    
    finally:
        session.close()

def check_recent_sold():
    """最近販売終了した物件を確認"""
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                pl.id,
                pl.title,
                pl.current_price,
                pl.sold_at,
                mp.building_id,
                mp.floor_number,
                mp.area,
                mp.layout,
                b.normalized_name
            FROM property_listings pl
            JOIN master_properties mp ON pl.master_property_id = mp.id
            JOIN buildings b ON mp.building_id = b.id
            WHERE pl.sold_at IS NOT NULL
            ORDER BY pl.sold_at DESC
            LIMIT 20
        """))
        
        print("\n最近販売終了した物件:")
        for row in result:
            print(f"  {row.normalized_name} {row.floor_number}F {row.area}㎡ {row.layout}")
            print(f"    価格: {row.current_price}万円, 販売終了: {row.sold_at.strftime('%Y-%m-%d')}")

if __name__ == "__main__":
    update_sold_properties()
    check_recent_sold()