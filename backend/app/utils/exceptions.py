"""共通の例外クラス"""


class TaskPausedException(Exception):
    """タスクが一時停止された場合の例外"""
    pass


class TaskCancelledException(Exception):
    """タスクがキャンセルされた場合の例外"""
    pass


class MaintenanceException(Exception):
    """サイトがメンテナンス中の場合の例外"""
    pass


class PropertyTypeNotSupportedError(Exception):
    """対象外の物件タイプの場合の例外（タウンハウス、一戸建てなど）"""
    pass