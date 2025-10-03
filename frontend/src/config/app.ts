/**
 * アプリケーション設定
 */
export const APP_CONFIG = {
  // アプリケーション名（環境変数から取得、なければデフォルト値）
  APP_NAME: import.meta.env.VITE_APP_NAME || '都心マンション価格チェッカー',

  // サブタイトル
  APP_DESCRIPTION: '東京23区の中古マンション情報を検索',

  // HTMLタイトル（ブラウザのタブに表示される）
  HTML_TITLE: import.meta.env.VITE_APP_NAME || '都心マンション価格チェッカー',

  // その他の設定値
  VERSION: '2.0',
} as const;