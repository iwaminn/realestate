import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useUserAuth } from '../contexts/UserAuthContext';
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';

export const ResetPasswordPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { checkAuth } = useUserAuth();
  const token = searchParams.get('token');

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // バリデーション
    if (newPassword !== confirmPassword) {
      setError('パスワードが一致しません');
      return;
    }

    if (newPassword.length < 8) {
      setError('パスワードは8文字以上である必要があります');
      return;
    }

    const hasLetter = /[A-Za-z]/.test(newPassword);
    const hasNumber = /[0-9]/.test(newPassword);
    if (!hasLetter || !hasNumber) {
      setError('パスワードには英字と数字を含む必要があります');
      return;
    }

    if (!token) {
      setError('無効なリセットトークンです');
      return;
    }

    setLoading(true);

    try {
      await axios.post('/auth/reset-password', {
        token,
        new_password: newPassword
      }, {
        withCredentials: true  // Cookieを受信
      });

      // 認証状態を更新（Cookieベース）
      await checkAuth();

      setSuccess(true);
      // 1秒後にホームページへ移動
      setTimeout(() => {
        navigate('/');
      }, 1000);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'パスワードリセットに失敗しました');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <ErrorIcon sx={{ fontSize: 80, color: 'error.main', mb: 3 }} />
            <Typography variant="h5" gutterBottom color="error">
              無効なリンクです
            </Typography>
            <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
              パスワードリセットリンクが無効または期限切れです。
            </Typography>
            <Button
              variant="contained"
              onClick={() => navigate('/request-password-reset')}
              sx={{ mb: 1 }}
            >
              パスワードリセットを再申請
            </Button>
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
              パスワードをリセットしました
            </Typography>
            <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
              ログイン済みの状態になりました。
            </Typography>
            <Typography variant="body2" color="text.secondary">
              1秒後にホームページへ移動します...
            </Typography>
          </CardContent>
        </Card>
      </Container>
    );
  }

  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Card>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h5" component="h1" gutterBottom>
            新しいパスワードを設定
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            8文字以上で、英字と数字を含むパスワードを設定してください。
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth
              type="password"
              label="新しいパスワード"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              margin="normal"
              required
              disabled={loading}
              autoFocus
              helperText="8文字以上、英字と数字を含む"
            />

            <TextField
              fullWidth
              type="password"
              label="新しいパスワード（確認）"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              margin="normal"
              required
              disabled={loading}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3 }}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'パスワードをリセット'}
            </Button>
          </Box>
        </CardContent>
      </Card>
    </Container>
  );
};
