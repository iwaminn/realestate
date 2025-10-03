import React, { useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { CircularProgress, Box, Typography } from '@mui/material';
import { useUserAuth } from '../contexts/UserAuthContext';

export const AuthCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleGoogleCallback } = useUserAuth();
  const hasProcessedRef = useRef(false);

  useEffect(() => {
    // 既に処理済みの場合はスキップ
    if (hasProcessedRef.current) {
      console.log('[AuthCallback] 既に処理済みのためスキップ');
      return;
    }

    const processCallback = async () => {
      const token = searchParams.get('token');

      if (token) {
        // 処理開始をマーク
        hasProcessedRef.current = true;

        // Googleログイン成功
        const success = await handleGoogleCallback(token);
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
      } else {
        // エラー
        hasProcessedRef.current = true;
        navigate('/?error=no_token');
      }
    };

    processCallback();
  }, [searchParams, navigate, handleGoogleCallback]);

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