"""共通の例外クラス"""


class TaskPausedException(Exception):
    """タスクが一時停止された場合の例外"""
    pass


class TaskCancelledException(Exception):
    """タスクがキャンセルされた場合の例外"""
    pass