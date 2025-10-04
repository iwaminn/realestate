import axios from 'axios';

// APIのベースURL
// Viteのproxyが /api を http://realestate-backend:8000 に転送するため、
// フロントエンドは /api をベースURLとして使用
axios.defaults.baseURL = '/api';

// Cookie認証を使用するために withCredentials を有効化
axios.defaults.withCredentials = true;

// Axiosのインターセプターを設定
axios.interceptors.request.use(
  (config) => {
    const userToken = localStorage.getItem('userToken');

    if (config.headers) {
      // 管理画面はCookie認証を使用（Authorizationヘッダー不要）
      // ユーザー向けAPIでBearerトークンがある場合のみ設定
      if (userToken && !config.url?.startsWith('/admin')) {
        config.headers['Authorization'] = `Bearer ${userToken}`;
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
        // 管理画面の場合（Cookie認証）
        // /admin/loginページ自体では401エラーでリダイレクトしない
        if (window.location.pathname !== '/admin/login') {
          localStorage.removeItem('adminUsername');
          // AuthContextに処理を任せる（リダイレクトループを防ぐ）
        }
      } else {
        // 一般ユーザーの場合
        // UserAuthContextのclearAuth()が呼ばれるようにエラーを返すだけ
        // トークンのクリアはUserAuthContext側で行う
      }
    }
    return Promise.reject(error);
  }
);

export default axios;