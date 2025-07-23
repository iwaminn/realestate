#!/usr/bin/env python3
"""
定期実行スケジューラー
不動産データの自動収集・処理を定期実行する
"""

import schedule
import time
import subprocess
import logging
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List
import threading
import signal
import sys

class RealEstateScheduler:
    def __init__(self, config_file='scheduler_config.json'):
        self.config_file = config_file
        self.running = False
        self.threads = []
        
        # ログ設定
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scheduler.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # 設定を読み込み
        self.config = self.load_config()
        
        # シグナルハンドラーを設定
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        default_config = {
            'scraping': {
                'enabled': True,
                'schedule': '0 6 * * *',  # 毎日朝6時
                'description': 'Daily scraping at 6 AM'
            },
            'deduplication': {
                'enabled': True,
                'schedule': '0 7 * * *',  # 毎日朝7時
                'description': 'Daily deduplication at 7 AM'
            },
            'price_history': {
                'enabled': True,
                'schedule': '0 8 * * *',  # 毎日朝8時
                'description': 'Daily price history update at 8 AM'
            },
            'database_cleanup': {
                'enabled': True,
                'schedule': '0 2 * * 0',  # 毎週日曜日午前2時
                'description': 'Weekly database cleanup'
            },
            'backup': {
                'enabled': True,
                'schedule': '0 3 * * *',  # 毎日午前3時
                'description': 'Daily database backup'
            },
            'notification': {
                'enabled': False,
                'email': '',
                'webhook_url': ''
            },
            'limits': {
                'max_runtime_minutes': 60,
                'max_retries': 3,
                'retry_delay_minutes': 5
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # デフォルト設定とマージ
                    default_config.update(user_config)
            except Exception as e:
                self.logger.error(f"設定ファイル読み込みエラー: {e}")
        else:
            # デフォルト設定ファイルを作成
            self.save_config(default_config)
        
        return default_config
    
    def save_config(self, config: Dict):
        """設定ファイルを保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"設定ファイル保存エラー: {e}")
    
    def run_command(self, command: str, description: str, timeout_minutes: int = 30) -> bool:
        """コマンドを実行"""
        self.logger.info(f"📋 実行開始: {description}")
        start_time = datetime.now()
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60
            )
            
            duration = datetime.now() - start_time
            
            if result.returncode == 0:
                self.logger.info(f"✅ 完了: {description} ({duration.total_seconds():.1f}秒)")
                if result.stdout:
                    self.logger.debug(f"出力: {result.stdout}")
                return True
            else:
                self.logger.error(f"❌ 失敗: {description} (終了コード: {result.returncode})")
                if result.stderr:
                    self.logger.error(f"エラー: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error(f"⏰ タイムアウト: {description} ({timeout_minutes}分)")
            return False
        except Exception as e:
            self.logger.error(f"❌ 実行エラー: {description} - {e}")
            return False
    
    def run_with_retry(self, command: str, description: str, max_retries: int = 3) -> bool:
        """リトライ機能付きでコマンドを実行"""
        for attempt in range(max_retries):
            if attempt > 0:
                self.logger.info(f"🔄 リトライ {attempt}/{max_retries}: {description}")
                time.sleep(self.config['limits']['retry_delay_minutes'] * 60)
            
            if self.run_command(command, description, self.config['limits']['max_runtime_minutes']):
                return True
        
        self.logger.error(f"❌ 最終失敗: {description} (最大リトライ回数に到達)")
        return False
    
    def scraping_job(self):
        """スクレイピングジョブ"""
        if not self.config['scraping']['enabled']:
            return
        
        self.logger.info("🏠 スクレイピングジョブ開始")
        
        # 改良版スクレイパーを使用
        success = self.run_with_retry(
            'python3 enhanced_scraper.py',
            'Enhanced scraping job',
            self.config['limits']['max_retries']
        )
        
        if success:
            self.record_job_execution('scraping', True)
            self.send_notification('スクレイピング完了', 'success')
        else:
            self.record_job_execution('scraping', False)
            self.send_notification('スクレイピング失敗', 'error')
    
    def deduplication_job(self):
        """重複排除ジョブ"""
        if not self.config['deduplication']['enabled']:
            return
        
        self.logger.info("🔄 重複排除ジョブ開始")
        
        # 自動重複排除を実行
        success = self.run_with_retry(
            'python3 -c "from deduplication_engine import DeduplicationEngine; engine = DeduplicationEngine(); engine.run_deduplication(auto_merge=True)"',
            'Deduplication job',
            self.config['limits']['max_retries']
        )
        
        if success:
            self.record_job_execution('deduplication', True)
            self.send_notification('重複排除完了', 'success')
        else:
            self.record_job_execution('deduplication', False)
            self.send_notification('重複排除失敗', 'error')
    
    def price_history_job(self):
        """価格履歴更新ジョブ"""
        if not self.config['price_history']['enabled']:
            return
        
        self.logger.info("📈 価格履歴更新ジョブ開始")
        
        success = self.run_with_retry(
            'python3 -c "from price_history_tracker import PriceHistoryTracker; tracker = PriceHistoryTracker(); tracker.update_all_price_history()"',
            'Price history update job',
            self.config['limits']['max_retries']
        )
        
        if success:
            self.record_job_execution('price_history', True)
            self.send_notification('価格履歴更新完了', 'success')
        else:
            self.record_job_execution('price_history', False)
            self.send_notification('価格履歴更新失敗', 'error')
    
    def database_cleanup_job(self):
        """データベースクリーンアップジョブ"""
        if not self.config['database_cleanup']['enabled']:
            return
        
        self.logger.info("🧹 データベースクリーンアップ開始")
        
        try:
            conn = sqlite3.connect('realestate.db')
            cursor = conn.cursor()
            
            # 古い価格履歴を削除（90日以上前）
            cursor.execute('''
                DELETE FROM price_history 
                WHERE updated_at < datetime('now', '-90 days')
            ''')
            
            # 無効なリスティングを削除（30日以上前）
            cursor.execute('''
                DELETE FROM property_listings 
                WHERE is_active = 0 AND updated_at < datetime('now', '-30 days')
            ''')
            
            # VACUUMでデータベースを最適化
            cursor.execute('VACUUM')
            
            conn.commit()
            conn.close()
            
            self.logger.info("✅ データベースクリーンアップ完了")
            self.record_job_execution('database_cleanup', True)
            self.send_notification('データベースクリーンアップ完了', 'success')
            
        except Exception as e:
            self.logger.error(f"❌ データベースクリーンアップエラー: {e}")
            self.record_job_execution('database_cleanup', False)
            self.send_notification('データベースクリーンアップ失敗', 'error')
    
    def backup_job(self):
        """バックアップジョブ"""
        if not self.config['backup']['enabled']:
            return
        
        self.logger.info("💾 バックアップジョブ開始")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        backup_file = f"{backup_dir}/realestate_backup_{timestamp}.db"
        
        success = self.run_command(
            f'cp realestate.db {backup_file}',
            f'Database backup to {backup_file}'
        )
        
        if success:
            # 古いバックアップを削除（7日以上前）
            cutoff_date = datetime.now() - timedelta(days=7)
            for file in os.listdir(backup_dir):
                if file.startswith('realestate_backup_') and file.endswith('.db'):
                    file_path = os.path.join(backup_dir, file)
                    if os.path.getctime(file_path) < cutoff_date.timestamp():
                        os.remove(file_path)
                        self.logger.info(f"🗑️  古いバックアップを削除: {file}")
            
            self.record_job_execution('backup', True)
            self.send_notification('バックアップ完了', 'success')
        else:
            self.record_job_execution('backup', False)
            self.send_notification('バックアップ失敗', 'error')
    
    def record_job_execution(self, job_name: str, success: bool):
        """ジョブ実行記録"""
        try:
            conn = sqlite3.connect('realestate.db')
            cursor = conn.cursor()
            
            # ジョブ実行履歴テーブルがなければ作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS job_execution_log (
                    id INTEGER PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                INSERT INTO job_execution_log (job_name, success)
                VALUES (?, ?)
            ''', (job_name, success))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"ジョブ実行記録エラー: {e}")
    
    def send_notification(self, message: str, level: str = 'info'):
        """通知送信"""
        if not self.config['notification']['enabled']:
            return
        
        # 簡単な通知実装（拡張可能）
        notification_data = {
            'message': message,
            'level': level,
            'timestamp': datetime.now().isoformat(),
            'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
        }
        
        self.logger.info(f"📢 通知: {message}")
        
        # WebhookやEmailの実装はここに追加
        # if self.config['notification']['webhook_url']:
        #     self.send_webhook_notification(notification_data)
    
    def setup_schedules(self):
        """スケジュールを設定"""
        self.logger.info("📅 スケジュール設定中...")
        
        # 各ジョブをスケジュールに登録
        if self.config['scraping']['enabled']:
            schedule.every().day.at("06:00").do(self.scraping_job)
            self.logger.info("📋 スクレイピング: 毎日 06:00")
        
        if self.config['deduplication']['enabled']:
            schedule.every().day.at("07:00").do(self.deduplication_job)
            self.logger.info("🔄 重複排除: 毎日 07:00")
        
        if self.config['price_history']['enabled']:
            schedule.every().day.at("08:00").do(self.price_history_job)
            self.logger.info("📈 価格履歴: 毎日 08:00")
        
        if self.config['database_cleanup']['enabled']:
            schedule.every().sunday.at("02:00").do(self.database_cleanup_job)
            self.logger.info("🧹 DB cleanup: 毎週日曜日 02:00")
        
        if self.config['backup']['enabled']:
            schedule.every().day.at("03:00").do(self.backup_job)
            self.logger.info("💾 バックアップ: 毎日 03:00")
        
        self.logger.info("✅ スケジュール設定完了")
    
    def signal_handler(self, signum, frame):
        """シグナルハンドラー"""
        self.logger.info(f"🛑 シグナル {signum} を受信しました。シャットダウン中...")
        self.running = False
    
    def run(self):
        """スケジューラーを開始"""
        self.logger.info("🚀 不動産スケジューラー開始")
        
        self.setup_schedules()
        self.running = True
        
        # 次回実行時刻を表示
        self.show_next_runs()
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # 1分ごとにチェック
                
        except KeyboardInterrupt:
            self.logger.info("⚠️  キーボード割り込みを検出")
        finally:
            self.logger.info("👋 スケジューラーを停止しました")
    
    def show_next_runs(self):
        """次回実行時刻を表示"""
        jobs = schedule.jobs
        if jobs:
            self.logger.info("⏰ 次回実行予定:")
            for job in jobs:
                self.logger.info(f"  - {job.job_func.__name__}: {job.next_run}")
    
    def run_job_now(self, job_name: str):
        """指定されたジョブを即座に実行"""
        job_methods = {
            'scraping': self.scraping_job,
            'deduplication': self.deduplication_job,
            'price_history': self.price_history_job,
            'database_cleanup': self.database_cleanup_job,
            'backup': self.backup_job
        }
        
        if job_name in job_methods:
            self.logger.info(f"🔧 手動実行: {job_name}")
            job_methods[job_name]()
        else:
            self.logger.error(f"❌ 不明なジョブ: {job_name}")
    
    def show_job_history(self, limit: int = 10):
        """ジョブ実行履歴を表示"""
        try:
            conn = sqlite3.connect('realestate.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT job_name, success, executed_at
                FROM job_execution_log
                ORDER BY executed_at DESC
                LIMIT ?
            ''', (limit,))
            
            history = cursor.fetchall()
            
            if history:
                print(f"\n📊 ジョブ実行履歴 (最新{limit}件):")
                print("ジョブ名          | 結果 | 実行時刻")
                print("-" * 50)
                for job_name, success, executed_at in history:
                    status = "✅" if success else "❌"
                    print(f"{job_name:15s} | {status:4s} | {executed_at}")
            else:
                print("📊 ジョブ実行履歴はありません")
            
            conn.close()
            
        except Exception as e:
            self.logger.error(f"ジョブ履歴取得エラー: {e}")

def main():
    """メイン実行関数"""
    scheduler = RealEstateScheduler()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'run':
            scheduler.run()
        elif command == 'run-job' and len(sys.argv) > 2:
            scheduler.run_job_now(sys.argv[2])
        elif command == 'history':
            scheduler.show_job_history()
        elif command == 'next':
            scheduler.setup_schedules()
            scheduler.show_next_runs()
        else:
            print("使用方法:")
            print("  python3 scheduler.py run           # スケジューラーを開始")
            print("  python3 scheduler.py run-job JOB   # 指定ジョブを即座に実行")
            print("  python3 scheduler.py history       # ジョブ実行履歴を表示")
            print("  python3 scheduler.py next          # 次回実行予定を表示")
            print()
            print("利用可能なジョブ:")
            print("  - scraping")
            print("  - deduplication")
            print("  - price_history")
            print("  - database_cleanup")
            print("  - backup")
    else:
        print("📅 不動産スケジューラー")
        print("=" * 30)
        print("使用方法:")
        print("  python3 scheduler.py run           # スケジューラーを開始")
        print("  python3 scheduler.py run-job JOB   # 指定ジョブを即座に実行")
        print("  python3 scheduler.py history       # ジョブ実行履歴を表示")
        print("  python3 scheduler.py next          # 次回実行予定を表示")

if __name__ == '__main__':
    main()