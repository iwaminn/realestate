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
} from '@mui/material';
import {
  Undo as UndoIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

interface MergeHistory {
  id: number;
  primary_building: {
    id: number;
    normalized_name: string;
  };
  secondary_building?: {
    id: number;
    normalized_name: string;
    properties_moved: number | null;
  };
  moved_properties: number;
  merge_details: any;
  merged_by?: string;
  created_at: string;
  reverted_at: string | null;
  reverted_by: string | null;
}

const BuildingMergeHistory: React.FC = () => {
  const [histories, setHistories] = useState<MergeHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedHistory, setSelectedHistory] = useState<MergeHistory | null>(null);
  const [reverting, setReverting] = useState(false);
  const [includeReverted, setIncludeReverted] = useState(false);

  useEffect(() => {
    fetchHistories();
  }, [includeReverted]);

  const fetchHistories = async () => {
    setLoading(true);
    try {
      const response = await propertyApi.getMergeHistory({
        limit: 50,
        include_reverted: includeReverted
      });
      setHistories(response.histories);
    } catch (error) {
      console.error('Failed to fetch merge history:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRevert = async (historyId: number) => {
    if (!confirm('この統合を取り消しますか？')) {
      return;
    }

    setReverting(true);
    try {
      await propertyApi.revertBuildingMerge(historyId);
      alert('統合を取り消しました');
      fetchHistories();
    } catch (error: any) {
      console.error('Failed to revert building merge:', error);
      const errorMessage = error.response?.data?.detail || '取り消しに失敗しました';
      alert(errorMessage);
    } finally {
      setReverting(false);
      setSelectedHistory(null);
    }
  };

  const formatDate = (dateString: string) => {
    // サーバーから日本時間で返される
    return new Date(dateString).toLocaleString('ja-JP');
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
          <Typography variant="h6">建物統合履歴</Typography>
          <Button
            variant={includeReverted ? 'contained' : 'outlined'}
            onClick={() => setIncludeReverted(!includeReverted)}
          >
            取り消し済みを{includeReverted ? '非表示' : '表示'}
          </Button>
        </Box>

        {histories.length === 0 ? (
          <Alert severity="info">建物統合履歴がありません</Alert>
        ) : (
          <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>統合日時</TableCell>
                <TableCell>統合元建物（削除）</TableCell>
                <TableCell>→</TableCell>
                <TableCell>統合先建物（残存）</TableCell>
                <TableCell align="center">移動物件数</TableCell>
                <TableCell align="center">実行者</TableCell>
                <TableCell align="center">状態</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {histories.map((history) => (
                <TableRow key={history.id}>
                  <TableCell>{formatDate(history.created_at)}</TableCell>
                  <TableCell>
                    {history.secondary_building ? (
                      <Tooltip title={`ID: ${history.secondary_building.id}`}>
                        <Typography variant="body2">
                          {history.secondary_building.normalized_name}
                        </Typography>
                      </Tooltip>
                    ) : (
                      <Typography variant="body2" color="textSecondary">
                        -
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Typography variant="body2" color="textSecondary">→</Typography>
                  </TableCell>
                  <TableCell>
                    <Tooltip title={`ID: ${history.primary_building.id}`}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {history.primary_building.normalized_name}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center">{history.moved_properties}</TableCell>
                  <TableCell align="center">
                    {history.merged_by === 'auto_merge_script' ? (
                      <Chip label="自動統合" size="small" variant="outlined" />
                    ) : (
                      history.merged_by || '-'
                    )}
                  </TableCell>
                  <TableCell align="center">
                    {history.reverted_at ? (
                      <Chip label="取り消し済み" size="small" />
                    ) : (
                      <Chip label="有効" size="small" color="primary" />
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Tooltip title="詳細を表示">
                      <IconButton
                        size="small"
                        onClick={() => setSelectedHistory(history)}
                      >
                        <InfoIcon />
                      </IconButton>
                    </Tooltip>
                    {!history.reverted_at && (
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
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        )}
      </Paper>

      <Dialog
        open={!!selectedHistory}
        onClose={() => setSelectedHistory(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>建物統合詳細</DialogTitle>
        <DialogContent>
          {selectedHistory && (
            <Box>
              <Box mb={2}>
                <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                  統合の流れ
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  <Box flex={1}>
                    <Typography variant="caption" color="textSecondary">
                      統合元（削除された建物）
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, mt: 1 }}>
                      {selectedHistory.secondary_building ? (
                        <>
                          <Typography variant="body2" gutterBottom>
                            ID: {selectedHistory.secondary_building.id}
                          </Typography>
                          <Typography variant="body2">
                            {selectedHistory.secondary_building.normalized_name}
                          </Typography>
                        </>
                      ) : (
                        <Typography variant="body2" color="textSecondary">
                          情報なし
                        </Typography>
                      )}
                    </Paper>
                  </Box>
                  <Box>
                    <Typography variant="h6" color="textSecondary">→</Typography>
                  </Box>
                  <Box flex={1}>
                    <Typography variant="caption" color="textSecondary">
                      統合先（残った建物）
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, mt: 1, bgcolor: 'primary.50' }}>
                      <Typography variant="body2" gutterBottom sx={{ fontWeight: 'bold' }}>
                        ID: {selectedHistory.primary_building.id}
                      </Typography>
                      <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                        {selectedHistory.primary_building.normalized_name}
                      </Typography>
                    </Paper>
                  </Box>
                </Box>
              </Box>
              
              <Box mt={2}>
                <Typography variant="body2" color="textSecondary">
                  移動した物件数: {selectedHistory.moved_properties}件
                </Typography>
                {selectedHistory.merge_details?.batch_merge && (
                  <Alert severity="info" sx={{ mt: 1 }}>
                    この統合は複数建物の一括統合の一部です
                  </Alert>
                )}
              </Box>
              
              {selectedHistory.reverted_at && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  {formatDate(selectedHistory.reverted_at)} に取り消されました
                  {selectedHistory.reverted_by && ` (実行者: ${selectedHistory.reverted_by})`}
                </Alert>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedHistory(null)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default BuildingMergeHistory;