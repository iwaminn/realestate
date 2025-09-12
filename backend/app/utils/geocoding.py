#!/usr/bin/env python3
"""
座標取得ユーティリティ
国土地理院のAPIを使用して住所から緯度経度を取得
"""

import requests
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Building
from ..utils.logger import api_logger

class GeocodingService:
    """座標取得サービス"""
    
    # 国土地理院ジオコーディングAPI
    GSI_API_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
    
    @classmethod
    def get_coordinates_from_address(cls, address: str) -> Optional[Tuple[float, float]]:
        """
        住所から緯度経度を取得
        
        Args:
            address: 住所文字列
            
        Returns:
            (latitude, longitude) のタプル、または取得失敗時はNone
        """
        try:
            # 国土地理院APIにリクエスト
            response = requests.get(
                cls.GSI_API_URL,
                params={"q": address},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data and len(data) > 0:
                # 最初の結果を使用
                result = data[0]
                if "geometry" in result and "coordinates" in result["geometry"]:
                    # GeoJSON形式は[経度, 緯度]の順
                    lng, lat = result["geometry"]["coordinates"]
                    api_logger.info(f"座標取得成功: {address} -> ({lat}, {lng})")
                    return (lat, lng)
            
            api_logger.warning(f"座標が見つかりませんでした: {address}")
            return None
            
        except requests.RequestException as e:
            api_logger.error(f"ジオコーディングAPIエラー: {e}", exc_info=True)
            return None
        except Exception as e:
            api_logger.error(f"座標取得エラー: {e}", exc_info=True)
            return None
    
    @classmethod
    def update_building_coordinates(cls, db: Session, building_id: int) -> bool:
        """
        建物の座標を更新
        
        Args:
            db: データベースセッション
            building_id: 建物ID
            
        Returns:
            更新成功時はTrue
        """
        try:
            # 建物を取得
            building = db.query(Building).filter(Building.id == building_id).first()
            if not building:
                api_logger.warning(f"建物が見つかりません: ID={building_id}")
                return False
            
            # 住所がない場合はスキップ
            if not building.address:
                api_logger.info(f"建物に住所がありません: ID={building_id}")
                return False
            
            # 「号」まで含まれていない場合はスキップ（詳細住所のみ対象）
            # ただし「-」のみの判定は曖昧なので「号」を優先
            import re
            if not re.search(r'\d+-\d+-\d+|号', building.address):
                api_logger.info(f"詳細住所ではないためスキップ: {building.address}")
                return False
            
            # 座標を取得
            coords = cls.get_coordinates_from_address(building.address)
            if coords:
                lat, lng = coords
                building.latitude = lat
                building.longitude = lng
                building.geocoded_at = datetime.now()
                db.commit()
                api_logger.info(f"建物の座標を更新: ID={building_id}, ({lat}, {lng})")
                return True
            
            return False
            
        except Exception as e:
            api_logger.error(f"座標更新エラー: {e}", exc_info=True)
            db.rollback()
            return False
    
    @classmethod
    def get_or_update_coordinates(cls, db: Session, building_id: int) -> Optional[Tuple[float, float]]:
        """
        建物の座標を取得（キャッシュ優先、なければAPI取得）
        
        Args:
            db: データベースセッション
            building_id: 建物ID
            
        Returns:
            (latitude, longitude) のタプル、またはNone
        """
        try:
            # 建物を取得
            building = db.query(Building).filter(Building.id == building_id).first()
            if not building:
                return None
            
            # キャッシュされた座標があれば返す
            if building.latitude is not None and building.longitude is not None:
                api_logger.info(f"キャッシュから座標を返却: ID={building_id}")
                return (building.latitude, building.longitude)
            
            # なければ取得して保存
            if cls.update_building_coordinates(db, building_id):
                building = db.query(Building).filter(Building.id == building_id).first()
                if building.latitude is not None and building.longitude is not None:
                    return (building.latitude, building.longitude)
            
            return None
            
        except Exception as e:
            api_logger.error(f"座標取得エラー: {e}", exc_info=True)
            return None