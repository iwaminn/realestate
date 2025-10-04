import React, { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { CircularProgress, Box, Typography } from '@mui/material';
import { useUserAuth } from '../contexts/UserAuthContext';

export const AuthCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const { checkAuth } = useUserAuth();
  const hasProcessedRef = useRef(false);

  useEffect(() => {
    // 既に処理済みの場合はスキップ
    if (hasProcessedRef.current) {
      console.log('[AuthCallback] 既に処理済みのためスキップ');
      return;
    }

    const processCallback = async () => {
      // 処理開始をマーク
      hasProcessedRef.current = true;

      // Cookieに保存されたトークンで認証チェック
      const success = await checkAuth();

      if (success) {
        // ログイン前のURLに戻る（なければトップページ）
        const redirectPath = localStorage.getItem('redirectAfterLogin') || '/';
        console.log('[AuthCallback] localStorageから取得したパス:', redirectPath);
        localStorage.removeItem('redirectAfterLogin');
        console.log('[AuthCallback] リダイレクト先:', redirectPath);
        navigate(redirectPath);
      } else {
        navigate('/?error=google_login_failed');
      }
    };

    processCallback();
  }, [navigate, checkAuth]);

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
      }}
    >
      <CircularProgress size={60} />
      <Typography variant="h6" sx={{ mt: 3 }}>
        ログイン処理中...
      </Typography>
    </Box>
  );
};
