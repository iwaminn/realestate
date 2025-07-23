#!/usr/bin/env python3
"""
買い取り再販検出のデモンストレーション
"""

import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)

def demo_resale_detection():
    """買い取り再販検出のデモ"""
    
    with engine.connect() as conn:
        # 60日以内に販売終了した物件を確認
        print("=" * 80)
        print("買い取り再販検出の仕組み")
        print("=" * 80)
        print()
        print("1. システムは60日以内に販売終了した物件を監視します")
        print("2. 同じ建物・階数・面積・間取りの物件が再度売り出された場合")
        print("3. 価格が前回より高い場合、買い取り再販物件として判定されます")
        print()
        
        # 最近販売終了した物件の例を表示
        result = conn.execute(text("""
            SELECT 
                b.normalized_name,
                mp.floor_number,
                mp.area,
                mp.layout,
                pl.current_price,
                pl.sold_at
            FROM master_properties mp
            JOIN buildings b ON mp.building_id = b.id
            JOIN property_listings pl ON pl.master_property_id = mp.id
            WHERE pl.sold_at IS NOT NULL
                AND pl.sold_at >= CURRENT_DATE - INTERVAL '60 days'
            ORDER BY pl.sold_at DESC
            LIMIT 5
        """))
        
        print("最近60日以内に販売終了した物件の例:")
        print("-" * 80)
        for row in result:
            print(f"建物: {row.normalized_name}")
            print(f"  階数: {row.floor_number}F, 面積: {row.area}㎡, 間取り: {row.layout}")
            print(f"  販売価格: {row.current_price}万円")
            print(f"  販売終了日: {row.sold_at.strftime('%Y-%m-%d')}")
            print()
        
        print("\n再販物件の検出条件:")
        print("-" * 80)
        print("1. 販売終了から60日以内に再掲載された")
        print("2. 同じ建物の同じ階数・面積・間取り")
        print("3. 前回より高い価格で売り出されている")
        print()
        print("これらの条件を満たす物件は、買い取り再販マーク🔄が表示されます")
        
        # APIで返される情報を説明
        print("\n\nAPIレスポンスの例:")
        print("-" * 80)
        print("""
{
    "id": 12345,
    "building": { ... },
    "floor_number": 10,
    "area": 70.5,
    "layout": "3LDK",
    "is_resale": true,              // 買い取り再販フラグ
    "resale_property_id": 12300,    // 元の物件ID
    "min_price": 8500,
    "max_price": 8500,
    ...
}
""")
        
        print("\n\nフロントエンドでの表示:")
        print("-" * 80)
        print("1. 物件一覧: 「買い取り再販」バッジが表示されます")
        print("2. 物件詳細: 元の物件へのリンクが表示されます")
        print("3. 建物内物件一覧: 販売終了物件と再販物件の関係が分かります")

if __name__ == "__main__":
    demo_resale_detection()