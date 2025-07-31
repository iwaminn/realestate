import React, { useState, useEffect } from 'react';
import {
  Paper,
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
  Grid,
  Box,
  Chip,
  Alert,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  Typography,
  IconButton,
  Collapse,
  Radio,
  RadioGroup,
  FormControlLabel,
  Tooltip,
  Checkbox,
  Snackbar,
  TextField,
  InputAdornment,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Merge as MergeIcon,
  Info as InfoIcon,
  Block as BlockIcon,
  Check as CheckIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import axios from 'axios';

interface PropertyInGroup {
  id: number;
  room_number: string | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  current_price: number | null;
  agency_names: string | null;
  listing_count: number;
  source_count: number;
}

interface DuplicateGroup {
  group_id: string;
  property_count: number;
  building_name: string;
  floor_number: number | null;
  layout: string | null;
  properties: PropertyInGroup[];
}

interface PropertyDetail {
  id: number;
  building_id: number;
  building_name: string;
  display_building_name: string | null;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  listings: Array<{
    id: number;
    source_site: string;
    url: string;
    title: string;
    current_price: number | null;
    agency_name: string | null;
    is_active: boolean;
    last_scraped_at: string | null;
  }>;
}

const PropertyDuplicateGroups: React.FC = () => {
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [selectedGroup, setSelectedGroup] = useState<DuplicateGroup | null>(null);
  const [propertyDetails, setPropertyDetails] = useState<Record<number, PropertyDetail>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [primaryProperty, setPrimaryProperty] = useState<number | null>(null);
  const [selectedProperties, setSelectedProperties] = useState<Set<number>>(new Set());
  const [merging, setMerging] = useState(false);
  const [minSimilarity, setMinSimilarity] = useState(0.85);
  const [limit, setLimit] = useState(50);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' });
  const [currentOffset, setCurrentOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [totalGroups, setTotalGroups] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchGroups();
  }, [minSimilarity, limit]);

  const fetchGroups = async (search?: string, displayLimit?: number) => {
    setLoading(true);
    setError(null);
    
    try {
      const params: any = { 
        min_similarity: minSimilarity, 
        limit: displayLimit || limit
      };
      if (search || searchQuery) {
        params.building_name = search || searchQuery;
      }
      
      const response = await axios.get('/api/admin/duplicate-groups', {
        params
      });
      
      console.log('API Response:', response.data);
      
      // 古い形式（配列）と新しい形式（オブジェクト）の両方に対応
      if (Array.isArray(response.data)) {
        setGroups(response.data);
        setHasMore(false);
        setTotalGroups(response.data.length);
      } else {
        setGroups(response.data.groups || []);
        setHasMore(response.data.has_more || false);
        setTotalGroups(response.data.total || 0);
      }
    } catch (error: any) {
      console.error('Failed to fetch duplicate groups:', error);
      if (error.response?.status === 401) {
        setError('認証エラー: 管理画面に再度ログインしてください');
      } else {
        setError('データの読み込みに失敗しました。ページを再読み込みしてください。');
      }
      setGroups([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchPropertyDetail = async (propertyId: number): Promise<PropertyDetail | null> => {
    try {
      const response = await axios.get(`/api/admin/properties/${propertyId}`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch property detail:', error);
      return null;
    }
  };

  const handleToggleGroup = (groupId: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(groupId)) {
      newExpanded.delete(groupId);
    } else {
      newExpanded.add(groupId);
    }
    setExpandedGroups(newExpanded);
  };

  const handleShowDetail = async (group: DuplicateGroup) => {
    setSelectedGroup(group);
    setDetailLoading(true);
    setPrimaryProperty(null);
    setSelectedProperties(new Set(group.properties.map(p => p.id))); // デフォルトで全選択
    setPropertyDetails({});

    // すべての物件の詳細を取得
    const details: Record<number, PropertyDetail> = {};
    await Promise.all(
      group.properties.map(async (prop) => {
        const detail = await fetchPropertyDetail(prop.id);
        if (detail) {
          details[prop.id] = detail;
        }
      })
    );

    setPropertyDetails(details);
    setDetailLoading(false);
  };

  const handleExclude = async () => {
    if (!selectedGroup || selectedProperties.size < 1) return;

    try {
      // 選択された物件と選択されなかった物件を分ける
      const selectedIds = Array.from(selectedProperties);
      const unselectedIds = selectedGroup.properties
        .map(p => p.id)
        .filter(id => !selectedProperties.has(id));

      if (unselectedIds.length > 0) {
        // 一部選択の場合：選択vs未選択のみ除外（選択同士は除外しない）
        for (const selectedId of selectedIds) {
          for (const unselectedId of unselectedIds) {
            await axios.post('/api/admin/exclude-properties', {
              property1_id: selectedId,
              property2_id: unselectedId,
              reason: '別グループとして分離'
            });
          }
        }
      } else {
        // 全選択の場合：すべての組み合わせを除外
        for (let i = 0; i < selectedIds.length; i++) {
          for (let j = i + 1; j < selectedIds.length; j++) {
            await axios.post('/api/admin/exclude-properties', {
              property1_id: selectedIds[i],
              property2_id: selectedIds[j],
              reason: '手動で別物件として指定'
            });
          }
        }
      }

      const message = unselectedIds.length > 0
        ? `選択した${selectedIds.length}件をグループから分離しました。選択した物件同士は引き続き重複候補として表示されます。`
        : `${selectedIds.length}件を相互に別物件として登録しました。`;

      setSnackbar({ 
        open: true, 
        message, 
        severity: 'success' 
      });
      
      // グループを更新
      let shouldFetchMore = false;
      
      if (unselectedIds.length <= 1) {
        // 残りが1件以下の場合はグループごと削除
        setGroups(prev => prev.filter(g => g.group_id !== selectedGroup.group_id));
        shouldFetchMore = true;
      } else {
        // 残りが2件以上の場合は選択された物件を除外してグループを更新
        setGroups(prev => prev.map(g => {
          if (g.group_id === selectedGroup.group_id) {
            const remainingProperties = g.properties.filter(p => !selectedProperties.has(p.id));
            // グループ内の物件が1件以下になった場合は削除
            if (remainingProperties.length <= 1) {
              shouldFetchMore = true;
              return null;
            }
            return {
              ...g,
              properties: remainingProperties,
              property_count: remainingProperties.length
            };
          }
          return g;
        }).filter(g => g !== null) as DuplicateGroup[]);
      }
      
      // 削除されたグループの数だけ追加データを取得
      // TODO: 追加ロード機能を後で実装
      // if (shouldFetchMore && hasMore && groups.length < limit) {
      //   await fetchGroups(true);
      // }
      
      setSelectedGroup(null);
      setPropertyDetails({});
    } catch (error) {
      console.error('Failed to exclude properties:', error);
      setSnackbar({ open: true, message: '物件の除外に失敗しました', severity: 'error' });
    }
  };

  const handleMerge = async () => {
    if (!selectedGroup || !primaryProperty || selectedProperties.size < 2) return;

    console.log('Starting merge:', {
      primaryProperty,
      selectedProperties: Array.from(selectedProperties),
      selectedGroup
    });

    setMerging(true);
    try {
      // 選択された物件の中で統合先以外を統合
      const secondaryProperties = Array.from(selectedProperties)
        .filter(id => id !== primaryProperty);

      console.log('Secondary properties to merge:', secondaryProperties);

      for (const secondaryId of secondaryProperties) {
        console.log(`Merging ${secondaryId} into ${primaryProperty}...`);
        try {
          const response = await axios.post('/api/admin/merge-properties', {
            primary_property_id: primaryProperty,
            secondary_property_id: secondaryId
          });
          console.log(`Merge response:`, response.data);
        } catch (error: any) {
          console.error(`Failed to merge ${secondaryId}:`, error);
          console.error('Error response:', error.response?.data);
          throw error;
        }
      }

      setSnackbar({ 
        open: true, 
        message: `${secondaryProperties.length}件の物件を物件ID ${primaryProperty} に統合しました`, 
        severity: 'success' 
      });
      
      // グループから統合した物件を削除
      let shouldFetchMore = false;
      
      if (selectedProperties.size === selectedGroup.properties.length) {
        // 全物件を統合した場合はグループごと削除
        setGroups(prev => prev.filter(g => g.group_id !== selectedGroup.group_id));
        shouldFetchMore = true;
      } else {
        // 一部の物件を統合した場合はグループを更新
        setGroups(prev => prev.map(g => {
          if (g.group_id === selectedGroup.group_id) {
            const remainingProperties = g.properties.filter(p => !selectedProperties.has(p.id) || p.id === primaryProperty);
            // グループ内の物件が1件以下になった場合は削除
            if (remainingProperties.length <= 1) {
              shouldFetchMore = true;
              return null;
            }
            return {
              ...g,
              properties: remainingProperties,
              property_count: remainingProperties.length
            };
          }
          return g;
        }).filter(g => g !== null) as DuplicateGroup[]);
      }
      
      // 削除されたグループの数だけ追加データを取得
      // TODO: 追加ロード機能を後で実装
      // if (shouldFetchMore && hasMore && groups.length < limit) {
      //   await fetchGroups(true);
      // }
      
      setSelectedGroup(null);
      setPropertyDetails({});
    } catch (error: any) {
      console.error('Failed to merge properties:', error);
      const errorMessage = error.response?.data?.detail || error.message || '物件の統合に失敗しました';
      setSnackbar({ open: true, message: errorMessage, severity: 'error' });
    } finally {
      setMerging(false);
    }
  };

  const renderPropertyCard = (propertyId: number, isSelected: boolean) => {
    const property = selectedGroup?.properties.find(p => p.id === propertyId);
    const detail = propertyDetails[propertyId];
    
    if (!property) return null;
    
    return (
      <Paper 
        elevation={selectedProperties.has(propertyId) ? 4 : 1} 
        sx={{ 
          height: 'auto',
          minHeight: 380,
          display: 'flex',
          flexDirection: 'column',
          border: 2,
          borderColor: selectedProperties.has(propertyId) 
            ? (isSelected ? 'primary.main' : 'success.main')
            : 'grey.300',
          bgcolor: selectedProperties.has(propertyId)
            ? (isSelected ? 'primary.50' : 'success.50')
            : 'grey.50',
          opacity: selectedProperties.has(propertyId) ? 1 : 0.6,
          transition: 'all 0.2s',
          overflow: 'hidden',
          transform: selectedProperties.has(propertyId) ? 'scale(1)' : 'scale(0.98)'
        }}
      >
        {/* ヘッダー */}
        <Box sx={{ 
          p: 2, 
          pb: 1,
          borderBottom: 1,
          borderColor: 'divider',
          bgcolor: selectedProperties.has(propertyId)
            ? (isSelected ? 'primary.100' : 'success.100')
            : 'grey.100'
        }}>
          <Box>
            <Box display="flex" alignItems="center" gap={1} mb={0.5}>
              <Box sx={{ width: 80 }} /> {/* チェックボックスとラジオボタンのスペース */}
              <Typography 
                variant="subtitle1" 
                fontWeight="bold"
                sx={{ 
                  color: selectedProperties.has(propertyId) ? 'text.primary' : 'text.secondary'
                }}
              >
                物件ID: {property.id}
              </Typography>
            </Box>
            <Box display="flex" gap={0.5} pl={10}>
              {selectedProperties.has(propertyId) && !isSelected && (
                <Chip label="選択中" color="success" size="small" />
              )}
              {isSelected && <Chip label="統合先" color="primary" size="small" />}
              {!selectedProperties.has(propertyId) && (
                <Chip label="未選択" color="default" size="small" variant="outlined" />
              )}
            </Box>
          </Box>
        </Box>
        
        {/* 物件情報 */}
        <Box sx={{ p: 2, flex: 1, display: 'flex', flexDirection: 'column' }}>
          {/* 建物名 */}
          {detail && (
            <Box mb={1}>
              <Typography variant="caption" color="text.secondary" display="block">建物名（物件独自）</Typography>
              <Typography variant="body2" fontWeight="medium" sx={{ 
                fontSize: '0.85rem',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color: detail.display_building_name !== detail.building_name ? 'error.main' : 'text.primary'
              }}>
                {detail.display_building_name || detail.building_name}
              </Typography>
              {detail.display_building_name && detail.display_building_name !== detail.building_name && (
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                  （建物マスター: {detail.building_name}）
                </Typography>
              )}
            </Box>
          )}
          <Grid container spacing={1.5}>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary" display="block">階数</Typography>
              <Typography variant="body2" fontWeight="medium">{selectedGroup?.floor_number}階</Typography>
            </Grid>
            {property.room_number && (
              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary" display="block">部屋番号</Typography>
                <Typography variant="body2" fontWeight="medium">{property.room_number}</Typography>
              </Grid>
            )}
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary" display="block">間取り</Typography>
              <Typography variant="body2" fontWeight="medium">{property.layout || detail?.layout || '-'}</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary" display="block">面積</Typography>
              <Typography variant="body2" fontWeight="medium">{property.area}㎡</Typography>
            </Grid>
            <Grid item xs={6}>
              <Typography variant="caption" color="text.secondary" display="block">方角</Typography>
              <Typography variant="body2" fontWeight="medium">{property.direction || '-'}</Typography>
            </Grid>
          </Grid>

          {/* 価格 */}
          <Box sx={{ mt: 2, mb: 1.5 }}>
            <Typography variant="caption" color="text.secondary" display="block">価格</Typography>
            <Typography variant="h5" color="primary" fontWeight="bold">
              {property.current_price ? `${property.current_price.toLocaleString()}万円` : '価格不明'}
            </Typography>
          </Box>

          {/* 掲載情報 */}
          <Box sx={{ flex: 1, minHeight: 0 }}>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              掲載: {property.listing_count}件 / {property.source_count}サイト
            </Typography>
            
            {detail && detail.listings.length > 0 && (
              <Box sx={{ mt: 0.5 }}>
                {detail.listings.slice(0, 4).map(listing => (
                  <Box key={listing.id} display="flex" alignItems="center" gap={0.5} mb={0.25}>
                    <Chip 
                      label={listing.source_site} 
                      size="small" 
                      color={listing.is_active ? 'success' : 'default'}
                      sx={{ height: 16, fontSize: '0.65rem' }}
                    />
                    <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                      {listing.current_price?.toLocaleString()}万円
                    </Typography>
                  </Box>
                ))}
                {detail.listings.length > 4 && (
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                    他{detail.listings.length - 4}件の掲載あり
                  </Typography>
                )}
              </Box>
            )}
          </Box>
        </Box>

        {/* 不動産会社情報 */}
        {property.agency_names && (
          <Box sx={{ 
            p: 1.5, 
            bgcolor: 'grey.50',
            borderTop: 1,
            borderColor: 'divider'
          }}>
            <Typography 
              variant="caption" 
              color="text.secondary"
              sx={{ 
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                lineHeight: 1.3
              }}
            >
              {property.agency_names}
            </Typography>
          </Box>
        )}
      </Paper>
    );
  };

  return (
    <>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          物件重複グループ管理
        </Typography>
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              placeholder="建物名で検索（例：白金ザスカイ）"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  fetchGroups(searchQuery);
                }
              }}
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
                          fetchGroups('');
                        }}
                        sx={{ mr: 1 }}
                      >
                        <ClearIcon />
                      </IconButton>
                    )}
                    <Button 
                      variant="contained" 
                      onClick={() => fetchGroups(searchQuery)}
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
                onChangeCommitted={() => fetchGroups(searchQuery)}
                min={0.5}
                max={1.0}
                step={0.05}
                marks={[
                  { value: 0.5, label: '50%' },
                  { value: 0.7, label: '70%' },
                  { value: 0.85, label: '85%' },
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
                fetchGroups(searchQuery, newLimit);
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

      {loading ? (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : (
        <>
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Alert severity="info" sx={{ flex: 1, mr: 2 }}>
              {groups.length}グループの重複候補が見つかりました。
              各グループを展開して詳細を確認し、統合する物件を選択してください。
            </Alert>
            <IconButton 
              onClick={() => fetchGroups(searchQuery, limit)}
              disabled={loading}
              color="primary"
              sx={{ bgcolor: 'action.hover' }}
            >
              <Tooltip title="リロード">
                {loading ? <CircularProgress size={24} /> : <RefreshIcon />}
              </Tooltip>
            </IconButton>
          </Box>

          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell width={50}></TableCell>
                  <TableCell>建物名</TableCell>
                  <TableCell align="center">階</TableCell>
                  <TableCell align="center">間取り</TableCell>
                  <TableCell align="center">物件数</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {groups.map((group) => (
                  <React.Fragment key={group.group_id}>
                    <TableRow>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={() => handleToggleGroup(group.group_id)}
                        >
                          {expandedGroups.has(group.group_id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        </IconButton>
                      </TableCell>
                      <TableCell>{group.building_name}</TableCell>
                      <TableCell align="center">{group.floor_number}階</TableCell>
                      <TableCell align="center">{group.layout}</TableCell>
                      <TableCell align="center">
                        <Chip 
                          label={`${group.property_count}件`}
                          color="warning"
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title="詳細を表示">
                          <IconButton 
                            size="small" 
                            onClick={() => handleShowDetail(group)}
                            color="primary"
                          >
                            <InfoIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell colSpan={6} sx={{ py: 0 }}>
                        <Collapse in={expandedGroups.has(group.group_id)} timeout="auto" unmountOnExit>
                          <Box sx={{ margin: 2 }}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>物件ID</TableCell>
                                  <TableCell>部屋番号</TableCell>
                                  <TableCell>面積</TableCell>
                                  <TableCell>方角</TableCell>
                                  <TableCell>価格</TableCell>
                                  <TableCell>掲載数</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {group.properties.map((prop) => (
                                  <TableRow key={prop.id}>
                                    <TableCell>{prop.id}</TableCell>
                                    <TableCell>{prop.room_number || '-'}</TableCell>
                                    <TableCell>{prop.area}㎡</TableCell>
                                    <TableCell>{prop.direction || '-'}</TableCell>
                                    <TableCell>{prop.current_price ? `${prop.current_price}万円` : '-'}</TableCell>
                                    <TableCell>{prop.listing_count}件 ({prop.source_count}サイト)</TableCell>
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
        </>
      )}

      <Dialog 
        open={!!selectedGroup} 
        onClose={() => setSelectedGroup(null)} 
        maxWidth="xl" 
        fullWidth
        PaperProps={{
          sx: {
            height: '90vh',
            display: 'flex',
            flexDirection: 'column'
          }
        }}
      >
        <DialogTitle sx={{ pb: 1, flexShrink: 0 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Typography variant="h6">
              物件グループ詳細 - {selectedGroup?.building_name} {selectedGroup?.floor_number}階 {selectedGroup?.layout}
            </Typography>
            <Chip 
              label={`${selectedGroup?.property_count}件の重複候補`}
              color="warning"
              variant="outlined"
            />
          </Box>
        </DialogTitle>
        <DialogContent sx={{ pt: 2, pb: 2, overflow: 'auto' }}>
          {detailLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  以下の物件から操作対象を選択してください：
                </Typography>
                <Box sx={{ pl: 2, mt: 1 }}>
                  <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Checkbox size="small" disabled checked /> 統合・除外する物件を選択（緑色のカード）
                  </Typography>
                  <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    <Radio size="small" disabled checked /> 統合先の物件を指定（青色のカード）
                  </Typography>
                  <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Checkbox size="small" disabled /> 未選択の物件（灰色のカード）
                  </Typography>
                </Box>
              </Alert>
              
              <Box>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={selectedProperties.size === selectedGroup?.properties.length}
                        indeterminate={selectedProperties.size > 0 && selectedProperties.size < (selectedGroup?.properties.length || 0)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedProperties(new Set(selectedGroup?.properties.map(p => p.id) || []));
                          } else {
                            setSelectedProperties(new Set());
                          }
                        }}
                      />
                    }
                    label="すべて選択"
                  />
                  <Typography variant="body2" color="text.secondary">
                    {selectedProperties.size}件選択中
                  </Typography>
                </Box>
                
                <Grid container spacing={2}>
                  {selectedGroup?.properties
                    .sort((a, b) => {
                      // 掲載数が多い順（降順）でソート
                      return (b.listing_count || 0) - (a.listing_count || 0);
                    })
                    .map((prop) => (
                    <Grid item xs={12} sm={6} lg={4} key={prop.id}>
                      <Box sx={{ 
                        position: 'relative',
                        '&:hover .property-card': {
                          transform: selectedProperties.has(prop.id) ? 'scale(1.02)' : 'scale(1)',
                          boxShadow: selectedProperties.has(prop.id) ? 6 : 2
                        }
                      }}>
                        <Box sx={{ 
                          position: 'absolute', 
                          top: 4, 
                          left: 4, 
                          zIndex: 1, 
                          display: 'flex', 
                          gap: 0.5,
                          bgcolor: selectedProperties.has(prop.id) 
                            ? 'rgba(255, 255, 255, 0.95)' 
                            : 'rgba(255, 255, 255, 0.7)',
                          borderRadius: 1,
                          p: 0.5,
                          boxShadow: selectedProperties.has(prop.id) ? 2 : 0
                        }}>
                          <Checkbox
                            checked={selectedProperties.has(prop.id)}
                            onChange={(e) => {
                              const newSelected = new Set(selectedProperties);
                              if (e.target.checked) {
                                newSelected.add(prop.id);
                              } else {
                                newSelected.delete(prop.id);
                                // 統合先から除外された場合は統合先をクリア
                                if (primaryProperty === prop.id) {
                                  setPrimaryProperty(null);
                                }
                              }
                              setSelectedProperties(newSelected);
                            }}
                            size="small"
                          />
                          <Radio
                            checked={primaryProperty === prop.id}
                            onChange={() => setPrimaryProperty(prop.id)}
                            disabled={!selectedProperties.has(prop.id)}
                            size="small"
                          />
                        </Box>
                        <Box 
                          className="property-card"
                          onClick={() => {
                            if (selectedProperties.has(prop.id)) {
                              setPrimaryProperty(prop.id);
                            }
                          }}
                          sx={{ 
                            cursor: selectedProperties.has(prop.id) ? 'pointer' : 'default',
                            transition: 'all 0.2s'
                          }}
                        >
                          {renderPropertyCard(prop.id, primaryProperty === prop.id)}
                        </Box>
                        {selectedProperties.has(prop.id) && (
                          <Box
                            sx={{
                              position: 'absolute',
                              top: -2,
                              right: -2,
                              width: 32,
                              height: 32,
                              bgcolor: primaryProperty === prop.id ? 'primary.main' : 'success.main',
                              borderRadius: '0 8px 0 50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              boxShadow: 2
                            }}
                          >
                            <CheckIcon sx={{ color: 'white', fontSize: 18, ml: 0.5, mt: -0.5 }} />
                          </Box>
                        )}
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </Box>
              
              {primaryProperty && selectedProperties.has(primaryProperty) && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>統合先:</strong> 物件ID {primaryProperty}
                  </Typography>
                  <Typography variant="body2">
                    <strong>統合される物件:</strong> {selectedProperties.size - 1}件（選択した{selectedProperties.size}件のうち統合先以外）
                  </Typography>
                </Alert>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ flexShrink: 0, borderTop: 1, borderColor: 'divider' }}>
          <Button onClick={() => setSelectedGroup(null)}>キャンセル</Button>
          <Tooltip title={
            (() => {
              const unselectedCount = (selectedGroup?.properties.length || 0) - selectedProperties.size;
              if (selectedProperties.size === 0) {
                return "物件を選択してください";
              } else if (selectedProperties.size === selectedGroup?.properties.length) {
                return "すべての物件を相互に別物件として登録します。これらは今後重複候補として表示されません。";
              } else if (unselectedCount > 0) {
                return `選択した${selectedProperties.size}件を1つのグループとして分離します。選択した物件同士は重複候補として残り、選択されなかった${unselectedCount}件とは別物件として扱われます。`;
              }
              return "";
            })()
          }>
            <span>
              <Button 
                onClick={() => {
                  const unselectedCount = (selectedGroup?.properties.length || 0) - selectedProperties.size;
                  let confirmMessage = '';
                  
                  if (selectedProperties.size === selectedGroup?.properties.length) {
                    confirmMessage = 'すべての物件を別物件として登録しますか？\n\nこれらの物件は今後、お互いに重複候補として表示されなくなります。';
                  } else if (unselectedCount > 0) {
                    confirmMessage = `選択した${selectedProperties.size}件をグループから分離しますか？\n\n・選択した${selectedProperties.size}件：1つのグループとして分離（お互いは重複候補のまま）\n・選択されなかった${unselectedCount}件：別のグループとして残る\n・2つのグループ間は別物件として扱われます`;
                  }
                  
                  if (confirmMessage && window.confirm(confirmMessage)) {
                    handleExclude();
                  }
                }}
                variant="outlined"
                color="warning"
                startIcon={<BlockIcon />}
                disabled={selectedProperties.size < 1}
              >
                {(() => {
                  const unselectedCount = (selectedGroup?.properties.length || 0) - selectedProperties.size;
                  if (selectedProperties.size === 1 && unselectedCount > 0) {
                    return `1件を分離`;
                  } else if (selectedProperties.size > 1 && unselectedCount > 0) {
                    return `選択した${selectedProperties.size}件を分離`;
                  } else {
                    return `${selectedProperties.size}件を別物件として登録`;
                  }
                })()}
              </Button>
            </span>
          </Tooltip>
          <Button 
            onClick={handleMerge} 
            variant="contained" 
            startIcon={<MergeIcon />}
            disabled={!primaryProperty || selectedProperties.size < 2 || !selectedProperties.has(primaryProperty) || merging}
          >
            {merging ? '統合中...' : `選択した物件を統合 (${selectedProperties.size}件→1件)`}
          </Button>
        </DialogActions>
      </Dialog>
      
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert onClose={() => setSnackbar({ ...snackbar, open: false })} severity={snackbar.severity}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </>
  );
};

export default PropertyDuplicateGroups;