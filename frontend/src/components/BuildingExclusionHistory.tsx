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
} from '@mui/material';
import {
  Undo as UndoIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

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
  const [snackbar, setSnackbar] = useState({ 
    open: false, 
    message: '', 
    severity: 'success' as 'success' | 'error' 
  });

  useEffect(() => {
    fetchExclusions();
  }, []);

  const fetchExclusions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await propertyApi.getBuildingExclusions({ limit: 100 });
      setExclusions(response.exclusions || []);
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
    </Box>
  );
};

export default BuildingExclusionHistory;