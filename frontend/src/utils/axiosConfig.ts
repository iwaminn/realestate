import axios from 'axios';

// APIのベースURL（本番環境では相対パス、開発環境ではlocalhost）
// Viteの環境変数を使用
axios.defaults.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Axiosのインターセプターを設定
axios.interceptors.request.use(
  (config) => {
    const userToken = localStorage.getItem('userToken');
    const adminAuth = localStorage.getItem('adminAuth');
    
    if (config.headers) {
      // 管理画面のエンドポイントではadminAuthを優先
      // baseURLに既に/apiが含まれているため、/adminで始まるURLをチェック
      if (config.url?.startsWith('/admin')) {
        if (adminAuth) {
          config.headers['Authorization'] = adminAuth;
        } else if (userToken) {
          config.headers['Authorization'] = `Bearer ${userToken}`;
        }
      } else {
        // それ以外ではユーザー認証トークンを優先
        if (userToken) {
          config.headers['Authorization'] = `Bearer ${userToken}`;
        } else if (adminAuth) {
          config.headers['Authorization'] = adminAuth;
        }
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
      if (window.location.pathname.startsWith('/admin')) {
        // 管理画面の場合
        localStorage.removeItem('adminAuth');
        localStorage.removeItem('adminUsername');
        window.location.href = '/admin/login';
      } else {
        // 一般ユーザーの場合
        // UserAuthContextのclearAuth()が呼ばれるようにエラーを返すだけ
        // トークンのクリアはUserAuthContext側で行う
        console.log('[axiosConfig] 401エラー: 認証が必要です');
      }
    }
    return Promise.reject(error);
  }
);

export default axios;