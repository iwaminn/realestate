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
  Home as HomeIcon,
  Square as SquareIcon,
  Stairs as StairsIcon,
  Explore as ExploreIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

interface Property {
  id: number;
  building_id: number;
  building_name: string;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  current_price: number | null;
  listing_count: number;
}

const ManualPropertyMerger: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Property[]>([]);
  const [selectedProperties, setSelectedProperties] = useState<Property[]>([]);
  const [primaryPropertyId, setPrimaryPropertyId] = useState<number | null>(null);
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
      const response = await propertyApi.searchPropertiesForMerge(searchQuery);
      setSearchResults(response.properties);
    } catch (err) {
      setError('物件の検索に失敗しました');
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

  const addToSelectedProperties = (property: Property) => {
    if (!selectedProperties.find(p => p.id === property.id)) {
      setSelectedProperties([...selectedProperties, property]);
      // 最初に選択した物件をデフォルトのプライマリに設定
      if (selectedProperties.length === 0) {
        setPrimaryPropertyId(property.id);
      }
    }
  };

  const removeFromSelectedProperties = (propertyId: number) => {
    setSelectedProperties(selectedProperties.filter(p => p.id !== propertyId));
    // プライマリが削除された場合は、残りの最初の物件をプライマリに
    if (propertyId === primaryPropertyId && selectedProperties.length > 1) {
      const remaining = selectedProperties.filter(p => p.id !== propertyId);
      if (remaining.length > 0) {
        setPrimaryPropertyId(remaining[0].id);
      }
    }
  };

  const formatPrice = (price: number | null) => {
    if (!price) return '価格未定';
    
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      if (man === 0) {
        return `${oku}億円`;
      } else {
        return `${oku}億${man.toLocaleString()}万円`;
      }
    }
    
    return `${price.toLocaleString()}万円`;
  };

  const handleMerge = async () => {
    if (!primaryPropertyId || selectedProperties.length < 2) return;

    setLoading(true);
    setError(null);
    try {
      // 異なる建物の物件を統合しようとしていないかチェック
      const buildingIds = [...new Set(selectedProperties.map(p => p.building_id))];
      if (buildingIds.length > 1) {
        setError('異なる建物の物件は統合できません');
        setLoading(false);
        return;
      }

      // プライマリ以外の物件IDを収集
      const secondaryIds = selectedProperties
        .filter(p => p.id !== primaryPropertyId)
        .map(p => p.id);

      // 物件を1つずつ統合
      let successCount = 0;
      for (const secondaryId of secondaryIds) {
        try {
          await propertyApi.mergeProperties(primaryPropertyId, secondaryId);
          successCount++;
        } catch (err) {
          console.error(`Failed to merge property ${secondaryId}:`, err);
        }
      }
      
      setSuccess(`${successCount}件の物件を統合しました`);
      setSelectedProperties([]);
      setSearchResults([]);
      setSearchQuery('');
      setPrimaryPropertyId(null);
      setConfirmDialogOpen(false);
    } catch (err) {
      setError('物件の統合に失敗しました');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          任意の物件を統合
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          物件IDまたは建物名で検索して、統合したい物件を選択してください。
        </Typography>

        <Grid container spacing={3}>
          {/* 検索セクション */}
          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 2 }}>
              <TextField
                fullWidth
                placeholder="物件IDまたは建物名で検索"
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
                  {searchResults.map((property, index) => (
                    <React.Fragment key={property.id}>
                      {index > 0 && <Divider />}
                      <ListItem>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Typography variant="body1">
                                {property.building_name}
                                {property.room_number && ` ${property.room_number}`}
                              </Typography>
                              <Chip label={`ID: ${property.id}`} size="small" />
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Box display="flex" gap={2} flexWrap="wrap" mt={0.5}>
                                {property.floor_number && (
                                  <Box display="flex" alignItems="center">
                                    <StairsIcon fontSize="small" sx={{ mr: 0.5 }} />
                                    <Typography variant="body2">{property.floor_number}階</Typography>
                                  </Box>
                                )}
                                {property.area && (
                                  <Box display="flex" alignItems="center">
                                    <SquareIcon fontSize="small" sx={{ mr: 0.5 }} />
                                    <Typography variant="body2">{property.area}㎡</Typography>
                                  </Box>
                                )}
                                {property.layout && (
                                  <Box display="flex" alignItems="center">
                                    <HomeIcon fontSize="small" sx={{ mr: 0.5 }} />
                                    <Typography variant="body2">{property.layout}</Typography>
                                  </Box>
                                )}
                                {property.direction && (
                                  <Box display="flex" alignItems="center">
                                    <ExploreIcon fontSize="small" sx={{ mr: 0.5 }} />
                                    <Typography variant="body2">{property.direction}向き</Typography>
                                  </Box>
                                )}
                              </Box>
                              <Typography variant="body2" color="primary" sx={{ mt: 0.5 }}>
                                {formatPrice(property.current_price)} • {property.listing_count}件の掲載
                              </Typography>
                            </Box>
                          }
                        />
                        <ListItemSecondaryAction>
                          <IconButton
                            edge="end"
                            onClick={() => addToSelectedProperties(property)}
                            disabled={selectedProperties.some(p => p.id === property.id)}
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

          {/* 選択された物件セクション */}
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle1" gutterBottom>
              統合する物件（{selectedProperties.length}件選択）
            </Typography>

            {selectedProperties.length < 2 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                統合するには最低2件の物件を選択してください
              </Alert>
            )}

            {selectedProperties.length > 0 && (
              <Paper variant="outlined" sx={{ mb: 2 }}>
                <List>
                  {selectedProperties.map((property, index) => (
                    <React.Fragment key={property.id}>
                      {index > 0 && <Divider />}
                      <ListItem
                        sx={{
                          bgcolor: property.id === primaryPropertyId ? 'action.selected' : 'inherit',
                        }}
                      >
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Typography variant="body1">
                                {property.building_name}
                                {property.room_number && ` ${property.room_number}`}
                              </Typography>
                              <Chip label={`ID: ${property.id}`} size="small" />
                              {property.id === primaryPropertyId && (
                                <Chip label="マスター" color="primary" size="small" />
                              )}
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Box display="flex" gap={2} flexWrap="wrap" mt={0.5}>
                                {property.floor_number && `${property.floor_number}階`}
                                {property.area && ` • ${property.area}㎡`}
                                {property.layout && ` • ${property.layout}`}
                                {property.direction && ` • ${property.direction}向き`}
                              </Box>
                              <Typography variant="body2" color="primary">
                                {formatPrice(property.current_price)} • {property.listing_count}件の掲載
                              </Typography>
                              {property.id !== primaryPropertyId && (
                                <Button
                                  size="small"
                                  onClick={() => setPrimaryPropertyId(property.id)}
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
                            onClick={() => removeFromSelectedProperties(property.id)}
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

            {selectedProperties.length >= 2 && (
              <Button
                variant="contained"
                fullWidth
                startIcon={<MergeIcon />}
                onClick={() => setConfirmDialogOpen(true)}
              >
                選択した物件を統合
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
        <DialogTitle>物件統合の確認</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            この操作は取り消せません。慎重に確認してください。
          </Alert>
          
          {primaryPropertyId && selectedProperties.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                マスター物件:
              </Typography>
              <Box sx={{ pl: 2, mb: 2 }}>
                {selectedProperties.find(p => p.id === primaryPropertyId) && (
                  <Typography variant="body2">
                    {selectedProperties.find(p => p.id === primaryPropertyId)!.building_name}
                    {selectedProperties.find(p => p.id === primaryPropertyId)!.room_number && 
                      ` ${selectedProperties.find(p => p.id === primaryPropertyId)!.room_number}`}
                    (ID: {primaryPropertyId})
                  </Typography>
                )}
              </Box>

              <Typography variant="subtitle2" gutterBottom>
                統合される物件:
              </Typography>
              <Box sx={{ pl: 2 }}>
                {selectedProperties
                  .filter(p => p.id !== primaryPropertyId)
                  .map(property => (
                    <Typography key={property.id} variant="body2">
                      • {property.building_name}
                      {property.room_number && ` ${property.room_number}`}
                      (ID: {property.id})
                    </Typography>
                  ))}
              </Box>

              <Alert severity="info" sx={{ mt: 2 }}>
                統合される物件の全ての掲載情報がマスター物件に移動されます。
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

export default ManualPropertyMerger;