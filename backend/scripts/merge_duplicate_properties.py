#!/usr/bin/env python3
"""
重複物件を統合するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import MasterProperty, PropertyListing
from app.database import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def merge_properties(property_id1: int, property_id2: int):
    """2つの物件を統合"""
    session = SessionLocal()
    
    try:
        # 物件を取得
        prop1 = session.query(MasterProperty).get(property_id1)
        prop2 = session.query(MasterProperty).get(property_id2)
        
        if not prop1 or not prop2:
            logger.error("指定された物件が見つかりません")
            return
        
        # 同じ建物、階、面積、間取りか確認（方角は除外）
        if (prop1.building_id != prop2.building_id or
            prop1.floor_number != prop2.floor_number or
            prop1.area != prop2.area or
            prop1.layout != prop2.layout):
            logger.warning("物件の属性が異なります")
            print(f"物件1: 建物ID={prop1.building_id}, 階={prop1.floor_number}, 面積={prop1.area}, 間取り={prop1.layout}, 方角={prop1.direction}")
            print(f"物件2: 建物ID={prop2.building_id}, 階={prop2.floor_number}, 面積={prop2.area}, 間取り={prop2.layout}, 方角={prop2.direction}")
            # 自動実行のため、同じ属性でない場合は中止
            return
        
        # 方角が異なる場合は警告のみ
        if prop1.direction != prop2.direction:
            logger.warning(f"方角が異なります: {prop1.direction} vs {prop2.direction}")
        
        # 主物件を選択（更新日時が新しい方）
        if prop1.updated_at > prop2.updated_at:
            primary, secondary = prop1, prop2
            primary_id, secondary_id = property_id1, property_id2
        else:
            primary, secondary = prop2, prop1
            primary_id, secondary_id = property_id2, property_id1
        
        logger.info(f"物件ID {primary_id} を主物件として、物件ID {secondary_id} を統合します")
        
        # 掲載情報を移動
        listings = session.query(PropertyListing).filter_by(
            master_property_id=secondary_id
        ).all()
        
        for listing in listings:
            # 同じソースサイトの掲載が既に存在するかチェック
            existing = session.query(PropertyListing).filter_by(
                master_property_id=primary_id,
                source_site=listing.source_site,
                site_property_id=listing.site_property_id
            ).first()
            
            if existing:
                logger.warning(f"既に同じソースサイトの掲載が存在: {listing.source_site}")
                # 価格履歴を移動してから削除
                session.execute(
                    f"UPDATE listing_price_history SET property_listing_id = {listing.id} "
                    f"WHERE property_listing_id = {existing.id}"
                )
                session.delete(existing)
                session.flush()
            
            listing.master_property_id = primary_id
            logger.info(f"掲載情報を移動: {listing.source_site} - {listing.url}")
        
        # フラッシュして掲載情報の更新を確定
        session.flush()
        
        # 副物件を削除
        session.delete(secondary)
        
        session.commit()
        logger.info("統合完了")
        
    except Exception as e:
        logger.error(f"エラー: {e}")
        session.rollback()
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def main():
    """メイン処理"""
    # 特定の物件IDを統合
    property_id1 = 834
    property_id2 = 836
    
    logger.info(f"物件ID {property_id1} と {property_id2} を統合します")
    merge_properties(property_id1, property_id2)


if __name__ == "__main__":
    main()