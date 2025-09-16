"""
エラーハンドラーコンポーネント

エラー処理と異常検知を担当
- エラーの分類と記録
- リトライ判定
- 異常検知とアラート
- 統計情報の管理
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from collections import defaultdict
import traceback


class ErrorHandlerComponent:
    """エラー処理を担当するコンポーネント"""
    
    # エラー種別
    ERROR_TYPES = {
        'network': 'ネットワークエラー',
        'parse': 'パースエラー',
        'validation': 'バリデーションエラー',
        'database': 'データベースエラー',
        'rate_limit': 'レート制限エラー',
        'unknown': '不明なエラー'
    }
    
    # リトライ可能なエラー種別
    RETRYABLE_ERRORS = {'network', 'rate_limit'}
    
    def __init__(self, logger: Optional[logging.Logger] = None,
                 max_consecutive_errors: int = 5,
                 error_rate_threshold: float = 0.5):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
            max_consecutive_errors: 最大連続エラー数
            error_rate_threshold: エラー率閾値
        """
        self.logger = logger or logging.getLogger(__name__)
        self.max_consecutive_errors = max_consecutive_errors
        self.error_rate_threshold = error_rate_threshold
        
        # エラー統計
        self.error_counts = defaultdict(int)
        self.consecutive_errors = 0
        self.total_attempts = 0
        self.total_errors = 0
        
        # フィールドエラー追跡
        self.field_errors = defaultdict(lambda: defaultdict(int))
        self.missing_elements = defaultdict(int)
        self.missing_element_consecutive = defaultdict(int)
    
    def handle_error(self, error: Exception, 
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        エラーを処理
        
        Args:
            error: 例外オブジェクト
            context: エラーコンテキスト
            
        Returns:
            エラー情報辞書
        """
        error_type = self._classify_error(error)
        error_info = {
            'type': error_type,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'context': context or {}
        }
        
        # エラー統計を更新
        self.error_counts[error_type] += 1
        self.total_errors += 1
        self.consecutive_errors += 1
        
        # ログ出力
        log_message = f"{self.ERROR_TYPES.get(error_type, '不明')}: {error}"
        if context:
            log_message += f" (コンテキスト: {context})"
        
        if error_type in self.RETRYABLE_ERRORS:
            self.logger.warning(log_message)
        else:
            self.logger.error(log_message, exc_info=True)
        
        # 異常検知
        if self._should_stop():
            error_info['should_stop'] = True
            self.logger.critical("エラー率が閾値を超えました。処理を停止します。")
        
        return error_info
    
    def _classify_error(self, error: Exception) -> str:
        """
        エラーを分類
        
        Args:
            error: 例外オブジェクト
            
        Returns:
            エラー種別
        """
        error_name = error.__class__.__name__
        error_message = str(error).lower()
        
        # ネットワークエラー
        if any(x in error_name for x in ['Request', 'Connection', 'Timeout', 'HTTP']):
            return 'network'
        
        # パースエラー
        if any(x in error_name for x in ['Parse', 'Attribute', 'Key', 'Index']):
            return 'parse'
        
        # バリデーションエラー
        if any(x in error_name for x in ['Validation', 'Value', 'Type']):
            return 'validation'
        
        # データベースエラー
        if any(x in error_name for x in ['SQL', 'Database', 'Integrity']):
            return 'database'
        
        # レート制限
        if '429' in error_message or 'rate' in error_message:
            return 'rate_limit'
        
        return 'unknown'
    
    def record_success(self) -> None:
        """成功を記録"""
        self.consecutive_errors = 0
        self.total_attempts += 1
    
    def record_attempt(self) -> None:
        """試行を記録"""
        self.total_attempts += 1
    
    def should_retry(self, error_type: str, attempt: int, max_retries: int = 3) -> bool:
        """
        リトライすべきか判定
        
        Args:
            error_type: エラー種別
            attempt: 現在の試行回数
            max_retries: 最大リトライ回数
            
        Returns:
            リトライすべきかどうか
        """
        if attempt >= max_retries:
            return False
        
        if error_type not in self.RETRYABLE_ERRORS:
            return False
        
        if self._should_stop():
            return False
        
        return True
    
    def _should_stop(self) -> bool:
        """
        処理を停止すべきか判定
        
        Returns:
            停止すべきかどうか
        """
        # 連続エラーチェック
        if self.consecutive_errors >= self.max_consecutive_errors:
            return True
        
        # エラー率チェック
        if self.total_attempts >= 10:  # 最低10回試行後に判定
            error_rate = self.total_errors / self.total_attempts
            if error_rate >= self.error_rate_threshold:
                return True
        
        return False
    
    def record_field_error(self, field_name: str, 
                          error_type: str = 'extraction',
                          is_critical: bool = False) -> None:
        """
        フィールドエラーを記録
        
        Args:
            field_name: フィールド名
            error_type: エラー種別
            is_critical: 致命的エラーかどうか
        """
        self.field_errors[field_name][error_type] += 1
        
        if is_critical:
            self.logger.error(f"致命的フィールドエラー: {field_name} ({error_type})")
    
    def track_missing_element(self, element_name: str, is_critical: bool = False) -> None:
        """
        欠落要素を追跡
        
        Args:
            element_name: 要素名
            is_critical: 致命的かどうか
        """
        self.missing_elements[element_name] += 1
        self.missing_element_consecutive[element_name] += 1
        
        # 連続欠落チェック
        consecutive = self.missing_element_consecutive[element_name]
        
        if consecutive >= 3:
            self.logger.warning(
                f"要素 '{element_name}' が{consecutive}回連続で欠落しています"
            )
        
        if is_critical and consecutive >= 5:
            self.logger.critical(
                f"致命的要素 '{element_name}' が{consecutive}回連続で欠落。"
                "HTML構造が変更された可能性があります。"
            )
    
    def reset_missing_element_tracking(self, element_name: str) -> None:
        """
        欠落要素の連続カウントをリセット
        
        Args:
            element_name: 要素名
        """
        self.missing_element_consecutive[element_name] = 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        統計情報を取得
        
        Returns:
            統計情報辞書
        """
        error_rate = 0.0
        if self.total_attempts > 0:
            error_rate = self.total_errors / self.total_attempts
        
        return {
            'total_attempts': self.total_attempts,
            'total_errors': self.total_errors,
            'error_rate': error_rate,
            'consecutive_errors': self.consecutive_errors,
            'error_counts': dict(self.error_counts),
            'field_errors': {
                field: dict(errors) 
                for field, errors in self.field_errors.items()
            },
            'missing_elements': dict(self.missing_elements)
        }
    
    def reset_statistics(self) -> None:
        """統計情報をリセット"""
        self.error_counts.clear()
        self.consecutive_errors = 0
        self.total_attempts = 0
        self.total_errors = 0
        self.field_errors.clear()
        self.missing_elements.clear()
        self.missing_element_consecutive.clear()
        
        self.logger.info("エラー統計をリセットしました")