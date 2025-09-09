import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  Typography,
  Link,
  Alert,
  CircularProgress,
  Tabs,
  Tab,
  Divider
} from '@mui/material';
import { useUserAuth } from '../contexts/UserAuthContext';
import { GoogleLoginButton } from './GoogleLoginButton';

interface LoginModalProps {
  open: boolean;
  onClose: () => void;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

export const LoginModal: React.FC<LoginModalProps> = ({ open, onClose }) => {
  const { login, register } = useUserAuth();
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showEmailVerificationNotice, setShowEmailVerificationNotice] = useState(false);

  // ログインフォーム
  const [loginForm, setLoginForm] = useState({
    email: '',
    password: ''
  });

  // 登録フォーム
  const [registerForm, setRegisterForm] = useState({
    email: '',
    password: '',
    confirmPassword: ''
  });

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    setError('');
    setSuccess('');
    setShowEmailVerificationNotice(false);
  };

  const handleClose = () => {
    setTabValue(0);
    setError('');
    setSuccess('');
    setLoginForm({ email: '', password: '' });
    setRegisterForm({ email: '', password: '', confirmPassword: '' });
    onClose();
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // メールアドレスの簡易検証
    const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailPattern.test(loginForm.email)) {
      setError('有効なメールアドレスを入力してください');
      setLoading(false);
      return;
    }

    const result = await login(loginForm.email, loginForm.password);
    
    if (result.success) {
      setSuccess('ログインに成功しました');
      setTimeout(() => {
        handleClose();
      }, 1000);
    } else {
      // メール確認が必要な場合の特別な処理
      if (result.error?.includes('メールアドレスの確認が必要')) {
        setError('');
        setShowEmailVerificationNotice(true);
      } else {
        setError(result.error || 'ログインに失敗しました');
      }
    }
    
    setLoading(false);
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // メールアドレスの検証
    const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailPattern.test(registerForm.email)) {
      setError('有効なメールアドレスを入力してください');
      setLoading(false);
      return;
    }

    if (registerForm.email.length > 254) {
      setError('メールアドレスが長すぎます');
      setLoading(false);
      return;
    }

    // パスワード確認
    if (registerForm.password !== registerForm.confirmPassword) {
      setError('パスワードが一致しません');
      setLoading(false);
      return;
    }

    // パスワードの検証
    if (registerForm.password.length < 8) {
      setError('パスワードは8文字以上である必要があります');
      setLoading(false);
      return;
    }

    if (!/[A-Za-z]/.test(registerForm.password)) {
      setError('パスワードには英字を含む必要があります');
      setLoading(false);
      return;
    }

    if (!/\d/.test(registerForm.password)) {
      setError('パスワードには数字を含む必要があります');
      setLoading(false);
      return;
    }

    const result = await register(
      registerForm.email, 
      registerForm.password
    );
    
    if (result.success) {
      setSuccess('アカウントを作成しました');
      setShowEmailVerificationNotice(true);
      setError('');
      // 確認メッセージを表示してからモーダルを閉じない（ユーザーがメッセージを読めるように）
    } else {
      setError(result.error || 'ユーザー登録に失敗しました');
    }
    
    setLoading(false);
  };

  return (
    <Dialog 
      open={open} 
      onClose={handleClose} 
      maxWidth="sm" 
      fullWidth
      onClick={(e) => e.stopPropagation()}
    >
      <DialogTitle>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="ログイン" />
          <Tab label="アカウント作成" />
        </Tabs>
      </DialogTitle>

      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {success}
          </Alert>
        )}

        {showEmailVerificationNotice && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
              メールアドレスの確認が必要です
            </Typography>
            <Typography variant="body2">
              {tabValue === 1 ? (
                <>
                  ご登録いただいたメールアドレス宛に確認メールを送信しました。
                  メール内のリンクをクリックして、メールアドレスの確認を完了してください。
                </>
              ) : (
                <>
                  アカウントのメールアドレスが確認されていません。
                  登録時に送信された確認メールをご確認ください。
                </>
              )}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              ※メールが届かない場合は、迷惑メールフォルダをご確認ください。
            </Typography>
            {tabValue === 0 && loginForm.email && (
              <Button 
                size="small" 
                sx={{ mt: 1 }}
                onClick={async () => {
                  const response = await fetch('/api/auth/resend-verification', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: loginForm.email })
                  });
                  if (response.ok) {
                    setSuccess('確認メールを再送信しました');
                  }
                }}
              >
                確認メールを再送信
              </Button>
            )}
          </Alert>
        )}

        {/* ログインタブ */}
        <TabPanel value={tabValue} index={0}>
          <Box component="form" onSubmit={handleLogin} sx={{ mt: 1 }}>
            <TextField
              fullWidth
              label="メールアドレス"
              type="email"
              value={loginForm.email}
              onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })}
              margin="normal"
              required
              autoFocus
            />
            <TextField
              fullWidth
              label="パスワード"
              type="password"
              value={loginForm.password}
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
              margin="normal"
              required
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'ログイン'}
            </Button>
            
            <Divider sx={{ my: 2 }}>または</Divider>
            
            <GoogleLoginButton text="signin" />
          </Box>
        </TabPanel>

        {/* 登録タブ */}
        <TabPanel value={tabValue} index={1}>
          <Box component="form" onSubmit={handleRegister} sx={{ mt: 1 }}>
            <TextField
              fullWidth
              label="メールアドレス"
              type="email"
              value={registerForm.email}
              onChange={(e) => setRegisterForm({ ...registerForm, email: e.target.value })}
              margin="normal"
              required
              autoFocus
            />
            <TextField
              fullWidth
              label="パスワード"
              type="password"
              value={registerForm.password}
              onChange={(e) => setRegisterForm({ ...registerForm, password: e.target.value })}
              margin="normal"
              required
              helperText="8文字以上、英字と数字を含む"
            />
            <TextField
              fullWidth
              label="パスワード（確認）"
              type="password"
              value={registerForm.confirmPassword}
              onChange={(e) => setRegisterForm({ ...registerForm, confirmPassword: e.target.value })}
              margin="normal"
              required
            />
            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'アカウント作成'}
            </Button>
            <Typography variant="body2" color="textSecondary" align="center">
              アカウントを作成することで、物件をブックマークして後で確認できます
            </Typography>
          </Box>
        </TabPanel>
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          キャンセル
        </Button>
      </DialogActions>
    </Dialog>
  );
};