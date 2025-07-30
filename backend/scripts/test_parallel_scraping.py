#!/usr/bin/env python3
"""
並列スクレイピングのテストスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.scripts.run_scrapers_parallel import ParallelScrapingManager
import time
from datetime import datetime

def test_parallel_scraping():
    """並列スクレイピングをテスト"""
    
    # テスト用の設定
    scrapers = ['suumo', 'homes']  # 2つのスクレイパーでテスト
    areas = ['港区', '千代田区']  # 2つのエリアでテスト
    max_properties = 10  # 少ない数でテスト
    
    print("=== 並列スクレイピングテスト開始 ===")
    print(f"スクレイパー: {scrapers}")
    print(f"エリア: {areas}")
    print(f"最大取得数: {max_properties}件/エリア")
    print()
    
    # マネージャーを作成
    manager = ParallelScrapingManager()
    
    # タスクIDを生成
    task_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 並列実行
    start_time = time.time()
    result = manager.run_parallel(
        task_id=task_id,
        areas=areas,
        scrapers=scrapers,
        max_properties=max_properties,
        force_detail_fetch=False
    )
    
    elapsed_time = time.time() - start_time
    
    print("\n=== テスト結果 ===")
    print(f"タスクID: {result['task_id']}")
    print(f"総処理数: {result['total_processed']}件")
    print(f"総エラー数: {result['total_errors']}件")
    print(f"実行時間: {elapsed_time:.1f}秒")
    
    # 予想される直列実行時間と比較
    estimated_serial_time = len(scrapers) * len(areas) * 30  # 各エリア30秒と仮定
    print(f"\n予想される直列実行時間: {estimated_serial_time}秒")
    print(f"高速化率: {estimated_serial_time / elapsed_time:.1f}倍")


if __name__ == "__main__":
    test_parallel_scraping()