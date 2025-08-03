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
  Radio,
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
  Clear as ClearIcon,
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
  const [minSimilarity, setMinSimilarity] = useState(0.7); // デフォルトを0.7に設定
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
    console.log('Fetching duplicate buildings with params:', {
      search,
      similarity: similarity || minSimilarity,
      limit: displayLimit || limit
    });
    setLoading(true);
    try {
      const params: any = { 
        limit: displayLimit || limit,
        min_similarity: similarity || minSimilarity
      };
      if (search) {
        params.search = search;
      }
      console.log('API params:', params);
      const response = await propertyApi.getDuplicateBuildings(params);
      console.log('Response:', response);
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
    // すべての建物を選択（主建物も含む）
    setSelectedCandidates([group.primary.id, ...group.candidates.map(c => c.id)]);
    
    // 物件数が最も多い建物をデフォルトのマスターに設定
    const allBuildings = [
      group.primary,
      ...group.candidates
    ];
    const buildingWithMostProperties = allBuildings.reduce((prev, current) => 
      current.property_count > prev.property_count ? current : prev
    );
    setSelectedMasterId(buildingWithMostProperties.id);
  };

  const handleToggleCandidate = (candidateId: number) => {
    setSelectedCandidates(prev => {
      const newSelection = prev.includes(candidateId)
        ? prev.filter(id => id !== candidateId)
        : [...prev, candidateId];
      
      // 選択解除された場合、その建物が統合先だったらクリア
      if (!newSelection.includes(candidateId) && selectedMasterId === candidateId) {
        setSelectedMasterId(null);
      }
      
      return newSelection;
    });
  };

  const handleSeparateFromGroup = async () => {
    if (!selectedGroup || selectedCandidates.length === 0) return;

    // 主建物が選択されているかチェック
    const isPrimarySelected = selectedCandidates.includes(selectedGroup.primary.id);
    
    // 選択されていない候補を特定（主建物を除く）
    const unselectedCandidates = selectedGroup.candidates.filter(
      c => !selectedCandidates.includes(c.id)
    );
    
    // 選択されていない建物の総数（主建物が選択されていない場合は主建物も含む）
    const unselectedBuildingsCount = unselectedCandidates.length + (isPrimarySelected ? 0 : 1);

    // 全選択か一部選択かで処理を分ける
    const isAllSelected = selectedCandidates.length === selectedGroup.candidates.length + 1; // 主建物も含めて全選択
    
    let confirmMessage = '';
    if (isAllSelected) {
      confirmMessage = 'すべての建物を別建物として登録しますか？\n\nこれらの建物は今後、お互いに重複候補として表示されなくなります。';
    } else {
      confirmMessage = `選択した${selectedCandidates.length}件をグループから分離しますか？\n\n・選択した建物：1つのグループとして分離（お互いは重複候補のまま）\n・選択されなかった${unselectedBuildingsCount}件：別のグループとして残る\n・2つのグループ間は別建物として扱われます`;
    }

    if (!confirm(confirmMessage)) {
      return;
    }

    setMerging(true);
    try {
      if (isAllSelected) {
        // 全選択の場合：すべての建物を相互に除外
        const allBuildings = selectedCandidates; // すでに主建物も含まれている
        for (let i = 0; i < allBuildings.length; i++) {
          for (let j = i + 1; j < allBuildings.length; j++) {
            await propertyApi.excludeBuildings(
              allBuildings[i],
              allBuildings[j],
              '手動で別建物として指定'
            );
          }
        }
      } else {
        // 一部選択の場合：選択vs未選択のみ除外
        const selectedBuildingIds = selectedCandidates; // 主建物も含めて選択された建物のみ
        const unselectedBuildingIds = [];
        
        // 主建物が選択されていない場合は未選択リストに追加
        if (!isPrimarySelected) {
          unselectedBuildingIds.push(selectedGroup.primary.id);
        }
        
        // 選択されていない候補を未選択リストに追加
        unselectedBuildingIds.push(...unselectedCandidates.map(c => c.id));
        
        for (const selected of selectedBuildingIds) {
          for (const unselected of unselectedBuildingIds) {
            await propertyApi.excludeBuildings(
              selected,
              unselected,
              '別グループとして分離'
            );
          }
        }
      }

      const message = isAllSelected
        ? `${selectedCandidates.length}件を相互に別建物として登録しました。`
        : `選択した${selectedCandidates.length}件をグループから分離しました。選択した建物同士は引き続き重複候補として表示されます。`;
      
      setSnackbar({
        open: true,
        message,
        severity: 'success'
      });

      // グループをローカルで更新
      if (isAllSelected) {
        // 全選択の場合はグループ自体を削除
        setDuplicateGroups(prevGroups => 
          prevGroups.filter(group => group.primary.id !== selectedGroup.primary.id)
        );
      } else {
        // 一部選択の場合は選択されなかった候補のみを残す
        setDuplicateGroups(prevGroups => {
          return prevGroups.map(group => {
            if (group.primary.id === selectedGroup.primary.id) {
              const remainingCandidates = group.candidates.filter(
                candidate => !selectedCandidates.includes(candidate.id)
              );
              
              // candidatesが空になった場合はグループ自体を削除
              if (remainingCandidates.length === 0) {
                return null;
              }
              
              return {
                ...group,
                candidates: remainingCandidates
              };
            }
            return group;
          }).filter(Boolean) as DuplicateGroup[];
        });
      }

      setSelectedGroup(null);
      setSelectedCandidates([]);
      setSelectedMasterId(null);
    } catch (error: any) {
      console.error('Failed to separate buildings:', error);
      setSnackbar({
        open: true,
        message: '建物の分離に失敗しました',
        severity: 'error'
      });
    } finally {
      setMerging(false);
    }
  };

  const handleMerge = async () => {
    if (!selectedGroup || selectedCandidates.length === 0 || !selectedMasterId) return;

    setMerging(true);
    try {
      // マスター以外の建物IDを収集
      const allBuildingIds = selectedCandidates; // 選択された建物のみ
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
        const mergedBuildingIds = new Set(selectedCandidates);
        
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
    } catch (error: any) {
      console.error('Failed to merge buildings:', error);
      const errorMessage = error.response?.data?.detail || error.message || '建物の統合に失敗しました';
      setSnackbar({ 
        open: true, 
        message: `エラー: ${errorMessage}`, 
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

  const handleChangePrimary = (newPrimaryId: number) => {
    const currentGroups = [...duplicateGroups];
    const groupIndex = currentGroups.findIndex(g => g.primary.id === selectedGroup?.primary.id);
    
    if (groupIndex === -1) return;
    
    const group = currentGroups[groupIndex];
    const newPrimaryCandidate = group.candidates.find(c => c.id === newPrimaryId);
    
    if (!newPrimaryCandidate) return;
    
    // 現在の主建物を候補に追加
    const oldPrimary = {
      ...group.primary,
      similarity: 1.0, // 元主建物なので類似度100%
      address_similarity: 1.0,
      floors_match: true
    };
    
    // 新しい主建物を候補から削除
    const newCandidates = [
      oldPrimary,
      ...group.candidates.filter(c => c.id !== newPrimaryId)
    ];
    
    // グループを更新
    currentGroups[groupIndex] = {
      primary: {
        id: newPrimaryCandidate.id,
        normalized_name: newPrimaryCandidate.normalized_name,
        address: newPrimaryCandidate.address,
        total_floors: newPrimaryCandidate.total_floors,
        property_count: newPrimaryCandidate.property_count
      },
      candidates: newCandidates
    };
    
    setDuplicateGroups(currentGroups);
    
    // 選択されたグループも更新
    if (selectedGroup && selectedGroup.primary.id === group.primary.id) {
      setSelectedGroup(currentGroups[groupIndex]);
    }
    
    setSnackbar({
      open: true,
      message: `主建物を「${newPrimaryCandidate.normalized_name}」に変更しました`,
      severity: 'success'
    });
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
                  {searchQuery && (
                    <IconButton
                      size="small"
                      onClick={() => {
                        setSearchQuery('');
                        fetchDuplicateBuildings('', minSimilarity, limit);
                      }}
                      sx={{ mr: 1 }}
                    >
                      <ClearIcon />
                    </IconButton>
                  )}
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
              {minSimilarity <= 0.3 && ' (棟違いも表示)'}
            </Typography>
            <Slider
              value={minSimilarity}
              onChange={(_, value) => setMinSimilarity(value as number)}
              onChangeCommitted={() => fetchDuplicateBuildings(searchQuery, minSimilarity, limit)}
              min={0.3}
              max={1.0}
              step={0.01}
              marks={[
                { value: 0.3, label: '30%' },
                { value: 0.5, label: '50%' },
                { value: 0.7, label: '70%' },
                { value: 0.85, label: '85%' },
                { value: 0.95, label: '95%' }
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
                <TableCell>建物名</TableCell>
                <TableCell>住所</TableCell>
                <TableCell align="center">階数</TableCell>
                <TableCell align="center">物件数</TableCell>
                <TableCell align="center">重複数</TableCell>
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
                    <Chip label={group.candidates.length + 1} size="small" color="primary" />
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
                  <TableCell colSpan={7} sx={{ p: 0 }}>
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
                                  <Box display="flex" flexDirection="column" alignItems="center" gap={0.5}>
                                    <Chip
                                      label={`名前: ${(candidate.similarity * 100).toFixed(0)}%`}
                                      size="small"
                                      color={getSimilarityColor(candidate.similarity)}
                                      sx={{ minWidth: '80px' }}
                                    />
                                    {candidate.address_similarity !== undefined && (
                                      <Chip
                                        label={`住所: ${(candidate.address_similarity * 100).toFixed(0)}%`}
                                        size="small"
                                        variant="outlined"
                                        sx={{ minWidth: '80px' }}
                                      />
                                    )}
                                  </Box>
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
                統合後も「統合履歴」タブから取消可能ですが、慎重に確認してください。
              </Alert>
              
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  以下の建物から操作対象を選択してください：
                </Typography>
                <Box sx={{ pl: 2, mt: 1 }}>
                  <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Checkbox size="small" disabled checked /> 統合・分離する建物を選択
                  </Typography>
                  <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Radio size="small" disabled checked /> 統合先の建物を指定（選択した建物のみ指定可能）
                  </Typography>
                </Box>
              </Alert>

              <Box sx={{ mb: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell width={50} align="center">選択</TableCell>
                      <TableCell width={50} align="center">統合先</TableCell>
                      <TableCell>建物名</TableCell>
                      <TableCell>住所</TableCell>
                      <TableCell align="center" width={80}>階数</TableCell>
                      <TableCell align="center" width={80}>物件数</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(() => {
                      // すべての建物を配列に集めて物件数で降順ソート
                      const allBuildings = [
                        selectedGroup.primary,
                        ...selectedGroup.candidates
                      ].sort((a, b) => b.property_count - a.property_count);
                      
                      return allBuildings.map((building) => {
                        const isCandidate = selectedGroup.candidates.some(c => c.id === building.id);
                        const isSelected = selectedCandidates.includes(building.id);
                        
                        return (
                          <TableRow 
                            key={building.id}
                            hover
                          >
                            <TableCell padding="checkbox" align="center">
                              <Checkbox
                                checked={isSelected}
                                onChange={(e) => {
                                  handleToggleCandidate(building.id);
                                }}
                              />
                            </TableCell>
                            <TableCell padding="checkbox" align="center">
                              <Radio
                                checked={selectedMasterId === building.id}
                                onChange={() => setSelectedMasterId(building.id)}
                                color="primary"
                                disabled={!isSelected}
                              />
                            </TableCell>
                            <TableCell>
                              <Typography fontWeight={selectedMasterId === building.id ? 'bold' : 'normal'}>
                                {building.normalized_name}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">
                                {building.address || '-'}
                              </Typography>
                            </TableCell>
                            <TableCell align="center">
                              {building.total_floors || '-'}F
                            </TableCell>
                            <TableCell align="center">
                              <Chip 
                                label={building.property_count} 
                                size="small" 
                                color={selectedMasterId === building.id ? 'primary' : 'default'}
                              />
                            </TableCell>
                          </TableRow>
                        );
                      });
                    })()}
                  </TableBody>
                </Table>
              </Box>

              {selectedMasterId && selectedCandidates.includes(selectedMasterId) && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>統合先:</strong> {
                      selectedMasterId === selectedGroup.primary.id 
                        ? selectedGroup.primary.normalized_name 
                        : selectedGroup.candidates.find(c => c.id === selectedMasterId)?.normalized_name
                    }
                  </Typography>
                  <Typography variant="body2">
                    <strong>統合される建物:</strong> {selectedCandidates.filter(id => id !== selectedMasterId).length}件（選択した{selectedCandidates.length}件のうち統合先以外）
                  </Typography>
                </Alert>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedGroup(null)}>
            キャンセル
          </Button>
          <Button
            onClick={handleSeparateFromGroup}
            variant="outlined"
            color="warning"
            disabled={selectedCandidates.length === 0 || merging}
          >
            {selectedCandidates.length === (selectedGroup?.candidates.length || 0) + 1
              ? `${selectedCandidates.length}件を別建物として登録`
              : `選択した${selectedCandidates.length}件を分離`}
          </Button>
          <Button 
            onClick={handleMerge}
            variant="contained"
            startIcon={<MergeIcon />}
            disabled={!selectedMasterId || selectedCandidates.length === 0 || !selectedCandidates.includes(selectedMasterId) || merging}
          >
            {merging ? '統合中...' : `選択した建物を統合 (${selectedCandidates.length}件→1件)`}
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