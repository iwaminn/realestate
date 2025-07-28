"""デバッグ用のファイルログ出力"""

import os
from datetime import datetime

DEBUG_LOG_FILE = "/tmp/scraper_debug.log"

def debug_log(message: str):
    """デバッグメッセージをファイルに出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DEBUG_LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()

def clear_debug_log():
    """デバッグログをクリア"""
    if os.path.exists(DEBUG_LOG_FILE):
        os.remove(DEBUG_LOG_FILE)