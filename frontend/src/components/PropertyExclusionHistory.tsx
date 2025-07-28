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
} from '@mui/material';
import {
  Undo as UndoIcon,
} from '@mui/icons-material';
import axios from 'axios';

interface PropertyExclusion {
  id: number;
  property1: {
    id: number;
    info: string;
  };
  property2: {
    id: number;
    info: string;
  };
  reason: string;
  excluded_by: string;
  created_at: string;
}

const PropertyExclusionHistory: React.FC = () => {
  const [exclusions, setExclusions] = useState<PropertyExclusion[]>([]);
  const [loading, setLoading] = useState(true);
  const [reverting, setReverting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    console.log('PropertyExclusionHistory mounted');
    fetchExclusions();
  }, []);

  const fetchExclusions = async () => {
    setLoading(true);
    setError(null);
    try {
      console.log('Fetching exclusions...');
      const response = await axios.get('/api/admin/property-exclusions', {
        params: { limit: 100 }
      });
      console.log('Response:', response.data);
      
      // APIレスポンスが配列かオブジェクトか確認
      let exclusionData: PropertyExclusion[] = [];
      if (Array.isArray(response.data)) {
        exclusionData = response.data;
      } else if (response.data && Array.isArray(response.data.exclusions)) {
        exclusionData = response.data.exclusions;
      } else if (response.data && Array.isArray(response.data.data)) {
        exclusionData = response.data.data;
      } else {
        console.warn('Unexpected response format:', response.data);
        exclusionData = [];
      }
      
      setExclusions(exclusionData);
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
      await axios.delete(`/api/admin/exclude-properties/${exclusionId}`);
      alert('除外設定を取り消しました');
      fetchExclusions();
    } catch (error) {
      console.error('Failed to revert property exclusion:', error);
      alert('取り消しに失敗しました');
    } finally {
      setReverting(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
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
        <Typography variant="h6" gutterBottom>物件除外履歴</Typography>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>物件除外履歴</Typography>
      {exclusions.length === 0 ? (
        <Alert severity="info">物件除外履歴がありません</Alert>
      ) : (
        <TableContainer component={Paper}>
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
                        <span>{exclusion.property1?.info || '不明'}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={`ID: ${exclusion.property2?.id || '-'}`}>
                        <span>{exclusion.property2?.info || '不明'}</span>
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
    </Box>
  );
};

export default PropertyExclusionHistory;