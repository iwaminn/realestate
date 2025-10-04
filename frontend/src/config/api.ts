/**
 * API設定の中央管理
 */

// 環境変数またはデフォルト値を使用
export const API_CONFIG = {
  // Viteの環境変数を使用（.envファイルで設定可能）
  BASE_URL: '',  // 相対パスを使用（vite proxyまたはnginxが適切にルーティング）
  
  // タイムアウト設定
  TIMEOUT: 30000,
  
  // APIパス（bookmarkServiceなどfetch APIで使用）
  PATHS: {
    PROPERTIES_GROUPED: '/api/properties-grouped-by-buildings',
    BOOKMARKS: '/api/bookmarks',
    AUTH: '/api/auth',
    GEOCODING: '/api/geocoding',
    ADMIN: '/api/admin',
  }
};

