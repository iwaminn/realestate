"""
スクレイパー関連のユーティリティ関数
単一URLの詳細取得など、スクレイパーを簡易的に使用するための関数を提供
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def get_scraper_instance(source_site: str):
    """
    サイト名からスクレイパーインスタンスを取得
    
    Args:
        source_site: サイト名（例: 'suumo', 'homes'）
    
    Returns:
        スクレイパーインスタンス or None
    """
    from ..scrapers.suumo_scraper import SuumoScraper
    from ..scrapers.homes_scraper import HomesScraper
    from ..scrapers.rehouse_scraper import RehouseScraper
    from ..scrapers.nomu_scraper import NomuScraper
    from ..scrapers.livable_scraper import LivableScraper
    
    # スクレイパーのマッピング（小文字で統一）
    scraper_classes = {
        'suumo': SuumoScraper,
        'homes': HomesScraper,
        'lifull homes': HomesScraper,
        "lifull home's": HomesScraper,
        'rehouse': RehouseScraper,
        '三井のリハウス': RehouseScraper,
        'nomu': NomuScraper,
        'ノムコム': NomuScraper,
        'livable': LivableScraper,
        '東急リバブル': LivableScraper,
    }
    
    scraper_class = scraper_classes.get(source_site.lower())
    if not scraper_class:
        logger.error(f"未対応のサイト: {source_site}")
        return None
    
    return scraper_class()


def fetch_property_detail(url: str, source_site: str) -> Optional[Dict[str, Any]]:
    """
    単一URLから物件詳細情報を取得
    
    Args:
        url: 物件詳細ページのURL
        source_site: サイト名
    
    Returns:
        詳細情報の辞書 or None
    """
    scraper = get_scraper_instance(source_site)
    if not scraper:
        return None
    
    try:
        # スクレイパーの詳細取得メソッドを呼び出し
        detail_info = scraper.parse_property_detail(url)
        if not detail_info:
            logger.warning(f"詳細情報を取得できませんでした: {url}")
        return detail_info
    except Exception as e:
        logger.error(f"詳細取得中にエラーが発生: {url}, error: {e}")
        return None


def update_listing_from_detail(listing, detail_info: Dict[str, Any]) -> None:
    """
    詳細情報から掲載情報オブジェクトを更新
    
    Args:
        listing: PropertyListingオブジェクト
        detail_info: 詳細情報の辞書
    """
    # 各フィールドを更新（存在する場合のみ）
    field_mapping = {
        'title': 'title',  # タイトルを追加
        'agency_name': 'agency_name',
        'agency_tel': 'agency_tel',
        'balcony_area': 'balcony_area',
        'remarks': 'remarks',

        'floor_number': 'listing_floor_number',
        'total_floors': 'listing_total_floors',
        'total_units': 'listing_total_units',  # 総戸数を追加
        'area': 'listing_area',
        'layout': 'listing_layout',
        'direction': 'listing_direction',
        'management_fee': 'management_fee',
        'repair_fund': 'repair_fund',
        'station_info': 'listing_station_info',  # 交通情報を追加
        'address': 'listing_address',  # 住所も追加（listing_addressフィールドに保存）
        'building_name': 'listing_building_name',  # 建物名も追加
    }
    
    for detail_key, listing_attr in field_mapping.items():
        if detail_key in detail_info:
            setattr(listing, listing_attr, detail_info[detail_key])