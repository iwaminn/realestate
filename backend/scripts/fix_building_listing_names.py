#!/usr/bin/env python3
"""
BuildingListingNameテーブルの不足データを修正するスクリプト

property_listingsテーブルのlisting_building_nameから
BuildingListingNameテーブルに未登録の建物名を登録します。
"""

import sys
import os
from datetime import datetime
from collections import defaultdict

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing, MasterProperty, BuildingListingName
from backend.app.utils.building_name_normalizer import canonicalize_building_name
from sqlalchemy import and_, func
from sqlalchemy.sql import text

def fix_building_listing_names():
    """BuildingListingNameテーブルの不足データを修正"""
    session = SessionLocal()
    
    try:
        print("BuildingListingNameテーブルの不足データを検索中...")
        
        # 未登録の建物名を持つ掲載情報を取得
        # SQLで直接実行（パフォーマンスのため）
        query = text("""
            SELECT DISTINCT 
                mp.building_id,
                pl.listing_building_name,
                pl.source_site,
                COUNT(*) as count
            FROM property_listings pl
            JOIN master_properties mp ON pl.master_property_id = mp.id
            WHERE pl.listing_building_name IS NOT NULL
                AND mp.building_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM building_listing_names bln
                    WHERE bln.building_id = mp.building_id
                    AND bln.listing_name = pl.listing_building_name
                )
            GROUP BY mp.building_id, pl.listing_building_name, pl.source_site
            ORDER BY mp.building_id, pl.listing_building_name, pl.source_site
        """)
        
        result = session.execute(query)
        missing_entries = result.fetchall()
        
        total_count = len(missing_entries)
        print(f"\n修正対象: {total_count}件の未登録建物名")
        
        if total_count == 0:
            print("修正対象の建物名はありません。")
            return
        
        # 建物ごとにグループ化して表示
        by_building = defaultdict(list)
        for building_id, listing_name, source_site, count in missing_entries:
            by_building[building_id].append({
                'normalized_name': listing_name,
                'source_site': source_site,
                'count': count
            })
        
        print(f"\n影響を受ける建物数: {len(by_building)}件")
        
        # 最初の5件を表示
        for i, (building_id, entries) in enumerate(list(by_building.items())[:5]):
            print(f"\n建物ID {building_id}:")
            for entry in entries[:3]:  # 各建物で最大3件表示
                print(f"  - '{entry['normalized_name']}' ({entry['source_site']}, {entry['count']}件)")
            if len(entries) > 3:
                print(f"  ... 他{len(entries)-3}件")
        
        if len(by_building) > 5:
            print(f"\n... 他{len(by_building)-5}建物")
        
        # 確認
        print("\n修正内容:")
        print("- property_listingsのlisting_building_nameから")
        print("- BuildingListingNameテーブルに未登録のエントリを追加します")
        
        response = input("\n修正を実行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("修正をキャンセルしました。")
            return
        
        # 修正実行
        print("\n修正を実行中...")
        added_count = 0
        
        for building_id, listing_name, source_site, count in missing_entries:
            # 正規化された名前を生成
            canonical_name = canonicalize_building_name(listing_name)
            
            # 既存のエントリを確認（念のため）
            existing = session.query(BuildingListingName).filter(
                and_(
                    BuildingListingName.building_id == building_id,
                    BuildingListingName.normalized_name == listing_name
                )
            ).first()
            
            if existing:
                # 既に存在する場合は、occurrence_countとsource_sitesを更新
                existing.occurrence_count = (existing.occurrence_count or 0) + count
                if source_site not in (existing.source_sites or ''):
                    if existing.source_sites:
                        existing.source_sites += f",{source_site}"
                    else:
                        existing.source_sites = source_site
                existing.last_seen_at = datetime.now()
            else:
                # 新規登録
                new_entry = BuildingListingName(
                    building_id=building_id,
                    normalized_name=listing_name,
                    canonical_name=canonical_name,
                    source_sites=source_site,
                    occurrence_count=count,
                    first_seen_at=datetime.now(),
                    last_seen_at=datetime.now()
                )
                session.add(new_entry)
                added_count += 1
                
            if added_count % 100 == 0 and added_count > 0:
                print(f"  {added_count}/{total_count} 件追加...")
                session.flush()  # 定期的にフラッシュ
        
        # コミット
        session.commit()
        print(f"\n✅ 修正完了: {added_count}件の建物名を追加しました")
        
        # 修正後の確認
        remaining_query = text("""
            SELECT COUNT(DISTINCT mp.building_id || '::' || pl.listing_building_name)
            FROM property_listings pl
            JOIN master_properties mp ON pl.master_property_id = mp.id
            WHERE pl.listing_building_name IS NOT NULL
                AND mp.building_id IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM building_listing_names bln
                    WHERE bln.building_id = mp.building_id
                    AND bln.listing_name = pl.listing_building_name
                )
        """)
        
        remaining = session.execute(remaining_query).scalar()
        
        if remaining > 0:
            print(f"⚠️ 警告: まだ{remaining}件の未登録建物名があります")
        else:
            print("✅ すべての建物名がBuildingListingNameテーブルに登録されています")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("=" * 60)
    print("BuildingListingName修正スクリプト")
    print("=" * 60)
    fix_building_listing_names()