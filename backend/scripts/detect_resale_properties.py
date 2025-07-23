#!/usr/bin/env python3
"""
既存データから買い取り再販物件を検出するスクリプト
"""

import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# パスを設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.models import MasterProperty, PropertyListing

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def detect_and_mark_resale_properties():
    """買い取り再販物件を検出してフラグを設定"""
    
    session = Session()
    
    try:
        # 60日以内に販売終了した物件と、その後に登録された同じ条件の物件を探す
        cutoff_date = datetime.now() - timedelta(days=60)
        
        # 潜在的な再販ペアを検出
        potential_resales = session.execute(text("""
            WITH sold_properties AS (
                -- 販売終了した物件
                SELECT DISTINCT
                    mp.id as sold_id,
                    mp.building_id,
                    mp.floor_number,
                    mp.area,
                    mp.layout,
                    pl.current_price as sold_price,
                    pl.sold_at,
                    b.normalized_name
                FROM master_properties mp
                JOIN property_listings pl ON pl.master_property_id = mp.id
                JOIN buildings b ON mp.building_id = b.id
                WHERE pl.sold_at IS NOT NULL
                    AND pl.sold_at >= :cutoff_date
            ),
            active_properties AS (
                -- 現在掲載中の物件
                SELECT DISTINCT
                    mp.id as active_id,
                    mp.building_id,
                    mp.floor_number,
                    mp.area,
                    mp.layout,
                    mp.is_resale,
                    mp.resale_property_id,
                    pl.current_price as active_price,
                    pl.first_seen_at
                FROM master_properties mp
                JOIN property_listings pl ON pl.master_property_id = mp.id
                WHERE pl.is_active = TRUE
            )
            SELECT 
                sp.sold_id,
                ap.active_id,
                sp.normalized_name,
                sp.floor_number,
                sp.area,
                sp.layout,
                sp.sold_price,
                ap.active_price,
                sp.sold_at,
                ap.first_seen_at,
                ap.is_resale,
                ap.resale_property_id
            FROM sold_properties sp
            JOIN active_properties ap ON (
                sp.building_id = ap.building_id
                AND sp.floor_number = ap.floor_number
                AND sp.area = ap.area
                AND sp.layout = ap.layout
                AND sp.sold_id != ap.active_id
                AND ap.first_seen_at > sp.sold_at
            )
            WHERE ap.active_price > sp.sold_price  -- 価格が上がっている場合のみ
            ORDER BY sp.normalized_name, sp.floor_number
        """), {"cutoff_date": cutoff_date})
        
        resale_count = 0
        updates = []
        
        print("買い取り再販候補物件:")
        print("-" * 80)
        
        for row in potential_resales:
            # 既に再販として登録されている場合はスキップ
            if row.is_resale and row.resale_property_id == row.sold_id:
                continue
                
            resale_count += 1
            price_diff = row.active_price - row.sold_price
            price_increase_pct = (price_diff / row.sold_price * 100) if row.sold_price > 0 else 0
            
            print(f"\n建物: {row.normalized_name}")
            print(f"  階数: {row.floor_number}F, 面積: {row.area}㎡, 間取り: {row.layout}")
            print(f"  元物件ID: {row.sold_id} → 新物件ID: {row.active_id}")
            print(f"  販売価格: {row.sold_price}万円 → {row.active_price}万円")
            print(f"  価格差: +{price_diff}万円 ({price_increase_pct:.1f}%増)")
            print(f"  販売終了日: {row.sold_at.strftime('%Y-%m-%d')}")
            print(f"  再掲載日: {row.first_seen_at.strftime('%Y-%m-%d')}")
            days_between = (row.first_seen_at - row.sold_at).days
            print(f"  期間: {days_between}日")
            
            updates.append({
                'active_id': row.active_id,
                'sold_id': row.sold_id
            })
        
        if resale_count > 0:
            print(f"\n\n{resale_count}件の買い取り再販候補を検出しました")
            
            # 更新を実行するか確認
            confirm = input("\nこれらの物件を買い取り再販として登録しますか？ (y/N): ")
            if confirm.lower() == 'y':
                for update in updates:
                    session.execute(text("""
                        UPDATE master_properties
                        SET is_resale = TRUE,
                            resale_property_id = :sold_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :active_id
                    """), update)
                
                session.commit()
                print(f"\n{len(updates)}件の物件を買い取り再販として登録しました")
            else:
                print("\n登録をキャンセルしました")
        else:
            print("\n買い取り再販候補は見つかりませんでした")
            
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
    finally:
        session.close()

def show_resale_stats():
    """再販物件の統計を表示"""
    
    with engine.connect() as conn:
        # 再販物件の統計
        result = conn.execute(text("""
            SELECT 
                COUNT(DISTINCT mp.id) as resale_count,
                COUNT(DISTINCT mp.building_id) as building_count,
                AVG(pl.current_price - pl_old.current_price) as avg_price_diff
            FROM master_properties mp
            JOIN property_listings pl ON pl.master_property_id = mp.id
            LEFT JOIN master_properties mp_old ON mp.resale_property_id = mp_old.id
            LEFT JOIN property_listings pl_old ON pl_old.master_property_id = mp_old.id
            WHERE mp.is_resale = TRUE
                AND pl.is_active = TRUE
        """))
        
        stats = result.fetchone()
        
        print("\n" + "=" * 50)
        print("買い取り再販物件の統計")
        print("=" * 50)
        print(f"再販物件数: {stats.resale_count}件")
        print(f"対象建物数: {stats.building_count}棟")
        if stats.avg_price_diff:
            print(f"平均価格差: +{stats.avg_price_diff:.0f}万円")

if __name__ == "__main__":
    detect_and_mark_resale_properties()
    show_resale_stats()