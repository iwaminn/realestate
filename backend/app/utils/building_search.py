"""建物名検索の共通ユーティリティ"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy import or_, and_
from sqlalchemy.sql import text
from backend.app.utils.search_normalizer import create_search_patterns, normalize_search_text


def create_building_search_filter(building_name: str, column_name: str = "normalized_name", table_alias: str = "") -> Tuple[List, Dict]:
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