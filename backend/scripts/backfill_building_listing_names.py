#!/usr/bin/env python3
"""
building_listing_namesテーブルのレコードが欠落している建物を修正するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Building, BuildingListingName, PropertyListing, MasterProperty
from app.scrapers.data_normalizer import canonicalize_building_name
from sqlalchemy import func, text
from collections import defaultdict


def backfill_building_listing_names():
    """building_listing_namesが欠落している建物のレコードを作成"""
    db = SessionLocal()
    
    try:
        # building_listing_namesが存在しない建物を特定
        buildings_without_listing_names = db.query(Building).filter(
            ~Building.id.in_(
                db.query(BuildingListingName.building_id).distinct()
            )
        ).all()
        
        print(f"building_listing_namesが欠落している建物: {len(buildings_without_listing_names)}件")
        
        if not buildings_without_listing_names:
            print("✅ すべての建物にbuilding_listing_namesレコードが存在します")
            return
        
        print("-" * 60)
        
        created_count = 0
        for building in buildings_without_listing_names:
            # この建物の物件を取得
            properties = db.query(MasterProperty).filter_by(building_id=building.id).all()
            
            if not properties:
                print(f"建物ID {building.id} ({building.normalized_name}): 物件なし - スキップ")
                continue
            
            # 物件の掲載情報から建物名を収集
            listing_names = defaultdict(lambda: {'count': 0, 'sources': set()})
            
            for prop in properties:
                listings = db.query(PropertyListing).filter_by(
                    master_property_id=prop.id
                ).filter(
                    PropertyListing.listing_building_name.isnot(None)
                ).all()
                
                for listing in listings:
                    if listing.listing_building_name:
                        name = listing.listing_building_name
                        listing_names[name]['count'] += 1
                        listing_names[name]['sources'].add(listing.source_site)
            
            if not listing_names:
                # display_building_nameから作成
                if properties[0].display_building_name:
                    name = properties[0].display_building_name
                    canonical = canonicalize_building_name(name)
                    
                    new_listing_name = BuildingListingName(
                        building_id=building.id,
                        listing_name=name,
                        canonical_name=canonical,
                        occurrence_count=1,
                        source_sites=['unknown']
                    )
                    db.add(new_listing_name)
                    created_count += 1
                    print(f"建物ID {building.id}: display_building_nameから作成 - {name}")
                else:
                    print(f"建物ID {building.id}: 建物名情報なし - スキップ")
                continue
            
            # 最も多く使われている建物名からレコードを作成
            for name, info in listing_names.items():
                canonical = canonicalize_building_name(name)
                
                # 既存のレコードをチェック
                existing = db.query(BuildingListingName).filter_by(
                    building_id=building.id,
                    canonical_name=canonical
                ).first()
                
                if existing:
                    # 既存レコードがある場合は更新
                    existing.occurrence_count += info['count']
                    existing.source_sites = list(set(existing.source_sites) | info['sources'])
                    print(f"建物ID {building.id}: {name} - 既存レコード更新")
                else:
                    # 新規作成
                    new_listing_name = BuildingListingName(
                        building_id=building.id,
                        listing_name=name,
                        canonical_name=canonical,
                        occurrence_count=info['count'],
                        source_sites=list(info['sources'])
                    )
                    db.add(new_listing_name)
                    created_count += 1
                
                print(f"建物ID {building.id}: {name} (出現回数: {info['count']}, サイト: {', '.join(info['sources'])})")
        
        if created_count > 0:
            db.commit()
            print("-" * 60)
            print(f"✅ {created_count}件のbuilding_listing_namesレコードを作成しました")
        else:
            print("作成が必要なレコードはありませんでした")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    backfill_building_listing_names()