#!/usr/bin/env python3
"""
プレースホルダー建物名（物件_で始まる名前）を修正するスクリプト

掲載情報のタイトルから正しい建物名を抽出し、
既存の正しい建物と統合するか、建物名を更新します。
"""

import os
import sys
import re
from typing import Optional, Dict, List, Tuple
from datetime import datetime

# プロジェクトのルートディレクトリをPATHに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import Building, MasterProperty, PropertyListing
from app.database import DATABASE_URL


def extract_building_name_from_title(title: str) -> Optional[str]:
    """掲載タイトルから建物名を抽出"""
    if not title:
        return None
    
    # 特殊ケース1: ・ネット見学予約機能 【独占公開！】オープンレジデンシア虎ノ門
    if 'オープンレジデンシア虎ノ門' in title:
        return 'オープンレジデンシア虎ノ門'
    
    # 特殊ケース2: クレストプライムタワー芝
    if 'クレストプライムタワー芝' in title:
        return 'クレストプライムタワー芝'
    
    # 特殊ケース3: 【予約制内覧会実施】白金ザ・スカイE棟
    if '白金ザ・スカイ' in title:
        return '白金ザ・スカイE棟'
    
    # まず明確な建物名を探す
    # パターン1: 建物名【説明】または建物名（説明）のパターン
    match = re.search(r'^([^【（\(・]+)(?:[【（]|$)', title)
    if match:
        building_name = match.group(1).strip()
        # 末尾の記号や空白を削除
        building_name = re.sub(r'[　\s]+$', '', building_name)
        building_name = re.sub(r'[・。、]+$', '', building_name)
        
        # 建物名として妥当かチェック
        if (building_name and 
            len(building_name) > 2 and 
            '万円' not in building_name and
            '内覧' not in building_name and
            '見学' not in building_name and
            '公開' not in building_name and
            '車庫' not in building_name and
            'リノベ' not in building_name and
            '！' not in building_name and
            '≪' not in building_name and
            '◇' not in building_name):
            return building_name
    
    # パターン2: 【建物名】が最初にある場合（説明ではなく建物名の場合）
    match = re.search(r'^【([^】]+)】', title)
    if match:
        building_name = match.group(1).strip()
        if (building_name and 
            len(building_name) > 2 and 
            '万円' not in building_name and
            not any(word in building_name for word in ['内覧', '見学', '公開', '車庫', 'リノベ', '新築', '築浅', '即日', '独占'])):
            return building_name
    
    # パターン3: 「建物名」のパターン
    match = re.search(r'「([^」]+)」', title)
    if match:
        building_name = match.group(1).strip()
        if building_name and len(building_name) > 2 and '万円' not in building_name:
            return building_name
    
    return None


def find_existing_building(session, building_name: str, address: str) -> Optional[Building]:
    """同じ建物名または住所の既存建物を検索"""
    # 完全一致で検索
    existing = session.query(Building).filter(
        Building.normalized_name == building_name
    ).first()
    
    if existing:
        return existing
    
    # 住所で検索（番地の表記ゆれを考慮）
    if address:
        # 住所の正規化（全角数字を半角に、ハイフンの統一など）
        normalized_address = address
        for i in range(10):
            normalized_address = normalized_address.replace(f'０１２３４５６７８９'[i], str(i))
        normalized_address = normalized_address.replace('－', '-').replace('ー', '-')
        
        # 番地部分を抽出
        address_base = re.sub(r'(\d+)丁目(\d+)', r'\1-\2', normalized_address)
        
        similar_buildings = session.query(Building).filter(
            Building.address.like(f'%{address_base[:15]}%')
        ).all()
        
        for building in similar_buildings:
            # 建築年、階数が一致すれば同じ建物の可能性が高い
            if (building.built_year and building.total_floors and 
                not building.normalized_name.startswith('物件_')):
                return building
    
    return None


