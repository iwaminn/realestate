#!/usr/bin/env python3
"""
建物名更新スクリプト

スクレイピング時に建物名が変更されている場合の更新と、
同一建物の複数物件から最適な建物名を選択するロジック
"""

import time
import requests
from bs4 import BeautifulSoup
from collections import Counter
import re
import os
import sys

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.models import Building, BuildingAlias, MasterProperty, PropertyListing
from backend.app.database import SessionLocal


def is_advertising_text(text):
    """広告文かどうかを判定"""
    if not text:
        return False
    
    # 広告文のパターン
    advertising_patterns = [
        r'≪.*≫',  # ≪≫で囲まれた文字
        r'【.*】',  # 【】で囲まれた文字
        r'！',      # 感嘆符
        r'即日',
        r'頭金',
        r'0円',
        r'案内',
        r'購入可',
        r'おすすめ',
        r'新着',
        r'送迎',
        r'サービス',
        r'実施中',
        r'可能です',
        r'ご.*[来店|見学|内覧]',
    ]
    
    for pattern in advertising_patterns:
        if re.search(pattern, text):
            return True
    
    return False


def extract_building_name_from_detail_page(url):
    """詳細ページから正しい建物名を取得"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 詳細ページの物件名を探す
        # パターン1: テーブル形式
        tables = soup.select('table')
        for table in tables:
            rows = table.select('tr')
            for row in rows:
                th = row.select_one('th')
                td = row.select_one('td')
                if th and td:
                    if '物件名' in th.get_text():
                        building_name = td.get_text(strip=True)
                        if building_name and not is_advertising_text(building_name):
                            return building_name
        
        # パターン2: 定義リスト形式
        dls = soup.select('dl')
        for dl in dls:
            dts = dl.select('dt')
            dds = dl.select('dd')
            for dt, dd in zip(dts, dds):
                if '物件名' in dt.get_text():
                    building_name = dd.get_text(strip=True)
                    if building_name and not is_advertising_text(building_name):
                        return building_name
        
        # パターン3: セクションタイトル
        h1_elem = soup.select_one('h1.section_h1-header-title')
        if h1_elem:
            text = h1_elem.get_text(strip=True)
            # SUUMOの詳細ページタイトルから建物名を抽出
            match = re.match(r'(.+?)の物件詳細', text)
            if match:
                building_name = match.group(1)
                if not is_advertising_text(building_name):
                    return building_name
                    
        return None
        
    except Exception as e:
        print(f"エラー: {e}")
        return None


def select_best_building_name(building_names):
    """複数の建物名候補から最適なものを選択"""
    if not building_names:
        return None
    
    # 広告文でないものを優先
    non_ad_names = [name for name in building_names if not is_advertising_text(name)]
    if non_ad_names:
        # 最も頻繁に出現する名前を選択
        name_counts = Counter(non_ad_names)
        return name_counts.most_common(1)[0][0]
    
    # すべて広告文の場合は最短のものを選択（広告文が少ない可能性が高い）
    return min(building_names, key=len)


def update_building_names():
    """建物名を更新"""
    session = SessionLocal()
    
    try:
        # 広告文のような建物名を持つ建物を取得
        from sqlalchemy import or_
        problematic_buildings = session.query(Building).filter(
            or_(
                Building.normalized_name.like('%≪%'),
                Building.normalized_name.like('%【%'),
                Building.normalized_name.like('%送迎%'),
                Building.normalized_name.like('%サービス%'),
                Building.normalized_name.like('%見学%'),
                Building.normalized_name.like('%内覧%')
            )
        ).all()
        
        print(f"更新対象の建物数: {len(problematic_buildings)}")
        
        for building in problematic_buildings:
            print(f"\n建物ID {building.id}: {building.normalized_name}")
            
            # この建物に関連するアクティブな物件を取得
            listings = session.query(PropertyListing).join(
                MasterProperty
            ).filter(
                MasterProperty.building_id == building.id,
                PropertyListing.is_active == True
            ).all()
            
            if not listings:
                print("  → アクティブな物件なし")
                continue
            
            # 各物件から建物名を収集
            collected_names = []
            
            for listing in listings[:5]:  # 最大5件チェック
                print(f"  → {listing.source_site} URL: {listing.url}")
                
                if listing.source_site == 'SUUMO':
                    # 詳細ページから建物名を取得
                    building_name = extract_building_name_from_detail_page(listing.url)
                    if building_name:
                        print(f"    → 取得した建物名: {building_name}")
                        collected_names.append(building_name)
                    
                    time.sleep(2)  # レート制限
            
            # 最適な建物名を選択
            best_name = select_best_building_name(collected_names)
            
            if best_name and best_name != building.normalized_name:
                print(f"  → 新しい建物名: {best_name}")
                
                # 既存の建物名をエイリアスとして保存
                existing_alias = session.query(BuildingAlias).filter(
                    BuildingAlias.building_id == building.id,
                    BuildingAlias.alias_name == building.normalized_name
                ).first()
                
                if not existing_alias:
                    alias = BuildingAlias(
                        building_id=building.id,
                        alias_name=building.normalized_name,
                        source='SUUMO'
                    )
                    session.add(alias)
                
                # 建物名を更新
                building.normalized_name = best_name
                session.commit()
                print("  → 更新完了")
                
        print("\n処理完了")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
    finally:
        session.close()


def update_building_names_on_scraping(session, property_data, building):
    """
    スクレイピング時に建物名を更新する関数
    スクレイパーから呼び出される
    """
    if not property_data.get('building_name'):
        return
    
    new_name = property_data['building_name']
    
    # 新しい建物名が広告文でない場合のみ更新を検討
    if not is_advertising_text(new_name):
        # 現在の建物名が広告文の場合は更新
        if is_advertising_text(building.normalized_name):
            # 既存の名前をエイリアスとして保存
            existing_alias = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id,
                BuildingAlias.alias_name == building.normalized_name
            ).first()
            
            if not existing_alias:
                alias = BuildingAlias(
                    building_id=building.id,
                    alias_name=building.normalized_name,
                    source=property_data.get('source_site', 'UNKNOWN')
                )
                session.add(alias)
            
            # 建物名を更新
            building.normalized_name = new_name
            print(f"[建物名更新] ID {building.id}: {building.normalized_name} -> {new_name}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='建物名を更新')
    parser.add_argument('--building-id', type=int, help='特定の建物IDのみ更新')
    
    args = parser.parse_args()
    
    if args.building_id:
        # 特定の建物のみ更新
        session = SessionLocal()
        building = session.query(Building).filter(Building.id == args.building_id).first()
        if building:
            print(f"建物ID {building.id} の更新を開始")
            # 処理...
        session.close()
    else:
        update_building_names()