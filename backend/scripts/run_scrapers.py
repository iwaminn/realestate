#!/usr/bin/env python3
"""
スクレイピングスケジューラー
全てのスクレイパーを定期的に実行
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import schedule
import time
import logging
import argparse
from datetime import datetime
from backend.app.scrapers.suumo_scraper import SuumoScraper
from backend.app.scrapers.athome_scraper import AtHomeScraper
from backend.app.scrapers.homes_scraper import HomesScraper
from backend.app.scrapers.rehouse_scraper import RehouseScraper
from backend.app.scrapers.nomu_scraper import NomuScraper

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def run_all_scrapers(area: str = "minato", max_pages: int = 3, force_detail_fetch: bool = False):
    """全てのスクレイパーを実行"""
    logger.info(f"Starting scraping job for area: {area}")
    if force_detail_fetch:
        logger.info("Force detail fetch mode is enabled")
    
    scrapers = [
        ('SUUMO', SuumoScraper(force_detail_fetch=force_detail_fetch)),
        ('AtHome', AtHomeScraper(force_detail_fetch=force_detail_fetch)),
        ('HOMES', HomesScraper(force_detail_fetch=force_detail_fetch)),
        ('Rehouse', RehouseScraper(force_detail_fetch=force_detail_fetch)),
        ('NOMU', NomuScraper(force_detail_fetch=force_detail_fetch)),
    ]
    
    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    for name, scraper in scrapers:
        try:
            logger.info(f"Running {name} scraper...")
            scraper.scrape_area(area, max_pages)
            results['success'] += 1
            logger.info(f"{name} scraper completed successfully")
        except Exception as e:
            logger.error(f"{name} scraper failed: {e}")
            results['failed'] += 1
            results['errors'].append(f"{name}: {str(e)}")
    
    logger.info(f"Scraping job completed. Success: {results['success']}, Failed: {results['failed']}")
    
    if results['errors']:
        logger.error(f"Errors: {', '.join(results['errors'])}")
    
    return results


def run_single_scraper(scraper_name: str, area: str = "minato", max_pages: int = 3, force_detail_fetch: bool = False):
    """単一のスクレイパーを実行"""
    scrapers = {
        'suumo': SuumoScraper,
        'athome': AtHomeScraper,
        'homes': HomesScraper,
        'rehouse': RehouseScraper,
        'nomu': NomuScraper,
    }
    
    if scraper_name.lower() not in scrapers:
        logger.error(f"Unknown scraper: {scraper_name}")
        return
    
    try:
        logger.info(f"Running {scraper_name} scraper for area: {area}")
        if force_detail_fetch:
            logger.info("Force detail fetch mode is enabled")
        scraper = scrapers[scraper_name.lower()](force_detail_fetch=force_detail_fetch)
        # AtHomeSeleniumScraperは runメソッドを使用
        if hasattr(scraper, 'run'):
            scraper.run(area, max_pages)
        else:
            scraper.scrape_area(area, max_pages)
        logger.info(f"{scraper_name} scraper completed successfully")
    except Exception as e:
        logger.error(f"{scraper_name} scraper failed: {e}", exc_info=True)


def scheduled_job():
    """スケジュールされたジョブ"""
    logger.info("=" * 50)
    logger.info(f"Scheduled job started at {datetime.now()}")
    run_all_scrapers()
    logger.info(f"Scheduled job completed at {datetime.now()}")
    logger.info("=" * 50)


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='不動産スクレイピングツール')
    parser.add_argument('--scraper', type=str, help='実行するスクレイパー (suumo, athome, homes, rehouse, nomu, all)')
    parser.add_argument('--area', type=str, default='minato', help='検索エリア（デフォルト: minato）')
    parser.add_argument('--pages', type=int, default=3, help='取得するページ数（デフォルト: 3）')
    parser.add_argument('--schedule', action='store_true', help='スケジュール実行モード')
    parser.add_argument('--interval', type=int, default=6, help='スケジュール実行間隔（時間）（デフォルト: 6）')
    parser.add_argument('--force-detail-fetch', action='store_true', help='強制的にすべての物件の詳細を取得')
    
    args = parser.parse_args()
    
    if args.schedule:
        # スケジュール実行モード
        logger.info(f"Starting scheduled mode. Running every {args.interval} hours")
        
        # 初回実行
        scheduled_job()
        
        # スケジュール設定
        schedule.every(args.interval).hours.do(scheduled_job)
        
        # スケジュール実行
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1分ごとにチェック
    else:
        # 単発実行モード
        if args.scraper and args.scraper.lower() != 'all':
            run_single_scraper(args.scraper, args.area, args.pages, args.force_detail_fetch)
        else:
            run_all_scrapers(args.area, args.pages, args.force_detail_fetch)


if __name__ == "__main__":
    main()