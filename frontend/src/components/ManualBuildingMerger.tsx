import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Grid,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Divider,
  Chip,
  InputAdornment,
} from '@mui/material';
import {
  Search as SearchIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Merge as MergeIcon,
  Info as InfoIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

interface Building {
  id: number;
  normalized_name: string;
  address: string;
  total_floors: number | null;
  property_count: number;
}

const ManualBuildingMerger: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Building[]>([]);
  const [selectedBuildings, setSelectedBuildings] = useState<Building[]>([]);
  const [primaryBuildingId, setPrimaryBuildingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setSearching(true);
    setError(null);
    try {
      const response = await propertyApi.searchBuildingsForMerge(searchQuery);
      setSearchResults(response.buildings);
    } catch (err) {
      setError('建物の検索に失敗しました');
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const addToSelectedBuildings = (building: Building) => {
    if (!selectedBuildings.find(b => b.id === building.id)) {
      setSelectedBuildings([...selectedBuildings, building]);
      // 最初に選択した建物をデフォルトのプライマリに設定
      if (selectedBuildings.length === 0) {
        setPrimaryBuildingId(building.id);
      }
    }
  };

  const removeFromSelectedBuildings = (buildingId: number) => {
    setSelectedBuildings(selectedBuildings.filter(b => b.id !== buildingId));
    // プライマリが削除された場合は、残りの最初の建物をプライマリに
    if (buildingId === primaryBuildingId && selectedBuildings.length > 1) {
      const remaining = selectedBuildings.filter(b => b.id !== buildingId);
      if (remaining.length > 0) {
        setPrimaryBuildingId(remaining[0].id);
      }
    }
  };

  const handleMerge = async () => {
    if (!primaryBuildingId || selectedBuildings.length < 2) return;

    setLoading(true);
    setError(null);
    try {
      const secondaryIds = selectedBuildings
        .filter(b => b.id !== primaryBuildingId)
        .map(b => b.id);

      const response = await propertyApi.mergeBuildings(primaryBuildingId, secondaryIds);
      
      setSuccess(`${response.merged_count}件の建物を統合し、${response.moved_properties}件の物件を移動しました`);
      setSelectedBuildings([]);
      setSearchResults([]);
      setSearchQuery('');
      setPrimaryBuildingId(null);
      setConfirmDialogOpen(false);
    } catch (err) {
      setError('建物の統合に失敗しました');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          任意の建物を統合
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          建物名または建物IDで検索して、統合したい建物を選択してください。
        </Typography>

        <Grid container spacing={3}>
          {/* 検索セクション */}
          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 2 }}>
              <TextField
                fullWidth
                placeholder="建物名または建物IDで検索"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleKeyPress}
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
                          onClick={() => setSearchQuery('')}
                          sx={{ mr: 1 }}
                        >
                          <ClearIcon />
                        </IconButton>
                      )}
                      <Button
                        variant="contained"
                        onClick={handleSearch}
                        disabled={searching || !searchQuery.trim()}
                      >
                        検索
                      </Button>
                    </InputAdornment>
                  ),
                }}
              />
            </Box>

            {searching && (
              <Box display="flex" justifyContent="center" p={2}>
                <CircularProgress size={24} />
              </Box>
            )}

            {searchResults.length > 0 && (
              <Paper variant="outlined" sx={{ maxHeight: 400, overflow: 'auto' }}>
                <List>
                  {searchResults.map((building, index) => (
                    <React.Fragment key={building.id}>
                      {index > 0 && <Divider />}
                      <ListItem>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Typography variant="body1">
                                {building.normalized_name}
                              </Typography>
                              <Chip label={`ID: ${building.id}`} size="small" />
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Typography variant="body2" color="textSecondary">
                                {building.address || '住所なし'}
                              </Typography>
                              <Typography variant="body2" color="textSecondary">
                                {building.total_floors ? `${building.total_floors}階建` : '階数不明'} • 
                                {building.property_count}件の物件
                              </Typography>
                            </Box>
                          }
                        />
                        <ListItemSecondaryAction>
                          <IconButton
                            edge="end"
                            onClick={() => addToSelectedBuildings(building)}
                            disabled={selectedBuildings.some(b => b.id === building.id)}
                          >
                            <AddIcon />
                          </IconButton>
                        </ListItemSecondaryAction>
                      </ListItem>
                    </React.Fragment>
                  ))}
                </List>
              </Paper>
            )}
          </Grid>

          {/* 選択された建物セクション */}
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" gutterBottom>
              統合する建物（{selectedBuildings.length}件選択）
            </Typography>

            {selectedBuildings.length < 2 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                統合するには最低2件の建物を選択してください
              </Alert>
            )}

            {selectedBuildings.length > 0 && (
              <Paper variant="outlined" sx={{ mb: 2 }}>
                <List>
                  {selectedBuildings.map((building, index) => (
                    <React.Fragment key={building.id}>
                      {index > 0 && <Divider />}
                      <ListItem
                        sx={{
                          bgcolor: building.id === primaryBuildingId ? 'action.selected' : 'inherit',
                        }}
                      >
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Typography variant="body1">
                                {building.normalized_name}
                              </Typography>
                              <Chip label={`ID: ${building.id}`} size="small" />
                              {building.id === primaryBuildingId && (
                                <Chip label="マスター" color="primary" size="small" />
                              )}
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Typography variant="body2" color="textSecondary">
                                {building.address || '住所なし'}
                              </Typography>
                              <Typography variant="body2" color="textSecondary">
                                {building.total_floors ? `${building.total_floors}階建` : '階数不明'} • 
                                {building.property_count}件の物件
                              </Typography>
                              {building.id !== primaryBuildingId && (
                                <Button
                                  size="small"
                                  onClick={() => setPrimaryBuildingId(building.id)}
                                  sx={{ mt: 0.5 }}
                                >
                                  マスターに設定
                                </Button>
                              )}
                            </Box>
                          }
                        />
                        <ListItemSecondaryAction>
                          <IconButton
                            edge="end"
                            onClick={() => removeFromSelectedBuildings(building.id)}
                          >
                            <DeleteIcon />
                          </IconButton>
                        </ListItemSecondaryAction>
                      </ListItem>
                    </React.Fragment>
                  ))}
                </List>
              </Paper>
            )}

            {selectedBuildings.length >= 2 && (
              <Button
                variant="contained"
                fullWidth
                startIcon={<MergeIcon />}
                onClick={() => setConfirmDialogOpen(true)}
              >
                選択した建物を統合
              </Button>
            )}
          </Grid>
        </Grid>

        {error && (
          <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mt: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}
      </Paper>

      {/* 確認ダイアログ */}
      <Dialog open={confirmDialogOpen} onClose={() => setConfirmDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>建物統合の確認</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            統合後も「統合履歴」タブから取消可能ですが、慎重に確認してください。
          </Alert>
          
          {primaryBuildingId && selectedBuildings.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                マスター建物:
              </Typography>
              <Box sx={{ pl: 2, mb: 2 }}>
                {selectedBuildings.find(b => b.id === primaryBuildingId) && (
                  <Typography variant="body2">
                    {selectedBuildings.find(b => b.id === primaryBuildingId)!.normalized_name} 
                    (ID: {primaryBuildingId})
                  </Typography>
                )}
              </Box>

              <Typography variant="subtitle2" gutterBottom>
                統合される建物:
              </Typography>
              <Box sx={{ pl: 2 }}>
                {selectedBuildings
                  .filter(b => b.id !== primaryBuildingId)
                  .map(building => (
                    <Typography key={building.id} variant="body2">
                      • {building.normalized_name} (ID: {building.id})
                    </Typography>
                  ))}
              </Box>

              <Alert severity="info" sx={{ mt: 2 }}>
                統合される建物の全ての物件がマスター建物に移動されます。
              </Alert>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDialogOpen(false)}>
            キャンセル
          </Button>
          <Button
            onClick={handleMerge}
            variant="contained"
            startIcon={<MergeIcon />}
            disabled={loading}
          >
            {loading ? '統合中...' : '統合実行'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ManualBuildingMerger;