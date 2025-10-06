import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Button
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';

export const VerifyPasswordSetPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [verifying, setVerifying] = useState(true);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const verifyPasswordSet = async () => {
      const token = searchParams.get('token');

      if (!token) {
        setError('確認トークンが見つかりません');
        setVerifying(false);
        return;
      }

      try {
        const response = await axios.get(`/auth/verify-password-set?token=${token}`);
        setSuccess(true);
        setVerifying(false);

        // 3秒後にアカウント設定ページへリダイレクト
        setTimeout(() => {
          navigate('/account/settings');
        }, 3000);
      } catch (error: any) {
        setError(error.response?.data?.detail || 'パスワード設定の確認に失敗しました');
        setVerifying(false);
      }
    };

    verifyPasswordSet();
  }, [searchParams, navigate]);

  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Card>
        <CardContent sx={{ textAlign: 'center', py: 4 }}>
          {verifying && (
            <>
              <CircularProgress size={60} sx={{ mb: 3 }} />
              <Typography variant="h5" gutterBottom>
                パスワード設定を確認中...
              </Typography>
              <Typography variant="body2" color="text.secondary">
                しばらくお待ちください
              </Typography>
            </>
          )}

          {!verifying && success && (
            <>
              <CheckCircleIcon
                sx={{ fontSize: 80, color: 'success.main', mb: 3 }}
              />
              <Typography variant="h5" gutterBottom color="success.main">
                パスワードが設定されました
              </Typography>
              <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
                次回からメールアドレスとパスワードでもログインできます。
              </Typography>
              <Typography variant="body2" color="text.secondary">
                3秒後にアカウント設定ページへ移動します...
              </Typography>
            </>
          )}

          {!verifying && error && (
            <>
              <ErrorIcon
                sx={{ fontSize: 80, color: 'error.main', mb: 3 }}
              />
              <Typography variant="h5" gutterBottom color="error">
                確認に失敗しました
              </Typography>
              <Alert severity="error" sx={{ mt: 2, mb: 3, textAlign: 'left' }}>
                {error}
              </Alert>
              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
                <Button
                  variant="outlined"
                  onClick={() => navigate('/account/settings')}
                >
                  アカウント設定へ
                </Button>
                <Button
                  variant="contained"
                  onClick={() => navigate('/properties')}
                >
                  トップページへ
                </Button>
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Container>
  );
};
