#!/usr/bin/env python3
"""
掲載情報がない物件のクリーンアップスクリプト

このスクリプトは以下の処理を行います：
1. 一度も掲載されたことがない物件を削除
2. 長期間（デフォルト90日）掲載されていない物件を削除候補としてリストアップ
"""

import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import argparse

# パスを設定
sys.path.insert(0, '/app')
from app.models import MasterProperty, PropertyListing, PropertyMergeHistory
from app.database import SessionLocal

def analyze_inactive_properties(session, days_inactive=90):
    """掲載情報がない物件を分析"""
    
    # 統計情報を取得
    stats_query = text("""
        WITH property_status AS (
            SELECT 
                mp.id,
                mp.created_at,
                COUNT(pl.id) as total_listings,
                COUNT(CASE WHEN pl.is_active = true THEN 1 END) as active_listings,
                MAX(pl.last_scraped_at) as last_seen
            FROM master_properties mp
            LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
            GROUP BY mp.id, mp.created_at
        )
        SELECT 
            COUNT(*) as total_properties,
            COUNT(CASE WHEN total_listings = 0 THEN 1 END) as never_listed,
            COUNT(CASE WHEN active_listings = 0 AND total_listings > 0 THEN 1 END) as inactive_properties,
            COUNT(CASE WHEN active_listings > 0 THEN 1 END) as active_properties
        FROM property_status
    """)
    
    stats = session.execute(stats_query).fetchone()
    
    print(f"物件統計:")
    print(f"  総物件数: {stats.total_properties}")
    print(f"  有効な掲載あり: {stats.active_properties}")
    print(f"  掲載終了: {stats.inactive_properties}")
    print(f"  一度も掲載なし: {stats.never_listed}")
    print()
    
    # 一度も掲載されたことがない物件
    never_listed_query = text("""
        SELECT mp.id, mp.building_id, b.normalized_name, mp.floor_number, mp.area, mp.layout, mp.created_at
        FROM master_properties mp
        JOIN buildings b ON mp.building_id = b.id
        LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
        WHERE pl.id IS NULL
        ORDER BY mp.created_at DESC
        LIMIT 20
    """)
    
    print("一度も掲載されたことがない物件（最新20件）:")
    never_listed = session.execute(never_listed_query).fetchall()
    for prop in never_listed:
        print(f"  ID {prop.id}: {prop.normalized_name} {prop.floor_number}F {prop.area}㎡ {prop.layout} (作成: {prop.created_at.strftime('%Y-%m-%d')})")
    
    # 長期間掲載されていない物件
    cutoff_date = datetime.now() - timedelta(days=days_inactive)
    
    inactive_query = text("""
        SELECT 
            mp.id, 
            mp.building_id, 
            b.normalized_name, 
            mp.floor_number, 
            mp.area, 
            mp.layout,
            MAX(pl.last_scraped_at) as last_seen
        FROM master_properties mp
        JOIN buildings b ON mp.building_id = b.id
        JOIN property_listings pl ON mp.id = pl.master_property_id
        WHERE pl.is_active = false
        GROUP BY mp.id, mp.building_id, b.normalized_name, mp.floor_number, mp.area, mp.layout
        HAVING MAX(pl.last_scraped_at) < :cutoff_date
        ORDER BY MAX(pl.last_scraped_at) ASC
        LIMIT 20
    """)
    
    print(f"\n{days_inactive}日以上掲載されていない物件（最古20件）:")
    inactive = session.execute(inactive_query, {"cutoff_date": cutoff_date}).fetchall()
    for prop in inactive:
        days_ago = (datetime.now() - prop.last_seen).days
        print(f"  ID {prop.id}: {prop.normalized_name} {prop.floor_number}F {prop.area}㎡ {prop.layout} (最終掲載: {days_ago}日前)")

def cleanup_never_listed_properties(session, dry_run=True):
    """一度も掲載されたことがない物件を削除"""
    
    # 削除対象を取得
    delete_query = text("""
        SELECT mp.id
        FROM master_properties mp
        LEFT JOIN property_listings pl ON mp.id = pl.master_property_id
        LEFT JOIN property_merge_history pmh1 ON mp.id = pmh1.primary_property_id
        LEFT JOIN property_merge_history pmh2 ON mp.id = pmh2.secondary_property_id
        WHERE pl.id IS NULL
          AND pmh1.id IS NULL  -- 統合先として使用されていない
          AND pmh2.id IS NULL  -- 統合元として使用されていない
    """)
    
    properties_to_delete = session.execute(delete_query).fetchall()
    
    print(f"\n削除対象: {len(properties_to_delete)}件の物件")
    
    if not dry_run and properties_to_delete:
        print("削除を実行中...")
        
        # 物件を削除
        for prop in properties_to_delete:
            session.query(MasterProperty).filter(MasterProperty.id == prop.id).delete()
        
        session.commit()
        print(f"{len(properties_to_delete)}件の物件を削除しました")
    else:
        print("(ドライランモード: 実際の削除は行われません)")

def main():
    parser = argparse.ArgumentParser(description='掲載情報がない物件のクリーンアップ')
    parser.add_argument('--days-inactive', type=int, default=90, help='非アクティブと見なす日数')
    parser.add_argument('--cleanup', action='store_true', help='一度も掲載されたことがない物件を削除')
    parser.add_argument('--force', action='store_true', help='確認なしで削除を実行')
    
    args = parser.parse_args()
    
    session = SessionLocal()
    
    try:
        # 分析を実行
        analyze_inactive_properties(session, args.days_inactive)
        
        # クリーンアップを実行
        if args.cleanup:
            if not args.force:
                confirm = input("\n本当に削除を実行しますか? (yes/no): ")
                if confirm.lower() != 'yes':
                    print("キャンセルしました")
                    return
            
            cleanup_never_listed_properties(session, dry_run=not args.force)
    
    finally:
        session.close()

if __name__ == "__main__":
    main()