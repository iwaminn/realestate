"""
ロギングユーティリティ
アプリケーション全体で使用する統一されたロガーを提供
"""

import logging
import logging.handlers
import os
import json
from datetime import datetime
from pathlib import Path
import traceback
from typing import Any, Dict, Optional

# ログディレクトリの設定
LOG_DIR = Path("/app/logs")
if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログファイルのパス
GENERAL_LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"
API_LOG_FILE = LOG_DIR / "api_requests.log"
DB_LOG_FILE = LOG_DIR / "database.log"


class StructuredFormatter(logging.Formatter):
    """構造化されたログフォーマッター（JSON形式）"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # エラーの場合は追加情報を含める
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info) if record.exc_info else None
            }
        
        # カスタム属性があれば追加
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName", 
                          "levelname", "levelno", "lineno", "module", "msecs", 
                          "pathname", "process", "processName", "relativeCreated", 
                          "thread", "threadName", "exc_info", "exc_text", "stack_info",
                          "getMessage"]:
                log_data[key] = value
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_logger(
    name: str,
    log_file: Path,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_json: bool = True
) -> logging.Logger:
    """ロガーをセットアップ"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 既存のハンドラーをクリア
    logger.handlers.clear()
    
    # ファイルハンドラー（ローテーション付き）
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    
    # フォーマッターを設定
    if use_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # コンソールハンドラー（開発環境用）
    if os.getenv("DEBUG", "false").lower() == "true":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


# アプリケーション用ロガー
app_logger = setup_logger("app", GENERAL_LOG_FILE, level=logging.DEBUG)
error_logger = setup_logger("errors", ERROR_LOG_FILE, level=logging.ERROR)
api_logger = setup_logger("api", API_LOG_FILE)
db_logger = setup_logger("database", DB_LOG_FILE)


class LogContext:
    """ログコンテキストマネージャー"""
    
    def __init__(self, logger: logging.Logger, operation: str, **kwargs):
        self.logger = logger
        self.operation = operation
        self.context = kwargs
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        self.logger.info(f"{self.operation} started", extra={
            "operation": self.operation,
            "context": self.context,
            "start_time": self.start_time.isoformat()
        })
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.utcnow()
        duration = (end_time - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.info(f"{self.operation} completed", extra={
                "operation": self.operation,
                "context": self.context,
                "duration_seconds": duration,
                "status": "success"
            })
        else:
            self.logger.error(f"{self.operation} failed", extra={
                "operation": self.operation,
                "context": self.context,
                "duration_seconds": duration,
                "status": "error",
                "error_type": exc_type.__name__,
                "error_message": str(exc_val)
            }, exc_info=True)
            # エラーログにも記録
            error_logger.error(f"{self.operation} failed", extra={
                "operation": self.operation,
                "context": self.context,
                "error_type": exc_type.__name__,
                "error_message": str(exc_val),
                "traceback": traceback.format_tb(exc_tb)
            })
        
        return False  # 例外を再発生させる


def log_api_request(request, response=None, error=None):
    """APIリクエストをログに記録"""
    log_data = {
        "method": request.method,
        "path": str(request.url.path),
        "query_params": dict(request.query_params),
        "client_host": request.client.host if request.client else None,
    }
    
    if response:
        log_data["status_code"] = response.status_code
        api_logger.info("API request", extra=log_data)
    elif error:
        log_data["error"] = str(error)
        api_logger.error("API request failed", extra=log_data, exc_info=True)


def log_database_operation(operation: str, table: str, affected_rows: int = 0, error: Optional[Exception] = None):
    """データベース操作をログに記録"""
    log_data = {
        "operation": operation,
        "table": table,
        "affected_rows": affected_rows
    }
    
    if error:
        db_logger.error(f"Database operation failed: {operation} on {table}", 
                       extra=log_data, exc_info=True)
    else:
        db_logger.info(f"Database operation: {operation} on {table}", extra=log_data)


# ログを読みやすくするユーティリティ関数
def read_json_logs(log_file: Path, tail: int = 100) -> list[Dict[str, Any]]:
    """JSON形式のログファイルを読み込み"""
    logs = []
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-tail:]:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    return logs


def search_logs(log_file: Path, **criteria) -> list[Dict[str, Any]]:
    """ログを検索"""
    logs = []
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line.strip())
                    match = True
                    for key, value in criteria.items():
                        if key not in log_entry or log_entry[key] != value:
                            match = False
                            break
                    if match:
                        logs.append(log_entry)
                except json.JSONDecodeError:
                    continue
    return logs