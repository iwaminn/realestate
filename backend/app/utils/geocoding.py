#!/usr/bin/env python3
"""
座標取得ユーティリティ
東京大学CSISのシンプルジオコーディングAPIを使用して住所から緯度経度を取得
"""

import requests
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Building
from ..utils.logger import api_logger

class GeocodingService:
    """座標取得サービス"""

    # 東京大学CSISシンプルジオコーディングAPI
    CSIS_API_URL = "https://geocode.csis.u-tokyo.ac.jp/cgi-bin/simple_geocode.cgi"
    
    @classmethod
    def get_coordinates_from_address(cls, address: str) -> Optional[Tuple[float, float]]:
        """
        住所から緯度経度を取得（東京大学CSISシンプルジオコーディング使用）

        Args:
            address: 住所文字列

        Returns:
            (latitude, longitude) のタプル、または取得失敗時はNone
        """
        try:
            # 東京大学CSISシンプルジオコーディングAPIにリクエスト
            response = requests.get(
                cls.CSIS_API_URL,
                params={
                    "addr": address,
                    "charset": "UTF8"
                },
                timeout=10
            )
            response.raise_for_status()

            # XMLレスポンスをパース
            root = ET.fromstring(response.content)

            # 最初の候補を取得
            candidate = root.find('candidate')
            if candidate is not None:
                longitude_elem = candidate.find('longitude')
                latitude_elem = candidate.find('latitude')

                if longitude_elem is not None and latitude_elem is not None:
                    lng = float(longitude_elem.text)
                    lat = float(latitude_elem.text)
                    api_logger.info(f"座標取得成功: {address} -> ({lat}, {lng})")
                    return (lat, lng)

            api_logger.warning(f"座標が見つかりませんでした: {address}")
            return None

        except requests.RequestException as e:
            api_logger.error(f"ジオコーディングAPIエラー: {e}", exc_info=True)
            return None
        except ET.ParseError as e:
            api_logger.error(f"XMLパースエラー: {e}", exc_info=True)
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
            
            # 番地情報が含まれているかチェック（より柔軟な判定）
            # 以下のいずれかのパターンにマッチすれば詳細住所とみなす：
            # - 1-2 形式（2つの数字、例：2-101）
            # - 1-2-3 形式（3つ以上の数字、例：2-3-101）
            # - 「号」が含まれる（例：2丁目3番101号）
            import re
            if not re.search(r'\d+-\d+|号', building.address):
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