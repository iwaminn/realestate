/**
 * API設定の中央管理
 */

// 環境変数またはデフォルト値を使用
export const API_CONFIG = {
  // Viteの環境変数を使用（.envファイルで設定可能）
  BASE_URL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  
  // タイムアウト設定
  TIMEOUT: 30000,
  
  // APIパス（bookmarkServiceなどfetch APIで使用）
  PATHS: {
    PROPERTIES_GROUPED: '/properties-grouped-by-buildings',
    BOOKMARKS: '/bookmarks',
    AUTH: '/auth',
    GEOCODING: '/geocoding',
    ADMIN: '/admin',
  }
};

// 開発環境でのデバッグ用
if (import.meta.env.DEV) {
  console.log('API Base URL:', API_CONFIG.BASE_URL);
}