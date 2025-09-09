import React, { useEffect, useState } from 'react';
import {
  Container,
  Box,
  Typography,
  Paper,
  CircularProgress,
  Alert,
  Button
} from '@mui/material';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { CheckCircle, Error as ErrorIcon } from '@mui/icons-material';
import axios from 'axios';

export const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [verifying, setVerifying] = useState(true);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');

  useEffect(() => {
    const verifyEmail = async () => {
      const token = searchParams.get('token');
      
      if (!token) {
        setError('確認トークンが見つかりません');
        setVerifying(false);
        return;
      }

      try {
        const response = await axios.get(`/api/auth/verify-email?token=${token}`);
        
        if (response.status === 200) {
          setSuccess(true);
          setEmail(response.data.email);
        }
      } catch (error: any) {
        console.error('メール確認エラー:', error);
        
        if (error.response?.status === 400) {
          setError('無効または期限切れの確認トークンです');
        } else {
          setError('メール確認中にエラーが発生しました');
        }
      } finally {
        setVerifying(false);
      }
    };

    verifyEmail();
  }, [searchParams]);

  const handleGoToLogin = () => {
    navigate('/');
  };

  const handleGoToHome = () => {
    navigate('/');
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ mt: 8, mb: 4 }}>
        <Paper elevation={3} sx={{ p: 4 }}>
          {verifying && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CircularProgress size={60} />
              <Typography variant="h6" sx={{ mt: 3 }}>
                メールアドレスを確認中...
              </Typography>
            </Box>
          )}

          {!verifying && success && (
            <Box sx={{ textAlign: 'center', py: 2 }}>
              <CheckCircle sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
              <Typography variant="h5" gutterBottom fontWeight="bold">
                メールアドレスの確認が完了しました
              </Typography>
              <Typography variant="body1" color="textSecondary" sx={{ mb: 1 }}>
                {email}
              </Typography>
              <Alert severity="success" sx={{ mt: 3, mb: 3 }}>
                アカウントが正常に有効化されました。
                ログインして全ての機能をご利用いただけます。
              </Alert>
              <Button
                variant="contained"
                color="primary"
                size="large"
                onClick={handleGoToLogin}
                sx={{ mt: 2 }}
              >
                ログインページへ
              </Button>
            </Box>
          )}

          {!verifying && error && (
            <Box sx={{ textAlign: 'center', py: 2 }}>
              <ErrorIcon sx={{ fontSize: 80, color: 'error.main', mb: 2 }} />
              <Typography variant="h5" gutterBottom fontWeight="bold">
                メールアドレスの確認に失敗しました
              </Typography>
              <Alert severity="error" sx={{ mt: 3, mb: 3 }}>
                {error}
              </Alert>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                以下の原因が考えられます：
              </Typography>
              <Box sx={{ textAlign: 'left', pl: 4, mb: 3 }}>
                <Typography variant="body2" color="textSecondary">
                  • リンクの有効期限（24時間）が切れている
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  • 既にメールアドレスが確認済み
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  • URLが正しくない
                </Typography>
              </Box>
              <Button
                variant="outlined"
                color="primary"
                size="large"
                onClick={handleGoToHome}
                sx={{ mt: 2 }}
              >
                ホームへ戻る
              </Button>
            </Box>
          )}
        </Paper>
      </Box>
    </Container>
  );
};