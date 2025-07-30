#!/usr/bin/env python3
"""
停止したスクレイピングタスクを検出してエラーステータスに変更するスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from backend.app.database import SessionLocal
from backend.app.models_scraping_task import ScrapingTask, ScrapingTaskProgress
from backend.app.config.scraping_config import (
    STALLED_TASK_THRESHOLD_MINUTES,
    STALLED_PAUSED_TASK_THRESHOLD_MINUTES
)
import logging

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_stalled_tasks(stall_threshold_minutes: int = 10):
    """
    停止したタスクを検出してエラーステータスに変更
    
    Args:
        stall_threshold_minutes: 何分間更新がなければ停止とみなすか（デフォルト10分）
    """
    db = SessionLocal()
    try:
        # 現在時刻
        now = datetime.now()
        threshold = now - timedelta(minutes=stall_threshold_minutes)
        
        # runningまたはpausedステータスのタスクを取得
        active_tasks = db.query(ScrapingTask).filter(
            ScrapingTask.status.in_(['running', 'paused'])
        ).all()
        
        logger.info(f"アクティブなタスク数: {len(active_tasks)}")
        
        stalled_tasks = []
        
        for task in active_tasks:
            # タスクの進捗を確認
            latest_progress = db.query(ScrapingTaskProgress).filter(
                ScrapingTaskProgress.task_id == task.task_id
            ).order_by(
                ScrapingTaskProgress.last_updated.desc()
            ).first()
            
            if latest_progress:
                # 最終更新時刻をチェック
                if latest_progress.last_updated < threshold:
                    time_since_update = now - latest_progress.last_updated
                    minutes_since_update = time_since_update.total_seconds() / 60
                    
                    logger.warning(
                        f"タスク {task.task_id} が {minutes_since_update:.1f}分間更新されていません"
                    )
                    
                    # pausedステータスの場合は、より長い時間待つ
                    if task.status == 'paused':
                        # pausedの場合は設定値（デフォルト30分）待つ
                        if minutes_since_update > STALLED_PAUSED_TASK_THRESHOLD_MINUTES:
                            logger.info(f"一時停止中のタスク {task.task_id} が{STALLED_PAUSED_TASK_THRESHOLD_MINUTES}分以上更新されていません - 停止と判断")
                            stalled_tasks.append(task)
                    else:
                        stalled_tasks.append(task)
            else:
                # 進捗レコードがない場合
                if task.started_at and task.started_at < threshold:
                    time_since_start = now - task.started_at
                    minutes_since_start = time_since_start.total_seconds() / 60
                    
                    logger.warning(
                        f"タスク {task.task_id} が開始から {minutes_since_start:.1f}分間進捗がありません"
                    )
                    stalled_tasks.append(task)
        
        # 停止したタスクをエラーステータスに変更
        for task in stalled_tasks:
            logger.error(f"タスク {task.task_id} を停止として検出、エラーステータスに変更します")
            
            # タスクステータスを更新
            task.status = 'error'
            task.completed_at = now
            
            # エラーログを追加
            error_logs = task.error_logs or []
            error_logs.append({
                'error': 'Task stalled - no progress updates',
                'timestamp': now.isoformat(),
                'details': f'No updates for more than {stall_threshold_minutes} minutes'
            })
            task.error_logs = error_logs
            
            # 進捗ステータスも更新（completed, cancelled以外をerrorに）
            db.query(ScrapingTaskProgress).filter(
                ScrapingTaskProgress.task_id == task.task_id,
                ScrapingTaskProgress.status.in_(['running', 'pending', 'paused'])
            ).update({
                'status': 'error',
                'completed_at': now
            })
        
        if stalled_tasks:
            db.commit()
            logger.info(f"{len(stalled_tasks)}個のタスクをエラーステータスに変更しました")
        else:
            logger.info("停止したタスクは見つかりませんでした")
        
        return len(stalled_tasks)
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='停止したタスクをチェックしてエラーステータスに変更')
    parser.add_argument(
        '--threshold',
        type=int,
        default=10,
        help='何分間更新がなければ停止とみなすか（デフォルト: 10分）'
    )
    
    args = parser.parse_args()
    
    logger.info(f"停止したタスクのチェックを開始します（閾値: {args.threshold}分）")
    stalled_count = check_stalled_tasks(args.threshold)
    logger.info(f"チェック完了: {stalled_count}個のタスクをエラーに変更しました")


if __name__ == "__main__":
    main()