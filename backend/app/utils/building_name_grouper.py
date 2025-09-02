"""
建物名のグループ化を行うモジュール

建物名正規化関数を使用して、表記ゆれを吸収します。
正規化後、さらにスペースを除去してグループ化のキーとします。
"""

from typing import Dict, List, Set, Tuple
import logging
import re
from .building_name_normalizer import normalize_building_name

logger = logging.getLogger(__name__)


class BuildingNameGrouper:
    """建物名をグループ化するクラス"""
    
    def __init__(self):
        """初期化"""
        pass
    
    def group_building_names(self, names: List[str]) -> Dict[str, List[str]]:
        """建物名をグループ化（基本版）
        
        1. normalize_building_name関数で正規化
        2. さらにスペースを除去してグループ化キーを生成
        3. 同じキーを持つ建物名を同一グループとして扱います
        
        Args:
            names: 建物名のリスト
            
        Returns:
            グループ化された建物名（キーはスペース除去後の文字列）
        """
        if not names:
            return {}
        
        # 正規化とスペース除去を行ってグループ化
        groups = {}
        
        for name in names:
            # 1. 共通の正規化関数を使用（全角→半角、大文字化など）
            normalized = normalize_building_name(name)
            
            # 2. グループ化のキーとしてスペースを完全に除去
            group_key = re.sub(r'\s+', '', normalized)
            
            # グループに追加
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(name)
        
        return groups
    
    
    def find_best_representation(self, names: List[str], name_weights: Dict[str, float] = None) -> str:
        """グループ内で最も適切な表記を選択
        
        重み情報がある場合は最も重みの高い名前を選択、
        ない場合は最も短い名前を選択します。
        
        Args:
            names: 同一グループの建物名リスト
            name_weights: 各建物名の重み（オプション）
            
        Returns:
            代表となる建物名
        """
        if not names:
            return ""
        
        if name_weights:
            # 重み情報がある場合は、重みが最も高いものを選択
            best_name = None
            best_weight = -1
            
            for name in names:
                weight = name_weights.get(name, 0)
                if weight > best_weight:
                    best_weight = weight
                    best_name = name
            
            return best_name if best_name else names[0]
        else:
            # 重み情報がない場合は、最も短い名前を選択
            return min(names, key=len)


# シングルトンインスタンス
_grouper = None


def get_grouper() -> BuildingNameGrouper:
    """BuildingNameGrouperのシングルトンインスタンスを取得
    
    Returns:
        BuildingNameGrouperインスタンス
    """
    global _grouper
    if _grouper is None:
        _grouper = BuildingNameGrouper()
    return _grouper