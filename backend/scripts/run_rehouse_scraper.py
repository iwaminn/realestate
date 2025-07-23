#!/usr/bin/env python3
"""
三井のリハウススクレイパーの実行スクリプト
"""

import sys
import os
import logging
from datetime import datetime

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.scrapers.rehouse_scraper import RehouseScraper

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/rehouse_scraper_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    try:
        logger.info("=== 三井のリハウススクレイパー開始 ===")
        
        # テスト用に最大3件のみ取得
        scraper = RehouseScraper(max_properties=3)
        
        # テスト実行（最初は1ページのみ）
        properties = scraper.scrape_area(
            area="minato",  # 港区
            max_pages=1     # 最初は1ページのみ
        )
        
        logger.info(f"スクレイピング完了: {len(properties)}件の物件を取得")
        
        # 取得した最初の物件の情報を表示
        if properties:
            first_prop = properties[0]
            logger.info("\n=== 最初の物件情報 ===")
            for key, value in first_prop.items():
                if key != 'image_urls':  # 画像URLは省略
                    logger.info(f"{key}: {value}")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        
    finally:
        logger.info("=== スクレイピング終了 ===")


if __name__ == "__main__":
    main()