def main(dry_run=False):
    """メイン処理"""
    # コマンドライン引数処理
    import argparse
    parser = argparse.ArgumentParser(description='プレースホルダー建物名を修正')
    parser.add_argument('--dry-run', action='store_true', help='実行せずに計画のみ表示')
    parser.add_argument('--yes', '-y', action='store_true', help='確認なしで実行')
    args = parser.parse_args()
    
    # データベース接続
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # プレースホルダー建物を取得
        placeholder_buildings = session.query(Building).filter(
            Building.normalized_name.like('物件_%')
        ).all()
        
        print(f"プレースホルダー建物数: {len(placeholder_buildings)}")
        
        updates = []
        merges = []
        
        for building in placeholder_buildings:
            # この建物に紐づく物件と掲載情報を取得
            properties_with_listings = session.query(
                MasterProperty,
                PropertyListing.title
            ).join(
                PropertyListing,
                MasterProperty.id == PropertyListing.master_property_id
            ).filter(
                MasterProperty.building_id == building.id,
                PropertyListing.is_active == True
            ).all()
            
            if not properties_with_listings:
                print(f"建物ID {building.id} ({building.normalized_name}): アクティブな掲載情報なし")
                continue
            
            # タイトルから建物名を抽出
            building_names = []
            for prop, title in properties_with_listings:
                extracted_name = extract_building_name_from_title(title)
                if extracted_name:
                    building_names.append(extracted_name)
            
            if not building_names:
                print(f"建物ID {building.id} ({building.normalized_name}): 建物名を抽出できず")
                continue
            
            # 最も頻度の高い建物名を採用
            from collections import Counter
            name_counter = Counter(building_names)
            most_common_name = name_counter.most_common(1)[0][0]
            
            print(f"\n建物ID {building.id} ({building.normalized_name}):")
            print(f"  住所: {building.address}")
            print(f"  抽出された建物名: {most_common_name}")
            print(f"  掲載タイトル例: {properties_with_listings[0][1]}")
            
            # 既存の建物を検索
            existing_building = find_existing_building(session, most_common_name, building.address)
            
            if existing_building and existing_building.id != building.id:
                print(f"  → 既存建物と統合: ID {existing_building.id} ({existing_building.normalized_name})")
                merges.append((building.id, existing_building.id, most_common_name))
            else:
                print(f"  → 建物名を更新: {most_common_name}")
                updates.append((building.id, most_common_name))
        
        # 確認
        print(f"\n\n=== 実行計画 ===")
        print(f"建物名更新: {len(updates)}件")
        print(f"建物統合: {len(merges)}件")
        
        if not updates and not merges:
            print("更新対象がありません。")
            return
        
        if args.dry_run:
            print("\n[DRY RUN] 実際の更新は行いません。")
            return
        
        if not args.yes:
            response = input("\n実行しますか？ (y/n): ")
            if response.lower() != 'y':
                print("キャンセルしました。")
                return
        
        # 実行
        print("\n実行中...")
        
        # 建物名の更新
        for building_id, new_name in updates:
            session.execute(
                text("UPDATE buildings SET normalized_name = :name, updated_at = :now WHERE id = :id"),
                {"name": new_name, "now": datetime.now(), "id": building_id}
            )
            print(f"建物ID {building_id}: 名前を「{new_name}」に更新")
        
        # 建物の統合
        for old_building_id, new_building_id, building_name in merges:
            # 物件を新しい建物に移動
            session.execute(
                text("UPDATE master_properties SET building_id = :new_id WHERE building_id = :old_id"),
                {"new_id": new_building_id, "old_id": old_building_id}
            )
            print(f"建物ID {old_building_id}の物件を建物ID {new_building_id}（{building_name}）に移動")
        
        session.commit()
        print("\n完了しました！")
        
        # 統合後の空の建物を表示
        if merges:
            print("\n以下の建物は物件がなくなりました（手動で削除を検討してください）:")
            for old_building_id, _, _ in merges:
                print(f"  - 建物ID {old_building_id}")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()