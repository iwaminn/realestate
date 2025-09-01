"""建物名検索の共通ユーティリティ"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy import or_, and_
from sqlalchemy.orm import Query
from .search_normalizer import (
    create_search_patterns, normalize_search_text
)


def create_building_search_filter(
    building_name: str,
    column_name: str = "normalized_name",
    table_alias: str = ""
) -> Tuple[List, Dict]:
    """
    建物名検索用のSQLAlchemyフィルター条件とパラメータを生成
    
    Args:
        building_name: 検索する建物名
        column_name: 検索対象のカラム名（デフォルト: normalized_name）
        table_alias: テーブルエイリアス（例: "b."）
        
    Returns:
        (conditions, params): フィルター条件のリストとパラメータの辞書
    """
    if not building_name:
        return [], {}
    
    # 検索パターンを生成
    search_patterns = create_search_patterns(building_name)
    
    # 検索文字列を正規化してAND検索用に分割
    normalized_search = normalize_search_text(building_name)
    search_terms = normalized_search.split()
    
    conditions = []
    
    # 複数の検索語がある場合
    if len(search_terms) > 1:
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                col = f"{table_alias}{column_name}" if table_alias else column_name
                term_conditions.append(f"{col}.ilike('%{pattern}%')")
            if term_conditions:
                and_conditions.append(f"({' OR '.join(term_conditions)})")
        
        if and_conditions:
            # 全ての検索語を含む（AND条件のみ）
            conditions.append(f"({' AND '.join(and_conditions)})")
    else:
        # 単一の検索語の場合
        for pattern in search_patterns:
            col = f"{table_alias}{column_name}" if table_alias else column_name
            conditions.append(f"{col}.ilike('%{pattern}%')")
    
    return conditions, {}


def create_building_search_params(building_name: str, param_prefix: str = "building_name") -> Tuple[List[str], Dict[str, str]]:
    """
    建物名検索用のパラメータ化されたSQL条件とパラメータを生成
    
    Args:
        building_name: 検索する建物名
        param_prefix: パラメータ名のプレフィックス
        
    Returns:
        (conditions, params): 条件文字列のリストとパラメータの辞書
    """
    if not building_name:
        return [], {}
    
    # 検索パターンを生成
    search_patterns = create_search_patterns(building_name)
    
    # 検索文字列を正規化してAND検索用に分割
    normalized_search = normalize_search_text(building_name)
    search_terms = normalized_search.split()
    
    all_conditions = []
    params = {}
    param_count = 0
    
    # 複数の検索語がある場合
    if len(search_terms) > 1:
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                param_name = f"{param_prefix}_{param_count}"
                term_conditions.append(f":{param_name}")
                params[param_name] = f"%{pattern}%"
                param_count += 1
            if term_conditions:
                and_conditions.append(f"({' OR '.join(term_conditions)})")
        
        if and_conditions:
            all_conditions.append(f"({' AND '.join(and_conditions)})")
    else:
        # 単一の検索語の場合
        for pattern in search_patterns:
            param_name = f"{param_prefix}_{param_count}"
            all_conditions.append(f":{param_name}")
            params[param_name] = f"%{pattern}%"
            param_count += 1
    
    return all_conditions, params


def apply_building_search_to_query(query, building_name: str, building_table):
    """
    SQLAlchemyクエリに建物名検索フィルターを適用
    
    Args:
        query: SQLAlchemyクエリオブジェクト
        building_name: 検索する建物名
        building_table: 建物テーブルのモデルクラス
        
    Returns:
        フィルター適用後のクエリ
    """
    if not building_name:
        return query
    
    # 検索パターンを生成
    search_patterns = create_search_patterns(building_name)
    
    # 検索文字列を正規化してAND検索用に分割
    normalized_search = normalize_search_text(building_name)
    search_terms = normalized_search.split()
    
    # 複数の検索語がある場合
    if len(search_terms) > 1:
        # AND条件（全ての単語を含む）
        and_conditions = []
        for term in search_terms:
            term_patterns = create_search_patterns(term)
            term_conditions = []
            for pattern in term_patterns:
                term_conditions.append(building_table.normalized_name.ilike(f"%{pattern}%"))
            if term_conditions:
                # 各検索語について、いずれかのパターンにマッチ
                and_conditions.append(or_(*term_conditions))
        
        if and_conditions:
            # 全ての検索語を含む（AND条件）
            query = query.filter(and_(*and_conditions))
    else:
        # 単一の検索語の場合
        search_conditions = []
        for pattern in search_patterns:
            search_conditions.append(building_table.normalized_name.ilike(f"%{pattern}%"))
        
        if search_conditions:
            query = query.filter(or_(*search_conditions))
    
    return query


def apply_building_name_filter_with_alias(
    query: Query,
    search_text: str,
    db_session,
    building_table,
    property_table=None,
    search_building_name: bool = True,
    search_property_display_name: bool = False,
    search_aliases: bool = True,
    exclude_building_id: Optional[int] = None
) -> Query:
    """
    建物名検索のフィルターを適用する共通関数（掲載情報ベース）
    
    Args:
        query: 既存のクエリオブジェクト
        search_text: 検索文字列（スペース区切りでAND検索）
        db_session: データベースセッション
        building_table: Buildingモデルクラス
        property_table: MasterPropertyモデルクラス（オプション）
        search_building_name: Building.normalized_nameを検索対象に含めるか
        search_property_display_name: MasterProperty.display_building_nameを検索対象に含めるか
        search_aliases: 掲載情報の建物名を検索対象に含めるか
        exclude_building_id: 除外する建物ID
    
    Returns:
        フィルターが適用されたクエリ
    """
    if not search_text:
        return query
    
    # BuildingListingNameテーブルを使用
    from ..models import BuildingListingName
    
    # スペース区切りでAND検索
    search_terms = search_text.strip().split()
    
    if not search_terms:
        return query
    
    # 検索語の正規化
    from ..scrapers.data_normalizer import normalize_building_name
    import re
    
    # 検索文字列を正規化して分割
    # 「白金ザ・スカイ」→「白金ザ スカイ」→ ['白金ザ', 'スカイ']
    # 「白金ザスカイ」の場合も考慮する
    normalized_search = normalize_building_name(search_text)
    search_terms = normalized_search.split()
    
    # 元の検索語にスペースがない場合、賢く分割する
    if not search_terms or len(search_terms) == 1:
        # カタカナと漢字の境界で分割を試みる
        # 「白金ザスカイ」→ ['白金', 'ザ', 'スカイ']
        original_term = search_terms[0] if search_terms else search_text
        
        # 漢字、カタカナ、ひらがな、英数字の塊で分割
        parts = re.findall(r'[一-龥]+|[ァ-ヴー]+|[ぁ-ん]+|[a-zA-Z0-9]+', original_term)
        
        if len(parts) > 1:
            # 複数パートに分かれた場合はそれぞれを検索語にする
            new_terms = []
            for part in parts:
                # カタカナの場合、「ザ」「ノ」「ガ」などの1〜2文字の助詞で始まるか確認
                if re.match(r'^[ァ-ヴー]+$', part) and len(part) > 2:
                    # 「ザスカイ」→「ザ」「スカイ」のように分割を試みる
                    if part[:1] in ['ザ', 'ノ', 'ガ', 'デ']:
                        new_terms.append(part[:1])  # 「ザ」
                        new_terms.append(part[1:])  # 「スカイ」
                    elif part[:2] in ['ザ・']:
                        new_terms.append(part[:2])
                        new_terms.append(part[2:])
                    else:
                        new_terms.append(part)
                else:
                    new_terms.append(part)
            search_terms = new_terms
    
    # 重複を除去
    search_terms = list(dict.fromkeys(search_terms))
    
    for term in search_terms:
        if not term:  # 空文字列をスキップ
            continue
        
        conditions = []
        
        # Building.normalized_nameでの検索（すでに正規化済みの名前同士で比較）
        if search_building_name:
            conditions.append(building_table.normalized_name.ilike(f"%{term}%"))
        
        # MasterProperty.display_building_nameでの検索
        if search_property_display_name and property_table:
            conditions.append(property_table.display_building_name.ilike(f"%{term}%"))
        
        # 掲載情報の建物名での検索（BuildingListingNameテーブル使用）
        if search_aliases:
            # 検索語をcanonical形式に変換
            from ..scrapers.data_normalizer import canonicalize_building_name
            canonical_term = canonicalize_building_name(term)
            
            listing_building_ids = db_session.query(
                BuildingListingName.building_id
            ).filter(
                # canonical_nameで検索（ひらがな→カタカナ変換済み）
                BuildingListingName.canonical_name.ilike(f"%{canonical_term}%")
            )
            
            # 現在の建物を除外
            if exclude_building_id:
                listing_building_ids = listing_building_ids.filter(
                    BuildingListingName.building_id != exclude_building_id
                )
            
            listing_building_ids = listing_building_ids.distinct()
            conditions.append(building_table.id.in_(listing_building_ids.subquery()))
        
        # 各検索語に対してOR条件を適用（AND条件でつなげる）
        if conditions:
            query = query.filter(or_(*conditions))
    
    return query