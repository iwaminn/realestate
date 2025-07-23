#!/usr/bin/env python3
"""
APIから呼び出されるスクレイピング実行スクリプト
Docker環境で実行されることを想定
"""

import sys
import os
import json
import time
from datetime import datetime

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.suumo_scraper import SUUMOScraper
from app.scrapers.homes_scraper import HOMESScraper
from app.scrapers.rehouse_scraper import RehouseScraper


def update_status(status_file, task_id, updates):
    """ステータスファイルを更新"""
    try:
        with open(status_file, 'r') as f:
            data = json.load(f)
    except:
        data = {}
    
    if task_id not in data:
        data[task_id] = {}
    
    data[task_id].update(updates)
    
    with open(status_file, 'w') as f:
        json.dump(data, f)


def main():
    if len(sys.argv) < 5:
        print("Usage: api_scraper.py <task_id> <scrapers> <area_code> <max_properties>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    scrapers = sys.argv[2].split(',')
    area_code = sys.argv[3]
    max_properties = int(sys.argv[4])
    
    # ステータスファイルのパス
    status_file = f"/tmp/scraping_status_{task_id}.json"
    
    # 初期ステータスを書き込み
    update_status(status_file, task_id, {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "progress": {}
    })
    
    scraper_classes = {
        "suumo": SUUMOScraper,
        "homes": HOMESScraper,
        "rehouse": RehouseScraper
    }
    
    errors = []
    
    for scraper_name in scrapers:
        if scraper_name not in scraper_classes:
            error_msg = f"Unknown scraper: {scraper_name}"
            errors.append(error_msg)
            continue
        
        try:
            # 進行状況を更新
            update_status(status_file, task_id, {
                "progress": {
                    scraper_name: {
                        "status": "running",
                        "properties_scraped": 0,
                        "started_at": datetime.now().isoformat()
                    }
                }
            })
            
            # スクレイピング実行
            scraper_class = scraper_classes[scraper_name]
            print(f"[{task_id}] Starting {scraper_name} scraper for area {area_code}")
            
            with scraper_class(max_properties=max_properties) as scraper:
                scraper.scrape_area(area_code, max_pages=10)
            
            # 完了を更新
            update_status(status_file, task_id, {
                "progress": {
                    scraper_name: {
                        "status": "completed",
                        "completed_at": datetime.now().isoformat()
                    }
                }
            })
            
            print(f"[{task_id}] Completed {scraper_name} scraper")
            
        except Exception as e:
            error_msg = f"Error in {scraper_name}: {str(e)}"
            print(f"[{task_id}] {error_msg}")
            errors.append(error_msg)
            
            update_status(status_file, task_id, {
                "progress": {
                    scraper_name: {
                        "status": "failed",
                        "error": str(e),
                        "completed_at": datetime.now().isoformat()
                    }
                }
            })
    
    # タスク完了
    update_status(status_file, task_id, {
        "status": "completed",
        "completed_at": datetime.now().isoformat(),
        "errors": errors
    })
    
    print(f"[{task_id}] All scrapers completed")


if __name__ == "__main__":
    main()