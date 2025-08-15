# ログシステム統一設計案

## 現状の問題
- 通常ログ（Python logging）と管理画面用ログ（メソッドオーバーライド）の2系統が存在
- 使い分けが不明確で、メンテナンスが困難

## 提案する統一設計

### 1. Python loggingシステムに統一
```python
class BaseScraper:
    def _setup_logger(self):
        logger = logging.getLogger(f'scraper.{self.source_site}')
        
        # コンソールハンドラー（既存）
        console_handler = logging.StreamHandler()
        logger.addHandler(console_handler)
        
        # 管理画面用ハンドラー（新規）
        if hasattr(self, 'admin_handler'):
            logger.addHandler(self.admin_handler)
        
        return logger
```

### 2. 管理画面用カスタムハンドラー
```python
class AdminLogHandler(logging.Handler):
    """管理画面にログを送信するハンドラー"""
    
    def __init__(self, task_id, scraping_tasks):
        super().__init__()
        self.task_id = task_id
        self.scraping_tasks = scraping_tasks
    
    def emit(self, record):
        # ログレベルに応じて適切なリストに追加
        if record.levelno >= logging.ERROR:
            log_type = "error_logs"
        elif record.levelno >= logging.WARNING:
            log_type = "warning_logs"
        else:
            log_type = "logs"
        
        # scraping_tasksに追加
        if self.task_id in self.scraping_tasks:
            if log_type not in self.scraping_tasks[self.task_id]:
                self.scraping_tasks[self.task_id][log_type] = []
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "message": record.getMessage(),
                "level": record.levelname,
                **getattr(record, 'extra', {})
            }
            self.scraping_tasks[self.task_id][log_type].append(log_entry)
```

### 3. 使用方法の統一
```python
# 統一された使用方法
self.logger.info("新規物件登録", extra={"url": url, "price": price})
self.logger.warning("価格不一致", extra={"url": url, "list_price": list_price})
self.logger.error("保存失敗", extra={"url": url, "error": str(e)})
```

## メリット
1. **一貫性**: すべてのログが同じインターフェースを使用
2. **拡張性**: 新しいハンドラーを追加するだけで出力先を増やせる
3. **標準準拠**: Python標準のloggingモジュールを活用
4. **保守性**: コードの複雑性が減少

## 実装手順
1. AdminLogHandlerクラスを作成
2. admin/scraping.pyでハンドラーをセットアップ
3. base_scraper.pyのlog_warning/log_errorメソッドを削除
4. 既存のログ呼び出しをlogger.info/warning/errorに置き換え