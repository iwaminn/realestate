import React, { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { CircularProgress, Box, Typography } from '@mui/material';
import { useUserAuth } from '../contexts/UserAuthContext';

export const AuthCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleGoogleCallback } = useUserAuth();

  useEffect(() => {
    const processCallback = async () => {
      const token = searchParams.get('token');
      
      if (token) {
        // Googleログイン成功
        const success = await handleGoogleCallback(token);
        if (success) {
          navigate('/');
        } else {
          navigate('/?error=google_login_failed');
        }
      } else {
        // エラー
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