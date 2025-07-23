"""
スクレイパー設定
環境変数またはデフォルト値から設定を読み込む
"""

import os
from typing import Dict, Any

class ScraperConfig:
    """スクレイパーの設定クラス"""
    
    # デフォルト設定
    DEFAULT_DELAY = 2  # スクレイピング間隔（秒）
    DEFAULT_DETAIL_REFETCH_DAYS = 90  # 詳細ページ再取得間隔（日）
    DEFAULT_MAX_PAGES = 5  # デフォルトの最大ページ数
    DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """環境変数またはデフォルト値から設定を取得"""
        return {
            'delay': int(os.getenv('SCRAPER_DELAY', cls.DEFAULT_DELAY)),
            'detail_refetch_days': int(os.getenv('SCRAPER_DETAIL_REFETCH_DAYS', cls.DEFAULT_DETAIL_REFETCH_DAYS)),
            'max_pages': int(os.getenv('SCRAPER_MAX_PAGES', cls.DEFAULT_MAX_PAGES)),
            'user_agent': os.getenv('SCRAPER_USER_AGENT', cls.DEFAULT_USER_AGENT),
        }
    
    @classmethod
    def get_scraper_specific_config(cls, scraper_name: str) -> Dict[str, Any]:
        """特定のスクレイパー用の設定を取得"""
        base_config = cls.get_config()
        
        # スクレイパー固有の設定を環境変数から読み込む
        scraper_upper = scraper_name.upper()
        
        # スクレイパー固有の遅延時間
        if f'SCRAPER_{scraper_upper}_DELAY' in os.environ:
            base_config['delay'] = int(os.environ[f'SCRAPER_{scraper_upper}_DELAY'])
        
        # スクレイパー固有の詳細再取得間隔
        if f'SCRAPER_{scraper_upper}_DETAIL_REFETCH_DAYS' in os.environ:
            base_config['detail_refetch_days'] = int(os.environ[f'SCRAPER_{scraper_upper}_DETAIL_REFETCH_DAYS'])
        
        return base_config