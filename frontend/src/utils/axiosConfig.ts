import axios from 'axios';

// APIのベースURL（本番環境では相対パス、開発環境ではlocalhost）
// Viteの環境変数を使用
axios.defaults.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Axiosのインターセプターを設定
axios.interceptors.request.use(
  (config) => {
    // ユーザー認証トークンを優先（Google OAuth用）
    const userToken = localStorage.getItem('auth_token');
    const adminAuth = localStorage.getItem('adminAuth');
    
    if (config.headers) {
      if (userToken) {
        // ユーザー認証トークンがあれば優先
        config.headers['Authorization'] = `Bearer ${userToken}`;
      } else if (adminAuth) {
        // なければ管理画面のBasic認証を使用
        config.headers['Authorization'] = adminAuth;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// レスポンスインターセプター
axios.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // 401エラーの場合、認証情報をクリア
    if (error.response?.status === 401) {
      // 管理画面のパスの場合のみ認証情報をクリア
      if (window.location.pathname.startsWith('/admin')) {
        localStorage.removeItem('adminAuth');
        localStorage.removeItem('adminUsername');
        window.location.href = '/admin/login';
      }
    }
    return Promise.reject(error);
  }
);

export default axios;