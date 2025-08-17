#!/usr/bin/env python3
"""
ひらがな検索のテストスクリプト
"""

import os
import sys
sys.path.append('/home/ubuntu/realestate')
os.environ['DATABASE_URL'] = 'postgresql://realestate:realestate_pass@localhost:5432/realestate'

from backend.app.database import SessionLocal
from backend.app.models import Building, BuildingListingName
from backend.app.scrapers.data_normalizer import canonicalize_building_name
from sqlalchemy import or_

def test_hiragana_search():
    """ひらがなでの建物検索をテスト"""
    db = SessionLocal()
    
    # テストケース
    test_queries = [
        '白金ざ　すかい',  # ひらがなと全角スペース
        '白金ざすかい',    # ひらがな
        'しろかねざすかい', # 全部ひらがな
    ]
    
    for query in test_queries:
        print(f"\n=== 検索語: '{query}' ===")
        
        # canonicalize処理
        canonical_search = canonicalize_building_name(query)
        print(f"  canonical形式: '{canonical_search}'")
        
        # BuildingListingNameから検索
        matches = db.query(BuildingListingName).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_search}%")
        ).limit(5).all()
        
        if matches:
            print(f"  見つかった建物名:")
            for match in matches:
                building = db.query(Building).filter(
                    Building.id == match.building_id
                ).first()
                if building:
                    print(f"    - {match.listing_name} → 建物: {building.normalized_name}")
        else:
            print(f"  マッチする建物が見つかりませんでした")
    
    db.close()

if __name__ == '__main__':
    test_hiragana_search()