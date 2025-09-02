"""
重複管理API（建物・物件）
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, text
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from ...database import get_db
from ...models import (
    Building, MasterProperty, PropertyListing,
    BuildingMergeHistory, PropertyMergeHistory,
    BuildingMergeExclusion, PropertyMergeExclusion,
    BuildingExternalId
)
from ...utils.enhanced_building_matcher import EnhancedBuildingMatcher
from ...utils.majority_vote_updater import MajorityVoteUpdater
from ...utils.building_listing_name_manager import BuildingListingNameManager
from ...utils.property_utils import update_earliest_listing_date
from ...scrapers.data_normalizer import normalize_layout, normalize_direction

router = APIRouter(tags=["admin-duplicates"])

def clear_duplicate_buildings_cache():
    """重複建物キャッシュをクリア（無効化）"""
    # この関数は互換性のために残されています
    pass


class DuplicateCandidate(BaseModel):
    """重複候補の物件ペア"""
    property1_id: int
    property2_id: int
    building_name: str
    floor_number: Optional[int]
    area: Optional[float]
    layout: Optional[str]
    similarity_score: Optional[float]


class BuildingMergeRequest(BaseModel):
    """建物統合リクエスト"""
    primary_building_id: int
    secondary_building_id: int


class BuildingMergeBatchRequest(BaseModel):
    """複数建物統合リクエスト"""
    primary_id: int
    secondary_ids: List[int]


class PropertyMergeRequest(BaseModel):
    """物件統合リクエスト"""
    primary_property_id: int
    secondary_property_id: int


@router.get("/duplicate-buildings")
async def get_duplicate_buildings(
    search: Optional[str] = Query(None, description="検索キーワード"),
    min_similarity: float = Query(0.7, description="類似度の閾値"),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """建物の重複候補を取得（改善版）"""
    import re
    import time
    from ...utils.enhanced_building_matcher import EnhancedBuildingMatcher
    
    # 処理時間測定開始
    start_time = time.time()
    phase_times = {}
    
    # フェーズ1: Matcherの初期化
    phase_start = time.time()
    
    # ロガーのインポート
    import logging
    logger = logging.getLogger(__name__)
    
    # EnhancedBuildingMatcherのインスタンスを作成（まだキャッシュなし）
    matcher = None  # 後で建物リスト取得後に初期化
    phase_times['matcher_init'] = time.time() - phase_start
    
    # フェーズ2: 建物データの取得
    phase_start = time.time()
    
    # 検索条件がある場合は通常通り処理
    if search:
        # ベースクエリ
        base_query = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).group_by(Building.id).having(
            func.count(MasterProperty.id) > 0  # 物件がある建物のみ
        )
        
        # BuildingListingNameを使用した検索
        from ...models import BuildingListingName
        from ...scrapers.data_normalizer import canonicalize_building_name
        
        # 検索語を正規化
        canonical_search = canonicalize_building_name(search)
        
        # BuildingListingNameから該当する建物IDを取得
        matching_building_ids = db.query(BuildingListingName.building_id).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_search}%")
        ).distinct().subquery()
        
        # Building.normalized_name または BuildingListingNameでマッチ
        base_query = base_query.filter(
            or_(
                Building.normalized_name.ilike(f"%{search}%"),
                Building.id.in_(matching_building_ids)
            )
        )
        
        buildings_with_count = base_query.order_by(
            Building.normalized_name,
            Building.id  # 同じ名前内でもID順で安定したソート
        ).all()
    else:
        # 検索条件がない場合：重複の可能性が高い建物群を効率的に見つける
        
        # 優先度1: 同じ建物名または類似した建物名を持つ建物（最も重複の可能性が高い）
        # まず完全一致する建物名のグループを取得
        exact_match_subquery = db.query(
            Building.normalized_name,
            func.count(Building.id).label('name_count')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            )
        ).group_by(Building.normalized_name).having(
            func.count(Building.id) > 1  # 同じ名前の建物が2つ以上
        ).subquery()
        
        # 同名建物をすべて取得
        buildings_with_count = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).filter(
            Building.normalized_name.in_(
                db.query(exact_match_subquery.c.normalized_name)
            )
        ).group_by(Building.id).order_by(
            Building.normalized_name,
            Building.id  # 同じ名前内でもID順で安定したソート
        ).all()
        
        # 優先度2: 同じ住所・築年・階数の組み合わせを持つ建物を追加
        # 同名建物だけでなく、属性が一致する建物も必ず含める
        # 同じ住所前半部分、同じ築年、同じ階数を持つ建物のグループを検索
        # これらは表記ゆれや入力ミスによる重複の可能性が高い
        duplicate_candidates = db.query(
            Building,
            func.count(MasterProperty.id).label('property_count')
        ).outerjoin(
            MasterProperty, Building.id == MasterProperty.building_id
        ).filter(
            Building.id.notin_([b[0].id for b in buildings_with_count])
        ).group_by(Building.id).having(
            func.count(MasterProperty.id) > 0
        )
        
        # サブクエリで重複の可能性が高い組み合わせを特定
        # 総戸数、総階数がすべて一致し、築年が近い建物を優先的に検索
        # 築年は±1年の許容範囲を考慮するため、個別に処理
        from sqlalchemy import case
        
        attribute_groups = []
        
        # 住所、総階数、総戸数でグループ化（築年は後で個別チェック）
        base_groups = db.query(
            func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
            Building.total_floors,
            Building.total_units,
            func.array_agg(Building.id).label('building_ids'),
            func.array_agg(Building.built_year).label('built_years'),
            func.count(Building.id).label('group_count')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            ),
            Building.total_floors.isnot(None),
            Building.total_units.isnot(None)  # 総戸数が存在する建物のみ
        ).group_by(
            func.substring(Building.normalized_address, 1, 10),
            Building.total_floors,
            Building.total_units
        ).having(
            func.count(Building.id) > 1  # 同じ属性の組み合わせが2つ以上
        ).all()  # limitを削除して全ての重複候補を検出
        
        # パターン2: 住所と総階数が一致し、建物名が部分一致
        # （総戸数はNULLまたは異なる）
        address_floor_groups = db.query(
            func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
            Building.total_floors,
            func.array_agg(Building.id).label('building_ids'),
            func.array_agg(Building.canonical_name).label('canonical_names')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            ),
            Building.total_floors.isnot(None),
            Building.canonical_name.isnot(None)
        ).group_by(
            func.substring(Building.normalized_address, 1, 10),
            Building.total_floors
        ).having(
            func.count(Building.id) > 1
        ).all()
        
        # パターン3: 住所と総戸数が一致し、建物名が部分一致
        # （総階数はNULLまたは異なる）
        address_units_groups = db.query(
            func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
            Building.total_units,
            func.array_agg(Building.id).label('building_ids'),
            func.array_agg(Building.canonical_name).label('canonical_names')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            ),
            Building.total_units.isnot(None),
            Building.canonical_name.isnot(None)
        ).group_by(
            func.substring(Building.normalized_address, 1, 10),
            Building.total_units
        ).having(
            func.count(Building.id) > 1
        ).all()
        
        # パターン4: 住所と築年が一致し、建物名が部分一致
        # （他はNULLまたは異なる）
        address_year_groups = db.query(
            func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
            Building.built_year,
            func.array_agg(Building.id).label('building_ids'),
            func.array_agg(Building.canonical_name).label('canonical_names')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            ),
            Building.built_year.isnot(None),
            Building.canonical_name.isnot(None)
        ).group_by(
            func.substring(Building.normalized_address, 1, 10),
            Building.built_year
        ).having(
            func.count(Building.id) > 1
        ).all()
        
        # パターン2〜4の結果を処理して、canonical_nameが部分一致する建物を抽出
        partial_match_groups = []
        
        # 建物名の部分一致判定を改善する関数
        def is_name_match(name1: str, name2: str) -> bool:
            """建物名の部分一致を判定（共通接頭辞も考慮）"""
            if not name1 or not name2:
                return False
            # 完全一致
            if name1 == name2:
                return True
            # 片方が他方に含まれる
            if name1 in name2 or name2 in name1:
                return True
            # 共通接頭辞が5文字以上（棟番号などの違いを許容）
            min_len = min(len(name1), len(name2))
            if min_len >= 5:
                for i in range(min_len, 4, -1):  # 5文字以上の共通部分を探す
                    if name1[:i] == name2[:i]:
                        return True
            return False
        
        # パターン2: 住所と総階数が一致し、建物名が部分一致
        for group in address_floor_groups:
            building_ids = group.building_ids if group.building_ids else []
            canonical_names = group.canonical_names if group.canonical_names else []
            
            # canonical_nameが部分一致するペアを探す
            matched_pairs = []
            for i in range(len(building_ids)):
                for j in range(i + 1, len(building_ids)):
                    if canonical_names[i] and canonical_names[j]:
                        # 改善された建物名マッチング
                        if is_name_match(canonical_names[i], canonical_names[j]):
                            matched_pairs.append((building_ids[i], building_ids[j]))
            
            if matched_pairs:
                # グループとして追加
                all_ids = set()
                for id1, id2 in matched_pairs:
                    all_ids.add(id1)
                    all_ids.add(id2)
                partial_match_groups.append({
                    'type': 'address_floor_name',
                    'building_ids': list(all_ids),
                    'address_prefix': group.address_prefix,
                    'total_floors': group.total_floors
                })
        
        # パターン3: 住所と総戸数が一致し、建物名が部分一致
        for group in address_units_groups:
            building_ids = group.building_ids if group.building_ids else []
            canonical_names = group.canonical_names if group.canonical_names else []
            
            matched_pairs = []
            for i in range(len(building_ids)):
                for j in range(i + 1, len(building_ids)):
                    if canonical_names[i] and canonical_names[j]:
                        if is_name_match(canonical_names[i], canonical_names[j]):
                            matched_pairs.append((building_ids[i], building_ids[j]))
            
            if matched_pairs:
                all_ids = set()
                for id1, id2 in matched_pairs:
                    all_ids.add(id1)
                    all_ids.add(id2)
                partial_match_groups.append({
                    'type': 'address_units_name',
                    'building_ids': list(all_ids),
                    'address_prefix': group.address_prefix,
                    'total_units': group.total_units
                })
        
        # パターン4: 住所と築年が一致し、建物名が部分一致
        for group in address_year_groups:
            building_ids = group.building_ids if group.building_ids else []
            canonical_names = group.canonical_names if group.canonical_names else []
            
            matched_pairs = []
            for i in range(len(building_ids)):
                for j in range(i + 1, len(building_ids)):
                    if canonical_names[i] and canonical_names[j]:
                        if is_name_match(canonical_names[i], canonical_names[j]):
                            matched_pairs.append((building_ids[i], building_ids[j]))
            
            if matched_pairs:
                all_ids = set()
                for id1, id2 in matched_pairs:
                    all_ids.add(id1)
                    all_ids.add(id2)
                partial_match_groups.append({
                    'type': 'address_year_name',
                    'building_ids': list(all_ids),
                    'address_prefix': group.address_prefix,
                    'built_year': group.built_year
                })
        
        # partial_match_groupsをattribute_groupsに追加
        for pmg in partial_match_groups:
            attribute_groups.append({
                'type': pmg['type'],
                'building_ids': pmg['building_ids'],
                'group_count': len(pmg['building_ids'])
            })
        
        # パターン5: 特殊ケース - 階数/戸数が異なるが同じ建物の可能性
        # 住所と築年が一致し、建物名の共通部分が長い場合
        special_case_groups = db.query(
            func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
            Building.built_year,
            func.array_agg(Building.id).label('building_ids'),
            func.array_agg(Building.canonical_name).label('canonical_names'),
            func.array_agg(Building.normalized_name).label('normalized_names')
        ).filter(
            Building.id.in_(
                db.query(MasterProperty.building_id).distinct()
            ),
            Building.built_year.isnot(None),
            Building.canonical_name.isnot(None)
        ).group_by(
            func.substring(Building.normalized_address, 1, 10),
            Building.built_year
        ).having(
            func.count(Building.id) > 1
        ).all()
        
        for group in special_case_groups:
            building_ids = group.building_ids if group.building_ids else []
            canonical_names = group.canonical_names if group.canonical_names else []
            normalized_names = group.normalized_names if group.normalized_names else []
            
            matched_pairs = []
            for i in range(len(building_ids)):
                for j in range(i + 1, len(building_ids)):
                    # 建物名の共通接頭辞が7文字以上の場合（より厳しい条件）
                    if canonical_names[i] and canonical_names[j]:
                        common_len = 0
                        for k in range(min(len(canonical_names[i]), len(canonical_names[j]))):
                            if canonical_names[i][k] == canonical_names[j][k]:
                                common_len += 1
                            else:
                                break
                        # 共通接頭辞が7文字以上（「白金ザスカイ」は7文字）
                        if common_len >= 7:
                            matched_pairs.append((building_ids[i], building_ids[j]))
            
            if matched_pairs:
                all_ids = set()
                for id1, id2 in matched_pairs:
                    all_ids.add(id1)
                    all_ids.add(id2)
                attribute_groups.append({
                    'type': 'special_case_long_common_name',
                    'building_ids': list(all_ids),
                    'group_count': len(all_ids)
                })
        
        # 築年が±1年以内の建物をグループとして追加
        for group in base_groups:
            building_ids = group.building_ids if group.building_ids else []
            built_years = group.built_years if group.built_years else []
            
            # 築年が±1年以内のペアがあるかチェック
            # 築年が完全に同じ場合も含める
            has_close_years = False
            if len(building_ids) > 1:  # グループに複数の建物がある
                # 築年がすべて存在するかチェック
                valid_years = [y for y in built_years if y is not None]
                if len(valid_years) == len(building_ids):
                    # すべての建物に築年がある場合
                    for i in range(len(valid_years)):
                        for j in range(i + 1, len(valid_years)):
                            if abs(valid_years[i] - valid_years[j]) <= 1:
                                has_close_years = True
                                break
                        if has_close_years:
                            break
            
            if has_close_years:
                # 仮想的なグループとして追加（後の処理で使用）
                attribute_groups.append({
                    'address_prefix': group.address_prefix,
                    'total_floors': group.total_floors,
                    'total_units': group.total_units,
                    'building_ids': building_ids,
                    'group_count': len(building_ids)
                })
        
        # 追加: 総階数が±1階の誤差を許容するパターンも検索
        if len(buildings_with_count) < limit * 2:
            flexible_groups = db.query(
                func.substring(Building.normalized_address, 1, 10).label('address_prefix'),
                Building.built_year,
                Building.total_units,
                func.count(Building.id).label('group_count')
            ).filter(
                Building.id.in_(
                    db.query(MasterProperty.building_id).distinct()
                ),
                Building.built_year.isnot(None),
                Building.total_units.isnot(None)
            ).group_by(
                func.substring(Building.normalized_address, 1, 10),
                Building.built_year,
                Building.total_units
            ).having(
                func.count(Building.id) > 1
            ).limit(30).all()
            
            for group in flexible_groups:
                if len(buildings_with_count) >= limit * 3:
                    break
                matching_buildings = duplicate_candidates.filter(
                    Building.normalized_address.like(f"{group.address_prefix}%"),
                    Building.built_year == group.built_year,
                    Building.total_units == group.total_units
                ).limit(10).all()
                
                # 既に追加済みの建物は除外
                for building, count in matching_buildings:
                    if not any(b[0].id == building.id for b in buildings_with_count):
                        buildings_with_count.append((building, count))
        
        # 見つかった組み合わせに一致する建物を取得（バッチクエリ化）
        # 全building_idを収集
        all_building_ids = []
        for group in attribute_groups:
            if 'building_ids' in group and group['building_ids']:
                all_building_ids.extend(group['building_ids'])
        
        if all_building_ids:
            # 建物と物件数を一括取得
            batch_results = db.query(
                Building,
                func.count(MasterProperty.id).label('property_count')
            ).outerjoin(
                MasterProperty, Building.id == MasterProperty.building_id
            ).filter(
                Building.id.in_(all_building_ids)
            ).group_by(Building.id).all()
            
            # 結果をマップに格納
            batch_map = {building.id: (building, count) for building, count in batch_results}
            
            # マップから既に追加済みでない建物を追加
            for building_id in all_building_ids:
                if building_id in batch_map and not any(b[0].id == building_id for b in buildings_with_count):
                    buildings_with_count.append(batch_map[building_id])
        
        # 優先度3: まだ枠がある場合は、通常の建物を追加（フォールバック）
        # 最大30件に制限して高速化（実際の重複はほぼ優先度1,2で見つかる）
        if len(buildings_with_count) < 30:
            remaining_buildings = db.query(
                Building,
                func.count(MasterProperty.id).label('property_count')
            ).outerjoin(
                MasterProperty, Building.id == MasterProperty.building_id
            ).filter(
                Building.id.notin_([b[0].id for b in buildings_with_count])
            ).group_by(Building.id).having(
                func.count(MasterProperty.id) > 0
            ).order_by(
                Building.normalized_name,
                Building.id  # 同じ名前内でもID順で安定したソート
            ).all()
            
            buildings_with_count.extend(remaining_buildings)
    
    phase_times['building_fetch'] = time.time() - phase_start
    
    # フェーズ3: 掲載履歴の一括取得とキャッシュ作成
    phase_start = time.time()
    
    # 全建物IDを収集
    all_building_ids = [b[0].id for b in buildings_with_count]
    
    # BuildingListingNameを一括取得
    from ...models import BuildingListingName
    all_listing_names = db.query(BuildingListingName).filter(
        BuildingListingName.building_id.in_(all_building_ids)
    ).all()
    
    # 建物IDごとにエイリアスをグループ化してキャッシュを作成
    aliases_cache = {}
    for listing in all_listing_names:
        building_id = listing.building_id
        if building_id not in aliases_cache:
            aliases_cache[building_id] = []
        
        # 重複を避けながら追加
        if listing.listing_name and listing.listing_name not in aliases_cache[building_id]:
            aliases_cache[building_id].append(listing.listing_name)
    
    # ログ出力
    logger.info(f"掲載履歴キャッシュ作成: {len(all_building_ids)}件の建物, {len(all_listing_names)}件の掲載名")
    
    phase_times['aliases_cache_build'] = time.time() - phase_start
    
    # フェーズ4: Matcherの初期化（キャッシュ付き）
    phase_start = time.time()
    
    # キャッシュを渡してMatcherを初期化
    matcher = EnhancedBuildingMatcher(aliases_cache=aliases_cache)
    
    phase_times['matcher_init_with_cache'] = time.time() - phase_start
    
    # フェーズ5: 除外ペアの取得
    phase_start = time.time()
    
    # 除外ペアを取得
    exclusions = db.query(BuildingMergeExclusion).all()
    excluded_pairs = set()
    for exclusion in exclusions:
        excluded_pairs.add((exclusion.building1_id, exclusion.building2_id))
        excluded_pairs.add((exclusion.building2_id, exclusion.building1_id))
    

    phase_times['exclusion_fetch'] = time.time() - phase_start
    
    # フェーズ6: 重複候補の検出と類似度計算（推移的グループ化対応）
    phase_start = time.time()
    
    duplicate_groups = []
    processed_ids = set()
    
    building_count = len(buildings_with_count)
    candidate_fetch_times = []
    similarity_calc_times = []
    
    # 推移的グループを構築するための隣接リストを準備
    # key: building_id, value: dict of {related_building_id: similarity}
    similarity_graph = {}
    # 地名による事前グループ化で比較回数を削減
    area_groups = {}  # 地名でグループ化した建物マップ
    building_to_area = {}  # 建物IDから地名へのマップ
    
    for building, count in buildings_with_count:
        # 地名部分の抽出とグループ化
        area_prefix = None
        if building.normalized_address:
            # 地名部分（丁目より前）を抽出
            addr_match = re.match(r'(.*?[区市町村][^0-9０-９]*)', building.normalized_address)
            if addr_match:
                area_prefix = addr_match.group(1)
        
        if not area_prefix and building.address:
            addr_match = re.match(r'(.*?[区市町村][^0-9０-９]*)', building.address)
            if addr_match:
                area_prefix = addr_match.group(1)
        
        # 地名でグループ化
        if area_prefix:
            if area_prefix not in area_groups:
                area_groups[area_prefix] = []
            area_groups[area_prefix].append((building, count))
            building_to_area[building.id] = area_prefix
        else:
            # 地名が取得できない場合は「その他」グループ
            if "その他" not in area_groups:
                area_groups["その他"] = []
            area_groups["その他"].append((building, count))
            building_to_area[building.id] = "その他"
    
    # ログ出力：地名グループの統計
    logger.info(f"地名グループ数: {len(area_groups)}")
    for area_name, buildings in area_groups.items():
        if len(buildings) > 1:  # 複数建物があるグループのみ
            logger.debug(f"  {area_name}: {len(buildings)}件")
    
    # まず全ての類似関係を構築
    all_building_ids = [b[0].id for b in buildings_with_count]
    for building_id in all_building_ids:
        similarity_graph[building_id] = {}
    
    # バッチクエリ最適化: 全建物のベース名を事前に計算し、類似建物を一括取得
    base_name_patterns = []
    for building, _ in buildings_with_count:
        base_name = building.normalized_name
        # 汎用的な棟番号除去のみ行う
        base_name = re.sub(r'[　\s]+[^　\s]*棟$', '', base_name)
        base_name = re.sub(r'[　\s]+[０-９0-9]+$', '', base_name)
        base_name = base_name.strip()
        if len(base_name) >= 5:
            base_name_patterns.append(base_name)
    
    # 同じベース名の建物を一括取得
    same_base_buildings_map = {}
    if base_name_patterns:
        # 全パターンをOR条件で検索
        base_name_conditions = [Building.normalized_name.like(f"{pattern}%") for pattern in set(base_name_patterns)]
        if base_name_conditions:
            same_base_query = db.query(Building).filter(
                or_(*base_name_conditions)
            )
            same_base_results = same_base_query.all()
            
            # 結果を各ベース名ごとにグループ化
            for building in same_base_results:
                for pattern in set(base_name_patterns):
                    if building.normalized_name.startswith(pattern):
                        if pattern not in same_base_buildings_map:
                            same_base_buildings_map[pattern] = []
                        same_base_buildings_map[pattern].append(building)
    
    # フェーズ4-1: 地名グループ内でのみ類似関係を構築（最適化）
    # 各地名グループ内でのみ比較を実行
    total_comparisons = 0
    skipped_comparisons = 0
    
    for area_name, area_buildings in area_groups.items():
        if len(area_buildings) < 2:
            continue  # 1件しかないグループはスキップ
        
        # グループ内の建物同士のみを比較
        for i, (building1, count1) in enumerate(area_buildings):
            building_start = time.time()
            
            # 同じ地名グループ内の他の建物のみを候補とする
            area_candidate_buildings = [
                (b, c) for b, c in area_buildings 
                if b.id != building1.id and b.id > building1.id  # IDが大きいものだけ比較（重複防止）
            ]
            
            # 建物名の共通部分を先に抽出（グループ検出の改善）
            base_name = building1.normalized_name
            # 汎用的な棟番号除去のみ行う
            # 末尾の「棟」を含む部分（数字棟、アルファベット棟、方角棟など）を除去
            base_name = re.sub(r'[　\s]+[^　\s]*棟$', '', base_name)
            # 末尾の数字部分を除去（部屋番号などの可能性）
            base_name = re.sub(r'[　\s]+[０-９0-9]+$', '', base_name)
            base_name = base_name.strip()
        
            # 同じベース名の建物を事前に処理済みリストに追加（重複防止）
            group_building_ids = set([building1.id])
            if len(base_name) >= 5:
                # バッチクエリから取得済みのデータを使用
                same_base_buildings = same_base_buildings_map.get(base_name, [])
                
                # グループ内の全建物IDを記録（後で重複しないようにする）
                for same_base in same_base_buildings:
                    if same_base.id != building1.id:
                        group_building_ids.add(same_base.id)
            
            # 地名グループ内での類似度計算
            if not area_candidate_buildings:
                continue
            
            candidate_fetch_times.append(time.time() - building_start)
            similarity_start = time.time()
            
            # 詳細な類似度計算とグラフ構築（地名グループ内のみ）
            for building2, count2 in area_candidate_buildings:
                total_comparisons += 1
                # 除外ペアをチェック
                is_excluded = (building1.id, building2.id) in excluded_pairs or (building2.id, building1.id) in excluded_pairs
                
                # 除外されている場合はスキップ
                if is_excluded:
                    skipped_comparisons += 1
                    continue
                
                # 類似度を計算
                calc_start = time.time()
                similarity = matcher.calculate_comprehensive_similarity(building1, building2, db)
                calc_time = time.time() - calc_start
                if calc_time > 0.1:  # 0.1秒以上かかった場合はログ出力
                    logger.warning(f"類似度計算が遅い: {calc_time:.2f}秒 (建物1: {building1.id}, 建物2: {building2.id})")
                
                if similarity >= min_similarity:
                    # グラフに辺を追加（双方向）
                    similarity_graph[building1.id][building2.id] = similarity
                    
                    if building2.id not in similarity_graph:
                        similarity_graph[building2.id] = {}
                    similarity_graph[building2.id][building1.id] = similarity
            
            similarity_calc_times.append(time.time() - similarity_start)
    
    phase_times['similarity_graph_build'] = time.time() - phase_start
    
    # フェーズ7: 連結成分を見つけて推移的グループを構築
    phase_start = time.time()
    
    def find_connected_components(graph):
        """グラフから連結成分を見つける（深さ優先探索）"""
        visited = set()
        components = []
        
        def dfs(node, component):
            visited.add(node)
            component.add(node)
            for neighbor in graph.get(node, {}):
                if neighbor not in visited:
                    dfs(neighbor, component)
        
        for node in graph:
            if node not in visited:
                component = set()
                dfs(node, component)
                if len(component) > 1:  # 単独の建物は除外
                    components.append(component)
        
        return components
    
    # 連結成分を見つける
    connected_components = find_connected_components(similarity_graph)
    
    # 除外設定を考慮してコンポーネントを分割
    def split_component_by_exclusions(component, excluded_pairs):
        """除外設定に基づいてコンポーネントを分割
        
        除外ペアがある場合、類似度の高い組み合わせを優先してサブグループを作成する。
        例: [A, B, C]で(A, B)が除外ペアだが、AとCの類似度が高い場合、
        [A, C]のグループを優先的に作成する。
        """
        # コンポーネント内で除外されているペアがあるかチェック
        building_ids = list(component)
        has_exclusion = False
        
        # コンポーネント内の除外ペアを収集
        component_exclusions = []
        for i in range(len(building_ids)):
            for j in range(i + 1, len(building_ids)):
                if (building_ids[i], building_ids[j]) in excluded_pairs:
                    component_exclusions.append((building_ids[i], building_ids[j]))
                    has_exclusion = True
        
        # 除外設定がない場合はそのまま返す
        if not has_exclusion:
            return [component]
        
        # 除外ペアがある場合、類似度を考慮してグループを作成
        # 各建物から最も類似度の高い候補を選んでグループを作る
        used_buildings = set()
        subgroups = []
        
        # 類似度の高い順に建物ペアをソート
        building_pairs_with_similarity = []
        for i in range(len(building_ids)):
            for j in range(i + 1, len(building_ids)):
                bid1, bid2 = building_ids[i], building_ids[j]
                # 除外ペアは除く
                if (bid1, bid2) not in excluded_pairs and (bid2, bid1) not in excluded_pairs:
                    # 類似度を取得
                    sim = similarity_graph.get(bid1, {}).get(bid2, 0)
                    if sim > 0:  # 類似度がある場合のみ
                        building_pairs_with_similarity.append((sim, bid1, bid2))
        
        # 類似度の高い順にソート
        building_pairs_with_similarity.sort(reverse=True)
        
        # 類似度の高いペアから順にグループを作成
        for sim, bid1, bid2 in building_pairs_with_similarity:
            if bid1 in used_buildings or bid2 in used_buildings:
                continue  # すでに使用済みの建物はスキップ
            
            # 新しいグループを作成
            new_group = {bid1, bid2}
            
            # このグループに追加できる建物を探す
            for bid in building_ids:
                if bid in new_group or bid in used_buildings:
                    continue
                
                # 新グループのすべてのメンバーと除外関係にないかチェック
                can_add = True
                for member in new_group:
                    if (bid, member) in excluded_pairs or (member, bid) in excluded_pairs:
                        can_add = False
                        break
                
                # 追加可能で、かつ類似度がある場合は追加
                if can_add:
                    # グループ内の少なくとも1つの建物と類似度がある場合のみ追加
                    has_similarity = False
                    for member in new_group:
                        if bid in similarity_graph.get(member, {}) or member in similarity_graph.get(bid, {}):
                            has_similarity = True
                            break
                    
                    if has_similarity:
                        new_group.add(bid)
            
            # グループが2つ以上の建物を含む場合のみ追加
            if len(new_group) > 1:
                subgroups.append(new_group)
                used_buildings.update(new_group)
        
        # まだグループに入っていない建物を処理
        remaining_buildings = set(building_ids) - used_buildings
        if remaining_buildings:
            # 残りの建物で可能なグループを作成
            for bid in remaining_buildings:
                if bid in used_buildings:
                    continue
                
                # この建物と組める建物を探す
                group = {bid}
                for other_bid in remaining_buildings:
                    if other_bid == bid or other_bid in used_buildings:
                        continue
                    
                    # 除外関係をチェック
                    can_add = True
                    for member in group:
                        if (other_bid, member) in excluded_pairs or (member, other_bid) in excluded_pairs:
                            can_add = False
                            break
                    
                    if can_add:
                        # 類似度があるかチェック
                        has_similarity = False
                        for member in group:
                            if other_bid in similarity_graph.get(member, {}) or member in similarity_graph.get(other_bid, {}):
                                has_similarity = True
                                break
                        
                        if has_similarity:
                            group.add(other_bid)
                            used_buildings.add(other_bid)
                
                if len(group) > 1:
                    subgroups.append(group)
                    used_buildings.update(group)
        
        return subgroups if subgroups else []
    
    # 各連結成分を除外設定で分割してからグループを構築
    duplicate_groups = []
    for component in connected_components:
        # 除外設定で分割
        subcomponents = split_component_by_exclusions(component, excluded_pairs)
        
        for subcomponent in subcomponents:
            # limitのチェックを削除して、全グループを収集してからソート後に制限
            
            # サブコンポーネント内の建物情報を取得
            component_buildings = []
            for building_id in subcomponent:  # component → subcomponent に修正
                # buildings_with_countから建物情報を探す
                building_info = None
                for building, count in buildings_with_count:
                    if building.id == building_id:
                        building_info = (building, count)
                        break
                
                if building_info:
                    component_buildings.append({
                        "id": building_info[0].id,
                        "normalized_name": building_info[0].normalized_name,
                        "address": building_info[0].address,
                        "total_floors": building_info[0].total_floors,
                        "total_units": building_info[0].total_units if hasattr(building_info[0], 'total_units') else None,
                        "built_year": building_info[0].built_year,
                        "built_month": building_info[0].built_month,
                        "property_count": building_info[1] or 0
                    })
            
            if len(component_buildings) > 1:
                # 類似度マトリックスを作成して最適なプライマリを選択
                # 他のすべての建物との平均類似度が最も高い建物をプライマリとする
                best_primary_id = None
                best_avg_similarity = -1
                
                for building in component_buildings:
                    total_sim = 0
                    count = 0
                    for other_building in component_buildings:
                        if building["id"] != other_building["id"]:
                            sim = similarity_graph.get(building["id"], {}).get(other_building["id"], 0)
                            total_sim += sim
                            count += 1
                    
                    if count > 0:
                        avg_sim = total_sim / count
                        # 平均類似度が同じ場合は物件数を考慮
                        if avg_sim > best_avg_similarity or (avg_sim == best_avg_similarity and building["property_count"] > component_buildings[0]["property_count"]):
                            best_avg_similarity = avg_sim
                            best_primary_id = building["id"]
                
                # 最適なプライマリを設定（見つからない場合は物件数が最多のものを使用）
                if best_primary_id:
                    primary = next(b for b in component_buildings if b["id"] == best_primary_id)
                    other_buildings = [b for b in component_buildings if b["id"] != best_primary_id]
                else:
                    # 物件数が最も多い建物をprimaryとする（フォールバック）
                    component_buildings.sort(key=lambda x: x["property_count"], reverse=True)
                    primary = component_buildings[0]
                    other_buildings = component_buildings[1:]
                
                candidates = []
                
                # 他の建物をcandidatesとして追加（類似度の高い順）
                for building in other_buildings:
                    # グラフから類似度を取得
                    similarity = similarity_graph.get(primary["id"], {}).get(building["id"], 0)
                    building["similarity"] = round(similarity, 3)
                    building["is_excluded"] = False
                    candidates.append(building)
                
                # 類似度でソート（高い順）
                candidates.sort(key=lambda x: -x["similarity"])
                
                duplicate_groups.append({
                    "primary": primary,
                    "candidates": candidates,
                    "total_candidates": len(candidates),
                    "excluded_count": 0,
                    "group_info": f"推移的グループ: 合計{len(component_buildings)}件の建物"
                })
    
    phase_times['connected_components'] = time.time() - phase_start
    phase_times['duplicate_detection'] = phase_times['similarity_graph_build'] + phase_times['connected_components']
    phase_times['avg_candidate_fetch'] = sum(candidate_fetch_times) / len(candidate_fetch_times) if candidate_fetch_times else 0
    phase_times['avg_similarity_calc'] = sum(similarity_calc_times) / len(similarity_calc_times) if similarity_calc_times else 0
    phase_times['total_buildings_processed'] = len(candidate_fetch_times)
    
    # 重複グループを信頼度でソート（高信頼度のものを優先）
    # 属性が完全に一致する建物（住所、階数、戸数、築年が同じ）を優先
    def calculate_group_confidence(group):
        """グループの信頼度スコアを計算"""
        primary = group["primary"]
        candidates = group.get("candidates", [])
        
        if not candidates:
            return 0
        
        # 基本スコア（類似度の平均）
        avg_similarity = sum(c.get("similarity", 0) for c in candidates) / len(candidates) if candidates else 0
        base_score = avg_similarity
        
        # 属性一致ボーナス
        attribute_bonus = 0
        for candidate in candidates:
            # 属性一致のカウント（住所は部分一致も考慮）
            matches = 0
            
            # 住所の比較（丁目レベルまでの一致を確認）
            primary_addr = primary.get("address", "")
            candidate_addr = candidate.get("address", "")
            if primary_addr and candidate_addr:
                import re
                # 住所から丁目部分までを抽出（例：東京都港区愛宕１ → 東京都港区愛宕）
                # パターン: 最後の数字部分（丁目）を除去
                def extract_district(addr):
                    # 末尾の数字、ハイフン、漢数字等を除去
                    # 例: "愛宕１" → "愛宕", "西新宿３-１６-３３" → "西新宿"
                    match = re.match(r'^(.*?[区市町村][^0-9０-９一二三四五六七八九十\-－]*)', addr)
                    if match:
                        return match.group(1)
                    # 区市町村が見つからない場合は、最後の数字より前を取る
                    match = re.match(r'^(.*?)[\d０-９一二三四五六七八九十\-－]', addr)
                    if match:
                        return match.group(1)
                    return addr
                
                primary_district = extract_district(primary_addr)
                candidate_district = extract_district(candidate_addr)
                
                # 完全一致または地区レベルで一致する場合
                if primary_addr == candidate_addr or primary_district == candidate_district:
                    matches += 1
            
            # 階数の一致
            if (primary.get("total_floors") and 
                primary.get("total_floors") == candidate.get("total_floors")):
                matches += 1
            
            # 戸数の一致
            if (primary.get("total_units") and 
                primary.get("total_units") == candidate.get("total_units")):
                matches += 1
            
            # 築年の一致（±1年の誤差を許容）
            if (primary.get("built_year") and candidate.get("built_year") and
                abs(primary.get("built_year") - candidate.get("built_year")) <= 1):
                matches += 1
            
            # 4つすべて一致は最高優先度
            if matches == 4:
                attribute_bonus = max(attribute_bonus, 1.5)  # 完全一致は最高優先度
            # 3つの属性が一致
            elif matches >= 3:
                attribute_bonus = max(attribute_bonus, 0.8)
            # 2つの属性が一致
            elif matches >= 2:
                attribute_bonus = max(attribute_bonus, 0.3)
        
        # 物件数ボーナス（多い方が信頼度高い）
        property_bonus = min(primary.get("property_count", 0) / 100, 0.2)
        
        return base_score + attribute_bonus + property_bonus
    
    # 信頼度でソート（降順）、同じ信頼度の場合は建物名→建物IDで安定ソート
    duplicate_groups.sort(
        key=lambda g: (
            -calculate_group_confidence(g),  # 信頼度（降順）
            g.get("primary", {}).get("normalized_name", ""),  # 建物名（昇順）
            g.get("primary", {}).get("id", 0)  # 建物ID（昇順）
        )
    )
    
    # 結果を返す
    result = {
        "duplicate_groups": duplicate_groups[:limit],
        "total_groups": len(duplicate_groups),
        "processing_time": f"{time.time() - start_time:.2f}秒",
        "building_count": len(buildings_with_count),
        "phase_times": phase_times
    }
    
    # 処理時間のログ出力
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"建物重複候補取得: 処理時間={time.time() - start_time:.2f}秒, 建物数={len(buildings_with_count)}, グループ数={len(duplicate_groups)}")
    logger.info(f"フェーズ別時間: {phase_times}")
    
    return result



@router.get("/duplicate-properties")
def get_duplicate_properties(
    min_similarity: float = 0.8,
    limit: int = 50,
    offset: int = 0,
    building_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """重複候補の物件グループを取得（最適化版v3 - 単一クエリ実行）"""
    
    import time
    start_time = time.time()
    
    # 1. 除外ペアを効率的にセットで管理
    exclusion_set = set()
    exclusions = db.query(PropertyMergeExclusion.property1_id, PropertyMergeExclusion.property2_id).all()
    for ex in exclusions:
        exclusion_set.add((ex.property1_id, ex.property2_id))
        exclusion_set.add((ex.property2_id, ex.property1_id))
    
    # 2. 建物名フィルタの準備
    building_ids = None
    if building_name:
        # BuildingListingNameを使用した検索
        from ...models import BuildingListingName
        from ...scrapers.data_normalizer import canonicalize_building_name
        
        # 検索語を正規化
        canonical_search = canonicalize_building_name(building_name)
        
        # BuildingListingNameから該当する建物IDを取得
        matching_listing_ids = db.query(BuildingListingName.building_id).filter(
            BuildingListingName.canonical_name.ilike(f"%{canonical_search}%")
        ).distinct()
        
        # Building.normalized_name または BuildingListingNameでマッチ
        building_ids = [b.id for b in db.query(Building.id).filter(
            or_(
                Building.normalized_name.ilike(f"%{building_name}%"),
                Building.id.in_(matching_listing_ids.subquery())
            )
        ).all()]
        
        if not building_ids:
            return {"groups": [], "total": 0, "offset": offset, "limit": limit}
    
    # 3. 単一のクエリで全ての重複候補を取得（最適化の核心）
    # SQLで正規化処理も含めて実行し、N+1問題を解決
    query = text("""
        WITH active_listings AS (
            -- アクティブな掲載情報のみを対象
            SELECT DISTINCT master_property_id 
            FROM property_listings 
            WHERE is_active = true
        ),
        candidate_properties AS (
            -- 重複候補となる物件（アクティブな掲載あり）
            -- 片方のみ部屋番号がある場合も重複候補として検出
            SELECT 
                mp.*,
                b.normalized_name as building_name
            FROM master_properties mp
            INNER JOIN buildings b ON mp.building_id = b.id
            WHERE 
                mp.id IN (SELECT master_property_id FROM active_listings)
                AND (:building_ids IS NULL OR mp.building_id = ANY(:building_ids))
        ),
        property_groups AS (
            -- 同じ属性でグループ化（階数、面積）
            -- 方角と間取りは類似していれば重複候補とする
            -- 部屋番号の有無も考慮しない
            SELECT 
                building_id,
                floor_number,
                -- 面積を1㎡単位で丸める（40.03と40.3を同じグループにするため）
                ROUND(CAST(area AS NUMERIC)) as rounded_area,
                -- 間取りの基本部分を抽出して正規化
                -- 例: 2LDK+S → 2LDK, 3SLDK → 3LDK, 1DK → 1DK, 3LD → 3LDK
                CASE 
                    WHEN layout ~ '^[0-9]+S\+S$' THEN layout  -- 特殊ケース: 1S+S等はそのまま
                    ELSE REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(layout, '\+[A-Z]+', '', 'g'),  -- +S, +WIC等を除去
                                '([0-9]+)S(LDK|DK|K)', '\1\2', 'g'  -- SLDK → LDK, SDK → DK
                            ),
                            '([0-9]+)LD$', '\1LDK', 'g'  -- LD → LDK
                        ),
                        '([0-9]+)K$', '\1DK', 'g'  -- K → DK
                    )
                END as base_layout,
                building_name,
                COUNT(*) as property_count,
                ARRAY_AGG(id ORDER BY created_at) as property_ids,
                ARRAY_AGG(room_number) as room_numbers,
                ARRAY_AGG(area) as areas,
                ARRAY_AGG(layout) as layouts,
                ARRAY_AGG(direction) as directions
            FROM candidate_properties
            GROUP BY 
                building_id,
                floor_number,
                ROUND(CAST(area AS NUMERIC)),
                CASE 
                    WHEN layout ~ '^[0-9]+S\+S$' THEN layout
                    ELSE REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(layout, '\+[A-Z]+', '', 'g'),
                                '([0-9]+)S(LDK|DK|K)', '\1\2', 'g'
                            ),
                            '([0-9]+)LD$', '\1LDK', 'g'
                        ),
                        '([0-9]+)K$', '\1DK', 'g'
                    )
                END,
                building_name
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 200
        )
        SELECT 
            pg.*,
            (
                SELECT JSON_AGG(prop_data ORDER BY prop_data->>'listing_count' DESC, prop_data->>'id')
                FROM (
                    SELECT 
                        JSON_BUILD_OBJECT(
                            'id', mp.id,
                            'room_number', mp.room_number,
                            'area', mp.area,
                            'layout', mp.layout,
                            'direction', mp.direction,
                            'current_price', COALESCE(
                                MODE() WITHIN GROUP (ORDER BY pl.current_price),
                                MIN(pl.current_price)
                            ),
                            'listing_count', COUNT(pl.id)::text
                        ) as prop_data
                    FROM master_properties mp
                    LEFT JOIN property_listings pl ON mp.id = pl.master_property_id AND pl.is_active = true
                    WHERE mp.id = ANY(pg.property_ids)
                    GROUP BY mp.id, mp.room_number, mp.area, mp.layout, mp.direction
                ) as subquery
            ) as property_details
        FROM property_groups pg
    """)
    
    results = db.execute(query, {
        "building_ids": building_ids
    }).fetchall()
    
    # 4. 結果を処理（除外ペアのチェックと正規化）
    duplicate_groups = []
    
    for row in results:
        # property_idsを取得
        property_ids = row.property_ids if row.property_ids else []
        
        # 除外ペアのチェック（効率化）
        has_exclusion = False
        for i, id1 in enumerate(property_ids):
            for id2 in property_ids[i+1:]:
                if (id1, id2) in exclusion_set:
                    has_exclusion = True
                    break
            if has_exclusion:
                break
        
        if has_exclusion:
            continue
        
        # property_detailsが正しくパースされているか確認
        property_details = row.property_details if row.property_details else []
        
        duplicate_groups.append({
            "group_id": f"group_{len(duplicate_groups) + 1}",
            "property_count": row.property_count,
            "building_name": row.building_name,
            "floor_number": row.floor_number,
            "layout": row.base_layout if hasattr(row, 'base_layout') else None,
            "direction": None,  # 方角は個別物件で異なる可能性があるため省略
            "area": float(row.rounded_area) if row.rounded_area else None,
            "properties": property_details
        })
    
    # 5. ページング処理
    total = len(duplicate_groups)
    paginated_groups = duplicate_groups[offset:offset + limit]
    
    elapsed_time = time.time() - start_time
    
    return {
        "groups": paginated_groups,
        "total": total,
        "offset": offset,
        "limit": limit,
        "processing_time": f"{elapsed_time:.2f}秒",
        "optimization": "v3_single_query"
    }



@router.get("/properties/search")
def search_properties_for_merge(
    query: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """物件をIDまたは建物名で検索（統合用）"""
    results = []
    
    # まずIDで検索を試みる
    if query.isdigit():
        property_id = int(query)
        property_data = db.query(MasterProperty).filter(
            MasterProperty.id == property_id
        ).first()
        
        if property_data:
            building = db.query(Building).filter(
                Building.id == property_data.building_id
            ).first()
            
            # アクティブな掲載情報を取得
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id,
                PropertyListing.is_active == True
            ).all()
            
            # 最低価格を取得
            min_price = None
            if active_listings:
                prices = [l.current_price for l in active_listings if l.current_price]
                if prices:
                    min_price = min(prices)
            
            results.append({
                "id": property_data.id,
                "building_id": property_data.building_id,
                "building_name": building.normalized_name if building else "不明",
                "room_number": property_data.room_number,
                "floor_number": property_data.floor_number,
                "area": property_data.area,
                "layout": property_data.layout,
                "direction": property_data.direction,
                "current_price": min_price,
                "listing_count": len(active_listings)
            })
    
    # 建物名で検索（BuildingListingName対応）
    from ...models import BuildingListingName
    from ...scrapers.data_normalizer import canonicalize_building_name
    
    # 検索語を正規化
    canonical_search = canonicalize_building_name(query)
    
    # BuildingListingNameから該当する建物IDを取得
    matching_building_ids = db.query(BuildingListingName.building_id).filter(
        BuildingListingName.canonical_name.ilike(f"%{canonical_search}%")
    ).distinct().subquery()
    
    # Building.normalized_name または BuildingListingNameでマッチ
    name_query = db.query(MasterProperty).join(
        Building, MasterProperty.building_id == Building.id
    ).filter(
        or_(
            Building.normalized_name.ilike(f"%{query}%"),
            Building.id.in_(matching_building_ids)
        )
    )
    
    properties = name_query.limit(limit).all()
    
    for property_data in properties:
        # 既にIDで見つかった物件は除外
        if not any(r["id"] == property_data.id for r in results):
            building = db.query(Building).filter(
                Building.id == property_data.building_id
            ).first()
            
            # アクティブな掲載情報を取得
            active_listings = db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_data.id,
                PropertyListing.is_active == True
            ).all()
            
            # 最低価格を取得
            min_price = None
            if active_listings:
                prices = [l.current_price for l in active_listings if l.current_price]
                if prices:
                    min_price = min(prices)
            
            results.append({
                "id": property_data.id,
                "building_id": property_data.building_id,
                "building_name": building.normalized_name if building else "不明",
                "room_number": property_data.room_number,
                "floor_number": property_data.floor_number,
                "area": property_data.area,
                "layout": property_data.layout,
                "direction": property_data.direction,
                "current_price": min_price,
                "listing_count": len(active_listings)
            })
    
    return {"properties": results, "total": len(results)}


@router.post("/move-property-to-building")
def move_property_to_building(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """物件を別の建物に移動"""
    property_id = request.get("property_id")
    target_building_id = request.get("target_building_id")
    
    if not property_id or not target_building_id:
        raise HTTPException(status_code=400, detail="property_id and target_building_id are required")
    
    # 物件を取得
    property_obj = db.query(MasterProperty).filter(MasterProperty.id == property_id).first()
    if not property_obj:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # 移動先の建物を取得
    target_building = db.query(Building).filter(Building.id == target_building_id).first()
    if not target_building:
        raise HTTPException(status_code=404, detail="Target building not found")
    
    # 元の建物IDを記録
    original_building_id = property_obj.building_id
    
    if original_building_id == target_building_id:
        raise HTTPException(status_code=400, detail="Property is already in the target building")
    
    try:
        # 移動先に同じ物件が既に存在するかチェック
        existing_property = db.query(MasterProperty).filter(
            MasterProperty.building_id == target_building_id,
            MasterProperty.floor_number == property_obj.floor_number,
            MasterProperty.area == property_obj.area,
            MasterProperty.layout == property_obj.layout,
            MasterProperty.direction == property_obj.direction,
            MasterProperty.id != property_id
        ).first()
        
        if existing_property:
            # 重複物件が存在する場合の処理
            # 掲載情報を既存の物件に移動
            db.query(PropertyListing).filter(
                PropertyListing.master_property_id == property_id
            ).update({
                "master_property_id": existing_property.id
            })
            
            # 移動元の物件を削除
            db.delete(property_obj)
            moved_property_id = existing_property.id
            message = f"物件を移動し、重複物件と統合しました（物件ID: {property_id} → {existing_property.id}）"
        else:
            # 重複がない場合は通常の移動
            property_obj.building_id = target_building_id
            moved_property_id = property_id
            message = f"物件を建物ID {original_building_id} から {target_building_id} に移動しました"
        
        db.flush()
        
        # BuildingListingNameテーブルを更新（物件分離）
        listing_name_manager = BuildingListingNameManager(db)
        listing_name_manager.update_from_property_split(
            original_property_id=property_id,
            new_property_id=moved_property_id,
            new_building_id=target_building_id
        )
        
        # 多数決による建物情報の更新
        updater = MajorityVoteUpdater(db)
        
        # 元の建物の情報を更新（物件が減ったため）
        if original_building_id:
            original_building = db.query(Building).filter(Building.id == original_building_id).first()
            if original_building:
                updater.update_building_by_majority(original_building)
        
        # 移動先の建物の情報を更新（物件が増えたため）
        target_building_obj = db.query(Building).filter(Building.id == target_building_id).first()
        if target_building_obj:
            updater.update_building_by_majority(target_building_obj)
        
        # 移動した物件の最初の掲載日と価格改定日を更新
        from ...utils.property_utils import update_earliest_listing_date, update_latest_price_change
        update_earliest_listing_date(db, moved_property_id)
        update_latest_price_change(db, moved_property_id)
        
        db.commit()
        
        # 結果を返す
        return {
            "success": True,
            "message": message,
            "moved_property_id": moved_property_id,
            "original_building_id": original_building_id,
            "target_building_id": target_building_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/merge-buildings")
async def merge_buildings(
    request: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """複数の建物を統合（admin_old.pyと互換性のある実装）"""
    
    # リクエストの形式を判定
    if "primary_id" in request and "secondary_ids" in request:
        # 複数建物の統合（旧形式）
        primary_id = request.get("primary_id")
        secondary_ids = request.get("secondary_ids", [])
        
        if not primary_id or not secondary_ids:
            raise HTTPException(status_code=400, detail="primary_id and secondary_ids are required")
        
        # 主建物を取得
        primary = db.query(Building).filter(Building.id == primary_id).first()
        if not primary:
            # 統合履歴を確認
            merge_history = db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.merged_building_id == primary_id
            ).order_by(BuildingMergeHistory.merged_at.desc()).first()
            
            if merge_history:
                primary_building = db.query(Building).filter(
                    Building.id == merge_history.primary_building_id
                ).first()
                if primary_building:
                    error_message = f"統合先として指定された建物ID {primary_id} は既に建物「{primary_building.normalized_name}」(ID: {primary_building.id})に統合済みです。\n画面を更新して最新の状態を確認してください。"
                else:
                    error_message = f"統合先として指定された建物ID {primary_id} は既に他の建物に統合済みです。\n画面を更新して最新の状態を確認してください。"
            else:
                error_message = f"統合先として指定された建物ID {primary_id} が見つかりません。\n画面を更新して最新の状態を確認してください。"
            
            raise HTTPException(status_code=404, detail=error_message)
        
        # 副建物を取得
        secondary_buildings = db.query(Building).filter(Building.id.in_(secondary_ids)).all()
        if len(secondary_buildings) != len(secondary_ids):
            found_ids = [b.id for b in secondary_buildings]
            missing_ids = [sid for sid in secondary_ids if sid not in found_ids]
            
            # より詳細なエラーメッセージを生成
            error_details = []
            for missing_id in missing_ids:
                # 統合履歴を確認
                merge_history = db.query(BuildingMergeHistory).filter(
                    BuildingMergeHistory.merged_building_id == missing_id
                ).order_by(BuildingMergeHistory.merged_at.desc()).first()
                
                if merge_history:
                    primary_building = db.query(Building).filter(
                        Building.id == merge_history.primary_building_id
                    ).first()
                    if primary_building:
                        error_details.append(
                            f"建物ID {missing_id} は既に建物「{primary_building.normalized_name}」(ID: {primary_building.id})に統合済みです"
                        )
                    else:
                        error_details.append(
                            f"建物ID {missing_id} は既に他の建物に統合済みです"
                        )
                else:
                    error_details.append(
                        f"建物ID {missing_id} が見つかりません（削除された可能性があります）"
                    )
            
            error_message = "以下の建物は統合できません：\n" + "\n".join(error_details)
            error_message += "\n\n画面を更新して最新の状態を確認してください。"
            
            raise HTTPException(
                status_code=404, 
                detail=error_message
            )
    elif "primary_building_id" in request and "secondary_building_id" in request:
        # 単一建物の統合（新形式）
        primary_id = request.get("primary_building_id")
        secondary_id = request.get("secondary_building_id")
        
        primary = db.query(Building).filter(Building.id == primary_id).first()
        secondary = db.query(Building).filter(Building.id == secondary_id).first()
        
        if not primary or not secondary:
            raise HTTPException(status_code=404, detail="Building not found")
        
        secondary_buildings = [secondary]
    else:
        raise HTTPException(status_code=400, detail="Invalid request format")
    
    # 複数の建物を統合
    try:
        merged_count = 0
        moved_properties = 0
        building_infos = []
        duplicate_properties_merged = 0  # 統合された重複物件数
        duplicate_merge_details = []  # 重複物件統合の詳細
        
        for secondary_building in secondary_buildings:
            # 統合履歴を記録（詳細情報を含む）
            merge_details = {
                "merged_buildings": [{
                    "id": secondary_building.id,
                    "normalized_name": secondary_building.normalized_name,
                    "address": secondary_building.address,
                    "total_floors": secondary_building.total_floors,
                    "built_year": secondary_building.built_year,
                    "construction_type": secondary_building.construction_type if hasattr(secondary_building, 'construction_type') else None,
                    "property_ids": [],  # 後で追加
                    "properties_moved": 0  # 後で更新
                }]
            }
            
            merge_history = BuildingMergeHistory(
                primary_building_id=primary_id,
                merged_building_id=secondary_building.id,
                merged_building_name=secondary_building.normalized_name,
                canonical_merged_name=secondary_building.canonical_name,
                merge_details=merge_details,  # 詳細情報を保存
                merged_at=datetime.now(),
                merged_by="admin"
            )
            db.add(merge_history)
            
            # 物件を移動
            properties_to_move = db.query(MasterProperty).filter(
                MasterProperty.building_id == secondary_building.id
            ).all()
            
            property_ids_moved = []
            for prop in properties_to_move:
                # PropertyMergeHistoryの参照は更新しない（履歴は保持）
                # 物件を新しい建物に移動
                prop.building_id = primary_id
                moved_properties += 1
                property_ids_moved.append(prop.id)
            
            # merge_detailsに物件IDを記録
            merge_history.merge_details["merged_buildings"][0]["property_ids"] = property_ids_moved
            merge_history.merge_details["merged_buildings"][0]["properties_moved"] = len(property_ids_moved)
            
            # 外部IDを移動（重複がある場合は削除）
            external_ids_to_move = db.query(BuildingExternalId).filter(
                BuildingExternalId.building_id == secondary_building.id
            ).all()
            
            for ext_id in external_ids_to_move:
                # 同じ外部IDが既に主建物に存在するか確認
                existing = db.query(BuildingExternalId).filter(
                    BuildingExternalId.building_id == primary_id,
                    BuildingExternalId.source_site == ext_id.source_site,
                    BuildingExternalId.external_id == ext_id.external_id
                ).first()
                
                if existing:
                    # 重複する場合は削除
                    db.delete(ext_id)
                else:
                    # 重複しない場合は移動
                    ext_id.building_id = primary_id
            
            # 変更をフラッシュ（物件と外部IDの移動を確実に反映）
            db.flush()
            
            # 建物情報を保存（レスポンス用）
            building_infos.append({
                "id": secondary_building.id,
                "name": secondary_building.normalized_name,
                "properties_moved": len(properties_to_move)
            })
            
            # 既存の統合履歴の参照を更新（この建物が他の統合履歴で参照されている場合）
            db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.primary_building_id == secondary_building.id
            ).update({
                "primary_building_id": primary_id
            })
            
            # direct_primary_building_idの参照も更新
            db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.direct_primary_building_id == secondary_building.id
            ).update({
                "direct_primary_building_id": primary_id
            })
            
            # final_primary_building_idの参照も更新
            db.query(BuildingMergeHistory).filter(
                BuildingMergeHistory.final_primary_building_id == secondary_building.id
            ).update({
                "final_primary_building_id": primary_id
            })
            
            # ambiguous_property_matchesテーブルのbuilding_id参照を更新
            from sqlalchemy import text
            db.execute(
                text("""
                    UPDATE ambiguous_property_matches 
                    SET building_id = :primary_id 
                    WHERE building_id = :secondary_id
                """),
                {"primary_id": primary_id, "secondary_id": secondary_building.id}
            )
            
            # 建物除外テーブルの参照を削除または更新
            # building1_idとして参照されている場合
            db.query(BuildingMergeExclusion).filter(
                BuildingMergeExclusion.building1_id == secondary_building.id
            ).delete()
            
            # building2_idとして参照されている場合
            db.query(BuildingMergeExclusion).filter(
                BuildingMergeExclusion.building2_id == secondary_building.id
            ).delete()
            
            # 建物を削除
            db.delete(secondary_building)
            merged_count += 1
        
        # 全ての建物移動が完了した後、重複物件を検出して統合
        # 主建物内の全物件を取得
        all_properties = db.query(MasterProperty).filter(
            MasterProperty.building_id == primary_id
        ).order_by(
            MasterProperty.floor_number,
            MasterProperty.area,
            MasterProperty.layout,
            MasterProperty.direction,
            MasterProperty.created_at  # 古い物件を優先
        ).all()
        
        # 重複物件を検出（階数、面積、間取り、方角が同じ物件）
        seen_properties = {}  # キー: (floor, area, layout, direction), 値: primary_property
        properties_to_merge = []  # [(primary_id, secondary_id), ...]
        
        for prop in all_properties:
            # 重複判定のキーを作成（面積は0.5㎡の誤差を考慮）
            # 面積を0.5㎡単位に丸める
            rounded_area = round(prop.area * 2) / 2 if prop.area else None
            # 間取りと方角を正規化
            normalized_layout = normalize_layout(prop.layout) if prop.layout else None
            normalized_direction = normalize_direction(prop.direction) if prop.direction else None
            
            key = (
                prop.floor_number,
                rounded_area,
                normalized_layout,
                normalized_direction
            )
            
            if key in seen_properties:
                # 重複物件が見つかった
                primary_prop = seen_properties[key]
                
                # 部屋番号の処理
                # 優先順位: 1. 両方あるなら異なる場合はスキップ 2. 片方のみある場合は統合 3. 両方ない場合は統合
                if primary_prop.room_number and prop.room_number:
                    if primary_prop.room_number != prop.room_number:
                        # 部屋番号が異なるので別物件として扱う
                        continue
                
                properties_to_merge.append((primary_prop.id, prop.id))
            else:
                seen_properties[key] = prop
        
        # 重複物件を統合
        for primary_prop_id, secondary_prop_id in properties_to_merge:
            try:
                # 掲載情報を移動
                listings_moved = db.query(PropertyListing).filter(
                    PropertyListing.master_property_id == secondary_prop_id
                ).update({
                    "master_property_id": primary_prop_id
                })
                
                # ambiguous_property_matchesテーブルの参照を更新
                db.execute(
                    text("""
                        UPDATE ambiguous_property_matches 
                        SET selected_property_id = :primary_id 
                        WHERE selected_property_id = :secondary_id
                    """),
                    {"primary_id": primary_prop_id, "secondary_id": secondary_prop_id}
                )
                
                # ambiguous_property_matchesのJSON配列を更新
                # この処理は複雑なので、一旦削除された物件IDを持つレコードを取得してPython側で処理
                ambiguous_matches = db.execute(
                    text("""
                        SELECT id, candidate_property_ids 
                        FROM ambiguous_property_matches 
                        WHERE candidate_property_ids::text LIKE :pattern
                    """),
                    {"pattern": f"%{secondary_prop_id}%"}
                ).fetchall()
                
                for match in ambiguous_matches:
                    candidate_ids = match.candidate_property_ids if match.candidate_property_ids else []
                    # 削除対象IDを主物件IDに置き換える
                    new_candidates = []
                    for cid in candidate_ids:
                        if cid == secondary_prop_id:
                            if primary_prop_id not in new_candidates:
                                new_candidates.append(primary_prop_id)
                        else:
                            if cid not in new_candidates:
                                new_candidates.append(cid)
                    
                    # 更新
                    if new_candidates != candidate_ids:
                        db.execute(
                            text("""
                                UPDATE ambiguous_property_matches 
                                SET candidate_property_ids = :candidates 
                                WHERE id = :match_id
                            """),
                            {"candidates": json.dumps(new_candidates), "match_id": match.id}
                        )
                
                # 建物統合による自動統合は履歴に記録しない
                # （スクレイピング時の自動紐付けと同様の扱い）
                
                # 統合詳細を記録
                secondary_prop = db.query(MasterProperty).filter(
                    MasterProperty.id == secondary_prop_id
                ).first()
                
                if secondary_prop:
                    duplicate_merge_details.append({
                        "primary_id": primary_prop_id,
                        "secondary_id": secondary_prop_id,
                        "floor": secondary_prop.floor_number,
                        "area": secondary_prop.area,
                        "layout": secondary_prop.layout,
                        "direction": secondary_prop.direction,
                        "listings_moved": listings_moved
                    })
                    
                    # PropertyMergeHistoryから参照されているかチェック
                    is_referenced = db.query(PropertyMergeHistory).filter(
                        or_(
                            PropertyMergeHistory.primary_property_id == secondary_prop_id,
                            PropertyMergeHistory.direct_primary_property_id == secondary_prop_id,
                            PropertyMergeHistory.final_primary_property_id == secondary_prop_id
                        )
                    ).first()
                    
                    if not is_referenced:
                        # 参照されていない場合のみ削除
                        db.delete(secondary_prop)
                        duplicate_properties_merged += 1
                    else:
                        # 参照されている場合はログを出力（削除しない）
                        import logging
                        logging.info(f"物件ID {secondary_prop_id} はPropertyMergeHistoryから参照されているため削除をスキップ")
                    
            except Exception as e:
                # 個別のエラーはログに記録して続行
                import logging
                logging.error(f"物件統合エラー: primary={primary_prop_id}, secondary={secondary_prop_id}, error={e}")
                continue
        
        # 多数決で建物情報を更新
        updater = MajorityVoteUpdater(db)
        primary_building = db.query(Building).filter(Building.id == primary_id).first()
        if primary_building:
            updater.update_building_by_majority(primary_building)
        
        # BuildingListingNameテーブルを更新
        listing_name_manager = BuildingListingNameManager(db)
        for secondary_building in secondary_buildings:
            listing_name_manager.update_from_building_merge(
                primary_building_id=primary_id,
                secondary_building_id=secondary_building.id
            )
        
        db.commit()
        
        # 重複候補リストが変更される可能性があるため再計算を促す
        clear_duplicate_buildings_cache()
        
        return {
            "merged_count": merged_count,
            "moved_properties": moved_properties,
            "primary_building": {
                "id": primary.id,
                "normalized_name": primary.normalized_name,
                "address": primary.address if hasattr(primary, 'address') else None,
                "property_count": db.query(MasterProperty).filter(
                    MasterProperty.building_id == primary_id
                ).count()
            },
            "message": f"{merged_count}件の建物を統合し、{moved_properties}件の物件を処理しました。" + (f"{duplicate_properties_merged}件の重複物件を自動統合しました。" if duplicate_properties_merged > 0 else ""),
            "merged_buildings": building_infos,
            "duplicate_properties_merged": duplicate_properties_merged,
            "duplicate_merge_details": duplicate_merge_details if duplicate_properties_merged > 0 else []
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/revert-building-merge/{history_id}")
async def revert_building_merge(
    history_id: int,
    db: Session = Depends(get_db)
):
    """統合を取り消す（建物を復元）"""
    history = db.query(BuildingMergeHistory).filter(
        BuildingMergeHistory.id == history_id
    ).first()
    
    if not history:
        raise HTTPException(status_code=404, detail="統合履歴が見つかりません")
    
    # merge_detailsがない場合は基本情報から復元
    if not history.merge_details:
        # 旧形式の履歴の場合、最小限の情報で復元を試みる
        # merged_building_idが存在するか確認
        if not history.merged_building_id:
            raise HTTPException(
                status_code=400,
                detail="統合履歴に必要な情報がないため、取り消しできません。"
            )
        
        # 簡易的なmerge_detailsを作成
        history.merge_details = {
            "merged_buildings": [{
                "id": history.merged_building_id,
                "normalized_name": history.merged_building_name or f"建物{history.merged_building_id}",
                "address": None,
                "total_floors": None,
                "built_year": None,
                "construction_type": None,
                "property_ids": [],
                "properties_moved": 0
            }]
        }
    
    # 建物が既に存在するかどうかで取り消し済みかを判断
    for merged_building in history.merge_details.get("merged_buildings", []):
        existing = db.query(Building).filter(Building.id == merged_building["id"]).first()
        if existing:
            raise HTTPException(status_code=400, detail="既に取り消し済みです（建物が既に存在します）")
    
    try:
        # 主建物の存在確認
        primary_building = db.query(Building).filter(
            Building.id == history.primary_building_id
        ).first()
        
        if not primary_building:
            raise HTTPException(status_code=404, detail="主建物が見つかりません")
        
        # 統合時の詳細情報から建物を復元
        restored_count = 0
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            
            # 既に存在するかチェック
            existing = db.query(Building).filter(Building.id == building_id).first()
            if existing:
                continue
            
            # 建物を復元（読み仮名も生成）
            from ...utils.reading_generator import generate_reading
            building = Building(
                id=building_id,
                normalized_name=merged_building["normalized_name"],
                address=merged_building.get("address"),
                reading=generate_reading(merged_building["normalized_name"]),
                total_floors=merged_building.get("total_floors"),
                built_year=merged_building.get("built_year"),
                construction_type=merged_building.get("construction_type")
            )
            db.add(building)
            
            # この建物に移動された物件を元に戻す
            property_ids = merged_building.get("property_ids", [])
            if property_ids:
                existing_properties = db.query(MasterProperty).filter(
                    MasterProperty.id.in_(property_ids),
                    MasterProperty.building_id == history.primary_building_id
                ).all()
                
                for prop in existing_properties:
                    prop.building_id = building_id
            
            restored_count += 1
        
        # 統合時に作成された可能性のある除外ペアを削除
        merged_building_ids = [b["id"] for b in history.merge_details.get("merged_buildings", [])]
        for building_id in merged_building_ids:
            db.query(BuildingMergeExclusion).filter(
                or_(
                    and_(
                        BuildingMergeExclusion.building1_id == history.primary_building_id,
                        BuildingMergeExclusion.building2_id == building_id
                    ),
                    and_(
                        BuildingMergeExclusion.building1_id == building_id,
                        BuildingMergeExclusion.building2_id == history.primary_building_id
                    )
                )
            ).delete()
        
        # BuildingListingNameテーブルを更新（建物分離）
        listing_name_manager = BuildingListingNameManager(db)
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            property_ids = merged_building.get("property_ids", [])
            if property_ids:
                # 復元された建物に移動した物件のIDを渡して更新
                listing_name_manager.update_from_building_split(
                    original_building_id=history.primary_building_id,
                    new_building_id=building_id,
                    property_ids_to_move=property_ids
                )
        
        # 多数決による建物情報更新
        updater = MajorityVoteUpdater(db)
        
        # 主建物の全属性を更新
        if primary_building:
            updater.update_building_by_majority(primary_building)
        
        # 復元された建物の全属性も更新
        for merged_building in history.merge_details.get("merged_buildings", []):
            building_id = merged_building["id"]
            restored_building = db.query(Building).filter(Building.id == building_id).first()
            if restored_building:
                updater.update_building_by_majority(restored_building)
        
        # 履歴レコードを削除
        db.delete(history)
        
        db.commit()
        
        message = f"統合を取り消しました。{restored_count}件の建物を復元しました。"
        
        return {
            "success": True,
            "message": message,
            "restored_count": restored_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"取り消し中にエラーが発生しました: {str(e)}")


@router.post("/merge-properties")
async def merge_properties(
    request: PropertyMergeRequest,
    db: Session = Depends(get_db)
):
    """2つの物件を統合"""
    
    # 物件の存在確認
    primary = db.query(MasterProperty).filter(
        MasterProperty.id == request.primary_property_id
    ).first()
    secondary = db.query(MasterProperty).filter(
        MasterProperty.id == request.secondary_property_id
    ).first()
    
    if not primary and not secondary:
        raise HTTPException(
            status_code=404, 
            detail=f"Both properties not found: primary_id={request.primary_property_id}, secondary_id={request.secondary_property_id}"
        )
    elif not primary:
        raise HTTPException(
            status_code=404, 
            detail=f"Primary property not found: id={request.primary_property_id}"
        )
    elif not secondary:
        # 既に統合済みかチェック
        merge_history = db.query(PropertyMergeHistory).filter(
            PropertyMergeHistory.merged_property_id == request.secondary_property_id
        ).first()
        
        if merge_history:
            raise HTTPException(
                status_code=400,
                detail=f"Secondary property (id={request.secondary_property_id}) has already been merged into property id={merge_history.primary_property_id}"
            )
        else:
            raise HTTPException(
                status_code=404, 
                detail=f"Secondary property not found: id={request.secondary_property_id}"
            )
    
    # 二次物件の情報をバックアップ（取り消し用）
    secondary_backup = {
        "id": secondary.id,
        "building_id": secondary.building_id,
        "room_number": secondary.room_number,
        "floor_number": secondary.floor_number,
        "area": secondary.area,
        "balcony_area": secondary.balcony_area,
        "layout": secondary.layout,
        "direction": secondary.direction,

        "management_fee": secondary.management_fee,
        "repair_fund": secondary.repair_fund,
        "station_info": secondary.station_info,
        "parking_info": secondary.parking_info,
        "display_building_name": secondary.display_building_name,
        "created_at": secondary.created_at.isoformat() if secondary.created_at else None,
        "updated_at": secondary.updated_at.isoformat() if secondary.updated_at else None
    }
    
    # 掲載情報を移動
    listings_to_move = db.query(PropertyListing).filter(
        PropertyListing.master_property_id == request.secondary_property_id
    ).all()
    
    moved_count = 0
    moved_listings_info = []
    for listing in listings_to_move:
        # 移動前の情報を記録
        moved_listings_info.append({
            "listing_id": listing.id,
            "source_site": listing.source_site,
            "url": listing.url
        })
        listing.master_property_id = request.primary_property_id
        moved_count += 1
    
    # 統合履歴を記録（詳細情報を含む）
    merge_history = PropertyMergeHistory(
        primary_property_id=request.primary_property_id,
        merged_property_id=request.secondary_property_id,
        merge_details={
            "secondary_property": secondary_backup,
            "moved_listings": moved_listings_info
        },
        merged_at=datetime.now(),
        merged_by="admin"
    )
    db.add(merge_history)
    
    # ambiguous_property_matchesテーブルの参照を更新
    # 1. selected_property_idが削除対象の場合、主物件IDに更新
    db.execute(
        text("""
            UPDATE ambiguous_property_matches 
            SET selected_property_id = :primary_id 
            WHERE selected_property_id = :secondary_id
        """),
        {"primary_id": request.primary_property_id, "secondary_id": request.secondary_property_id}
    )
    
    # 2. candidate_property_idsから削除対象IDを除去し、主物件IDがなければ追加
    ambiguous_matches = db.execute(
        text("""
            SELECT id, candidate_property_ids 
            FROM ambiguous_property_matches 
            WHERE candidate_property_ids::text LIKE :pattern
        """),
        {"pattern": f"%{request.secondary_property_id}%"}
    ).fetchall()
    
    for match in ambiguous_matches:
        candidate_ids = match.candidate_property_ids if match.candidate_property_ids else []
        # 削除対象IDを除去
        if request.secondary_property_id in candidate_ids:
            candidate_ids.remove(request.secondary_property_id)
        # 主物件IDがなければ追加
        if request.primary_property_id not in candidate_ids:
            candidate_ids.append(request.primary_property_id)
        
        # 更新
        db.execute(
            text("""
                UPDATE ambiguous_property_matches 
                SET candidate_property_ids = :candidates 
                WHERE id = :match_id
            """),
            {"candidates": json.dumps(candidate_ids), "match_id": match.id}
        )
    
    # PropertyMergeHistoryの参照を更新（二次物件が他の統合履歴で参照されている場合）
    # primary_property_idとして参照されている場合、主物件IDに更新
    db.query(PropertyMergeHistory).filter(
        PropertyMergeHistory.primary_property_id == request.secondary_property_id
    ).update({
        "primary_property_id": request.primary_property_id
    })
    
    # direct_primary_property_idとして参照されている場合
    db.query(PropertyMergeHistory).filter(
        PropertyMergeHistory.direct_primary_property_id == request.secondary_property_id
    ).update({
        "direct_primary_property_id": request.primary_property_id
    })
    
    # final_primary_property_idとして参照されている場合
    db.query(PropertyMergeHistory).filter(
        PropertyMergeHistory.final_primary_property_id == request.secondary_property_id
    ).update({
        "final_primary_property_id": request.primary_property_id
    })
    
    # 変更を確実に反映させる
    db.flush()
    
    # 二次物件を削除
    db.delete(secondary)
    
    # 多数決で物件情報を更新
    updater = MajorityVoteUpdater(db)
    primary_property = db.query(MasterProperty).filter(
        MasterProperty.id == request.primary_property_id
    ).first()
    if primary_property:
        updater.update_master_property_by_majority(primary_property)
    
    # BuildingListingNameテーブルを更新
    listing_name_manager = BuildingListingNameManager(db)
    listing_name_manager.update_from_property_merge(
        primary_property_id=request.primary_property_id,
        secondary_property_id=request.secondary_property_id
    )
    
    # 両方の物件の最初の掲載日を更新
    update_earliest_listing_date(db, request.primary_property_id)
    # secondary_property_idの物件は削除されているが、念のため
    
    db.commit()
    
    return {
        "message": "Properties merged successfully",
        "moved_listings": moved_count,
        "primary_property": {
            "id": primary.id,
            "building_id": primary.building_id,
            "floor": primary.floor_number,
            "layout": primary.layout
        }
    }


@router.post("/exclude-building-merge")
async def exclude_building_merge(
    building1_id: int,
    building2_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """建物の統合を除外設定に追加"""
    
    # 既存の除外設定をチェック
    existing = db.query(BuildingMergeExclusion).filter(
        or_(
            and_(
                BuildingMergeExclusion.building1_id == building1_id,
                BuildingMergeExclusion.building2_id == building2_id
            ),
            and_(
                BuildingMergeExclusion.building1_id == building2_id,
                BuildingMergeExclusion.building2_id == building1_id
            )
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Exclusion already exists")
    
    # 除外設定を追加
    exclusion = BuildingMergeExclusion(
        building1_id=min(building1_id, building2_id),
        building2_id=max(building1_id, building2_id),
        reason=reason,
        created_at=datetime.now(),
        created_by="admin"
    )
    db.add(exclusion)
    db.commit()
    
    return {"message": "Exclusion added successfully"}


@router.post("/exclude-property-merge")
async def exclude_property_merge(
    property1_id: int,
    property2_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """物件の統合を除外設定に追加"""
    
    # 既存の除外設定をチェック
    existing = db.query(PropertyMergeExclusion).filter(
        or_(
            and_(
                PropertyMergeExclusion.property1_id == property1_id,
                PropertyMergeExclusion.property2_id == property2_id
            ),
            and_(
                PropertyMergeExclusion.property1_id == property2_id,
                PropertyMergeExclusion.property2_id == property1_id
            )
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Exclusion already exists")
    
    # 除外設定を追加
    exclusion = PropertyMergeExclusion(
        property1_id=min(property1_id, property2_id),
        property2_id=max(property1_id, property2_id),
        reason=reason,
        created_at=datetime.now(),
        created_by="admin"
    )
    db.add(exclusion)
    db.commit()
    
    return {"message": "Exclusion added successfully"}

