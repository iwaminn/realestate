"""
キャッシュマネージャーコンポーネント

キャッシュ管理を担当
- ページキャッシュ
- データキャッシュ
- TTL管理
- メモリ管理
"""
import logging
import time
import hashlib
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
import pickle


class CacheManagerComponent:
    """キャッシュ管理を担当するコンポーネント"""
    
    def __init__(self, logger: Optional[logging.Logger] = None,
                 max_size: int = 1000,
                 default_ttl: int = 3600):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
            max_size: 最大キャッシュエントリ数
            default_ttl: デフォルトTTL（秒）
        """
        self.logger = logger or logging.getLogger(__name__)
        self.max_size = max_size
        self.default_ttl = default_ttl
        
        # LRUキャッシュ実装
        self.cache = OrderedDict()
        
        # 統計情報
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        キャッシュからデータを取得
        
        Args:
            key: キャッシュキー
            
        Returns:
            キャッシュされたデータ（存在しない場合はNone）
        """
        if key not in self.cache:
            self.misses += 1
            return None
        
        # TTLチェック
        entry = self.cache[key]
        if self._is_expired(entry):
            del self.cache[key]
            self.misses += 1
            self.logger.debug(f"キャッシュ期限切れ: {key}")
            return None
        
        # LRU: 最近使用したエントリを末尾に移動
        self.cache.move_to_end(key)
        self.hits += 1
        
        return entry['data']
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """
        データをキャッシュに保存
        
        Args:
            key: キャッシュキー
            data: 保存するデータ
            ttl: TTL（秒）
        """
        # キャッシュサイズ制限チェック
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl
        
        self.cache[key] = {
            'data': data,
            'expiry': expiry,
            'created_at': time.time()
        }
        
        self.logger.debug(f"キャッシュ保存: {key} (TTL: {ttl}秒)")
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """
        エントリが期限切れかチェック
        
        Args:
            entry: キャッシュエントリ
            
        Returns:
            期限切れかどうか
        """
        return time.time() > entry['expiry']
    
    def _evict_oldest(self) -> None:
        """最古のエントリを削除"""
        if self.cache:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.evictions += 1
            self.logger.debug(f"キャッシュエビクション: {oldest_key}")
    
    def delete(self, key: str) -> bool:
        """
        キャッシュからエントリを削除
        
        Args:
            key: キャッシュキー
            
        Returns:
            削除成功フラグ
        """
        if key in self.cache:
            del self.cache[key]
            self.logger.debug(f"キャッシュ削除: {key}")
            return True
        return False
    
    def clear(self) -> None:
        """キャッシュをクリア"""
        self.cache.clear()
        self.logger.info("キャッシュをクリアしました")
    
    def cleanup_expired(self) -> int:
        """
        期限切れエントリをクリーンアップ
        
        Returns:
            削除したエントリ数
        """
        expired_keys = []
        current_time = time.time()
        
        for key, entry in self.cache.items():
            if current_time > entry['expiry']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            self.logger.info(f"{len(expired_keys)}個の期限切れエントリを削除")
        
        return len(expired_keys)
    
    def get_page_cache_key(self, url: str, params: Optional[Dict] = None) -> str:
        """
        ページキャッシュ用のキーを生成
        
        Args:
            url: URL
            params: パラメータ
            
        Returns:
            キャッシュキー
        """
        cache_str = url
        if params:
            # パラメータをソートして一貫性のあるキーを生成
            sorted_params = sorted(params.items())
            cache_str += '?' + '&'.join(f"{k}={v}" for k, v in sorted_params)
        
        # MD5ハッシュでキーを生成
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def get_data_cache_key(self, data_type: str, **kwargs) -> str:
        """
        データキャッシュ用のキーを生成
        
        Args:
            data_type: データ種別
            **kwargs: キー生成用のパラメータ
            
        Returns:
            キャッシュキー
        """
        cache_dict = {'type': data_type, **kwargs}
        cache_str = json.dumps(cache_dict, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def cache_page(self, url: str, content: str, 
                  params: Optional[Dict] = None,
                  ttl: Optional[int] = None) -> None:
        """
        ページをキャッシュ
        
        Args:
            url: URL
            content: ページコンテンツ
            params: パラメータ
            ttl: TTL（秒）
        """
        key = self.get_page_cache_key(url, params)
        self.set(key, content, ttl)
    
    def get_cached_page(self, url: str, 
                       params: Optional[Dict] = None) -> Optional[str]:
        """
        キャッシュからページを取得
        
        Args:
            url: URL
            params: パラメータ
            
        Returns:
            キャッシュされたページコンテンツ
        """
        key = self.get_page_cache_key(url, params)
        return self.get(key)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        統計情報を取得
        
        Returns:
            統計情報辞書
        """
        hit_rate = 0.0
        total_requests = self.hits + self.misses
        if total_requests > 0:
            hit_rate = self.hits / total_requests
        
        # メモリ使用量の推定
        memory_usage = 0
        for entry in self.cache.values():
            try:
                memory_usage += len(pickle.dumps(entry['data']))
            except:
                pass
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'evictions': self.evictions,
            'memory_usage_bytes': memory_usage
        }
    
    def log_statistics(self) -> None:
        """統計情報をログ出力"""
        stats = self.get_statistics()
        self.logger.info(
            f"キャッシュ統計: "
            f"サイズ: {stats['size']}/{stats['max_size']}, "
            f"ヒット率: {stats['hit_rate']:.1%}, "
            f"ヒット: {stats['hits']}, ミス: {stats['misses']}, "
            f"エビクション: {stats['evictions']}"
        )