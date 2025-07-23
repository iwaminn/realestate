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
import axios from 'axios';

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
  reverted_at: string | null;
  reverted_by: string | null;
}

const PropertyMergeHistory: React.FC = () => {
  const [histories, setHistories] = useState<PropertyMergeHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedHistory, setSelectedHistory] = useState<PropertyMergeHistory | null>(null);
  const [reverting, setReverting] = useState(false);
  const [includeReverted, setIncludeReverted] = useState(false);

  useEffect(() => {
    fetchHistories();
  }, [includeReverted]);

  const fetchHistories = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/admin/property-merge-history', {
        params: {
          limit: 50,
          include_reverted: includeReverted
        }
      });
      setHistories(response.data.histories);
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
      await axios.post(`/api/admin/revert-property-merge/${historyId}`);
      alert('物件統合を取り消しました');
      fetchHistories();
    } catch (error) {
      console.error('Failed to revert property merge:', error);
      alert('取り消しに失敗しました');
    } finally {
      setReverting(false);
      setSelectedHistory(null);
    }
  };

  const formatDate = (dateString: string) => {
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
      <Box mb={2} display="flex" justifyContent="flex-end" alignItems="center">
        <Button
          variant={includeReverted ? 'contained' : 'outlined'}
          onClick={() => setIncludeReverted(!includeReverted)}
        >
          取り消し済みを{includeReverted ? '非表示' : '表示'}
        </Button>
      </Box>

      {histories.length === 0 ? (
        <Alert severity="info">物件統合履歴がありません</Alert>
      ) : (
        <TableContainer component={Paper}>
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

export default PropertyMergeHistory;