import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  Card,
  CardContent,
  Box,
  TextField,
  Button,
  Alert,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  CircularProgress
} from '@mui/material';
import {
  AccountCircle,
  Lock,
  Email,
  DeleteForever
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useUserAuth } from '../contexts/UserAuthContext';
import axios from '../utils/axiosConfig';

export const AccountSettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isLoading: authLoading, logout } = useUserAuth();

  // Googleアカウントかどうかを判定（google_idがある、またはhashed_passwordがない）
  const isGoogleAccount = user?.google_id ? true : false;
  // パスワード設定済みかどうかのフラグ（エラーメッセージで判定）
  const hasPassword = user?.has_password || false;

  // パスワード変更フォーム
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  // パスワード設定フォーム（Googleアカウント用）
  const [setPasswordMode, setSetPasswordMode] = useState(false);

  // メールアドレス変更フォーム
  const [newEmail, setNewEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [emailError, setEmailError] = useState('');
  const [emailSuccess, setEmailSuccess] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);

  // アカウント削除ダイアログ
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);

  // 未ログイン時はログインページへリダイレクト
  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/properties');
    }
  }, [user, authLoading, navigate]);

  if (authLoading) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  if (!user) {
    return null;
  }

  // パスワード変更処理
  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    // バリデーション
    if (newPassword !== confirmPassword) {
      setPasswordError('新しいパスワードが一致しません');
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError('パスワードは8文字以上である必要があります');
      return;
    }

    const hasLetter = /[A-Za-z]/.test(newPassword);
    const hasNumber = /[0-9]/.test(newPassword);
    if (!hasLetter || !hasNumber) {
      setPasswordError('パスワードには英字と数字を含む必要があります');
      return;
    }

    try {
      setPasswordLoading(true);
      
      // Googleアカウントでパスワード未設定の場合は設定リクエスト（メール確認）
      if (isGoogleAccount && !hasPassword && setPasswordMode) {
        await axios.post('/auth/request-password-set', {
          new_password: newPassword
        });
        setPasswordSuccess('パスワード設定確認メールを送信しました。メールをご確認ください。');
        // フォームは閉じずに、メッセージを表示したまま維持
        setNewPassword('');
        setConfirmPassword('');
      } else {
        // 通常のパスワード変更
        await axios.post('/auth/change-password', {
          current_password: currentPassword,
          new_password: newPassword
        });
        setPasswordSuccess('パスワードを変更しました');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      }
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'パスワードの操作に失敗しました';
      
      // 既にパスワードが設定されている場合は、メッセージを表示してフォームをリセット
      if (errorMessage.includes('既にパスワードが設定されています')) {
        setSetPasswordMode(false);
        setPasswordError('既にパスワードが設定されています。ページを再読み込みしてください。');
        setNewPassword('');
        setConfirmPassword('');
        // ユーザー情報を再取得
        setTimeout(() => window.location.reload(), 2000);
      } else {
        setPasswordError(errorMessage);
      }
    } finally {
      setPasswordLoading(false);
    }
  };

  // メールアドレス変更処理
  const handleEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailError('');
    setEmailSuccess('');

    // バリデーション
    const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailPattern.test(newEmail)) {
      setEmailError('有効なメールアドレスを入力してください');
      return;
    }

    try {
      setEmailLoading(true);
      const response = await axios.post('/auth/change-email', {
        new_email: newEmail,
        password: emailPassword
      });
      setEmailSuccess(response.data.message || '確認メールを送信しました。新しいメールアドレスをご確認ください。');
      setNewEmail('');
      setEmailPassword('');
    } catch (error: any) {
      setEmailError(error.response?.data?.detail || 'メールアドレスの変更に失敗しました');
    } finally {
      setEmailLoading(false);
    }
  };

  // アカウント削除処理
  const handleDeleteAccount = async () => {
    setDeleteError('');

    try {
      setDeleteLoading(true);
      await axios.delete('/auth/account', {
        data: { password: deletePassword }
      });
      // ログアウトしてトップページへ
      await logout();
      navigate('/properties');
    } catch (error: any) {
      setDeleteError(error.response?.data?.detail || 'アカウントの削除に失敗しました');
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      {/* ヘッダー */}
      <Box display="flex" alignItems="center" mb={4}>
        <AccountCircle sx={{ mr: 2, fontSize: 32 }} />
        <Typography variant="h4" component="h1">
          アカウント設定
        </Typography>
      </Box>

      {/* 現在のメールアドレス */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            アカウント情報
          </Typography>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              メールアドレス
            </Typography>
            <Typography variant="body1">
              {user.email}
            </Typography>
          </Box>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              登録日
            </Typography>
            <Typography variant="body1">
              {new Date(user.created_at).toLocaleDateString('ja-JP')}
            </Typography>
          </Box>
        </CardContent>
      </Card>

      {/* パスワード変更・設定 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <Lock sx={{ mr: 1 }} />
            <Typography variant="h6">
              {isGoogleAccount ? 'パスワード設定' : 'パスワード変更'}
            </Typography>
          </Box>

          {/* Googleアカウントでパスワード未設定の場合の説明 */}
          {isGoogleAccount && !hasPassword && !setPasswordMode && (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                Googleアカウントでログインしています。パスワードを設定すると、通常のメールアドレス・パスワードでもログインできるようになります。
              </Alert>
              <Button
                variant="outlined"
                onClick={() => setSetPasswordMode(true)}
              >
                パスワードを設定する
              </Button>
            </>
          )}

          {/* パスワード設定・変更フォーム */}
          {((!isGoogleAccount) || hasPassword || setPasswordMode) && (
            <>
              {passwordSuccess && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  {passwordSuccess}
                </Alert>
              )}

              {passwordError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {passwordError}
                </Alert>
              )}

              <Box component="form" onSubmit={handlePasswordChange}>
                {/* 通常ユーザーまたはパスワード設定済みGoogleユーザーは現在のパスワード入力 */}
                {((!isGoogleAccount) || (isGoogleAccount && hasPassword)) && (
                  <TextField
                    fullWidth
                    type="password"
                    label="現在のパスワード"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    margin="normal"
                    required
                    disabled={passwordLoading}
                  />
                )}
                
                <TextField
                  fullWidth
                  type="password"
                  label="新しいパスワード"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  margin="normal"
                  required
                  disabled={passwordLoading}
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
                  disabled={passwordLoading}
                />
                <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={passwordLoading}
                  >
                    {passwordLoading ? <CircularProgress size={24} /> : (isGoogleAccount ? 'パスワードを設定' : 'パスワードを変更')}
                  </Button>
                  {isGoogleAccount && setPasswordMode && (
                    <Button
                      variant="outlined"
                      onClick={() => {
                        setSetPasswordMode(false);
                        setPasswordError('');
                        setPasswordSuccess('');
                        setNewPassword('');
                        setConfirmPassword('');
                      }}
                      disabled={passwordLoading}
                    >
                      キャンセル
                    </Button>
                  )}
                </Box>
              </Box>
            </>
          )}
        </CardContent>
      </Card>

      {/* メールアドレス変更 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <Email sx={{ mr: 1 }} />
            <Typography variant="h6">
              メールアドレス変更
            </Typography>
          </Box>

          {emailSuccess && (
            <Alert severity="success" sx={{ mb: 2 }}>
              {emailSuccess}
            </Alert>
          )}

          {emailError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {emailError}
            </Alert>
          )}

          <Box component="form" onSubmit={handleEmailChange}>
            <TextField
              fullWidth
              type="email"
              label="新しいメールアドレス"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              margin="normal"
              required
              disabled={emailLoading}
            />
            <TextField
              fullWidth
              type="password"
              label="パスワード（確認用）"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              margin="normal"
              required
              disabled={emailLoading}
            />
            <Button
              type="submit"
              variant="contained"
              sx={{ mt: 2 }}
              disabled={emailLoading}
            >
              {emailLoading ? <CircularProgress size={24} /> : 'メールアドレスを変更'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* アカウント削除 */}
      <Card sx={{ mb: 3, borderColor: 'error.main', borderWidth: 1, borderStyle: 'solid' }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <DeleteForever sx={{ mr: 1, color: 'error.main' }} />
            <Typography variant="h6" color="error">
              アカウント削除
            </Typography>
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            アカウントを削除すると、すべてのデータ（ブックマークなど）が削除されます。この操作は取り消せません。
          </Typography>

          <Button
            variant="outlined"
            color="error"
            onClick={() => setDeleteDialogOpen(true)}
          >
            アカウントを削除
          </Button>
        </CardContent>
      </Card>

      {/* アカウント削除確認ダイアログ */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => !deleteLoading && setDeleteDialogOpen(false)}
      >
        <DialogTitle>アカウント削除の確認</DialogTitle>
        <DialogContent>
          <DialogContentText>
            本当にアカウントを削除しますか？この操作は取り消せません。
          </DialogContentText>

          {deleteError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {deleteError}
            </Alert>
          )}

          <TextField
            fullWidth
            type="password"
            label="パスワード（確認用）"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            margin="normal"
            required
            disabled={deleteLoading}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={deleteLoading}>
            キャンセル
          </Button>
          <Button
            onClick={handleDeleteAccount}
            color="error"
            variant="contained"
            disabled={deleteLoading || !deletePassword}
          >
            {deleteLoading ? <CircularProgress size={24} /> : '削除する'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};
