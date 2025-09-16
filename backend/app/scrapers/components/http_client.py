"""
HTTPクライアントコンポーネント

HTTP通信に関する処理を担当
- ページ取得
- リトライ処理
- エラーハンドリング
- セッション管理
"""
import requests
from typing import Optional, Tuple, Dict, Any, Callable
import logging
import time
from urllib.parse import urljoin


class HttpClientComponent:
    """HTTP通信を担当するコンポーネント"""
    
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None,
                 timeout: int = 30,
                 retry_count: int = 3,
                 retry_delay: float = 2.0):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
            timeout: タイムアウト秒数
            retry_count: リトライ回数
            retry_delay: リトライ間隔（秒）
        """
        self.logger = logger or logging.getLogger(__name__)
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # セッション作成
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
    
    def fetch(self, url: str, 
             method: str = 'GET',
             headers: Optional[Dict[str, str]] = None,
             params: Optional[Dict[str, Any]] = None,
             data: Optional[Dict[str, Any]] = None,
             check_content: Optional[Callable[[str], bool]] = None
             ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        URLからコンテンツを取得
        
        Args:
            url: 取得するURL
            method: HTTPメソッド
            headers: 追加ヘッダー
            params: URLパラメータ
            data: POSTデータ
            check_content: コンテンツ検証関数
            
        Returns:
            (content, error_info) のタプル
            - content: 取得したコンテンツ（成功時）
            - error_info: エラー情報（失敗時）
        """
        # ヘッダーのマージ
        req_headers = self.session.headers.copy()
        if headers:
            req_headers.update(headers)
        
        last_error = None
        
        for attempt in range(self.retry_count):
            try:
                # リクエスト送信
                self.logger.debug(f"HTTP {method} リクエスト送信: {url} (試行 {attempt + 1}/{self.retry_count})")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    params=params,
                    data=data,
                    timeout=self.timeout
                )
                
                # ステータスコードチェック
                if response.status_code == 404:
                    return None, {
                        'type': 'http_404',
                        'status_code': 404,
                        'url': url,
                        'message': 'Page not found'
                    }
                
                if response.status_code == 503:
                    return None, {
                        'type': 'http_503',
                        'status_code': 503,
                        'url': url,
                        'message': 'Service unavailable'
                    }
                
                response.raise_for_status()
                
                # エンコーディング設定
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding or 'utf-8'
                
                content = response.text
                
                # コンテンツ検証
                if check_content and not check_content(content):
                    raise ValueError("Content validation failed")
                
                self.logger.debug(f"コンテンツ取得成功: {url} (サイズ: {len(content)} bytes)")
                return content, None
                
            except requests.exceptions.Timeout:
                last_error = {
                    'type': 'timeout',
                    'url': url,
                    'message': f'Request timeout after {self.timeout} seconds'
                }
                
            except requests.exceptions.ConnectionError as e:
                last_error = {
                    'type': 'connection_error',
                    'url': url,
                    'message': str(e)
                }
                
            except requests.exceptions.HTTPError as e:
                last_error = {
                    'type': 'http_error',
                    'status_code': e.response.status_code if e.response else None,
                    'url': url,
                    'message': str(e)
                }
                
            except Exception as e:
                last_error = {
                    'type': 'unknown_error',
                    'url': url,
                    'message': str(e)
                }
            
            # リトライ前の待機
            if attempt < self.retry_count - 1:
                self.logger.warning(f"リトライ待機中 ({self.retry_delay}秒): {url}")
                time.sleep(self.retry_delay)
        
        # 全試行失敗
        self.logger.error(f"コンテンツ取得失敗 (全{self.retry_count}回失敗): {url}")
        return None, last_error
    
    def close(self):
        """セッションを閉じる"""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        """コンテキストマネージャーのエントリ"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャーの終了"""
        self.close()
    
    def set_header(self, key: str, value: str):
        """デフォルトヘッダーを設定"""
        self.session.headers[key] = value
    
    def get_absolute_url(self, base_url: str, relative_url: str) -> str:
        """相対URLを絶対URLに変換"""
        return urljoin(base_url, relative_url)