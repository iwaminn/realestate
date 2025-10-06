import React, { useState } from 'react';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
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
  Email as EmailIcon,
  ArrowBack as ArrowBackIcon
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useUserAuth } from '../contexts/UserAuthContext';

export const RequestPasswordResetPage: React.FC = () => {
  const navigate = useNavigate();
  const { openLoginModal } = useUserAuth();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // バリデーション
    const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailPattern.test(email)) {
      setError('有効なメールアドレスを入力してください');
      setLoading(false);
      return;
    }

    try {
      await axios.post('/auth/request-password-reset', { email });
      setSuccess(true);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'パスワードリセット申請に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <Container maxWidth="sm" sx={{ py: 8 }}>
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 4 }}>
            <EmailIcon sx={{ fontSize: 80, color: 'success.main', mb: 3 }} />
            <Typography variant="h5" gutterBottom color="success.main">
              メールを送信しました
            </Typography>
            <Typography variant="body1" sx={{ mt: 2, mb: 3 }}>
              パスワードリセットのリンクをメールで送信しました。メールをご確認ください。
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              メールが届かない場合は、迷惑メールフォルダもご確認ください。
            </Typography>
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={() => {
                navigate('/');
                openLoginModal();
              }}
            >
              ログインフォームを開く
            </Button>
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
            パスワードリセット
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            登録したメールアドレスを入力してください。パスワードリセットのリンクをお送りします。
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth
              type="email"
              label="メールアドレス"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              margin="normal"
              required
              disabled={loading}
              autoFocus
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'リセットリンクを送信'}
            </Button>

            <Box sx={{ textAlign: 'center' }}>
              <Button
                onClick={() => {
                  navigate('/');
                  openLoginModal();
                }}
                startIcon={<ArrowBackIcon />}
                sx={{ mt: 1 }}
              >
                ログインフォームを開く
              </Button>
            </Box>
          </Box>
        </CardContent>
      </Card>
    </Container>
  );
};
