import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useUserAuth } from '../contexts/UserAuthContext';

export const VerifyEmailChangePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { checkAuth } = useUserAuth();
  const token = searchParams.get('token');

  const [loading, setLoading] = useState(true);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const hasRunRef = React.useRef(false);

  useEffect(() => {
    // React 18 Strict Modeで2回実行されるのを防ぐ
    if (hasRunRef.current) return;
    hasRunRef.current = true;

    const verifyEmailChange = async () => {
      if (!token) {
        setError('無効な確認リンクです');
        setLoading(false);
        return;
      }

      try {
        const response = await axios.get(`/auth/verify-email-change?token=${token}`, {
          withCredentials: true
        });

        setNewEmail(response.data.new_email);
        setSuccess(true);

        // 認証状態を更新
        await checkAuth();

        // 2秒後にアカウント設定ページへ移動
        setTimeout(() => {
          navigate('/account/settings');
        }, 2000);
      } catch (error: any) {
        setError(error.response?.data?.detail || 'メールアドレスの確認に失敗しました');
      } finally {
        setLoading(false);
      }
    };

    verifyEmailChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress size={60} sx={{ mb: 3 }} />
            <Typography variant="h6">
              メールアドレスを確認しています...
            </Typography>
          </CardContent>
        </Card>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <ErrorIcon sx={{ fontSize: 80, color: 'error.main', mb: 3 }} />
            <Typography variant="h5" gutterBottom color="error">
              確認に失敗しました
            </Typography>
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          </CardContent>
        </Card>
      </Container>
    );
  }

  if (success) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircleIcon sx={{ fontSize: 80, color: 'success.main', mb: 3 }} />
            <Typography variant="h5" gutterBottom color="success.main">
              メールアドレスを変更しました
            </Typography>
            <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
              新しいメールアドレス: <strong>{newEmail}</strong>
            </Typography>
            <Typography variant="body2" color="text.secondary">
              2秒後にアカウント設定ページへ移動します...
            </Typography>
          </CardContent>
        </Card>
      </Container>
    );
  }

  return null;
};
