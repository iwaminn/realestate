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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  CircularProgress,
  Snackbar,
  Chip,
  Grid,
  FormControlLabel,
  Checkbox,
  IconButton,
  Collapse,
  TextField,
  InputAdornment,
  Tooltip,
  Slider,
  MenuItem,
} from '@mui/material';
import {
  Merge as MergeIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Search as SearchIcon,
  Block as BlockIcon,
  History as HistoryIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

interface DuplicateGroup {
  primary: {
    id: number;
    normalized_name: string;
    address: string;
    total_floors?: number | null;
    property_count: number;
  };
  candidates: Array<{
    id: number;
    normalized_name: string;
    address: string;
    total_floors?: number | null;
    property_count: number;
    similarity: number;
    address_similarity?: number;
    floors_match?: boolean;
  }>;
}

const BuildingDuplicateManager: React.FC = () => {
  const [duplicateGroups, setDuplicateGroups] = useState<DuplicateGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [merging, setMerging] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<DuplicateGroup | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<number[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<number[]>([]);
  const [selectedMasterId, setSelectedMasterId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [minSimilarity, setMinSimilarity] = useState(0.94); // 単独の「棟」がある場合も検出できるレベル
  const [limit, setLimit] = useState(30); // 表示件数
  const [snackbar, setSnackbar] = useState({ 
    open: false, 
    message: '', 
    severity: 'success' as 'success' | 'error' 
  });

  useEffect(() => {
    // console.log('BuildingDuplicateManager mounted');
    fetchDuplicateBuildings();
  }, []);

  const fetchDuplicateBuildings = async (search?: string, similarity?: number, displayLimit?: number) => {
    // console.log('Fetching duplicate buildings...');
    setLoading(true);
    try {
      const params: any = { 
        limit: displayLimit || limit,
        min_similarity: similarity || minSimilarity
      };
      if (search) {
        params.search = search;
      }
      const response = await propertyApi.getDuplicateBuildings(params);
      // console.log('Response:', response);
      setDuplicateGroups(response.duplicate_groups);
    } catch (error) {
      console.error('Failed to fetch duplicate buildings:', error);
      setSnackbar({ 
        open: true, 
        message: '重複建物の取得に失敗しました', 
        severity: 'error' 
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    fetchDuplicateBuildings(searchQuery, minSimilarity, limit);
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleToggleExpand = (groupIndex: number) => {
    setExpandedGroups(prev => 
      prev.includes(groupIndex) 
        ? prev.filter(i => i !== groupIndex)
        : [...prev, groupIndex]
    );
  };

  const handleSelectGroup = (group: DuplicateGroup) => {
    setSelectedGroup(group);
    setSelectedCandidates(group.candidates.map(c => c.id));
    setSelectedMasterId(group.primary.id); // デフォルトで現在の主建物をマスターに
  };

  const handleToggleCandidate = (candidateId: number) => {
    setSelectedCandidates(prev =>
      prev.includes(candidateId)
        ? prev.filter(id => id !== candidateId)
        : [...prev, candidateId]
    );
  };

  const handleMerge = async () => {
    if (!selectedGroup || selectedCandidates.length === 0 || !selectedMasterId) return;

    setMerging(true);
    try {
      // マスター以外の建物IDを収集
      const allBuildingIds = [selectedGroup.primary.id, ...selectedCandidates];
      const buildingsToMerge = allBuildingIds.filter(id => id !== selectedMasterId);
      
      const response = await propertyApi.mergeBuildings(
        selectedMasterId,
        buildingsToMerge
      );

      setSnackbar({ 
        open: true, 
        message: `${response.merged_count}件の建物を統合し、${response.moved_properties}件の物件を移動しました`, 
        severity: 'success' 
      });

      // 統合された建物を含むグループをリストから削除（スムースな更新）
      setDuplicateGroups(prevGroups => {
        // 統合に関わったすべての建物IDのセット
        const mergedBuildingIds = new Set([selectedGroup.primary.id, ...selectedCandidates]);
        
        // 統合された建物を含まないグループのみを残す
        return prevGroups.filter(group => {
          // プライマリ建物が統合されたかチェック
          if (mergedBuildingIds.has(group.primary.id)) return false;
          
          // 候補建物が統合されたかチェック
          const remainingCandidates = group.candidates.filter(
            candidate => !mergedBuildingIds.has(candidate.id)
          );
          
          // 候補がまだ残っている場合はグループを更新して保持
          if (remainingCandidates.length > 0) {
            group.candidates = remainingCandidates;
            return true;
          }
          
          // 候補がなくなった場合はグループを削除
          return false;
        });
      });
      
      setSelectedGroup(null);
      setSelectedCandidates([]);
      setSelectedMasterId(null);
    } catch (error) {
      console.error('Failed to merge buildings:', error);
      setSnackbar({ 
        open: true, 
        message: '建物の統合に失敗しました', 
        severity: 'error' 
      });
    } finally {
      setMerging(false);
    }
  };

  const getSimilarityColor = (similarity: number) => {
    if (similarity >= 0.95) return 'error';
    if (similarity >= 0.9) return 'warning';
    return 'info';
  };

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          建物重複管理
        </Typography>
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            placeholder="建物名で検索（例：白金ザスカイ）"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  <Button 
                    variant="contained" 
                    onClick={handleSearch}
                    disabled={loading}
                    startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
                  >
                    {loading ? '読み込み中...' : '検索'}
                  </Button>
                </InputAdornment>
              ),
            }}
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <Box sx={{ px: 2 }}>
            <Typography variant="body2" color="textSecondary" gutterBottom>
              類似度: {(minSimilarity * 100).toFixed(0)}%
            </Typography>
            <Slider
              value={minSimilarity}
              onChange={(_, value) => setMinSimilarity(value as number)}
              onChangeCommitted={() => fetchDuplicateBuildings(searchQuery, minSimilarity, limit)}
              min={0.85}
              max={1.0}
              step={0.01}
              marks={[
                { value: 0.85, label: '85%' },
                { value: 0.90, label: '90%' },
                { value: 0.95, label: '95%' },
                { value: 1.0, label: '100%' },
              ]}
              valueLabelDisplay="auto"
              valueLabelFormat={(value) => `${(value * 100).toFixed(0)}%`}
            />
          </Box>
        </Grid>
        <Grid item xs={12} md={3}>
          <TextField
            select
            fullWidth
            label="表示件数"
            value={limit}
            onChange={(e) => {
              const newLimit = Number(e.target.value);
              setLimit(newLimit);
              fetchDuplicateBuildings(searchQuery, minSimilarity, newLimit);
            }}
          >
            <MenuItem value={20}>20件</MenuItem>
            <MenuItem value={30}>30件</MenuItem>
            <MenuItem value={50}>50件</MenuItem>
            <MenuItem value={100}>100件</MenuItem>
          </TextField>
        </Grid>
      </Grid>
      </Paper>

      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Alert severity="info" sx={{ flex: 1, mr: 2 }}>
          {duplicateGroups.length}グループの重複候補が見つかりました。
          各グループを展開して詳細を確認し、統合する建物を選択してください。
        </Alert>
        <IconButton 
          onClick={() => fetchDuplicateBuildings(searchQuery, minSimilarity, limit)}
          disabled={loading}
          color="primary"
          sx={{ bgcolor: 'action.hover' }}
        >
          <Tooltip title="リロード">
            {loading ? <CircularProgress size={24} /> : <RefreshIcon />}
          </Tooltip>
        </IconButton>
      </Box>

      {loading ? (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell width={50}></TableCell>
                <TableCell>主建物名</TableCell>
                <TableCell>住所</TableCell>
                <TableCell align="center">階数</TableCell>
                <TableCell align="center">物件数</TableCell>
                <TableCell align="center">候補数</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {duplicateGroups.map((group, index) => (
              <React.Fragment key={`group-${group.primary.id}`}>
                <TableRow>
                  <TableCell>
                    <IconButton
                      size="small"
                      onClick={() => handleToggleExpand(index)}
                    >
                      {expandedGroups.includes(index) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body1" fontWeight="bold">
                      {group.primary.normalized_name}
                    </Typography>
                  </TableCell>
                  <TableCell>{group.primary.address || '-'}</TableCell>
                  <TableCell align="center">{group.primary.total_floors || '-'}F</TableCell>
                  <TableCell align="center">{group.primary.property_count}</TableCell>
                  <TableCell align="center">
                    <Chip label={group.candidates.length} size="small" color="primary" />
                  </TableCell>
                  <TableCell align="center">
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<MergeIcon />}
                      onClick={() => handleSelectGroup(group)}
                    >
                      統合
                    </Button>
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell colSpan={6} sx={{ p: 0 }}>
                    <Collapse in={expandedGroups.includes(index)}>
                      <Box sx={{ p: 2, bgcolor: 'grey.50' }}>
                        <Typography variant="subtitle2" gutterBottom>
                          重複候補:
                        </Typography>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>建物名</TableCell>
                              <TableCell>住所</TableCell>
                              <TableCell align="center">階数</TableCell>
                              <TableCell align="center">物件数</TableCell>
                              <TableCell align="center">類似度</TableCell>
                              <TableCell align="center">操作</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {group.candidates.map((candidate) => (
                              <TableRow key={candidate.id}>
                                <TableCell>{candidate.normalized_name}</TableCell>
                                <TableCell>{candidate.address || '-'}</TableCell>
                                <TableCell align="center">{candidate.total_floors || '-'}F</TableCell>
                                <TableCell align="center">{candidate.property_count}</TableCell>
                                <TableCell align="center">
                                  <Box>
                                    <Chip
                                      label={`名前: ${(candidate.similarity * 100).toFixed(0)}%`}
                                      size="small"
                                      color={getSimilarityColor(candidate.similarity)}
                                      sx={{ mb: 0.5 }}
                                    />
                                    {candidate.address_similarity !== undefined && (
                                      <Chip
                                        label={`住所: ${(candidate.address_similarity * 100).toFixed(0)}%`}
                                        size="small"
                                        variant="outlined"
                                        sx={{ ml: 0.5 }}
                                      />
                                    )}
                                  </Box>
                                </TableCell>
                                <TableCell align="center">
                                  <Tooltip title="統合候補から除外">
                                    <IconButton
                                      size="small"
                                      color="warning"
                                      onClick={async (e) => {
                                        e.stopPropagation();
                                        try {
                                          await propertyApi.excludeBuildings(
                                            group.primary.id,
                                            candidate.id,
                                            '同一建物ではないため'
                                          );
                                          setSnackbar({
                                            open: true,
                                            message: '統合候補から除外しました',
                                            severity: 'success'
                                          });
                                          // リストを再読み込み
                                          fetchDuplicateBuildings(searchQuery);
                                        } catch (error) {
                                          setSnackbar({
                                            open: true,
                                            message: '除外に失敗しました',
                                            severity: 'error'
                                          });
                                        }
                                      }}
                                    >
                                      <BlockIcon fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      )}

      <Dialog open={!!selectedGroup} onClose={() => setSelectedGroup(null)} maxWidth="md" fullWidth>
        <DialogTitle>
          建物統合の確認
        </DialogTitle>
        <DialogContent>
          {selectedGroup && (
            <Box>
              <Alert severity="warning" sx={{ mb: 2 }}>
                選択した建物を統合します。
                統合後は元に戻せませんので、慎重に確認してください。
              </Alert>
              
              <Typography variant="subtitle1" gutterBottom>
                マスター建物を選択（すべての情報がこの建物に統合されます）:
              </Typography>

              <Box sx={{ mb: 3 }}>
                <Paper 
                  sx={{ 
                    p: 2, 
                    mb: 1, 
                    border: selectedMasterId === selectedGroup.primary.id ? 2 : 1,
                    borderColor: selectedMasterId === selectedGroup.primary.id ? 'primary.main' : 'divider',
                    cursor: 'pointer',
                    '&:hover': { bgcolor: 'action.hover' }
                  }}
                  onClick={() => setSelectedMasterId(selectedGroup.primary.id)}
                >
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={selectedMasterId === selectedGroup.primary.id}
                        color="primary"
                      />
                    }
                    label={
                      <Grid container spacing={2}>
                        <Grid item xs={5}>
                          <Typography variant="body2" color="textSecondary">建物名</Typography>
                          <Typography>{selectedGroup.primary.normalized_name}</Typography>
                        </Grid>
                        <Grid item xs={4}>
                          <Typography variant="body2" color="textSecondary">住所</Typography>
                          <Typography variant="body2">{selectedGroup.primary.address || '-'}</Typography>
                        </Grid>
                        <Grid item xs={1}>
                          <Typography variant="body2" color="textSecondary">階数</Typography>
                          <Typography>{selectedGroup.primary.total_floors || '-'}F</Typography>
                        </Grid>
                        <Grid item xs={2}>
                          <Typography variant="body2" color="textSecondary">物件数</Typography>
                          <Typography>{selectedGroup.primary.property_count}</Typography>
                        </Grid>
                      </Grid>
                    }
                  />
                </Paper>
                
                {selectedGroup.candidates.filter(c => selectedCandidates.includes(c.id)).map((candidate) => (
                  <Paper 
                    key={candidate.id}
                    sx={{ 
                      p: 2, 
                      mb: 1, 
                      border: selectedMasterId === candidate.id ? 2 : 1,
                      borderColor: selectedMasterId === candidate.id ? 'primary.main' : 'divider',
                      cursor: 'pointer',
                      '&:hover': { bgcolor: 'action.hover' }
                    }}
                    onClick={() => setSelectedMasterId(candidate.id)}
                  >
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={selectedMasterId === candidate.id}
                          color="primary"
                        />
                      }
                      label={
                        <Grid container spacing={2}>
                          <Grid item xs={5}>
                            <Typography variant="body2" color="textSecondary">建物名</Typography>
                            <Typography>{candidate.normalized_name}</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="body2" color="textSecondary">住所</Typography>
                            <Typography variant="body2">{candidate.address || '-'}</Typography>
                          </Grid>
                          <Grid item xs={1}>
                            <Typography variant="body2" color="textSecondary">階数</Typography>
                            <Typography>{candidate.total_floors || '-'}F</Typography>
                          </Grid>
                          <Grid item xs={2}>
                            <Typography variant="body2" color="textSecondary">物件数</Typography>
                            <Typography>{candidate.property_count}</Typography>
                          </Grid>
                        </Grid>
                      }
                    />
                  </Paper>
                ))}
              </Box>

              <Alert severity="info" sx={{ mt: 2 }}>
                {selectedMasterId ? (
                  <>
                    選択されたマスター建物「
                    {selectedMasterId === selectedGroup.primary.id 
                      ? selectedGroup.primary.normalized_name 
                      : selectedGroup.candidates.find(c => c.id === selectedMasterId)?.normalized_name}
                    」に、他の建物の全ての物件が統合されます。
                  </>
                ) : (
                  '統合先の建物を選択してください。'
                )}
              </Alert>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedGroup(null)}>
            キャンセル
          </Button>
          <Button 
            onClick={handleMerge}
            variant="contained"
            startIcon={<MergeIcon />}
            disabled={selectedCandidates.length === 0 || merging}
          >
            {merging ? '統合中...' : `${selectedCandidates.length}件を統合`}
          </Button>
        </DialogActions>
      </Dialog>

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

export default BuildingDuplicateManager;