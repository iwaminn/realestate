FROM node:18-alpine

# 作業ディレクトリの設定
WORKDIR /app

# package.jsonとpackage-lock.jsonのコピー
COPY frontend/package*.json ./

# 依存関係のインストール
RUN npm ci

# アプリケーションコードのコピー
COPY frontend ./

# ポート3001を公開
EXPOSE 3001

# 開発サーバーの起動
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3001"]