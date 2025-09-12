import axios from 'axios';
import { API_CONFIG } from '../config/api';

// APIのベースURLを設定
axios.defaults.baseURL = API_CONFIG.BASE_URL;

// Axiosのインターセプターを設定
axios.interceptors.request.use(
  (config) => {
    // localStorageから認証情報を取得
    const authHeader = localStorage.getItem('adminAuth');
    if (authHeader && config.headers) {
      config.headers['Authorization'] = authHeader;
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