#!/usr/bin/env python3
"""
重複建物を統合するスクリプト
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Building, BuildingAlias, BuildingExternalId, MasterProperty

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


def find_duplicate_buildings():
    """重複している可能性の高い建物を特定"""
    print("=== 重複建物の特定 ===\n")
    
    # 同じcanonical_nameを持つ建物
    duplicates = session.execute(text("""
        SELECT canonical_name, array_agg(id ORDER BY id) as ids
        FROM buildings
        WHERE canonical_name IS NOT NULL
        GROUP BY canonical_name
        HAVING COUNT(*) > 1
    """)).fetchall()
    
    return duplicates


def merge_buildings(primary_id, duplicate_ids):
    """複数の建物を1つに統合"""
    print(f"\n建物ID {primary_id} に以下を統合: {duplicate_ids}")
    
    try:
        # 1. MasterPropertyを移行
        for dup_id in duplicate_ids:
            updated = session.execute(
                text("UPDATE master_properties SET building_id = :primary_id WHERE building_id = :dup_id"),
                {"primary_id": primary_id, "dup_id": dup_id}
            )
            print(f"  - 建物ID {dup_id} から {updated.rowcount} 件の物件を移行")
        
        # 2. BuildingAliasを移行
        for dup_id in duplicate_ids:
            # 重複するエイリアスは削除
            session.execute(
                text("""
                    DELETE FROM building_aliases 
                    WHERE building_id = :dup_id 
                    AND alias_name IN (
                        SELECT alias_name FROM building_aliases WHERE building_id = :primary_id
                    )
                """),
                {"primary_id": primary_id, "dup_id": dup_id}
            )
            
            # 残りを移行
            updated = session.execute(
                text("UPDATE building_aliases SET building_id = :primary_id WHERE building_id = :dup_id"),
                {"primary_id": primary_id, "dup_id": dup_id}
            )
            print(f"  - 建物ID {dup_id} から {updated.rowcount} 件のエイリアスを移行")
        
        # 3. BuildingExternalIdを移行
        for dup_id in duplicate_ids:
            # 重複する外部IDは削除
            session.execute(
                text("""
                    DELETE FROM building_external_ids 
                    WHERE building_id = :dup_id 
                    AND (source_site, external_id) IN (
                        SELECT source_site, external_id 
                        FROM building_external_ids 
                        WHERE building_id = :primary_id
                    )
                """),
                {"primary_id": primary_id, "dup_id": dup_id}
            )
            
            # 残りを移行
            updated = session.execute(
                text("UPDATE building_external_ids SET building_id = :primary_id WHERE building_id = :dup_id"),
                {"primary_id": primary_id, "dup_id": dup_id}
            )
            print(f"  - 建物ID {dup_id} から {updated.rowcount} 件の外部IDを移行")
        
        # 4. 重複建物を削除
        for dup_id in duplicate_ids:
            session.execute(
                text("DELETE FROM buildings WHERE id = :dup_id"),
                {"dup_id": dup_id}
            )
            print(f"  - 建物ID {dup_id} を削除")
        
        session.commit()
        print("  統合完了！")
        
    except Exception as e:
        session.rollback()
        print(f"  エラー: {e}")


def main():
    """メイン処理"""
    duplicates = find_duplicate_buildings()
    
    if not duplicates:
        print("重複建物は見つかりませんでした。")
        return
    
    print(f"{len(duplicates)} 組の重複建物が見つかりました。\n")
    
    # 各グループを確認
    for dup in duplicates[:5]:  # 最初の5組のみ処理
        canonical_name = dup.canonical_name
        ids = dup.ids
        
        print(f"\ncanonical_name: '{canonical_name}'")
        buildings = []
        for bid in ids:
            building = session.query(Building).filter(Building.id == bid).first()
            if building:
                prop_count = session.query(MasterProperty).filter(
                    MasterProperty.building_id == bid
                ).count()
                buildings.append({
                    'id': bid,
                    'name': building.normalized_name,
                    'address': building.address,
                    'prop_count': prop_count
                })
                print(f"  - ID {bid}: {building.normalized_name} ({prop_count}件)")
        
        if len(buildings) > 1:
            # 物件数が最も多い建物を主とする
            primary = max(buildings, key=lambda x: x['prop_count'])
            duplicates_to_merge = [b['id'] for b in buildings if b['id'] != primary['id']]
            
            confirm = input(f"\n建物ID {primary['id']} に他を統合しますか？ (y/N): ")
            if confirm.lower() == 'y':
                merge_buildings(primary['id'], duplicates_to_merge)


if __name__ == "__main__":
    try:
        main()
    finally:
        session.close()