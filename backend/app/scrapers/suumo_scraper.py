"""
SUUMOスクレイパー v3
一覧ページから直接情報を収集
"""

import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup, Tag

from .constants import SourceSite
from .base_scraper import BaseScraper
from .parsers import SuumoParser
from ..models import PropertyListing
from ..utils.exceptions import TaskPausedException, TaskCancelledException
from . import (
    normalize_integer, extract_price, extract_area, extract_floor_number,
    normalize_layout, normalize_direction, extract_monthly_fee,
    format_station_info, extract_built_year, parse_date, extract_total_floors
)


class SuumoScraper(BaseScraper):
    """SUUMOのスクレイパー（v3 - 一覧ページベース）"""
    
    BASE_URL = "https://suumo.jp"
    
    # 定数の定義
    MAX_DISPLAY_ITEMS = 100  # SUUMOの最大表示件数
    MAX_REMARKS_LENGTH = 500  # 備考の最大文字数
    MIN_REMARKS_LENGTH = 50  # 備考の最小文字数
    MIN_LONG_TEXT_LENGTH = 100  # 長文と判定する最小文字数
    
    def __init__(self, force_detail_fetch=False, max_properties=None, ignore_error_history=False, task_id=None):
        super().__init__(SourceSite.SUUMO, force_detail_fetch, max_properties, ignore_error_history, task_id)
        self.parser = SuumoParser(logger=self.logger)
        # 建物名取得エラーの履歴（メモリ内管理）
    
    
    def process_property_data(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing]) -> bool:
        """個別の物件を処理（SUUMOスクレイパー固有の実装）"""
        try:
            # process_property_with_detail_checkを直接呼び出す
            result = self.process_property_with_detail_check(
                property_data=property_data,
                existing_listing=existing_listing,
                parse_detail_func=self.parse_property_detail,
                save_property_func=self.save_property_common
            )
            return result
        except Exception as e:
            # エラーは呼び出し元で処理されるので、ここでは再スロー
            raise
    
    def get_search_url(self, area: str, page: int = 1) -> str:
        """SUUMOの検索URLを生成（100件/ページ）
        
        Args:
            area: エリアコード（scrape_areaから渡される）
            page: ページ番号
        """
        # エリアコードからローマ字を取得
        if area.isdigit() and len(area) == 5:
            # エリアコードの場合はローマ字に変換
            from ..scrapers.area_config import get_area_romaji_from_code
            area_romaji = get_area_romaji_from_code(area)
        else:
            # すでにローマ字の場合はそのまま使用
            area_romaji = area
        
        # 中古マンション検索用URL
        if page == 1:
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc={self.MAX_DISPLAY_ITEMS}"
        else:
            return f"{self.BASE_URL}/ms/chuko/tokyo/sc_{area_romaji}/?pc={self.MAX_DISPLAY_ITEMS}&page={page}"
    
    def parse_property_list(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """物件一覧を解析 - パーサーに委譲"""
        return self.parser.parse_property_list(soup)

    def is_last_page(self, soup: BeautifulSoup) -> bool:
        """現在のページが最終ページかどうかを判定 - パーサーに委譲"""
        return self.parser.is_last_page(soup)
    
    def validate_site_property_id(self, site_property_id: str, url: str) -> bool:
        """SUUMOのsite_property_idの妥当性を検証
        
        SUUMOの物件IDは数字のみで構成される（例：76583217）
        """
        # 基底クラスの共通検証
        if not super().validate_site_property_id(site_property_id, url):
            return False
            
        # SUUMO固有の検証：数字のみで構成されているか
        if not site_property_id.isdigit():
            self.logger.error(
                f"[SUUMO] site_property_idは数字のみで構成される必要があります: '{site_property_id}' URL={url}"
            )
            return False
            
        # 通常は6〜10桁程度
        if len(site_property_id) < 6 or len(site_property_id) > 10:
            self.logger.warning(
                f"[SUUMO] site_property_idの桁数が異常です（通常6-10桁）: '{site_property_id}' "
                f"(桁数: {len(site_property_id)}) URL={url}"
            )
            # 警告のみで続行（将来的に桁数が変わる可能性があるため）
            
        return True
    
    def extract_property_id(self, url: str) -> Optional[str]:
        """URLから物件IDを抽出
        
        Returns:
            str: 物件ID（抽出に失敗した場合はNone）
        """
        match = re.search(r'/nc_(\d+)/', url)
        if match:
            return match.group(1)
        else:
            self.logger.error(f"[SUUMO] URLから物件IDを抽出できませんでした: {url}")
            return None
    
    def save_property(self, property_data: Dict[str, Any], existing_listing: Optional[PropertyListing] = None):
        """物件情報を保存（スマートスクレイピング対応）"""
        # 共通の詳細チェック処理を使用
        return self.process_property_with_detail_check(
            property_data=property_data,
            existing_listing=existing_listing,
            parse_detail_func=self.parse_property_detail,
            save_property_func=self.save_property_common
        )
    
    
    def parse_property_detail(self, url: str) -> Optional[Dict[str, Any]]:
        """物件詳細ページを解析 - パーサーに委譲"""
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        # パーサーで詳細な解析を実行
        detail_data = self.parser.parse_property_detail(soup)
        
        # スクレイパー固有の処理
        if detail_data:
            detail_data["url"] = url
            detail_data["_page_text"] = soup.get_text()  # 建物名一致確認用
            
            # site_property_idの抽出と検証
            if "site_property_id" not in detail_data and url:
                site_id = self.extract_property_id(url)
                if site_id:
                    detail_data["site_property_id"] = site_id
        
        return detail_data

    
    
    
    
    
    
    

    

    
    
    
    
    
    
    
    
    
    
    
    def verify_building_names_match(self, detail_building_name: str, building_name_from_list: str,
                                    allow_partial_match: bool = False, threshold: float = 0.8) -> Tuple[bool, Optional[str]]:
        """建物名の一致確認（SUUMOの省略表示に対応）
        
        SUUMOの仕様：
        - 一覧ページでは長い建物名が「…」付きで省略表示される
        - 省略されている場合：詳細ページの建物名が一覧の建物名で始まるか確認（前方一致）
        - 省略されていない場合：詳細ページの建物名と一覧の建物名が同じか確認（完全一致）
        
        Args:
            detail_building_name: 詳細ページから取得した建物名
            building_name_from_list: 一覧ページから取得した建物名（省略されている可能性あり）
            threshold: 類似度の閾値（0.0-1.0）
            
        Returns:
            (建物名が確認できたか, 詳細ページの完全な建物名またはNone)
        """
        if not building_name_from_list or not detail_building_name:
            return False, None
        
        # 「…」で終わっている場合は省略されている
        is_abbreviated = building_name_from_list.endswith('…') or building_name_from_list.endswith('...')
        
        # 省略されていない場合は基底クラスの正規化処理を使用
        if not is_abbreviated:
            # 基底クラスのメソッドを使用（㎡とm2の正規化も含まれる）
            return super().verify_building_names_match(detail_building_name, building_name_from_list, 
                                                      allow_partial_match=False, threshold=threshold)
        
        if is_abbreviated:
            self.logger.info(f"[SUUMO] 省略された建物名を検出: '{building_name_from_list}'")
            
            # 省略記号を除去
            abbreviated_name = building_name_from_list.rstrip('….')
            
            # 基底クラスの正規化メソッドを使用
            normalized_abbreviated = self.normalize_building_name(abbreviated_name)
            normalized_detail = self.normalize_building_name(detail_building_name)
            
            # ログで確認
            self.logger.info(f"[SUUMO] 建物名比較（省略） - 一覧: '{abbreviated_name}' が 詳細: '{detail_building_name}' に前方一致するか確認")
            
            # 詳細ページの建物名が、省略された建物名で始まるか確認（正規化版で比較）
            if normalized_detail.startswith(normalized_abbreviated):
                self.logger.info(
                    f"[SUUMO] 省略された建物名が前方一致（成功）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
            
            self.logger.debug(
                f"[SUUMO] 正規化後 - 一覧: '{normalized_abbreviated}' が 詳細: '{normalized_detail}' に前方一致するか確認"
            )
            
            # 大文字小文字を無視して比較
            if normalized_detail.lower().startswith(normalized_abbreviated.lower()):
                self.logger.info(
                    f"[SUUMO] 省略された建物名が正規化後に前方一致（成功）: "
                    f"一覧「{building_name_from_list}」→ 詳細「{detail_building_name}」"
                )
                return True, detail_building_name
            
            # 見つからない場合
            self.logger.warning(
                f"[SUUMO] 省略された建物名が一致しません: "
                f"一覧「{building_name_from_list}」が詳細「{detail_building_name}」に前方一致しません"
            )
            return False, None
        else:
            # 省略されていない場合
            self.logger.info(f"[SUUMO] 建物名比較（完全） - 一覧: '{building_name_from_list}' と 詳細: '{detail_building_name}' が完全一致するか確認")
            
            if building_name_from_list == detail_building_name:
                self.logger.info(
                    f"[SUUMO] 建物名が完全一致（成功）: '{building_name_from_list}'"
                )
                return True, detail_building_name
            
            # 正規化して比較
            normalized_list = re.sub(r'[\s　・－―～〜]+', '', building_name_from_list)
            normalized_detail = re.sub(r'[\s　・－―～〜]+', '', detail_building_name)
            
            if normalized_list.lower() == normalized_detail.lower():
                self.logger.info(
                    f"[SUUMO] 建物名が正規化後に完全一致（成功）: '{building_name_from_list}'"
                )
                return True, detail_building_name
            
            # 一致しない場合は基底クラスのメソッドを使用（部分一致などの高度な比較）
            return super().verify_building_names_match(
                detail_building_name, 
                building_name_from_list, 
                allow_partial_match=self.allow_partial_building_name_match,
                threshold=threshold
            )
    
    
    
    def _update_building_name_statistics(self, property_data: Dict[str, Any]):
        """建物名取得元の統計を更新"""
        if property_data.get('building_name_source'):
            source = property_data['building_name_source']
            if source == 'table':
                self._scraping_stats['building_name_from_table'] += 1
            elif source == 'title':
                self._scraping_stats['building_name_from_title'] += 1
            elif source == 'fallback':
                self._scraping_stats['building_name_from_fallback'] += 1
            # property_dataから削除（DBに保存する必要はない）
            del property_data['building_name_source']
    
    
