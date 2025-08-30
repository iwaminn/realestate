import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  CircularProgress,
  IconButton,
  Tooltip,
  Chip,
  Snackbar,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material';
import {
  Undo as UndoIcon,
  Refresh as RefreshIcon,
  DeleteSweep as DeleteSweepIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';
import Pagination from './common/Pagination';

interface BuildingExclusion {
  id: number;
  building1: {
    id: number;
    normalized_name: string;
    address: string;
    property_count: number;
  };
  building2: {
    id: number;
    normalized_name: string;
    address: string;
    property_count: number;
  };
  reason: string;
  excluded_by: string;
  created_at: string;
}

const BuildingExclusionHistory: React.FC = () => {
  const [exclusions, setExclusions] = useState<BuildingExclusion[]>([]);
  const [loading, setLoading] = useState(true);
  const [reverting, setReverting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [snackbar, setSnackbar] = useState({ 
    open: false, 
    message: '', 
    severity: 'success' as 'success' | 'error' 
  });
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkDeleteConfirmText, setBulkDeleteConfirmText] = useState('');

  useEffect(() => {
    fetchExclusions();
  }, [page, pageSize]);

  const fetchExclusions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await propertyApi.getBuildingExclusions({ 
        limit: pageSize,
        offset: (page - 1) * pageSize
      });
      setExclusions(response.exclusions || []);
      setTotalCount(response.total || 0);
    } catch (error) {
      console.error('Failed to fetch building exclusions:', error);
      setError('除外履歴の取得に失敗しました');
      setExclusions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleRevert = async (exclusionId: number) => {
    if (!confirm('この除外設定を取り消しますか？これらの建物は再び重複候補として表示されるようになります。')) {
      return;
    }

    setReverting(true);
    try {
      await propertyApi.removeExclusion(exclusionId);
      setSnackbar({
        open: true,
        message: '除外設定を取り消しました',
        severity: 'success'
      });
      fetchExclusions();
    } catch (error) {
      console.error('Failed to revert building exclusion:', error);
      setSnackbar({
        open: true,
        message: '取り消しに失敗しました',
        severity: 'error'
      });
    } finally {
      setReverting(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      // サーバーから日本時間で返される
      return new Date(dateString).toLocaleString('ja-JP');
    } catch (e) {
      return dateString;
    }
  };

  const handleBulkDelete = async () => {
    if (bulkDeleteConfirmText !== '削除') {
      setSnackbar({
        open: true,
        message: '確認文字列が正しくありません',
        severity: 'error'
      });
      return;
    }

    try {
      const result = await propertyApi.bulkDeleteBuildingExclusions();
      setSnackbar({
        open: true,
        message: result.message,
        severity: 'success'
      });
      setBulkDeleteDialogOpen(false);
      setBulkDeleteConfirmText('');
      fetchExclusions();
    } catch (error: any) {
      console.error('Failed to bulk delete building exclusions:', error);
      const errorMessage = error.response?.data?.detail || '一括削除に失敗しました';
      setSnackbar({
        open: true,
        message: errorMessage,
        severity: 'error'
      });
    }
  };

  const getReasonDisplay = (reason: string) => {
    if (!reason) {
      return { label: '理由なし', color: 'default' as const };
    }
    if (reason === '同一建物ではないため') {
      return { label: '別建物', color: 'warning' as const };
    } else if (reason === '手動で別建物として指定') {
      return { label: '手動指定', color: 'error' as const };
    } else if (reason === '棟違い') {
      return { label: '棟違い', color: 'info' as const };
    }
    return { label: reason, color: 'default' as const };
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>建物除外履歴</Typography>
          <Alert severity="error">{error}</Alert>
        </Paper>
      </Box>
    );
  }

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">建物除外履歴</Typography>
          <Box display="flex" gap={1}>
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteSweepIcon />}
              onClick={() => setBulkDeleteDialogOpen(true)}
              disabled={exclusions.length === 0}
            >
              一括削除
            </Button>
            <IconButton 
              onClick={fetchExclusions}
              disabled={loading}
              color="primary"
            >
              <Tooltip title="リロード">
                <RefreshIcon />
              </Tooltip>
            </IconButton>
          </Box>
        </Box>
        
        {exclusions.length === 0 ? (
          <Alert severity="info">建物除外履歴がありません</Alert>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>除外日時</TableCell>
                  <TableCell>建物1</TableCell>
                  <TableCell>建物2</TableCell>
                  <TableCell align="center">物件数</TableCell>
                  <TableCell align="center">除外理由</TableCell>
                  <TableCell align="center">実行者</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {exclusions.map((exclusion) => {
                  const reasonDisplay = getReasonDisplay(exclusion.reason);
                  return (
                    <TableRow key={exclusion.id}>
                      <TableCell>{formatDate(exclusion.created_at)}</TableCell>
                      <TableCell>
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {exclusion.building1?.normalized_name || '不明'}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            {exclusion.building1?.address || '-'}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {exclusion.building2?.normalized_name || '不明'}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            {exclusion.building2?.address || '-'}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <Box>
                          <Chip 
                            label={exclusion.building1?.property_count || 0} 
                            size="small" 
                            sx={{ mr: 0.5 }}
                          />
                          <Chip 
                            label={exclusion.building2?.property_count || 0} 
                            size="small" 
                          />
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <Chip 
                          label={reasonDisplay.label} 
                          size="small" 
                          color={reasonDisplay.color}
                        />
                      </TableCell>
                      <TableCell align="center">
                        {exclusion.excluded_by || '-'}
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title="除外を取り消す">
                          <IconButton
                            size="small"
                            color="warning"
                            onClick={() => handleRevert(exclusion.id)}
                            disabled={reverting}
                          >
                            <UndoIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        
        <Pagination
          totalCount={totalCount}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </Paper>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>

      <Dialog
        open={bulkDeleteDialogOpen}
        onClose={() => {
          setBulkDeleteDialogOpen(false);
          setBulkDeleteConfirmText('');
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>建物除外履歴の一括削除</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            すべての建物除外履歴を削除します。この操作は取り消せません。
            削除後、除外していた建物ペアが再び重複候補として表示される可能性があります。
          </Alert>
          <Typography variant="body2" gutterBottom>
            削除を実行するには、下のフィールドに「削除」と入力してください。
          </Typography>
          <TextField
            fullWidth
            value={bulkDeleteConfirmText}
            onChange={(e) => setBulkDeleteConfirmText(e.target.value)}
            placeholder="削除"
            variant="outlined"
            sx={{ mt: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => {
              setBulkDeleteDialogOpen(false);
              setBulkDeleteConfirmText('');
            }}
          >
            キャンセル
          </Button>
          <Button 
            onClick={handleBulkDelete}
            color="error"
            variant="contained"
            disabled={bulkDeleteConfirmText !== '削除'}
          >
            一括削除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default BuildingExclusionHistory;