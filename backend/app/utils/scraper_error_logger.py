"""
スクレイパー専用のエラーログ機能
エラー発生時の詳細なコンテキスト情報を記録
"""

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List


class DateTimeEncoder(json.JSONEncoder):
    """datetimeオブジェクトをJSONエンコード可能にするカスタムエンコーダー"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
import os


class ScraperErrorLogger:
    """スクレイパーのエラーを構造化して記録するクラス"""
    
    def __init__(self, scraper_name: str):
        self.scraper_name = scraper_name
        
        # ログディレクトリの作成
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # エラーログファイルのパス
        self.error_json_path = self.log_dir / "scraper_errors.json"
        self.debug_log_path = self.log_dir / "scraper_debug.log"
        
        # 通常のロガー設定（詳細デバッグ用）
        self.logger = logging.getLogger(f"scraper_error.{scraper_name}")
        
        # デバッグログのハンドラー設定
        if not self.logger.handlers:
            handler = logging.FileHandler(self.debug_log_path, encoding='utf-8')
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
    
    def _load_error_history(self) -> List[Dict[str, Any]]:
        """既存のエラー履歴を読み込む"""
        if self.error_json_path.exists():
            try:
                with open(self.error_json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    
    def _save_error_history(self, errors: List[Dict[str, Any]]):
        """エラー履歴を保存（最新1000件のみ保持）"""
        # 最新1000件のみ保持
        if len(errors) > 1000:
            errors = errors[-1000:]
        
        with open(self.error_json_path, 'w', encoding='utf-8') as f:
            json.dump(errors, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
    
    def log_property_error(self, 
                          error_type: str,
                          url: Optional[str] = None,
                          building_name: Optional[str] = None,
                          property_data: Optional[Dict[str, Any]] = None,
                          error: Optional[Exception] = None,
                          phase: str = "unknown"):
        """物件処理エラーを記録
        
        Args:
            error_type: エラータイプ（validation, parsing, saving, detail_page等）
            url: 物件URL
            building_name: 建物名
            property_data: 処理中の物件データ
            error: 発生した例外
            phase: 処理フェーズ（list_parsing, detail_fetching, saving等）
        """
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "scraper": self.scraper_name,
            "error_type": error_type,
            "phase": phase,
            "url": url,
            "building_name": building_name,
            "error_message": str(error) if error else "Unknown error",
            "stack_trace": traceback.format_exc() if error else None,
            "property_data": property_data
        }
        
        # JSONファイルに追記
        errors = self._load_error_history()
        errors.append(error_record)
        self._save_error_history(errors)
        
        # デバッグログにも記録
        self.logger.error(
            f"Property error - Type: {error_type}, Phase: {phase}, "
            f"URL: {url}, Building: {building_name}, Error: {error}"
        )
        if property_data:
            self.logger.debug(f"Property data: {json.dumps(property_data, ensure_ascii=False, cls=DateTimeEncoder)}")
    
    def log_parsing_error(self,
                         url: str,
                         missing_selectors: List[str],
                         found_selectors: Optional[Dict[str, bool]] = None,
                         html_snippet: Optional[str] = None):
        """HTMLパースエラーを記録
        
        Args:
            url: パース対象のURL
            missing_selectors: 見つからなかったセレクタのリスト
            found_selectors: セレクタの検出結果（セレクタ名: 見つかったかどうか）
            html_snippet: デバッグ用のHTML断片
        """
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "scraper": self.scraper_name,
            "error_type": "parsing",
            "url": url,
            "missing_selectors": missing_selectors,
            "found_selectors": found_selectors,
            "html_snippet": html_snippet[:500] if html_snippet else None  # 最初の500文字のみ
        }
        
        # JSONファイルに追記
        errors = self._load_error_history()
        errors.append(error_record)
        self._save_error_history(errors)
        
        # デバッグログ
        self.logger.error(
            f"Parsing error - URL: {url}, "
            f"Missing selectors: {', '.join(missing_selectors)}"
        )
        if found_selectors:
            self.logger.debug(f"Selector check results: {found_selectors}")
    
    def log_validation_error(self,
                           property_data: Dict[str, Any],
                           validation_errors: List[str],
                           url: Optional[str] = None):
        """バリデーションエラーを記録
        
        Args:
            property_data: バリデーション対象のデータ
            validation_errors: バリデーションエラーのリスト
            url: 物件URL
        """
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "scraper": self.scraper_name,
            "error_type": "validation",
            "url": url or property_data.get('url'),
            "building_name": property_data.get('building_name'),
            "validation_errors": validation_errors,
            "property_data": property_data
        }
        
        # JSONファイルに追記
        errors = self._load_error_history()
        errors.append(error_record)
        self._save_error_history(errors)
        
        # デバッグログ
        self.logger.error(
            f"Validation error - URL: {url}, "
            f"Building: {property_data.get('building_name')}, "
            f"Errors: {', '.join(validation_errors)}"
        )
    
    def log_circuit_breaker_activation(self,
                                     error_rate: float,
                                     total_errors: int,
                                     total_attempts: int,
                                     consecutive_errors: int = 0):
        """サーキットブレーカー作動を記録"""
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "scraper": self.scraper_name,
            "error_type": "circuit_breaker",
            "error_rate": error_rate,
            "total_errors": total_errors,
            "total_attempts": total_attempts,
            "consecutive_errors": consecutive_errors
        }
        
        # JSONファイルに追記
        errors = self._load_error_history()
        errors.append(error_record)
        self._save_error_history(errors)
        
        # デバッグログ
        self.logger.critical(
            f"Circuit breaker activated - Error rate: {error_rate:.1%}, "
            f"Errors: {total_errors}/{total_attempts}, "
            f"Consecutive errors: {consecutive_errors}"
        )
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """指定時間内のエラーサマリーを取得"""
        errors = self._load_error_history()
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        
        recent_errors = [
            e for e in errors
            if datetime.fromisoformat(e['timestamp']).timestamp() > cutoff_time
        ]
        
        # エラータイプ別の集計
        error_types = {}
        for error in recent_errors:
            error_type = error.get('error_type', 'unknown')
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # URL別の集計
        url_errors = {}
        for error in recent_errors:
            url = error.get('url')
            if url:
                url_errors[url] = url_errors.get(url, 0) + 1
        
        # 最も多いエラーURL（上位10件）
        top_error_urls = sorted(
            url_errors.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_errors": len(recent_errors),
            "error_types": error_types,
            "top_error_urls": top_error_urls,
            "time_range_hours": hours,
            "scraper": self.scraper_name
        }
    
    def check_selector_changes(self) -> List[Dict[str, Any]]:
        """セレクタ変更の可能性を検出"""
        errors = self._load_error_history()
        parsing_errors = [e for e in errors if e.get('error_type') == 'parsing']
        
        # 最近24時間のパースエラーを分析
        cutoff_time = datetime.now().timestamp() - (24 * 3600)
        recent_parsing_errors = [
            e for e in parsing_errors
            if datetime.fromisoformat(e['timestamp']).timestamp() > cutoff_time
        ]
        
        # セレクタ別のエラー回数を集計
        selector_errors = {}
        for error in recent_parsing_errors:
            for selector in error.get('missing_selectors', []):
                selector_errors[selector] = selector_errors.get(selector, 0) + 1
        
        # 頻繁に失敗しているセレクタを検出
        problematic_selectors = [
            {
                "selector": selector,
                "error_count": count,
                "possible_change": count > 10  # 10回以上失敗している場合
            }
            for selector, count in selector_errors.items()
            if count > 5
        ]
        
        return sorted(problematic_selectors, key=lambda x: x['error_count'], reverse=True)