"""
サーバーサイドキャッシュユーティリティ
"""
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
import threading


class SimpleCache:
    """シンプルなメモリキャッシュ（スレッドセーフ）"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """キャッシュから値を取得"""
        with self._lock:
            if key not in self._cache:
                return None

            cache_entry = self._cache[key]

            # 有効期限チェック
            if cache_entry['expires_at'] and datetime.now() > cache_entry['expires_at']:
                del self._cache[key]
                return None

            return cache_entry['value']

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """キャッシュに値を設定"""
        with self._lock:
            expires_at = None
            if ttl_seconds:
                expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

            self._cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': datetime.now()
            }

    def delete(self, key: str):
        """キャッシュから値を削除"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """すべてのキャッシュをクリア"""
        with self._lock:
            self._cache.clear()

    def clear_pattern(self, pattern: str):
        """パターンに一致するキーをすべて削除"""
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]


# グローバルキャッシュインスタンス
_global_cache = SimpleCache()


def get_cache() -> SimpleCache:
    """グローバルキャッシュインスタンスを取得"""
    return _global_cache


def clear_recent_updates_cache():
    """直近更新情報のキャッシュをクリア"""
    cache = get_cache()
    cache.clear_pattern('recent_updates')
    print(f"[{datetime.now()}] キャッシュクリア: recent_updates")
