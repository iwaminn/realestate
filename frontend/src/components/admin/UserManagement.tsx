import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  Button,
  IconButton,
  Chip,
  Typography,
  Grid,
  Card,
  CardContent,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Tooltip,
  InputAdornment,
  FormControlLabel,
  Switch,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Checkbox
} from '@mui/material';
import {
  Search as SearchIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  Email as EmailIcon,
  VerifiedUser as VerifiedIcon,
  Block as BlockIcon,
  Bookmark as BookmarkIcon,
  PersonAdd as PersonAddIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import axios from 'axios';

interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  bookmark_count: number;
}

interface UserStats {
  total_users: number;
  active_users: number;
  users_with_bookmarks: number;
  new_users_today: number;
  new_users_this_week: number;
  new_users_this_month: number;
}

interface UserDetail extends User {
  updated_at: string;
  stats: {
    total_bookmarks: number;
    last_login_at: string | null;
    created_at: string;
    email_verified_at: string | null;
  };
}

export const UserManagement: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // フィルタと検索
  const [searchQuery, setSearchQuery] = useState('');
  const [filterActive, setFilterActive] = useState<boolean | null>(null);
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');

  // ページネーション
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // ダイアログ
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // 編集フォーム
  const [editForm, setEditForm] = useState({
    email: '',
    is_active: true,
    password: ''
  });

  // 削除確認用
  const [deleteConfirmation, setDeleteConfirmation] = useState({
    confirmEmail: '',
    confirmCheckboxes: {
      permanent: false,
      bookmarks: false,
      understand: false
    }
  });

  useEffect(() => {
    loadUsers();
    loadStats();
  }, [searchQuery, filterActive, sortBy, sortOrder, page, rowsPerPage]);

  const loadUsers = async () => {
    setLoading(true);
    setError('');
    
    try {
      const params = new URLSearchParams({
        skip: String(page * rowsPerPage),
        limit: String(rowsPerPage),
        sort_by: sortBy,
        sort_order: sortOrder
      });

      if (searchQuery) params.append('search', searchQuery);
      if (filterActive !== null) params.append('is_active', String(filterActive));

      const response = await axios.get(`/api/admin/users?${params}`);
      setUsers(response.data.users);
      setTotalUsers(response.data.total);
    } catch (error: any) {
      console.error('ユーザー一覧の取得エラー:', error);
      setError('ユーザー一覧の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const response = await axios.get('/api/admin/users/stats');
      setStats(response.data);
    } catch (error: any) {
      console.error('統計情報の取得エラー:', error);
    }
  };

  const loadUserDetail = async (userId: number) => {
    try {
      const response = await axios.get(`/api/admin/users/${userId}`);
      setSelectedUser(response.data);
      setDetailDialogOpen(true);
    } catch (error: any) {
      console.error('ユーザー詳細の取得エラー:', error);
      setError('ユーザー詳細の取得に失敗しました');
    }
  };

  const handleEdit = (user: User) => {
    setEditForm({
      email: user.email,
      is_active: user.is_active,
      password: ''
    });
    setSelectedUser(user as UserDetail);
    setEditDialogOpen(true);
  };

  const handleUpdate = async () => {
    if (!selectedUser) return;

    try {
      const updateData: any = {
        email: editForm.email,
        is_active: editForm.is_active
      };

      if (editForm.password) {
        updateData.password = editForm.password;
      }

      await axios.put(`/api/admin/users/${selectedUser.id}`, updateData);
      
      setSuccess('ユーザー情報を更新しました');
      setEditDialogOpen(false);
      loadUsers();
    } catch (error: any) {
      console.error('ユーザー更新エラー:', error);
      setError(error.response?.data?.detail || 'ユーザー更新に失敗しました');
    }
  };

  const handleDelete = async () => {
    if (!selectedUser) return;

    try {
      await axios.delete(`/api/admin/users/${selectedUser.id}`);
      
      setSuccess('ユーザーを削除しました');
      setDeleteDialogOpen(false);
      loadUsers();
      loadStats();
    } catch (error: any) {
      console.error('ユーザー削除エラー:', error);
      setError('ユーザー削除に失敗しました');
    }
  };


  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('ja-JP');
  };

  return (
    <Box>
      {/* 統計情報カード */}
      {stats && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  総ユーザー数
                </Typography>
                <Typography variant="h4">
                  {stats.total_users}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  今日: +{stats.new_users_today}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  アクティブユーザー
                </Typography>
                <Typography variant="h4">
                  {stats.active_users}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {Math.round((stats.active_users / stats.total_users) * 100)}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  ブックマーク利用者
                </Typography>
                <Typography variant="h4">
                  {stats.users_with_bookmarks}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  今週: +{stats.new_users_this_week}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* エラー・成功メッセージ */}
      {error && (
        <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" onClose={() => setSuccess('')} sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}

      {/* フィルタと検索 */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              label="検索（メール・名前）"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                )
              }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth>
              <InputLabel>アクティブ状態</InputLabel>
              <Select
                value={filterActive === null ? '' : filterActive}
                label="アクティブ状態"
                onChange={(e) => setFilterActive(e.target.value === '' ? null : e.target.value === 'true')}
              >
                <MenuItem value="">すべて</MenuItem>
                <MenuItem value="true">アクティブ</MenuItem>
                <MenuItem value="false">非アクティブ</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth>
              <InputLabel>並び順</InputLabel>
              <Select
                value={sortBy}
                label="並び順"
                onChange={(e) => setSortBy(e.target.value)}
              >
                <MenuItem value="created_at">登録日</MenuItem>
                <MenuItem value="last_login_at">最終ログイン</MenuItem>
                <MenuItem value="email">メールアドレス</MenuItem>
                <MenuItem value="bookmark_count">ブックマーク数</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Button
              fullWidth
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={() => {
                loadUsers();
                loadStats();
              }}
            >
              更新
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* ユーザーテーブル */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>メールアドレス</TableCell>
              <TableCell align="center">状態</TableCell>
              <TableCell align="center">ブックマーク</TableCell>
              <TableCell>登録日</TableCell>
              <TableCell>最終ログイン</TableCell>
              <TableCell align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.id}</TableCell>
                <TableCell>{user.email}</TableCell>
                <TableCell align="center">
                  {user.is_active ? (
                    <Chip label="アクティブ" color="success" size="small" />
                  ) : (
                    <Chip label="非アクティブ" color="default" size="small" />
                  )}
                </TableCell>
                <TableCell align="center">
                  <Chip
                    icon={<BookmarkIcon />}
                    label={user.bookmark_count}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>{formatDate(user.created_at)}</TableCell>
                <TableCell>{formatDate(user.last_login_at)}</TableCell>
                <TableCell align="center">
                  <IconButton
                    size="small"
                    onClick={() => loadUserDetail(user.id)}
                  >
                    <VisibilityIcon />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={() => handleEdit(user)}
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    size="small"
                    color="error"
                    onClick={() => {
                      setSelectedUser(user as UserDetail);
                      setDeleteConfirmation({
                        confirmEmail: '',
                        confirmCheckboxes: {
                          permanent: false,
                          bookmarks: false,
                          understand: false
                        }
                      });
                      setDeleteDialogOpen(true);
                    }}
                  >
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={totalUsers}
          page={page}
          onPageChange={(e, newPage) => setPage(newPage)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[10, 25, 50, 100]}
          labelRowsPerPage="表示件数:"
          labelDisplayedRows={({ from, to, count }) =>
            `${from}-${to} / ${count !== -1 ? count : `${to}+`}`
          }
        />
      </TableContainer>

      {/* ユーザー詳細ダイアログ */}
      <Dialog open={detailDialogOpen} onClose={() => setDetailDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>ユーザー詳細</DialogTitle>
        <DialogContent>
          {selectedUser && (
            <Box sx={{ pt: 2 }}>
              <Typography variant="body2" color="textSecondary">
                ID: {selectedUser.id}
              </Typography>
              <Typography variant="h6" sx={{ mt: 1 }}>
                {selectedUser.email}
              </Typography>
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="textSecondary">
                  登録日: {formatDate(selectedUser.created_at)}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  更新日: {formatDate(selectedUser.updated_at)}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  最終ログイン: {formatDate(selectedUser.last_login_at)}
                </Typography>
                {selectedUser.stats?.email_verified_at && (
                  <Typography variant="body2" color="textSecondary">
                    メール確認日: {formatDate(selectedUser.stats.email_verified_at)}
                  </Typography>
                )}
              </Box>
              <Box sx={{ mt: 2 }}>
                <Chip
                  label={selectedUser.is_active ? 'アクティブ' : '非アクティブ'}
                  color={selectedUser.is_active ? 'success' : 'default'}
                  sx={{ mr: 1 }}
                />
              </Box>
              {selectedUser.stats && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    ブックマーク数: {selectedUser.stats.total_bookmarks}
                  </Typography>
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailDialogOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>

      {/* 編集ダイアログ */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>ユーザー編集</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <TextField
              fullWidth
              label="メールアドレス"
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
              margin="normal"
            />
            <TextField
              fullWidth
              label="新しいパスワード（変更する場合のみ）"
              type="password"
              value={editForm.password}
              onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
              margin="normal"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                />
              }
              label="アクティブ"
              sx={{ mt: 2 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>キャンセル</Button>
          <Button onClick={handleUpdate} variant="contained" color="primary">
            更新
          </Button>
        </DialogActions>
      </Dialog>

      {/* 削除確認ダイアログ */}
      <Dialog 
        open={deleteDialogOpen} 
        onClose={() => setDeleteDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Typography variant="h6" color="error">
            ⚠️ ユーザー削除の確認
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 3 }}>
            <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
              この操作は取り消すことができません
            </Typography>
            <Typography variant="body2">
              ユーザーを削除すると、以下のデータもすべて削除されます：
            </Typography>
          </Alert>

          {selectedUser && (
            <>
              <Typography variant="subtitle1" sx={{ mb: 2 }}>
                削除対象ユーザー: <strong>{selectedUser.email}</strong>
              </Typography>

              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <BookmarkIcon color="action" />
                  </ListItemIcon>
                  <ListItemText 
                    primary="ブックマーク"
                    secondary={`${selectedUser.bookmark_count || 0}件のブックマークが削除されます`}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <EmailIcon color="action" />
                  </ListItemIcon>
                  <ListItemText 
                    primary="メール履歴"
                    secondary="すべてのメール履歴が削除されます"
                  />
                </ListItem>
              </List>

              <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }} color="error">
                削除を続行するには、以下を確認してください：
              </Typography>

              <Box sx={{ ml: 2 }}>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={deleteConfirmation.confirmCheckboxes.permanent}
                      onChange={(e) => setDeleteConfirmation({
                        ...deleteConfirmation,
                        confirmCheckboxes: {
                          ...deleteConfirmation.confirmCheckboxes,
                          permanent: e.target.checked
                        }
                      })}
                      color="error"
                    />
                  }
                  label="この操作は完全に不可逆であることを理解しました"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={deleteConfirmation.confirmCheckboxes.bookmarks}
                      onChange={(e) => setDeleteConfirmation({
                        ...deleteConfirmation,
                        confirmCheckboxes: {
                          ...deleteConfirmation.confirmCheckboxes,
                          bookmarks: e.target.checked
                        }
                      })}
                      color="error"
                    />
                  }
                  label="ユーザーのブックマークがすべて削除されることを理解しました"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={deleteConfirmation.confirmCheckboxes.understand}
                      onChange={(e) => setDeleteConfirmation({
                        ...deleteConfirmation,
                        confirmCheckboxes: {
                          ...deleteConfirmation.confirmCheckboxes,
                          understand: e.target.checked
                        }
                      })}
                      color="error"
                    />
                  }
                  label="本当にこのユーザーを削除したいです"
                />
              </Box>

              <TextField
                fullWidth
                label="確認のためユーザーのメールアドレスを入力"
                value={deleteConfirmation.confirmEmail}
                onChange={(e) => setDeleteConfirmation({
                  ...deleteConfirmation,
                  confirmEmail: e.target.value
                })}
                margin="normal"
                error={deleteConfirmation.confirmEmail !== '' && deleteConfirmation.confirmEmail !== selectedUser.email}
                helperText={
                  deleteConfirmation.confirmEmail !== '' && 
                  deleteConfirmation.confirmEmail !== selectedUser.email && 
                  "メールアドレスが一致しません"
                }
                sx={{ mt: 3 }}
              />
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button 
            onClick={() => {
              setDeleteDialogOpen(false);
              setDeleteConfirmation({
                confirmEmail: '',
                confirmCheckboxes: {
                  permanent: false,
                  bookmarks: false,
                  understand: false
                }
              });
            }}
            variant="outlined"
          >
            キャンセル
          </Button>
          <Button 
            onClick={handleDelete} 
            variant="contained" 
            color="error"
            disabled={
              !selectedUser ||
              deleteConfirmation.confirmEmail !== selectedUser.email ||
              !deleteConfirmation.confirmCheckboxes.permanent ||
              !deleteConfirmation.confirmCheckboxes.bookmarks ||
              !deleteConfirmation.confirmCheckboxes.understand
            }
          >
            ユーザーを削除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};