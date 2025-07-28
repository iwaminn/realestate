"""
物件ハッシュ生成ユーティリティ

物件の同一性を判定するためのハッシュ値を生成します。
ハッシュ生成には以下の要素を使用：
- 建物ID
- 所在階
- 専有面積
- 間取り
- 方角

注意：部屋番号はハッシュに含めません（サイトによって公開状況が異なるため）
"""

import hashlib
from typing import Optional


class PropertyHasher:
    """物件ハッシュ生成クラス"""
    
    @staticmethod
    def calculate_hash(
        building_id: int,
        floor_number: Optional[int] = None,
        area: Optional[float] = None,
        layout: Optional[str] = None,
        direction: Optional[str] = None
    ) -> str:
        """
        物件のハッシュ値を計算
        
        Args:
            building_id: 建物ID（必須）
            floor_number: 所在階
            area: 専有面積（㎡）
            layout: 間取り
            direction: 方角
            
        Returns:
            ハッシュ値（SHA256の16進数文字列）
        """
        # ハッシュの要素を準備
        hash_parts = []
        
        # 建物ID（必須）
        hash_parts.append(f"building:{building_id}")
        
        # 所在階
        if floor_number is not None:
            hash_parts.append(f"floor:{floor_number}")
        
        # 専有面積（小数点第2位まで）
        if area is not None:
            # 面積は小数点第2位で丸めて文字列化
            area_str = f"{area:.2f}"
            hash_parts.append(f"area:{area_str}")
        
        # 間取り
        if layout:
            # 間取りを正規化（大文字化、スペース除去）
            normalized_layout = layout.upper().replace(" ", "").replace("　", "")
            hash_parts.append(f"layout:{normalized_layout}")
        
        # 方角
        if direction:
            # 方角を正規化（スペース除去）
            normalized_direction = direction.replace(" ", "").replace("　", "")
            hash_parts.append(f"direction:{normalized_direction}")
        
        # ハッシュ文字列を生成
        hash_string = "|".join(sorted(hash_parts))
        
        # SHA256でハッシュ化
        hash_object = hashlib.sha256(hash_string.encode('utf-8'))
        return hash_object.hexdigest()
    
    @staticmethod
    def calculate_hash_without_direction(
        building_id: int,
        floor_number: Optional[int] = None,
        area: Optional[float] = None,
        layout: Optional[str] = None
    ) -> str:
        """
        方角を除いた物件のハッシュ値を計算（方角情報が不完全な場合の比較用）
        
        Args:
            building_id: 建物ID（必須）
            floor_number: 所在階
            area: 専有面積（㎡）
            layout: 間取り
            
        Returns:
            ハッシュ値（SHA256の16進数文字列）
        """
        return PropertyHasher.calculate_hash(
            building_id=building_id,
            floor_number=floor_number,
            area=area,
            layout=layout,
            direction=None
        )