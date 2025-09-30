#!/usr/bin/env python3
"""
全掲載が非アクティブだがsold_atが設定されていない物件を修正するスクリプト
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import MasterProperty, PropertyListing
from backend.app.utils.price_queries import calculate_final_price_for_sold_property

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def find_properties_without_active_listings():
    """全掲載が非アクティブでsold_atがnullの物件を検索"""
    session = Session()

    try:
        # 全掲載が非アクティブな物件を検索
        # サブクエリで各物件のアクティブな掲載数をカウント
        from sqlalchemy import func, and_

        # 各物件のアクティブな掲載数
        active_count_subquery = session.query(
            PropertyListing.master_property_id,
            func.count(PropertyListing.id).label('active_count')
        ).filter(
            PropertyListing.is_active == True
        ).group_by(
            PropertyListing.master_property_id
        ).subquery()

        # sold_atがnullで、アクティブな掲載が0件の物件
        properties = session.query(MasterProperty).outerjoin(
            active_count_subquery,
            MasterProperty.id == active_count_subquery.c.master_property_id
        ).filter(
            MasterProperty.sold_at.is_(None),
            func.coalesce(active_count_subquery.c.active_count, 0) == 0
        ).all()

        # さらに、少なくとも1件の掲載がある物件のみに絞る
        result = []
        for prop in properties:
            listing_count = session.query(func.count(PropertyListing.id)).filter(
                PropertyListing.master_property_id == prop.id
            ).scalar()

            if listing_count > 0:
                result.append(prop)

        return result
    finally:
        session.close()

def fix_sold_property(property_id: int):
    """物件を販売終了として設定"""
    session = Session()

    try:
        master_property = session.query(MasterProperty).filter(
            MasterProperty.id == property_id
        ).first()

        if not master_property:
            return None, "物件が見つかりません"

        # 全掲載の最新のdelisted_atを取得
        all_listings = session.query(PropertyListing).filter(
            PropertyListing.master_property_id == property_id
        ).all()

        if not all_listings:
            return None, "掲載情報がありません"

        max_delisted_at = max(
            (listing.delisted_at for listing in all_listings if listing.delisted_at),
            default=datetime.now()
        )

        # sold_atを設定
        master_property.sold_at = max_delisted_at

        # 最終価格を計算
        try:
            final_price = calculate_final_price_for_sold_property(session, property_id)
            if final_price:
                master_property.final_price = final_price
                master_property.final_price_updated_at = datetime.now()
        except Exception as e:
            print(f"  ⚠️ 最終価格の計算に失敗: {e}")

        session.commit()

        return max_delisted_at, None
    except Exception as e:
        session.rollback()
        return None, str(e)
    finally:
        session.close()

def main():
    print("全掲載が非アクティブでsold_atがnullの物件を検索中...\n")

    properties = find_properties_without_active_listings()

    if not properties:
        print("修正が必要な物件は見つかりませんでした。")
        return

    print(f"修正が必要な物件: {len(properties)}件\n")

    fixed_count = 0

    for prop in properties:
        # 建物情報を取得
        session = Session()
        try:
            from backend.app.models import Building
            building = session.query(Building).filter(
                Building.id == prop.building_id
            ).first()

            building_name = building.normalized_name if building else "不明"

            print(f"物件ID: {prop.id}")
            print(f"  建物: {building_name}")
            print(f"  階数: {prop.floor_number}階")
            print(f"  部屋番号: {prop.room_number or '不明'}")

            # 掲載情報を取得
            listings = session.query(PropertyListing).filter(
                PropertyListing.master_property_id == prop.id
            ).all()

            print(f"  掲載数: {len(listings)}件")
            for listing in listings:
                status = "アクティブ" if listing.is_active else "非アクティブ"
                print(f"    - {listing.source_site}: {status}, 掲載終了日: {listing.delisted_at}")
        finally:
            session.close()

        # 修正実行
        sold_at, error = fix_sold_property(prop.id)

        if error:
            print(f"  ❌ 修正失敗: {error}")
        else:
            print(f"  ✅ 販売終了日を設定: {sold_at}")
            fixed_count += 1

        print()

    print(f"完了: {fixed_count}/{len(properties)}件の物件を修正しました。")

if __name__ == "__main__":
    main()