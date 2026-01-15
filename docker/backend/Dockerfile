FROM python:3.10-slim

# 作業ディレクトリの設定
WORKDIR /app

# システムパッケージの更新とインストール
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    sqlite3 \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Google Chromeのインストール（新しい方法）
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriverのインストール（新しいAPIを使用）
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1) \
    && if [ "$CHROME_VERSION" -ge 115 ]; then \
        # Chrome 115以降は新しいAPIを使用
        CHROMEDRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
            python3 -c "import sys, json; data = json.load(sys.stdin); print(data['channels']['Stable']['downloads']['chromedriver'][0]['url'])") \
        && wget -q "$CHROMEDRIVER_URL" -O chromedriver.zip; \
    else \
        # Chrome 114以前は旧APIを使用
        CHROMEDRIVER_VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
        && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" -O chromedriver.zip; \
    fi \
    && unzip chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver*/chromedriver /usr/local/bin/ \
    && rm -rf chromedriver.zip /tmp/chromedriver* \
    && chmod +x /usr/local/bin/chromedriver

# Poetryのインストール
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Poetryの設定（仮想環境を作成しない）
RUN poetry config virtualenvs.create false

# 依存関係ファイルのコピー
COPY pyproject.toml poetry.lock ./

# 依存関係のインストール（プロジェクト自体はインストールしない）
RUN poetry install --no-interaction --no-ansi --no-root

# Playwrightブラウザのインストール（Chromiumのみ）
RUN playwright install chromium && playwright install-deps chromium

# アプリケーションコードのコピー
COPY backend ./backend

# データベースディレクトリの作成
RUN mkdir -p /app/data /app/logs

# ポート8000を公開
EXPOSE 8000

# デフォルトコマンド
CMD ["poetry", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]