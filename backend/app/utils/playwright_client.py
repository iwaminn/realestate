"""
Playwrightを使用したブラウザクライアント

JavaScript実行が必要なサイト（AWS WAF対策等）のスクレイピング用
"""

import asyncio
import logging
import time
import threading
import queue
from typing import Optional, Callable, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ボット検出回避用のステルススクリプト
STEALTH_SCRIPT = """
// webdriver検出の回避
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// Chrome検出
window.chrome = {
    runtime: {},
};

// Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ja-JP', 'ja', 'en-US', 'en'],
});

// Platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});

// Hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});
"""


class PlaywrightWorker:
    """Playwrightを単一スレッドで管理するワーカー"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._task_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._worker_thread = None
        self._running = False
        self._playwright = None
        self._browser = None
        self._context = None
        self._headless = True
        self._timeout = 30000
        self._initialized = True

    def _worker_loop(self):
        """ワーカースレッドのメインループ"""
        logger.info("Playwrightワーカースレッドを開始しました")

        while self._running:
            try:
                # タスクを取得（タイムアウト付き）
                task = self._task_queue.get(timeout=1.0)

                if task is None:  # 終了シグナル
                    break

                func, args, kwargs, result_event = task

                try:
                    result = func(*args, **kwargs)
                    self._result_queue.put((True, result))
                except Exception as e:
                    logger.error(f"Playwrightワーカーでエラー: {e}")
                    self._result_queue.put((False, e))
                finally:
                    result_event.set()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"ワーカーループでエラー: {e}")

        # クリーンアップ
        self._cleanup_browser()
        logger.info("Playwrightワーカースレッドを終了しました")

    def _ensure_worker_running(self):
        """ワーカースレッドが実行中であることを確認"""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="playwright-worker",
                daemon=True
            )
            self._worker_thread.start()

    def _execute_in_worker(self, func: Callable, *args, **kwargs) -> Any:
        """ワーカースレッドで関数を実行"""
        self._ensure_worker_running()

        result_event = threading.Event()
        self._task_queue.put((func, args, kwargs, result_event))

        # 結果を待機（タイムアウト付き）
        if not result_event.wait(timeout=120):
            raise TimeoutError("Playwrightワーカーがタイムアウトしました")

        success, result = self._result_queue.get()
        if success:
            return result
        else:
            raise result

    def _init_browser(self):
        """ブラウザを初期化（ワーカースレッド内で呼び出し）"""
        if self._browser is not None:
            return

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        self._context = self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='ja-JP',
            timezone_id='Asia/Tokyo',
            java_script_enabled=True,
        )
        self._context.add_init_script(STEALTH_SCRIPT)
        logger.info("Playwrightブラウザを起動しました")

    def _cleanup_browser(self):
        """ブラウザをクリーンアップ（ワーカースレッド内で呼び出し）"""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("Playwrightブラウザを停止しました")

    def _fetch_page_impl(self, url: str, wait_selector: str, wait_time: int, max_retries: int) -> Optional[str]:
        """ページを取得（ワーカースレッド内で呼び出し）"""
        self._init_browser()

        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(self._timeout)

            for attempt in range(max_retries + 1):
                logger.debug(f"Playwrightでページを取得 (attempt {attempt + 1}): {url}")
                response = page.goto(url, wait_until='domcontentloaded', timeout=60000)

                if response is None or not response.ok:
                    status = response.status if response else 'None'
                    logger.warning(f"ページ取得失敗: {url}, status={status}")
                    return None

                html = page.content()

                # AWS WAFチャレンジページの検出
                if 'JavaScript is disabled' in html or len(html) < 20000:
                    if attempt < max_retries:
                        logger.info(f"AWS WAFチャレンジを検出、待機してリトライ... (attempt {attempt + 1})")
                        time.sleep(3)
                        page.reload(wait_until='domcontentloaded', timeout=60000)
                        continue
                    else:
                        logger.warning(f"AWS WAFチャレンジを通過できませんでした: {url}")
                        break

                break

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15000)
                except Exception as e:
                    logger.warning(f"セレクタ待機タイムアウト: {wait_selector}, {e}")

            if wait_time > 0:
                time.sleep(wait_time)

            html = page.content()
            logger.debug(f"ページ取得成功: {url}, サイズ={len(html)}バイト")
            return html

        except Exception as e:
            logger.error(f"Playwrightでのページ取得エラー: {url}, {e}")
            return None
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def _restart_browser_impl(self):
        """ブラウザを再起動（ワーカースレッド内で呼び出し）"""
        self._cleanup_browser()
        time.sleep(2)
        self._init_browser()

    def fetch_page(self, url: str, wait_selector: str = None, wait_time: int = 3, max_retries: int = 2) -> Optional[str]:
        """ページを取得してHTMLを返す"""
        return self._execute_in_worker(self._fetch_page_impl, url, wait_selector, wait_time, max_retries)

    def restart_browser(self):
        """ブラウザを再起動"""
        self._execute_in_worker(self._restart_browser_impl)

    def shutdown(self):
        """ワーカーを終了"""
        if self._running:
            self._running = False
            self._task_queue.put(None)  # 終了シグナル
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=10)


# グローバルなワーカーインスタンスを取得
def get_playwright_worker() -> PlaywrightWorker:
    return PlaywrightWorker()


class PlaywrightClient:
    """Playwrightを使用したブラウザベースのHTTPクライアント（互換性用ラッパー）"""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（ミリ秒）
        """
        self._worker = get_playwright_worker()
        self._worker._headless = headless
        self._worker._timeout = timeout

    def start(self):
        """ブラウザを起動（互換性のため、実際の初期化はfetch_page時）"""
        pass

    def stop(self):
        """ブラウザを停止（シングルトンなので何もしない）"""
        pass

    def fetch_page(self, url: str, wait_selector: str = None, wait_time: int = 3, max_retries: int = 2) -> Optional[str]:
        """
        ページを取得してHTMLを返す

        Args:
            url: 取得するURL
            wait_selector: 待機するCSSセレクタ（指定時はこの要素が表示されるまで待機）
            wait_time: 追加の待機時間（秒）
            max_retries: AWS WAFチャレンジ時のリトライ回数

        Returns:
            HTML文字列、エラー時はNone
        """
        return self._worker.fetch_page(url, wait_selector, wait_time, max_retries)

    def restart_browser(self):
        """ブラウザを再起動"""
        self._worker.restart_browser()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@contextmanager
def get_playwright_client(headless: bool = True, timeout: int = 30000):
    """
    PlaywrightClientのコンテキストマネージャー

    使用例:
        with get_playwright_client() as client:
            html = client.fetch_page('https://example.com')
    """
    client = PlaywrightClient(headless=headless, timeout=timeout)
    try:
        client.start()
        yield client
    finally:
        client.stop()
