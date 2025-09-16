"""
進捗トラッカーコンポーネント

スクレイピング進捗を管理
- 進捗状況の追跡
- 統計情報の収集
- 時間推定
- ログ出力
"""
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict


class ProgressTrackerComponent:
    """進捗管理を担当するコンポーネント"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # 全体進捗
        self.start_time = None
        self.total_items = 0
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.skipped_items = 0
        
        # フェーズ別進捗
        self.phases = {}
        self.current_phase = None
        
        # 統計情報
        self.item_processing_times = []
        self.phase_times = defaultdict(list)
        
        # 詳細カウント
        self.detail_counts = {
            'new': 0,
            'updated': 0,
            'unchanged': 0,
            'error': 0
        }
    
    def start(self, total_items: Optional[int] = None, phase: str = 'main') -> None:
        """
        進捗追跡を開始
        
        Args:
            total_items: 処理予定アイテム数
            phase: フェーズ名
        """
        self.start_time = time.time()
        self.total_items = total_items or 0
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.skipped_items = 0
        
        self.start_phase(phase)
        
        if total_items:
            self.logger.info(f"処理開始: {total_items}件のアイテムを処理予定")
        else:
            self.logger.info("処理開始")
    
    def start_phase(self, phase: str) -> None:
        """
        フェーズを開始
        
        Args:
            phase: フェーズ名
        """
        # 現在のフェーズを終了
        if self.current_phase:
            self.end_phase()
        
        self.current_phase = phase
        self.phases[phase] = {
            'start_time': time.time(),
            'end_time': None,
            'items': 0,
            'success': 0,
            'failed': 0
        }
        
        self.logger.info(f"フェーズ開始: {phase}")
    
    def end_phase(self) -> None:
        """現在のフェーズを終了"""
        if not self.current_phase:
            return
        
        phase_data = self.phases[self.current_phase]
        phase_data['end_time'] = time.time()
        elapsed = phase_data['end_time'] - phase_data['start_time']
        
        self.phase_times[self.current_phase].append(elapsed)
        
        self.logger.info(
            f"フェーズ終了: {self.current_phase} "
            f"(処理時間: {elapsed:.1f}秒, "
            f"成功: {phase_data['success']}, "
            f"失敗: {phase_data['failed']})"
        )
        
        self.current_phase = None
    
    def update(self, success: bool = True, 
              detail_type: Optional[str] = None,
              item_name: Optional[str] = None) -> None:
        """
        進捗を更新
        
        Args:
            success: 成功フラグ
            detail_type: 詳細種別（new/updated/unchanged/error）
            item_name: アイテム名（ログ用）
        """
        item_start = time.time()
        
        self.processed_items += 1
        
        if success:
            self.successful_items += 1
            if self.current_phase:
                self.phases[self.current_phase]['success'] += 1
        else:
            self.failed_items += 1
            if self.current_phase:
                self.phases[self.current_phase]['failed'] += 1
        
        if detail_type and detail_type in self.detail_counts:
            self.detail_counts[detail_type] += 1
        
        # 処理時間を記録
        if len(self.item_processing_times) > 0:
            last_time = self.item_processing_times[-1][1]
            processing_time = item_start - last_time
            self.item_processing_times.append((item_start, item_start, processing_time))
        else:
            self.item_processing_times.append((item_start, item_start, 0))
        
        # 進捗ログ
        if self.total_items > 0 and self.processed_items % max(1, self.total_items // 20) == 0:
            self._log_progress()
        
        # アイテム名がある場合は詳細ログ
        if item_name:
            status = "成功" if success else "失敗"
            detail = f" ({detail_type})" if detail_type else ""
            self.logger.debug(f"処理{status}: {item_name}{detail}")
    
    def skip(self, count: int = 1, reason: Optional[str] = None) -> None:
        """
        スキップを記録
        
        Args:
            count: スキップ数
            reason: スキップ理由
        """
        self.skipped_items += count
        self.processed_items += count
        
        if reason:
            self.logger.info(f"{count}件をスキップ: {reason}")
    
    def _log_progress(self) -> None:
        """進捗状況をログ出力"""
        if self.total_items > 0:
            percentage = (self.processed_items / self.total_items) * 100
            remaining = self.total_items - self.processed_items
            
            # 推定残り時間
            elapsed = time.time() - self.start_time
            if self.processed_items > 0:
                avg_time = elapsed / self.processed_items
                eta = avg_time * remaining
                eta_str = str(timedelta(seconds=int(eta)))
            else:
                eta_str = "不明"
            
            self.logger.info(
                f"進捗: {self.processed_items}/{self.total_items} ({percentage:.1f}%) "
                f"成功: {self.successful_items}, 失敗: {self.failed_items}, "
                f"スキップ: {self.skipped_items}, 残り時間: {eta_str}"
            )
        else:
            self.logger.info(
                f"進捗: {self.processed_items}件処理 "
                f"(成功: {self.successful_items}, 失敗: {self.failed_items}, "
                f"スキップ: {self.skipped_items})"
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        統計情報を取得
        
        Returns:
            統計情報辞書
        """
        elapsed = 0.0
        if self.start_time:
            elapsed = time.time() - self.start_time
        
        # 平均処理時間
        avg_time = 0.0
        if self.item_processing_times:
            times = [t[2] for t in self.item_processing_times if t[2] > 0]
            if times:
                avg_time = sum(times) / len(times)
        
        # 成功率
        success_rate = 0.0
        if self.processed_items > 0:
            success_rate = self.successful_items / self.processed_items
        
        return {
            'elapsed_time': elapsed,
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'successful_items': self.successful_items,
            'failed_items': self.failed_items,
            'skipped_items': self.skipped_items,
            'success_rate': success_rate,
            'avg_processing_time': avg_time,
            'detail_counts': self.detail_counts.copy(),
            'phases': self.phases.copy()
        }
    
    def finish(self) -> Dict[str, Any]:
        """
        進捗追跡を終了
        
        Returns:
            最終統計情報
        """
        # 現在のフェーズを終了
        if self.current_phase:
            self.end_phase()
        
        stats = self.get_statistics()
        elapsed = stats['elapsed_time']
        
        # 最終サマリーをログ出力
        self.logger.info("=" * 60)
        self.logger.info("処理完了サマリー")
        self.logger.info("-" * 60)
        self.logger.info(f"処理時間: {str(timedelta(seconds=int(elapsed)))}")
        self.logger.info(f"処理件数: {self.processed_items}件")
        self.logger.info(f"成功: {self.successful_items}件")
        self.logger.info(f"失敗: {self.failed_items}件")
        self.logger.info(f"スキップ: {self.skipped_items}件")
        self.logger.info(f"成功率: {stats['success_rate']:.1%}")
        
        if self.detail_counts['new'] > 0 or self.detail_counts['updated'] > 0:
            self.logger.info("-" * 60)
            self.logger.info(f"新規: {self.detail_counts['new']}件")
            self.logger.info(f"更新: {self.detail_counts['updated']}件")
            self.logger.info(f"変更なし: {self.detail_counts['unchanged']}件")
        
        self.logger.info("=" * 60)
        
        return stats
    
    def estimate_remaining_time(self) -> Optional[float]:
        """
        残り時間を推定
        
        Returns:
            推定残り時間（秒）
        """
        if not self.start_time or self.processed_items == 0:
            return None
        
        if self.total_items == 0:
            return None
        
        elapsed = time.time() - self.start_time
        avg_time = elapsed / self.processed_items
        remaining = self.total_items - self.processed_items
        
        return avg_time * remaining