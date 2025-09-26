"""
販売終了物件のsold_atとfinal_priceを一括更新するスクリプト

全掲載が非アクティブだがsold_atがNULLの物件を対象に、
sold_atとfinal_priceを自動設定します。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from app.models import MasterProperty, PropertyListing
from app.utils.price_queries import calculate_final_price_for_sold_property

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def backfill_sold_properties():
    """販売終了物件のsold_atとfinal_priceを一括更新"""
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        properties = db.query(MasterProperty).filter(
            MasterProperty.sold_at.is_(None)
        ).all()

        updated_count = 0
        skipped_count = 0

        for prop in properties:
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop.id,
                PropertyListing.is_active == True
            ).count()

            if active_listings > 0:
                skipped_count += 1
                continue

            all_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop.id
            ).all()

            if not all_listings:
                skipped_count += 1
                continue

            max_delisted_at = max(
                (listing.delisted_at for listing in all_listings if listing.delisted_at),
                default=None
            )

            if max_delisted_at:
                prop.sold_at = max_delisted_at

                final_price = calculate_final_price_for_sold_property(db, prop.id)
                if final_price:
                    prop.final_price = final_price
                    print(f"物件ID={prop.id}: sold_at={max_delisted_at}, final_price={final_price}万円")
                else:
                    print(f"物件ID={prop.id}: sold_at={max_delisted_at}, final_price計算不可")

                updated_count += 1
            else:
                skipped_count += 1

        db.commit()

        print(f"\n=== 更新完了 ===")
        print(f"更新件数: {updated_count}件")
        print(f"スキップ件数: {skipped_count}件")

    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    backfill_sold_properties()