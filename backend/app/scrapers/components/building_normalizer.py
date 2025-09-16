"""
建物名正規化コンポーネント

建物名の正規化処理を担当するコンポーネント
"""
import logging
from typing import Optional
from ...utils.building_normalizer import BuildingNameNormalizer as BaseNormalizer


class BuildingNormalizerComponent:
    """建物名正規化コンポーネント"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
        self.normalizer = BaseNormalizer()
    
    def normalize(self, building_name: str) -> str:
        """
        建物名を正規化
        
        Args:
            building_name: 元の建物名
            
        Returns:
            正規化された建物名
        """
        if not building_name:
            return ""
        
        try:
            normalized = self.normalizer.normalize(building_name)
            self.logger.debug(f"建物名正規化: {building_name} -> {normalized}")
            return normalized
        except Exception as e:
            self.logger.error(f"建物名正規化エラー: {e}")
            return building_name
    
    def canonicalize(self, building_name: str) -> str:
        """
        建物名を正準化（より厳密な正規化）
        
        Args:
            building_name: 元の建物名
            
        Returns:
            正準化された建物名
        """
        if not building_name:
            return ""
        
        try:
            from ...utils.building_name_normalizer import canonicalize_building_name
            canonicalized = canonicalize_building_name(building_name)
            self.logger.debug(f"建物名正準化: {building_name} -> {canonicalized}")
            return canonicalized
        except Exception as e:
            self.logger.error(f"建物名正準化エラー: {e}")
            return building_name
    
    def extract_room_number(self, building_name: str) -> tuple[str, Optional[str]]:
        """
        建物名から部屋番号を抽出
        
        Args:
            building_name: 元の建物名
            
        Returns:
            (建物名, 部屋番号) のタプル
        """
        try:
            from ...utils.building_name_normalizer import extract_room_number_common
            building, room = extract_room_number_common(building_name)
            if room:
                self.logger.debug(f"部屋番号抽出: {building_name} -> 建物: {building}, 部屋: {room}")
            return building, room
        except Exception as e:
            self.logger.error(f"部屋番号抽出エラー: {e}")
            return building_name, None