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
  Button,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Tooltip,
  TextField,
} from '@mui/material';
import {
  Undo as UndoIcon,
  Info as InfoIcon,
  Delete as DeleteIcon,
  DeleteSweep as DeleteSweepIcon,
} from '@mui/icons-material';
import axios from 'axios';
import Pagination from './common/Pagination';

interface PropertyMergeHistory {
  id: number;
  primary_property: {
    id: number;
    building_name: string;
    room_number: string | null;
    floor_number: number | null;
    area: number | null;
    layout: string | null;
  };
  secondary_property: {
    id: number;
    room_number: string | null;
    floor_number: number | null;
    area: number | null;
    layout: string | null;
  };
  moved_listings: number;
  merge_details: any;
  merged_by: string;
  merged_at: string;
}

const PropertyMergeHistory: React.FC = () => {
  const [histories, setHistories] = useState<PropertyMergeHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedHistory, setSelectedHistory] = useState<PropertyMergeHistory | null>(null);
  const [reverting, setReverting] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkDeleteConfirmText, setBulkDeleteConfirmText] = useState('');

  useEffect(() => {
    fetchHistories();
  }, [page, pageSize]);

  const fetchHistories = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/admin/property-merge-history', {
        params: {
          limit: pageSize,
          offset: (page - 1) * pageSize
        }
      });
      setHistories(response.data.histories);
      setTotalCount(response.data.total || 0);
    } catch (error) {
      console.error('Failed to fetch property merge history:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRevert = async (historyId: number) => {
    if (!confirm('この物件統合を取り消しますか？')) {
      return;
    }

    setReverting(true);
    try {
      await axios.post(`/admin/revert-property-merge/${historyId}`);
      alert('物件統合を取り消しました');
      fetchHistories();
    } catch (error: any) {
      console.error('Failed to revert property merge:', error);
      const errorMessage = error.response?.data?.detail || error.message || '取り消しに失敗しました';
      alert(`取り消しに失敗しました: ${errorMessage}`);
    } finally {
      setReverting(false);
      setSelectedHistory(null);
    }
  };

  const handleDelete = async (historyId: number) => {
    if (!confirm('この統合履歴を削除しますか？\n（統合自体は維持され、履歴のみが削除されます）')) {
      return;
    }

    try {
      await axios.delete(`/admin/property-merge-history/${historyId}`);
      alert('統合履歴を削除しました');
      fetchHistories();
    } catch (error: any) {
      console.error('Failed to delete property merge history:', error);
      const errorMessage = error.response?.data?.detail || error.message || '削除に失敗しました';
      alert(`削除に失敗しました: ${errorMessage}`);
    }
  };

  const handleBulkDelete = async () => {
    if (bulkDeleteConfirmText !== '削除') {
      alert('確認文字列が正しくありません');
      return;
    }

    try {
      const result = await axios.delete('/admin/property-merge-history/bulk');
      alert(result.data.message);
      setBulkDeleteDialogOpen(false);
      setBulkDeleteConfirmText('');
      fetchHistories();
    } catch (error: any) {
      console.error('Failed to bulk delete property merge history:', error);
      const errorMessage = error.response?.data?.detail || '一括削除に失敗しました';
      alert(errorMessage);
    }
  };

  const formatDate = (dateString: string) => {
    // サーバーから日本時間で返される
    return new Date(dateString).toLocaleString('ja-JP');
  };

  const formatPropertyInfo = (property: any) => {
    const parts = [];
    if (property.room_number) parts.push(`部屋${property.room_number}`);
    if (property.floor_number) parts.push(`${property.floor_number}F`);
    if (property.area) parts.push(`${property.area}㎡`);
    if (property.layout) parts.push(property.layout);
    return parts.join(' / ') || '-';
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">物件統合履歴</Typography>
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteSweepIcon />}
            onClick={() => setBulkDeleteDialogOpen(true)}
            disabled={histories.length === 0}
          >
            一括削除
          </Button>
        </Box>

        {histories.length === 0 ? (
          <Alert severity="info">物件統合履歴がありません</Alert>
        ) : (
          <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>統合日時</TableCell>
                <TableCell>建物</TableCell>
                <TableCell>統合元物件（削除）</TableCell>
                <TableCell>→</TableCell>
                <TableCell>統合先物件（残存）</TableCell>
                <TableCell align="center">移動掲載数</TableCell>
                <TableCell align="center">実行者</TableCell>
                <TableCell align="center">状態</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {histories.map((history) => (
                <TableRow key={history.id}>
                  <TableCell>{formatDate(history.merged_at)}</TableCell>
                  <TableCell>{history.primary_property.building_name}</TableCell>
                  <TableCell>
                    <Tooltip title={`ID: ${history.secondary_property.id}`}>
                      <span>{formatPropertyInfo(history.secondary_property)}</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center">
                    <Typography variant="body2" color="textSecondary">→</Typography>
                  </TableCell>
                  <TableCell>
                    <Tooltip title={`ID: ${history.primary_property.id}`}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {formatPropertyInfo(history.primary_property)}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center">{history.moved_listings}</TableCell>
                  <TableCell align="center">
                    {history.merged_by === 'auto_merge_script' ? (
                      <Chip label="自動統合" size="small" variant="outlined" />
                    ) : (
                      history.merged_by || '-'
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Chip label="有効" size="small" color="primary" />
                  </TableCell>
                  <TableCell align="center">
                    <Box display="flex" justifyContent="center" gap={0.5}>
                      <Tooltip title="詳細を表示">
                        <IconButton
                          size="small"
                          onClick={() => setSelectedHistory(history)}
                        >
                          <InfoIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="統合を取り消す">
                        <IconButton
                          size="small"
                          color="warning"
                          onClick={() => handleRevert(history.id)}
                          disabled={reverting}
                        >
                          <UndoIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="履歴を削除">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleDelete(history.id)}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
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

      <Dialog
        open={!!selectedHistory}
        onClose={() => setSelectedHistory(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>物件統合詳細</DialogTitle>
        <DialogContent>
          {selectedHistory && (
            <Box>
              <Typography variant="subtitle1" gutterBottom>
                建物: {selectedHistory.primary_property.building_name}
              </Typography>
              
              <Box mb={2}>
                <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                  統合の流れ
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  <Box flex={1}>
                    <Typography variant="caption" color="textSecondary">
                      統合元（削除された物件）
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, mt: 1 }}>
                      <Typography variant="body2" gutterBottom>
                        ID: {selectedHistory.secondary_property.id}
                      </Typography>
                      <Typography variant="body2">
                        {formatPropertyInfo(selectedHistory.secondary_property)}
                      </Typography>
                    </Paper>
                  </Box>
                  <Box>
                    <Typography variant="h6" color="textSecondary">→</Typography>
                  </Box>
                  <Box flex={1}>
                    <Typography variant="caption" color="textSecondary">
                      統合先（残った物件）
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, mt: 1, bgcolor: 'primary.50' }}>
                      <Typography variant="body2" gutterBottom sx={{ fontWeight: 'bold' }}>
                        ID: {selectedHistory.primary_property.id}
                      </Typography>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {formatPropertyInfo(selectedHistory.primary_property)}
                      </Typography>
                    </Paper>
                  </Box>
                </Box>
              </Box>

              <Box mt={2}>
                <Typography variant="body2" color="textSecondary">
                  移動した掲載情報: {selectedHistory.moved_listings}件
                </Typography>
                {selectedHistory.merge_details?.reason && (
                  <Typography variant="body2" color="textSecondary">
                    統合理由: {selectedHistory.merge_details.reason}
                  </Typography>
                )}
              </Box>

            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedHistory(null)}>閉じる</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={bulkDeleteDialogOpen}
        onClose={() => {
          setBulkDeleteDialogOpen(false);
          setBulkDeleteConfirmText('');
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>物件統合履歴の一括削除</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            すべての物件統合履歴を削除します。この操作は取り消せません。
            統合自体は維持され、履歴のみが削除されます。
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

export default PropertyMergeHistory;