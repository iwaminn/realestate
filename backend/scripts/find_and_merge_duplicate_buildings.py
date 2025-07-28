#!/usr/bin/env python3
"""
重複建物を検出して統合するための汎用スクリプト
検索キーベースで同一建物の可能性があるものを検出
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from collections import defaultdict
from backend.app.database import SessionLocal
from backend.app.models import Building, BuildingAlias, MasterProperty, PropertyListing
from backend.app.utils.building_merger import merge_buildings_internal
from backend.app.scrapers.base_scraper import BaseScraper
from sqlalchemy import func
import logging
import re
import jaconv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DuplicateBuildingFinder:
    """重複建物検出クラス"""
    
    def __init__(self, session):
        self.session = session
        # BaseScraperのインスタンスを作成して検索キー生成メソッドを利用
        self.base_scraper = BaseScraper.__new__(BaseScraper)
        self.base_scraper.session = session
    
    def get_search_key(self, building_name: str) -> str:
        """建物検索用のキーを生成（BaseScraperと同じロジック）"""
        # 全角英数字→半角
        key = jaconv.z2h(building_name, kana=False, ascii=True, digit=True)
        # スペースと記号の正規化
        key = re.sub(r'[\s　・－―～〜]+', '', key)
        # 大文字統一
        key = key.upper()
        # 末尾の棟表記を除去（検索時のみ）
        key = re.sub(r'(EAST|WEST|NORTH|SOUTH|E|W|N|S|東|西|南|北)?棟$', '', key)
        return key
    
    def find_duplicate_buildings(self, min_properties=2):
        """重複建物を検出"""
        # 全建物を取得
        all_buildings = self.session.query(Building).all()
        
        # 検索キーでグループ化
        key_to_buildings = defaultdict(list)
        
        for building in all_buildings:
            # 建物名から検索キーを生成
            search_key = self.get_search_key(building.normalized_name)
            
            # エイリアスからも検索キーを生成
            aliases = self.session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id
            ).all()
            
            # 全ての名前から検索キーを生成
            all_keys = set()
            all_keys.add(search_key)
            
            for alias in aliases:
                alias_key = self.get_search_key(alias.alias_name)
                all_keys.add(alias_key)
            
            # 各キーでグループ化
            for key in all_keys:
                key_to_buildings[key].append(building)
        
        # 重複候補を検出
        duplicate_groups = []
        processed_building_ids = set()
        
        for search_key, buildings in key_to_buildings.items():
            # 重複を除去
            unique_buildings = []
            seen_ids = set()
            for b in buildings:
                if b.id not in seen_ids and b.id not in processed_building_ids:
                    unique_buildings.append(b)
                    seen_ids.add(b.id)
            
            # 複数の建物が同じキーを持つ場合
            if len(unique_buildings) >= 2:
                # 物件数でフィルタ
                buildings_with_properties = []
                for b in unique_buildings:
                    prop_count = self.session.query(MasterProperty).filter_by(
                        building_id=b.id
                    ).count()
                    if prop_count >= min_properties:
                        buildings_with_properties.append((b, prop_count))
                
                if len(buildings_with_properties) >= 2:
                    duplicate_groups.append({
                        'search_key': search_key,
                        'buildings': buildings_with_properties
                    })
                    # 処理済みとしてマーク
                    for b, _ in buildings_with_properties:
                        processed_building_ids.add(b.id)
        
        return duplicate_groups
    
    def analyze_duplicate_group(self, group):
        """重複グループの詳細を分析"""
        print(f"\n=== 検索キー: {group['search_key']} ===")
        
        buildings = sorted(group['buildings'], key=lambda x: x[1], reverse=True)
        
        for building, prop_count in buildings:
            listing_count = self.session.query(PropertyListing).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building.id
            ).count()
            
            # エイリアス情報
            aliases = self.session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id
            ).all()
            
            print(f"\nID: {building.id}")
            print(f"名前: {building.normalized_name}")
            print(f"住所: {building.address or '未設定'}")
            print(f"物件数: {prop_count}, 掲載数: {listing_count}")
            
            if aliases:
                print("エイリアス:")
                alias_counts = defaultdict(int)
                for alias in aliases:
                    alias_counts[alias.alias_name] += 1
                
                for name, count in sorted(alias_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  - '{name}' ({count}回)")
                
                if len(alias_counts) > 5:
                    print(f"  ... 他 {len(alias_counts) - 5}種類")


def main():
    """メイン処理"""
    session = SessionLocal()
    
    try:
        finder = DuplicateBuildingFinder(session)
        
        print("重複建物を検索中...")
        duplicate_groups = finder.find_duplicate_buildings(min_properties=1)
        
        if not duplicate_groups:
            print("重複建物は見つかりませんでした。")
            return
        
        print(f"\n{len(duplicate_groups)}個の重複グループが見つかりました。")
        
        # 各グループを分析
        for i, group in enumerate(duplicate_groups):
            print(f"\n{'='*60}")
            print(f"グループ {i+1}/{len(duplicate_groups)}")
            finder.analyze_duplicate_group(group)
        
        # 統合オプション
        print(f"\n{'='*60}")
        print("\n統合オプション:")
        print("1. 特定のグループを統合")
        print("2. 全てのグループを自動統合（物件数が最も多い建物を主とする）")
        print("3. キャンセル")
        
        choice = input("\n選択してください (1-3): ")
        
        if choice == "1":
            group_num = int(input("統合するグループ番号を入力してください: ")) - 1
            if 0 <= group_num < len(duplicate_groups):
                group = duplicate_groups[group_num]
                buildings = sorted(group['buildings'], key=lambda x: x[1], reverse=True)
                
                print("\n統合先を選択してください:")
                for i, (building, prop_count) in enumerate(buildings):
                    print(f"{i+1}. ID: {building.id}, 名前: {building.normalized_name}, 物件数: {prop_count}")
                
                primary_idx = int(input("統合先の番号を入力してください: ")) - 1
                if 0 <= primary_idx < len(buildings):
                    primary_building = buildings[primary_idx][0]
                    
                    for building, _ in buildings:
                        if building.id != primary_building.id:
                            print(f"統合中: {building.normalized_name} (ID: {building.id}) → {primary_building.normalized_name} (ID: {primary_building.id})")
                            merge_buildings_internal(session, primary_building.id, building.id, merge_type="duplicate")
                    
                    session.commit()
                    print("統合が完了しました。")
        
        elif choice == "2":
            confirm = input("全てのグループを自動統合しますか？ (yes/no): ")
            if confirm.lower() == "yes":
                for group in duplicate_groups:
                    buildings = sorted(group['buildings'], key=lambda x: x[1], reverse=True)
                    primary_building = buildings[0][0]
                    
                    print(f"\n統合グループ: {group['search_key']}")
                    for building, _ in buildings[1:]:
                        print(f"  統合中: {building.normalized_name} (ID: {building.id}) → {primary_building.normalized_name} (ID: {primary_building.id})")
                        merge_buildings_internal(session, primary_building.id, building.id, merge_type="duplicate")
                
                session.commit()
                print("\n全ての統合が完了しました。")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()