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
import axios from 'axios';
import Pagination from './common/Pagination';

interface PropertyInfo {
  id: number;
  info: string;
  building_name: string | null;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  direction: string | null;
  price: number | null;
}

interface PropertyExclusion {
  id: number;
  property1: PropertyInfo;
  property2: PropertyInfo;
  reason: string;
  excluded_by: string;
  created_at: string;
}

const PropertyDisplay: React.FC<{ property: PropertyInfo }> = ({ property }) => {
  if (!property) return <span>不明</span>;
  
  return (
    <Box>
      <Typography variant="body2" fontWeight="bold">
        {property.building_name || '建物名不明'}
        {property.room_number && ` ${property.room_number}`}
      </Typography>
      <Box display="flex" gap={1} flexWrap="wrap" mt={0.5}>
        {property.floor_number && (
          <Chip label={`${property.floor_number}階`} size="small" variant="outlined" />
        )}
        {property.area && (
          <Chip label={`${property.area}㎡`} size="small" variant="outlined" />
        )}
        {property.direction && (
          <Chip label={property.direction} size="small" variant="outlined" />
        )}
        {property.price && (
          <Chip 
            label={`${property.price.toLocaleString()}万円`} 
            size="small" 
            variant="outlined"
            color="primary"
          />
        )}
      </Box>
    </Box>
  );
};

const PropertyExclusionHistory: React.FC = () => {
  const [exclusions, setExclusions] = useState<PropertyExclusion[]>([]);
  const [loading, setLoading] = useState(true);
  const [reverting, setReverting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkDeleteConfirmText, setBulkDeleteConfirmText] = useState('');

  useEffect(() => {
    fetchExclusions();
  }, [page, pageSize]);

  const fetchExclusions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/admin/property-exclusions', {
        params: {
          limit: pageSize,
          offset: (page - 1) * pageSize
        }
      });
  
      
      // APIレスポンスが配列かオブジェクトか確認
      let exclusionData: PropertyExclusion[] = [];
      let total = 0;
      if (Array.isArray(response.data)) {
        exclusionData = response.data;
        total = response.data.length;
      } else if (response.data && Array.isArray(response.data.exclusions)) {
        exclusionData = response.data.exclusions;
        total = response.data.total || exclusionData.length;
      } else if (response.data && Array.isArray(response.data.data)) {
        exclusionData = response.data.data;
        total = response.data.total || exclusionData.length;
      } else {
        console.warn('Unexpected response format:', response.data);
        exclusionData = [];
      }
      
      setExclusions(exclusionData);
      setTotalCount(total);
    } catch (error) {
      console.error('Failed to fetch property exclusions:', error);
      setError('除外履歴の取得に失敗しました');
      setExclusions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleRevert = async (exclusionId: number) => {
    if (!confirm('この除外設定を取り消しますか？これらの物件は再び重複候補として表示されるようになります。')) {
      return;
    }

    setReverting(true);
    try {
      await axios.delete(`/admin/exclude-properties/${exclusionId}`);
      alert('除外設定を取り消しました');
      fetchExclusions();
    } catch (error: any) {
      console.error('Failed to revert property exclusion:', error);
      const errorMessage = error.response?.data?.detail || error.message || '取り消しに失敗しました';
      alert(`取り消しに失敗しました: ${errorMessage}`);
    } finally {
      setReverting(false);
    }
  };

  const handleBulkDelete = async () => {
    if (bulkDeleteConfirmText !== '削除') {
      alert('確認文字列が正しくありません');
      return;
    }

    try {
      const result = await axios.delete('/admin/property-exclusions/bulk');
      alert(result.data.message);
      setBulkDeleteDialogOpen(false);
      setBulkDeleteConfirmText('');
      fetchExclusions();
    } catch (error: any) {
      console.error('Failed to bulk delete property exclusions:', error);
      const errorMessage = error.response?.data?.detail || '一括削除に失敗しました';
      alert(errorMessage);
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

  const getReasonDisplay = (reason: string) => {
    if (!reason) {
      return { label: '理由なし', color: 'default' as const };
    }
    if (reason === '別グループとして分離') {
      return { label: 'グループ分離', color: 'warning' as const };
    } else if (reason === '手動で別物件として指定') {
      return { label: '別物件指定', color: 'error' as const };
    } else if (reason === '方角が異なる別物件として維持') {
      return { label: '方角相違', color: 'info' as const };
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
          <Typography variant="h6" gutterBottom>物件除外履歴</Typography>
          <Alert severity="error">{error}</Alert>
        </Paper>
      </Box>
    );
  }

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">物件除外履歴</Typography>
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
          <Alert severity="info">物件除外履歴がありません</Alert>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                <TableCell>除外日時</TableCell>
                <TableCell>物件1</TableCell>
                <TableCell>物件2</TableCell>
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
                      <Tooltip title={`ID: ${exclusion.property1?.id || '-'}`}>
                        <Box>
                          <PropertyDisplay property={exclusion.property1} />
                        </Box>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={`ID: ${exclusion.property2?.id || '-'}`}>
                        <Box>
                          <PropertyDisplay property={exclusion.property2} />
                        </Box>
                      </Tooltip>
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

      <Dialog
        open={bulkDeleteDialogOpen}
        onClose={() => {
          setBulkDeleteDialogOpen(false);
          setBulkDeleteConfirmText('');
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>物件除外履歴の一括削除</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            すべての物件除外履歴を削除します。この操作は取り消せません。
            削除後、除外していた物件ペアが再び重複候補として表示される可能性があります。
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

export default PropertyExclusionHistory;