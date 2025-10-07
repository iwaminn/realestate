import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

interface AuthContextType {
  isAuthenticated: boolean;
  username: string | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Cookie認証の場合、常に認証状態を確認
    checkAuth();
  }, []);

  // 定期的に認証状態を確認（10分ごと）
  useEffect(() => {
    if (isAuthenticated) {
      const interval = setInterval(() => {
        checkAuth();
      }, 10 * 60 * 1000); // 10分

      return () => clearInterval(interval);
    }
  }, [isAuthenticated]);

  const checkAuth = async () => {
    // 管理画面以外は認証チェックをスキップ
    if (!window.location.pathname.startsWith('/admin')) {
      setIsAuthenticated(false);
      setIsLoading(false);
      return;
    }

    // ログインページの場合も認証チェックをスキップ
    if (window.location.pathname === '/admin/login') {
      setIsAuthenticated(false);
      setIsLoading(false);
      return;
    }

    try {
      // Cookie認証を使用して管理者情報を取得
      const response = await axios.get('/admin/me', {
        timeout: 10000,  // 10秒のタイムアウト
        withCredentials: true  // Cookieを送信
      });

      if (response.status === 200) {
        setIsAuthenticated(true);
        const storedUsername = localStorage.getItem('adminUsername');
        setUsername(storedUsername || response.data.username);
      }
    } catch (error: any) {
      // 401エラーの場合のみ認証情報をクリア
      if (error.response?.status === 401) {
        setIsAuthenticated(false);
        setUsername(null);
        localStorage.removeItem('adminUsername');
      } else if (error.code === 'ECONNABORTED') {
        // タイムアウトエラーの場合は認証状態を維持
      }
      // その他のエラー（ネットワークエラー等）は無視
    } finally {
      // ローディング完了
      setIsLoading(false);
    }
  };

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      // Cookie認証を使用（管理者ログインエンドポイントを呼び出す）
      const response = await axios.post('/admin/login', {
        username,
        password
      }, {
        withCredentials: true  // Cookieを送受信
      });

      if (response.status === 200) {
        // 認証成功
        localStorage.setItem('adminUsername', username);
        setIsAuthenticated(true);
        setUsername(username);
        return true;
      }
    } catch (error) {
    }

    return false;
  };

  const logout = async () => {
    try {
      // サーバー側でログアウト処理（Cookieを削除）
      await axios.post('/admin/logout', {}, {
        withCredentials: true
      });
    } catch (error) {
    }

    // クライアント側の状態をクリア
    setIsAuthenticated(false);
    setUsername(null);
    localStorage.removeItem('adminUsername');
  };

  // ローディング中は何も表示しない
  if (isLoading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>認証確認中...</div>;
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};