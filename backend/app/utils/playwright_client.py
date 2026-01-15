"""
Playwrightを使用したブラウザクライアント

JavaScript実行が必要なサイト（AWS WAF対策等）のスクレイピング用
"""

import logging
import time
from typing import Optional
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


class PlaywrightClient:
    """Playwrightを使用したブラウザベースのHTTPクライアント"""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Args:
            headless: ヘッドレスモードで実行するか
            timeout: ページ読み込みタイムアウト（ミリ秒）
        """
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser = None
        self._context = None

    def start(self):
        """ブラウザを起動"""
        if self._browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
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
            # ステルススクリプトを全ページに適用
            self._context.add_init_script(STEALTH_SCRIPT)
            logger.info("Playwrightブラウザを起動しました")
        except Exception as e:
            logger.error(f"Playwrightブラウザの起動に失敗: {e}")
            raise

    def stop(self):
        """ブラウザを停止"""
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("Playwrightブラウザを停止しました")

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
        if self._browser is None:
            self.start()

        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(self.timeout)

            for attempt in range(max_retries + 1):
                # ページに移動（domcontentloadedで高速化）
                logger.debug(f"Playwrightでページを取得 (attempt {attempt + 1}): {url}")
                response = page.goto(url, wait_until='domcontentloaded', timeout=60000)

                if response is None or not response.ok:
                    status = response.status if response else 'None'
                    logger.warning(f"ページ取得失敗: {url}, status={status}")
                    return None

                # HTMLを取得してチャレンジページかチェック
                html = page.content()

                # AWS WAFチャレンジページの検出
                if 'JavaScript is disabled' in html or len(html) < 20000:
                    if attempt < max_retries:
                        logger.info(f"AWS WAFチャレンジを検出、待機してリトライ... (attempt {attempt + 1})")
                        time.sleep(3)  # チャレンジ完了を待つ
                        # ページをリロード
                        page.reload(wait_until='domcontentloaded', timeout=60000)
                        continue
                    else:
                        logger.warning(f"AWS WAFチャレンジを通過できませんでした: {url}")
                        break

                # 正常なページ取得成功
                break

            # 追加の待機（セレクタまたは時間ベース）
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15000)
                except Exception as e:
                    logger.warning(f"セレクタ待機タイムアウト: {wait_selector}, {e}")

            # JavaScript実行完了を待つ
            if wait_time > 0:
                time.sleep(wait_time)

            # HTMLを取得
            html = page.content()
            logger.debug(f"ページ取得成功: {url}, サイズ={len(html)}バイト")
            return html

        except Exception as e:
            logger.error(f"Playwrightでのページ取得エラー: {url}, {e}")
            return None
        finally:
            if page:
                page.close()

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
