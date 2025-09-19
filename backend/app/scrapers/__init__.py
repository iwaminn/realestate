# Scrapers package

# 定数のインポート
from .constants import SourceSite

# データ正規化フレームワークのインポート
from .data_normalizer import (
    DataNormalizer,
    extract_price,
    extract_area,
    extract_floor_number,
    extract_total_floors,
    normalize_layout,
    normalize_direction,
    normalize_structure,
    format_station_info,
    clean_address,
    normalize_property_data,
    validate_property_data,
    normalize_integer,
    extract_monthly_fee,
    extract_built_year,
    parse_date,
)

# スクレイパークラスのインポート
from .suumo_scraper import SuumoScraper
from .homes_scraper import HomesScraper
from .rehouse_scraper import RehouseScraper
from .nomu_scraper import NomuScraper
from .livable_scraper import LivableScraper


def get_scraper_class(source_site: str):
    """サイト名からスクレイパークラスを取得"""
    scrapers = {
        'suumo': SuumoScraper,
        'homes': HomesScraper,
        'rehouse': RehouseScraper,
        'nomu': NomuScraper,
        'livable': LivableScraper,
    }
    return scrapers.get(source_site.lower())


__all__ = [
    'SourceSite',
    'DataNormalizer',
    'extract_price',
    'extract_area',
    'extract_floor_number',
    'extract_total_floors',
    'normalize_layout',
    'normalize_direction',
    'normalize_structure',
    'format_station_info',
    'clean_address',
    'normalize_property_data',
    'validate_property_data',
    'normalize_integer',
    'extract_monthly_fee',
    'extract_built_year',
    'parse_date',
    'extract_built_year_month',
    'get_scraper_class',
    'SuumoScraper',
    'HomesScraper',
    'RehouseScraper',
    'NomuScraper',
    'LivableScraper',
]