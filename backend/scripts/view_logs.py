#!/usr/bin/env python3
"""
ログビューアスクリプト
構造化されたJSONログを読みやすく表示
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
import re

LOG_DIR = Path("/app/logs")

def format_timestamp(timestamp_str):
    """タイムスタンプを読みやすい形式に変換"""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp_str

def format_log_entry(entry):
    """ログエントリを読みやすく整形"""
    output = []
    
    # ヘッダー
    timestamp = format_timestamp(entry.get('timestamp', ''))
    level = entry.get('level', 'INFO')
    message = entry.get('message', '')
    
    # レベルに応じて色を付ける
    level_colors = {
        'ERROR': '\033[91m',  # 赤
        'WARNING': '\033[93m',  # 黄
        'INFO': '\033[92m',  # 緑
        'DEBUG': '\033[94m',  # 青
    }
    color = level_colors.get(level, '')
    reset = '\033[0m' if color else ''
    
    output.append(f"{color}[{timestamp}] {level}{reset} - {message}")
    
    # 詳細情報
    if 'module' in entry:
        output.append(f"  Module: {entry['module']}.{entry.get('function', '?')}:{entry.get('line', '?')}")
    
    # エラー情報
    if 'exception' in entry:
        exc = entry['exception']
        if exc:
            output.append(f"  Exception: {exc.get('type', '?')} - {exc.get('message', '?')}")
            if exc.get('traceback') and isinstance(exc['traceback'], list):
                output.append("  Traceback:")
                for line in exc['traceback']:
                    output.append(f"    {line.rstrip()}")
    
    # 追加のコンテキスト情報
    exclude_keys = {'timestamp', 'level', 'message', 'module', 'function', 'line', 'exception', 'logger'}
    context = {k: v for k, v in entry.items() if k not in exclude_keys}
    if context:
        output.append("  Context:")
        for key, value in context.items():
            output.append(f"    {key}: {value}")
    
    return '\n'.join(output)

def tail_log(log_file, lines=50, follow=False, filter_level=None, search=None):
    """ログファイルの末尾を表示"""
    if not log_file.exists():
        print(f"ログファイルが見つかりません: {log_file}")
        return
    
    with open(log_file, 'r', encoding='utf-8') as f:
        if not follow:
            # 末尾から指定行数を読む
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if lines < len(all_lines) else all_lines
            
            for line in tail_lines:
                try:
                    entry = json.loads(line.strip())
                    
                    # フィルタリング
                    if filter_level and entry.get('level') != filter_level:
                        continue
                    if search and search.lower() not in json.dumps(entry).lower():
                        continue
                    
                    print(format_log_entry(entry))
                    print("-" * 80)
                except json.JSONDecodeError:
                    print(line.strip())
        else:
            # リアルタイムでフォロー
            import time
            f.seek(0, 2)  # ファイルの末尾に移動
            
            while True:
                line = f.readline()
                if line:
                    try:
                        entry = json.loads(line.strip())
                        
                        # フィルタリング
                        if filter_level and entry.get('level') != filter_level:
                            continue
                        if search and search.lower() not in json.dumps(entry).lower():
                            continue
                        
                        print(format_log_entry(entry))
                        print("-" * 80)
                    except json.JSONDecodeError:
                        print(line.strip())
                else:
                    time.sleep(0.1)

def main():
    parser = argparse.ArgumentParser(description='構造化ログビューア')
    parser.add_argument('log_type', choices=['app', 'errors', 'api', 'database'],
                       help='表示するログタイプ')
    parser.add_argument('-n', '--lines', type=int, default=50,
                       help='表示する行数（デフォルト: 50）')
    parser.add_argument('-f', '--follow', action='store_true',
                       help='ログをリアルタイムで追跡')
    parser.add_argument('-l', '--level', choices=['ERROR', 'WARNING', 'INFO', 'DEBUG'],
                       help='表示するログレベル')
    parser.add_argument('-s', '--search', help='検索文字列')
    
    args = parser.parse_args()
    
    # ログファイルを選択
    log_files = {
        'app': LOG_DIR / 'app.log',
        'errors': LOG_DIR / 'errors.log',
        'api': LOG_DIR / 'api_requests.log',
        'database': LOG_DIR / 'database.log'
    }
    
    log_file = log_files[args.log_type]
    
    try:
        tail_log(log_file, args.lines, args.follow, args.level, args.search)
    except KeyboardInterrupt:
        print("\n終了します")

if __name__ == '__main__':
    main()