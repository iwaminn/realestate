#!/usr/bin/env python3
"""
LIFULL HOME'SのURLからsite_property_idを抽出して更新
"""
import os
import sys
import re
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


def update_homes_ids():
    """LIFULL HOME'SのURLからsite_property_idを抽出"""
    print("=== LIFULL HOME'Sのsite_property_id更新 ===\n")
    
    # site_property_idがNULLの物件を取得
    properties = session.execute(text("""
        SELECT id, url
        FROM property_listings
        WHERE source_site IN ('homes', 'HOMES')
        AND site_property_id IS NULL
        AND url IS NOT NULL
    """)).fetchall()
    
    print(f"更新対象: {len(properties)}件")
    
    updated = 0
    for prop in properties:
        # URLから物件IDを抽出（例: /mansion/b-1234567890/）
        match = re.search(r'/mansion/b-([^/]+)/', prop.url)
        if match:
            property_id = match.group(1)
            session.execute(text("""
                UPDATE property_listings
                SET site_property_id = :property_id
                WHERE id = :id
            """), {"property_id": property_id, "id": prop.id})
            updated += 1
            
            if updated % 10 == 0:
                print(f"  {updated}件更新...")
    
    session.commit()
    print(f"\n✓ {updated}件のsite_property_idを更新しました")


def update_nomu_ids():
    """ノムコムのURLからsite_property_idを抽出"""
    print("\n=== ノムコムのsite_property_id更新 ===\n")
    
    # site_property_idがNULLの物件を取得
    properties = session.execute(text("""
        SELECT id, url
        FROM property_listings
        WHERE source_site IN ('nomu', 'NOMU')
        AND site_property_id IS NULL
        AND url IS NOT NULL
    """)).fetchall()
    
    print(f"更新対象: {len(properties)}件")
    
    updated = 0
    for prop in properties:
        # URLから物件IDを抽出（例: /chukomap/xxxxxxxx.html）
        match = re.search(r'/chukomap/([^/]+)\.html', prop.url)
        if match:
            property_id = match.group(1)
            session.execute(text("""
                UPDATE property_listings
                SET site_property_id = :property_id
                WHERE id = :id
            """), {"property_id": property_id, "id": prop.id})
            updated += 1
    
    session.commit()
    print(f"✓ {updated}件のsite_property_idを更新しました")


def check_results():
    """更新結果を確認"""
    print("\n\n=== 更新後の状況 ===\n")
    
    result = session.execute(text("""
        SELECT 
            source_site,
            COUNT(*) as total,
            COUNT(site_property_id) as with_id,
            COUNT(*) - COUNT(site_property_id) as without_id
        FROM property_listings
        WHERE is_active = true
        GROUP BY source_site
        ORDER BY source_site;
    """)).fetchall()
    
    print("サイト別のsite_property_id設定状況:")
    for row in result:
        pct = (row.with_id / row.total * 100) if row.total > 0 else 0
        print(f"  {row.source_site}: 総数={row.total}, ID有り={row.with_id} ({pct:.1f}%), ID無し={row.without_id}")


if __name__ == "__main__":
    try:
        update_homes_ids()
        update_nomu_ids()
        check_results()
    finally:
        session.close()