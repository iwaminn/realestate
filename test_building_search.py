#!/usr/bin/env python3
"""
建物検索の問題を調査するテストスクリプト
"""

import os
import sys
sys.path.append('/home/ubuntu/realestate')

from backend.app.database import SessionLocal
from backend.app.models import Building
from backend.app.utils.address_normalizer import AddressNormalizer
from backend.app.scrapers.data_normalizer import canonicalize_building_name

def find_existing_building_by_key(session, search_key: str, address: str = None, 
                                  total_floors: int = None, built_year: int = None, 
                                  total_units: int = None):
    """find_existing_building_by_keyメソッドの動作を再現"""
    
    print(f"\n=== find_existing_building_by_key 実行 ===")
    print(f"search_key: {search_key}")
    print(f"address: {address}")
    print(f"total_floors: {total_floors}, built_year: {built_year}, total_units: {total_units}")
    
    if not address:
        print("住所が指定されていないため、建物検索をスキップ")
        return None
    
    normalizer = AddressNormalizer()
    normalized_address = normalizer.normalize_for_comparison(address)
    print(f"normalized_address: {normalized_address}")
    
    # まず、normalized_addressカラムで高速検索
    if hasattr(Building, 'normalized_address'):
        # 完全一致を先に試す
        building = session.query(Building).filter(
            Building.canonical_name == search_key,
            Building.normalized_address == normalized_address
        ).first()
        
        if building:
            print(f"✓ 完全一致で発見: 建物ID {building.id}, {building.normalized_name}")
            return building
        else:
            print("✗ 完全一致なし")
        
        # 部分一致を試す
        from sqlalchemy import or_
        partial_match_buildings = session.query(Building).filter(
            Building.canonical_name == search_key
        ).all()
        
        print(f"\ncanonical_name '{search_key}' の建物: {len(partial_match_buildings)}件")
        
        # Pythonレベルで部分一致をチェック
        partial_matches = []
        for b in partial_match_buildings:
            if b.normalized_address:
                match1 = b.normalized_address.startswith(normalized_address)
                match2 = normalized_address.startswith(b.normalized_address)
                
                print(f"\n建物ID {b.id}:")
                print(f"  normalized_address: '{b.normalized_address}'")
                print(f"  既存住所が新規住所で始まる: {match1}")
                print(f"  新規住所が既存住所で始まる: {match2}")
                
                if match1 or match2:
                    partial_matches.append(b)
                    print(f"  → 部分一致！")
        
        print(f"\n部分一致する建物: {len(partial_matches)}件")
        
        # 部分一致の場合も属性確認
        for building in partial_matches:
            # 属性検証（簡略版）
            if total_floors is None or built_year is None or total_units is None:
                print(f"✗ 建物ID {building.id}: スクレイピング情報の属性が不足")
                continue
            
            if (building.total_floors is None or building.built_year is None or 
                building.total_units is None):
                print(f"✗ 建物ID {building.id}: 既存建物の属性が不足")
                continue
            
            if (building.total_floors == total_floors and 
                building.built_year == built_year and 
                building.total_units == total_units):
                print(f"✓ 部分一致かつ属性一致: 建物ID {building.id}")
                return building
            else:
                print(f"✗ 建物ID {building.id}: 属性が一致しない")
                print(f"    総階数: {building.total_floors} vs {total_floors}")
                print(f"    築年: {building.built_year} vs {built_year}")
                print(f"    総戸数: {building.total_units} vs {total_units}")
    
    print("\n✗ 一致する建物が見つかりません")
    return None


def main():
    session = SessionLocal()
    
    # テストケース：WORLD TOWER RESIDENCE
    test_cases = [
        {
            'name': 'WORLD TOWER RESIDENCE',
            'address': '東京都港区浜松町2丁目3-9',
            'total_floors': 46,
            'built_year': 2024,
            'total_units': 389
        },
        {
            'name': 'キャピタルマークタワー',
            'address': '東京都港区芝浦4-10-1',
            'total_floors': 47,
            'built_year': 2007,
            'total_units': 869
        }
    ]
    
    for test in test_cases:
        print("\n" + "="*60)
        print(f"テスト: {test['name']}")
        print("="*60)
        
        # 検索キーを生成（canonicalize_building_nameを使用）
        search_key = canonicalize_building_name(test['name'])
        print(f"生成された検索キー: '{search_key}'")
        
        # 建物を検索
        building = find_existing_building_by_key(
            session,
            search_key,
            test['address'],
            test['total_floors'],
            test['built_year'],
            test['total_units']
        )
        
        if building:
            print(f"\n✓✓✓ 建物を発見: ID {building.id}, {building.normalized_name}")
        else:
            print(f"\n✗✗✗ 建物が見つかりません")
    
    session.close()


if __name__ == "__main__":
    main()