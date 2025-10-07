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

// リフレッシュ処理中かどうかのフラグ
let isRefreshing = false;
let failedQueue: any[] = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });

  failedQueue = [];
};

// レスポンスインターセプター
axios.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    // 401エラーの場合
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (window.location.pathname.startsWith('/admin')) {
        // 管理画面の場合（Cookie認証）
        // /admin/loginやリフレッシュAPIのエラーは再試行しない
        if (originalRequest.url?.includes('/admin/login') || originalRequest.url?.includes('/admin/refresh') || originalRequest.url?.includes('/admin/logout')) {
          return Promise.reject(error);
        }

        if (isRefreshing) {
          // リフレッシュ処理中の場合、キューに追加
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          }).then(() => {
            return axios(originalRequest);
          }).catch(err => {
            return Promise.reject(err);
          });
        }

        originalRequest._retry = true;
        isRefreshing = true;

        try {
          // 管理者用リフレッシュトークンでアクセストークンを更新
          await axios.post('/admin/refresh');

          processQueue(null);
          isRefreshing = false;

          // 元のリクエストを再試行
          return axios(originalRequest);
        } catch (refreshError) {
          // リフレッシュ失敗 - ログアウト状態にする
          processQueue(refreshError, null);
          isRefreshing = false;
          localStorage.removeItem('adminUsername');

          return Promise.reject(refreshError);
        }
      } else {
        // 一般ユーザーの場合 - リフレッシュトークンで自動更新を試みる
        if (originalRequest.url?.includes('/refresh') || originalRequest.url?.includes('/logout')) {
          // リフレッシュAPIやログアウトAPIのエラーは再試行しない
          return Promise.reject(error);
        }

        if (isRefreshing) {
          // リフレッシュ処理中の場合、キューに追加
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          }).then(() => {
            return axios(originalRequest);
          }).catch(err => {
            return Promise.reject(err);
          });
        }

        originalRequest._retry = true;
        isRefreshing = true;

        try {
          // リフレッシュトークンでアクセストークンを更新
          await axios.post('/auth/refresh');

          processQueue(null);
          isRefreshing = false;

          // 元のリクエストを再試行
          return axios(originalRequest);
        } catch (refreshError) {
          // リフレッシュ失敗 - ログアウト状態にする
          processQueue(refreshError, null);
          isRefreshing = false;

          // UserAuthContextのclearAuth()が呼ばれるようにエラーを返す
          return Promise.reject(refreshError);
        }
      }
    }

    return Promise.reject(error);
  }
);

export default axios;