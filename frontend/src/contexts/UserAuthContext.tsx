import React, { createContext, useContext, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import axios from 'axios';

interface User {
  id: number;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  google_id?: string | null;
  has_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface UserAuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  showLoginModal: boolean;
  openLoginModal: () => void;
  closeLoginModal: () => void;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  updateProfile: (data: {}) => Promise<{ success: boolean; error?: string }>;
  checkAuth: () => Promise<boolean>;
}

const UserAuthContext = createContext<UserAuthContextType | undefined>(undefined);

export const useUserAuth = () => {
  const context = useContext(UserAuthContext);
  if (!context) {
    throw new Error('useUserAuth must be used within a UserAuthProvider');
  }
  return context;
};

export const UserAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const location = useLocation();

  useEffect(() => {
    // 管理画面ではユーザー認証をスキップ
    if (location.pathname.startsWith('/admin')) {
      setIsLoading(false);
      return;
    }

    // 既存の認証情報をチェック（Cookieベース）
    checkAuth();
  }, [location.pathname]);

  const checkAuth = async (): Promise<boolean> => {
    try {
      // Cookieは自動的に送信される
      const response = await axios.get('/auth/me', {
        withCredentials: true  // Cookieを送信
      });

      if (response.status === 200) {
        setUser(response.data);
        setIsAuthenticated(true);
        setIsLoading(false);
        return true;
      }
    } catch (error: any) {
      // 認証エラーの場合は認証情報をクリア
      if (error.response?.status === 401) {
        clearAuth();
      }
    } finally {
      setIsLoading(false);
    }

    return false;
  };

  const clearAuth = () => {
    setUser(null);
    setIsAuthenticated(false);
    // localStorageのBearerトークンも削除
    localStorage.removeItem('userToken');
  };

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await axios.post('/auth/login', {
        email,
        password
      }, {
        withCredentials: true  // Cookieを受信
      });

      if (response.status === 200) {
        const { user: userData } = response.data;

        // ユーザー情報を設定（トークンはCookieに保存済み）
        setUser(userData);
        setIsAuthenticated(true);

        return { success: true };
      }
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'ログインに失敗しました';
      return { success: false, error: errorMessage };
    }

    return { success: false, error: 'ログインに失敗しました' };
  };

  const register = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await axios.post('/auth/register', {
        email,
        password
      });

      if (response.status === 200) {
        // 仮登録成功
        return { success: true };
      }
    } catch (error: any) {

      // バリデーションエラーの処理
      if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          const errorMessages = error.response.data.detail.map((err: any) => err.msg).join(', ');
          return { success: false, error: errorMessages };
        }
        return { success: false, error: error.response.data.detail };
      }

      return { success: false, error: 'ユーザー登録に失敗しました' };
    }

    return { success: false, error: 'ユーザー登録に失敗しました' };
  };

  const logout = async () => {
    try {
      // サーバーサイドでセッションを無効化（Cookieを削除）
      await axios.post('/auth/logout', {}, {
        withCredentials: true
      });
    } catch (error) {
    } finally {
      clearAuth();
    }
  };

  const updateProfile = async (data: {}): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await axios.put('/auth/me', data, {
        withCredentials: true
      });

      if (response.status === 200) {
        setUser(response.data);
        return { success: true };
      }
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'プロフィール更新に失敗しました';
      return { success: false, error: errorMessage };
    }

    return { success: false, error: 'プロフィール更新に失敗しました' };
  };

  const openLoginModal = () => setShowLoginModal(true);
  const closeLoginModal = () => setShowLoginModal(false);

  const value: UserAuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    showLoginModal,
    openLoginModal,
    closeLoginModal,
    login,
    register,
    logout,
    updateProfile,
    checkAuth
  };

  return (
    <UserAuthContext.Provider value={value}>
      {children}
    </UserAuthContext.Provider>
  );
};
