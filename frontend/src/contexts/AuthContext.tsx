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
    // 既存の認証情報をチェック
    const authHeader = localStorage.getItem('adminAuth');
    if (authHeader) {
      // テスト用のAPIリクエストを送信して認証を確認
      axios.defaults.headers.common['Authorization'] = authHeader;
      checkAuth();
    } else {
      // 認証情報がない場合はローディングを終了
      setIsLoading(false);
    }
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
    try {
      // 管理APIにアクセスして認証を確認
      await axios.get('/api/admin/areas', { timeout: 10000 }); // 10秒のタイムアウト
      setIsAuthenticated(true);
      const storedUsername = localStorage.getItem('adminUsername');
      setUsername(storedUsername);
    } catch (error: any) {
      // 401エラーの場合のみ認証情報をクリア
      if (error.response?.status === 401) {
        setIsAuthenticated(false);
        setUsername(null);
        delete axios.defaults.headers.common['Authorization'];
        localStorage.removeItem('adminAuth');
        localStorage.removeItem('adminUsername');
      } else if (error.code === 'ECONNABORTED') {
        // タイムアウトエラーの場合は認証状態を維持
        console.warn('Auth check timeout - maintaining current auth state');
      }
      // その他のエラー（ネットワークエラー等）は無視
      console.error('Auth check error:', error);
    } finally {
      // ローディング完了
      setIsLoading(false);
    }
  };

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      // Basic認証ヘッダーを作成
      const authHeader = 'Basic ' + btoa(username + ':' + password);
      
      // テスト用のAPIリクエストを送信
      const response = await axios.get('/api/admin/areas', {
        headers: {
          'Authorization': authHeader
        }
      });

      if (response.status === 200) {
        // 認証成功
        axios.defaults.headers.common['Authorization'] = authHeader;
        localStorage.setItem('adminAuth', authHeader);
        localStorage.setItem('adminUsername', username);
        setIsAuthenticated(true);
        setUsername(username);
        return true;
      }
    } catch (error) {
      console.error('Login failed:', error);
    }

    return false;
  };

  const logout = () => {
    setIsAuthenticated(false);
    setUsername(null);
    delete axios.defaults.headers.common['Authorization'];
    localStorage.removeItem('adminAuth');
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