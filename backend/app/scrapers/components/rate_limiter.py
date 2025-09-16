"""
レート制限コンポーネント

スクレイピングのレート制限を管理
- リクエスト間隔の制御
- サイト別レート制限
- 適応的レート調整
- 統計情報の提供
"""
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque


class RateLimiterComponent:
    """レート制限を管理するコンポーネント"""
    
    # デフォルトのレート制限設定（秒）
    DEFAULT_DELAYS = {
        'suumo': 2.0,
        'homes': 2.5,
        'rehouse': 2.0,
        'nomu': 2.0,
        'livable': 2.0,
        'default': 3.0
    }
    
    # 適応的調整の設定
    ADAPTIVE_CONFIG = {
        'min_delay': 1.0,      # 最小遅延
        'max_delay': 10.0,     # 最大遅延
        'increase_rate': 1.5,   # エラー時の増加率
        'decrease_rate': 0.9,   # 成功時の減少率
        'window_size': 100      # 統計ウィンドウサイズ
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None,
                 adaptive: bool = True):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
            adaptive: 適応的レート調整を有効にするか
        """
        self.logger = logger or logging.getLogger(__name__)
        self.adaptive = adaptive
        
        # サイト別の最終リクエスト時刻
        self.last_request_times = {}
        
        # サイト別の現在の遅延設定
        self.current_delays = self.DEFAULT_DELAYS.copy()
        
        # 統計情報
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.response_times = defaultdict(lambda: deque(maxlen=100))
        
        # 適応的調整の履歴
        self.success_history = defaultdict(lambda: deque(maxlen=self.ADAPTIVE_CONFIG['window_size']))
    
    def wait_if_needed(self, site: str) -> float:
        """
        必要に応じて待機
        
        Args:
            site: サイト名
            
        Returns:
            実際に待機した秒数
        """
        delay = self._get_delay(site)
        last_time = self.last_request_times.get(site)
        
        if last_time:
            elapsed = time.time() - last_time
            wait_time = max(0, delay - elapsed)
            
            if wait_time > 0:
                self.logger.debug(f"{site}: {wait_time:.1f}秒待機")
                time.sleep(wait_time)
                actual_wait = wait_time
            else:
                actual_wait = 0.0
        else:
            actual_wait = 0.0
        
        # 最終リクエスト時刻を更新
        self.last_request_times[site] = time.time()
        self.request_counts[site] += 1
        
        return actual_wait
    
    def _get_delay(self, site: str) -> float:
        """
        サイトの遅延設定を取得
        
        Args:
            site: サイト名
            
        Returns:
            遅延秒数
        """
        return self.current_delays.get(site, self.current_delays['default'])
    
    def record_success(self, site: str, response_time: Optional[float] = None) -> None:
        """
        成功を記録
        
        Args:
            site: サイト名
            response_time: レスポンス時間（秒）
        """
        if self.adaptive:
            self.success_history[site].append(True)
            self._adjust_delay(site, success=True)
        
        if response_time:
            self.response_times[site].append(response_time)
            
            # レスポンス時間が極端に遅い場合は警告
            avg_time = sum(self.response_times[site]) / len(self.response_times[site])
            if response_time > avg_time * 3:
                self.logger.warning(
                    f"{site}: レスポンス時間が通常より遅い "
                    f"({response_time:.1f}秒, 平均: {avg_time:.1f}秒)"
                )
    
    def record_error(self, site: str, error_type: str = 'unknown') -> None:
        """
        エラーを記録
        
        Args:
            site: サイト名
            error_type: エラー種別
        """
        self.error_counts[site] += 1
        
        if self.adaptive:
            self.success_history[site].append(False)
            
            # レート制限エラーの場合は大幅に増加
            if error_type == 'rate_limit':
                self._adjust_delay(site, success=False, multiplier=2.0)
            else:
                self._adjust_delay(site, success=False)
    
    def _adjust_delay(self, site: str, success: bool, multiplier: float = 1.0) -> None:
        """
        遅延を適応的に調整
        
        Args:
            site: サイト名
            success: 成功フラグ
            multiplier: 調整倍率
        """
        if not self.adaptive:
            return
        
        current = self._get_delay(site)
        config = self.ADAPTIVE_CONFIG
        
        if success:
            # 成功時は遅延を減少
            new_delay = current * config['decrease_rate']
            new_delay = max(config['min_delay'], new_delay)
        else:
            # エラー時は遅延を増加
            new_delay = current * config['increase_rate'] * multiplier
            new_delay = min(config['max_delay'], new_delay)
        
        if new_delay != current:
            self.current_delays[site] = new_delay
            self.logger.info(
                f"{site}: レート制限を調整 {current:.1f}秒 → {new_delay:.1f}秒"
            )
    
    def get_statistics(self, site: Optional[str] = None) -> Dict[str, Any]:
        """
        統計情報を取得
        
        Args:
            site: サイト名（Noneの場合は全サイト）
            
        Returns:
            統計情報辞書
        """
        if site:
            sites = [site]
        else:
            sites = list(self.request_counts.keys())
        
        stats = {}
        for s in sites:
            success_history = list(self.success_history[s])
            success_rate = 0.0
            if success_history:
                success_rate = sum(success_history) / len(success_history)
            
            avg_response_time = 0.0
            if self.response_times[s]:
                avg_response_time = sum(self.response_times[s]) / len(self.response_times[s])
            
            stats[s] = {
                'request_count': self.request_counts[s],
                'error_count': self.error_counts[s],
                'success_rate': success_rate,
                'current_delay': self._get_delay(s),
                'avg_response_time': avg_response_time
            }
        
        return stats if not site else stats.get(site, {})
    
    def reset_site(self, site: str) -> None:
        """
        サイトの統計をリセット
        
        Args:
            site: サイト名
        """
        self.last_request_times.pop(site, None)
        self.current_delays[site] = self.DEFAULT_DELAYS.get(site, self.DEFAULT_DELAYS['default'])
        self.request_counts[site] = 0
        self.error_counts[site] = 0
        self.response_times[site].clear()
        self.success_history[site].clear()
        
        self.logger.info(f"{site}: レート制限統計をリセット")
    
    def is_throttled(self, site: str) -> bool:
        """
        サイトがスロットル状態かチェック
        
        Args:
            site: サイト名
            
        Returns:
            スロットル状態かどうか
        """
        # 現在の遅延が最大値に近い場合はスロットル状態
        current = self._get_delay(site)
        return current >= self.ADAPTIVE_CONFIG['max_delay'] * 0.8
    
    def get_estimated_time(self, site: str, request_count: int) -> float:
        """
        推定所要時間を計算
        
        Args:
            site: サイト名
            request_count: リクエスト数
            
        Returns:
            推定所要時間（秒）
        """
        delay = self._get_delay(site)
        avg_response = 0.5  # デフォルトレスポンス時間
        
        if self.response_times[site]:
            avg_response = sum(self.response_times[site]) / len(self.response_times[site])
        
        return request_count * (delay + avg_response)