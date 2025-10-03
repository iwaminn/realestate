import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

interface User {
  id: number;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface UserAuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  updateProfile: (data: {}) => Promise<{ success: boolean; error?: string }>;
  handleGoogleCallback: (token: string) => Promise<boolean>;
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

  useEffect(() => {
    // 既存の認証情報をチェック
    const token = localStorage.getItem('userToken');
    if (token) {
      checkAuth(token);
    } else {
      setIsLoading(false);
    }
  }, []);

  const checkAuth = async (token?: string) => {
    try {
      const authToken = token || localStorage.getItem('userToken');
      if (!authToken) {
        setIsLoading(false);
        return;
      }

      const response = await axios.get('/auth/me', {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      });

      if (response.status === 200) {
        setUser(response.data);
        setIsAuthenticated(true);
        // axiosのデフォルトヘッダーに設定
        axios.defaults.headers.common['Authorization'] = `Bearer ${authToken}`;
      }
    } catch (error: any) {
      console.error('認証確認エラー:', error);
      // 認証エラーの場合は認証情報をクリア
      if (error.response?.status === 401) {
        clearAuth();
      }
    } finally {
      setIsLoading(false);
    }
  };

  const clearAuth = () => {
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('userToken');
    delete axios.defaults.headers.common['Authorization'];
  };

  const login = async (email: string, password: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await axios.post('/auth/login', {
        email,
        password
      });

      if (response.status === 200) {
        const { access_token, user: userData } = response.data;
        
        // トークンを保存
        localStorage.setItem('userToken', access_token);
        
        // ユーザー情報を設定
        setUser(userData);
        setIsAuthenticated(true);
        
        // axiosのデフォルトヘッダーに設定
        axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
        
        return { success: true };
      }
    } catch (error: any) {
      console.error('ログインエラー:', error);
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
      console.error('ユーザー登録エラー:', error);
      
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
      // サーバーサイドでセッションを無効化
      await axios.post('/auth/logout');
    } catch (error) {
      console.error('ログアウトエラー:', error);
    } finally {
      clearAuth();
    }
  };

  const updateProfile = async (data: {}): Promise<{ success: boolean; error?: string }> => {
    try {
      const response = await axios.put('/auth/me', data);
      
      if (response.status === 200) {
        setUser(response.data);
        return { success: true };
      }
    } catch (error: any) {
      console.error('プロフィール更新エラー:', error);
      const errorMessage = error.response?.data?.detail || 'プロフィール更新に失敗しました';
      return { success: false, error: errorMessage };
    }
    
    return { success: false, error: 'プロフィール更新に失敗しました' };
  };

  const handleGoogleCallback = async (token: string): Promise<boolean> => {
    try {
      // 古いBasic認証ヘッダーをクリア
      delete axios.defaults.headers.common['Authorization'];

      console.log('handleGoogleCallback: Starting with token:', typeof token === 'string' ? token.substring(0, 20) + '...' : token);

      // トークンをローカルストレージに保存（userTokenに統一）
      localStorage.setItem('userToken', token);

      // axiosのデフォルトヘッダーに設定
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      const authHeader = axios.defaults.headers.common['Authorization'];
      console.log('handleGoogleCallback: Authorization header set:', typeof authHeader === 'string' ? authHeader.substring(0, 30) + '...' : authHeader);
      
      console.log('handleGoogleCallback: Calling /auth/me');
      // ユーザー情報を取得（明示的にヘッダーを渡す）
      const response = await axios.get('/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (response.status === 200) {
        setUser(response.data);
        setIsAuthenticated(true);
        return true;
      }
    } catch (error) {
      console.error('Google認証エラー:', error);
      clearAuth();
    }
    
    return false;
  };

  const value: UserAuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout,
    updateProfile,
    handleGoogleCallback
  };

  return (
    <UserAuthContext.Provider value={value}>
      {children}
    </UserAuthContext.Provider>
  );
};