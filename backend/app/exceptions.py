"""
カスタム例外クラスの定義
"""

class TaskPausedException(Exception):
    """タスクが一時停止された場合の例外"""
    pass

class TaskCancelledException(Exception):
    """タスクがキャンセルされた場合の例外"""
    pass

class MaintenanceException(Exception):
    """サイトがメンテナンス中の場合の例外"""
    pass

class ScraperAlertException(Exception):
    """スクレイパーアラートが発生した場合の例外"""
    pass