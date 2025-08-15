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
  TablePagination,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Tabs,
  Tab,
  Card,
  CardContent,
  Divider,
  Alert,
  CircularProgress,
  SelectChangeEvent,
  Link,
  Tooltip,
} from '@mui/material';
import {
  Search as SearchIcon,
  Refresh as RefreshIcon,
  Visibility as VisibilityIcon,
  OpenInNew as OpenInNewIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { listingApi } from '../../api/listingApi';

interface Listing {
  id: number;
  source_site: string;
  site_property_id?: string;
  url: string;
  title?: string;
  listing_building_name?: string;
  current_price?: number;
  is_active: boolean;
  master_property_id: number;
  building_id: number;
  building_name: string;
  address?: string;
  floor_number?: number;
  area?: number;
  layout?: string;
  station_info?: string;
  first_seen_at?: string;
  last_confirmed_at?: string;
  delisted_at?: string;
  detail_fetched_at?: string;
  created_at: string;
  updated_at: string;
}

interface ListingDetail extends Listing {
  price_updated_at?: string;
  master_property: any;
  building: any;
  listing_floor_number?: number;
  listing_area?: number;
  listing_layout?: string;
  listing_direction?: string;
  management_fee?: number;
  repair_fund?: number;
  agency_name?: string;
  agency_tel?: string;
  remarks?: string;
  summary_remarks?: string;
  first_published_at?: string;
  published_at?: string;
  detail_info?: any;
  price_history: Array<{
    id: number;
    price: number;
    recorded_at: string;
    management_fee?: number;
    repair_fund?: number;
  }>;
}

export const ListingManagement: React.FC = () => {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedListing, setSelectedListing] = useState<ListingDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [tabIndex, setTabIndex] = useState(0);
  
  // フィルター
  const [filters, setFilters] = useState({
    source_site: '',
    building_name: '',
    is_active: '',
    ward: '',
  });
  
  // 統計情報
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    fetchListings();
  }, [page, rowsPerPage]);

  const fetchListings = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: any = {
        page: page + 1,
        per_page: rowsPerPage,
      };
      
      if (filters.source_site) params.source_site = filters.source_site;
      if (filters.building_name) params.building_name = filters.building_name;
      if (filters.is_active !== '') params.is_active = filters.is_active === 'true';
      if (filters.ward) params.ward = filters.ward;
      
      const response = await listingApi.getListings(params);
      setListings(response.listings);
      setTotalCount(response.total);
      setStats(response.stats);
    } catch (err) {
      console.error('Failed to fetch listings:', err);
      setError('掲載情報の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => {
    setPage(0);
    fetchListings();
  };

  const handleClearFilters = () => {
    setFilters({
      source_site: '',
      building_name: '',
      is_active: '',
      ward: '',
    });
    setPage(0);
  };

  const handlePageChange = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleViewDetail = async (listing: Listing) => {
    setLoading(true);
    try {
      const detail = await listingApi.getListingDetail(listing.id);
      setSelectedListing(detail);
      setDetailOpen(true);
      setTabIndex(0);
    } catch (err) {
      console.error('Failed to fetch listing detail:', err);
      setError('詳細情報の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const [refreshingListings, setRefreshingListings] = useState<Set<number>>(new Set());

  const handleRefreshDetail = async (listingId: number) => {
    setRefreshingListings(prev => new Set(prev).add(listingId));
    try {
      const response = await listingApi.refreshListingDetail(listingId);
      if (response.success) {
        setError(null);
        // 成功メッセージを表示
        alert(response.message);
        
        // 3秒後に掲載情報を再取得
        setTimeout(() => {
          // 現在の掲載情報を再取得
          if (selectedListing && selectedListing.id === listingId) {
            fetchListingDetail(listingId);
          }
        }, 3000);
      } else {
        // エラーの場合
        alert(response.message || '詳細再取得に失敗しました');
      }
    } catch (err) {
      console.error('Failed to refresh listing detail:', err);
      setError('詳細再取得に失敗しました');
    } finally {
      setRefreshingListings(prev => {
        const newSet = new Set(prev);
        newSet.delete(listingId);
        return newSet;
      });
    }
  };

  const getSourceChipColor = (source: string) => {
    const colors: { [key: string]: 'primary' | 'secondary' | 'success' | 'warning' | 'error' } = {
      'suumo': 'primary',
      'homes': 'secondary',
      'rehouse': 'success',
      'nomu': 'warning',
      'livable': 'error',
    };
    return colors[source] || 'default';
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    try {
      // APIは既に日本時間（+09:00）で返しているので、そのまま表示
      // date-fnsのformatはブラウザのタイムゾーンで表示する
      return format(new Date(dateString), 'yyyy/MM/dd HH:mm');
    } catch {
      return dateString;
    }
  };

  const formatPrice = (price?: number) => {
    if (!price) return '-';
    return `${price.toLocaleString()}万円`;
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        掲載情報管理
      </Typography>

      {/* 統計情報 */}
      {stats && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={4}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  総掲載数
                </Typography>
                <Typography variant="h5">
                  {stats.total_listings?.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={4}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  ユニーク物件数
                </Typography>
                <Typography variant="h5">
                  {stats.unique_properties?.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={4}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  アクティブ掲載
                </Typography>
                <Typography variant="h5">
                  {stats.active_listings?.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* フィルター */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 500, fontSize: '1.1rem' }}>
            検索フィルター
          </Typography>
        </Box>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              fullWidth
              size="small"
              label="建物名で検索"
              value={filters.building_name}
              onChange={(e) => setFilters({ ...filters, building_name: e.target.value })}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              helperText="スペース区切りでAND検索"
              InputProps={{
                startAdornment: (
                  <Box sx={{ mr: 1, display: 'flex', alignItems: 'center' }}>
                    <SearchIcon fontSize="small" color="action" />
                  </Box>
                ),
              }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>サイト</InputLabel>
              <Select
                value={filters.source_site}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, source_site: e.target.value })}
                label="サイト"
              >
                <MenuItem value="">
                  <em>すべて</em>
                </MenuItem>
                <Divider />
                <MenuItem value="suumo">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip label="SUUMO" size="small" color="primary" sx={{ height: 20 }} />
                  </Box>
                </MenuItem>
                <MenuItem value="homes">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip label="HOME'S" size="small" color="secondary" sx={{ height: 20 }} />
                  </Box>
                </MenuItem>
                <MenuItem value="rehouse">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip label="リハウス" size="small" color="success" sx={{ height: 20 }} />
                  </Box>
                </MenuItem>
                <MenuItem value="nomu">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip label="ノムコム" size="small" color="warning" sx={{ height: 20 }} />
                  </Box>
                </MenuItem>
                <MenuItem value="livable">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Chip label="リバブル" size="small" color="error" sx={{ height: 20 }} />
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>エリア</InputLabel>
              <Select
                value={filters.ward}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, ward: e.target.value })}
                label="エリア"
              >
                <MenuItem value="">
                  <em>すべて</em>
                </MenuItem>
                <Divider />
                <MenuItem value="千代田区">千代田区</MenuItem>
                <MenuItem value="中央区">中央区</MenuItem>
                <MenuItem value="港区">港区</MenuItem>
                <MenuItem value="新宿区">新宿区</MenuItem>
                <MenuItem value="文京区">文京区</MenuItem>
                <MenuItem value="台東区">台東区</MenuItem>
                <MenuItem value="墨田区">墨田区</MenuItem>
                <MenuItem value="江東区">江東区</MenuItem>
                <MenuItem value="品川区">品川区</MenuItem>
                <MenuItem value="目黒区">目黒区</MenuItem>
                <MenuItem value="大田区">大田区</MenuItem>
                <MenuItem value="世田谷区">世田谷区</MenuItem>
                <MenuItem value="渋谷区">渋谷区</MenuItem>
                <MenuItem value="中野区">中野区</MenuItem>
                <MenuItem value="杉並区">杉並区</MenuItem>
                <MenuItem value="豊島区">豊島区</MenuItem>
                <MenuItem value="北区">北区</MenuItem>
                <MenuItem value="荒川区">荒川区</MenuItem>
                <MenuItem value="板橋区">板橋区</MenuItem>
                <MenuItem value="練馬区">練馬区</MenuItem>
                <MenuItem value="足立区">足立区</MenuItem>
                <MenuItem value="葛飾区">葛飾区</MenuItem>
                <MenuItem value="江戸川区">江戸川区</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>状態</InputLabel>
              <Select
                value={filters.is_active}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, is_active: e.target.value })}
                label="状態"
              >
                <MenuItem value="">
                  <em>すべて</em>
                </MenuItem>
                <Divider />
                <MenuItem value="true">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        bgcolor: 'success.main',
                      }}
                    />
                    アクティブ
                  </Box>
                </MenuItem>
                <MenuItem value="false">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        bgcolor: 'grey.400',
                      }}
                    />
                    非アクティブ
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={12} md={2}>
            <Box sx={{ display: 'flex', gap: 1, justifyContent: { xs: 'flex-start', md: 'flex-end' } }}>
              <Button
                variant="contained"
                onClick={handleSearch}
                startIcon={<SearchIcon />}
                disabled={loading}
                fullWidth
                sx={{ maxWidth: { md: 120 } }}
              >
                検索
              </Button>
              <Button
                variant="outlined"
                onClick={handleClearFilters}
                disabled={loading}
                sx={{ minWidth: 'auto', px: 2 }}
              >
                <ClearIcon />
              </Button>
            </Box>
          </Grid>
        </Grid>
        
        {/* アクティブフィルター表示 */}
        {(filters.source_site || filters.building_name || filters.is_active !== '' || filters.ward) && (
          <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">
              適用中:
            </Typography>
            {filters.building_name && (
              <Chip
                size="small"
                label={`建物名: ${filters.building_name}`}
                onDelete={() => setFilters({ ...filters, building_name: '' })}
              />
            )}
            {filters.source_site && (
              <Chip
                size="small"
                label={`サイト: ${filters.source_site.toUpperCase()}`}
                onDelete={() => setFilters({ ...filters, source_site: '' })}
                color={getSourceChipColor(filters.source_site)}
              />
            )}
            {filters.ward && (
              <Chip
                size="small"
                label={`エリア: ${filters.ward}`}
                onDelete={() => setFilters({ ...filters, ward: '' })}
              />
            )}
            {filters.is_active !== '' && (
              <Chip
                size="small"
                label={`状態: ${filters.is_active === 'true' ? 'アクティブ' : '非アクティブ'}`}
                onDelete={() => setFilters({ ...filters, is_active: '' })}
                color={filters.is_active === 'true' ? 'success' : 'default'}
              />
            )}
          </Box>
        )}
      </Paper>

      {/* エラー表示 */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* 結果表示 */}
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="body1" color="text.secondary">
          検索結果: {totalCount.toLocaleString()}件
        </Typography>
        <TablePagination
          component="div"
          count={totalCount}
          page={page}
          onPageChange={handlePageChange}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleRowsPerPageChange}
          rowsPerPageOptions={[25, 50, 100]}
          labelRowsPerPage="表示件数:"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count !== -1 ? count : `${to}以上`}`}
        />
      </Box>

      {/* 掲載一覧 */}
      <TableContainer component={Paper} sx={{ position: 'relative' }}>
        {loading && (
          <Box 
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              bgcolor: 'rgba(255, 255, 255, 0.8)',
              zIndex: 1000,
            }}
          >
            <CircularProgress />
          </Box>
        )}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>サイト</TableCell>
              <TableCell>建物名</TableCell>
              <TableCell>階数</TableCell>
              <TableCell>面積</TableCell>
              <TableCell>間取り</TableCell>
              <TableCell align="right">価格</TableCell>
              <TableCell>状態</TableCell>
              <TableCell>最終確認</TableCell>
              <TableCell align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {listings.map((listing) => (
              <TableRow key={listing.id} hover>
                <TableCell>{listing.id}</TableCell>
                <TableCell>
                  <Chip
                    label={listing.source_site.toUpperCase()}
                    size="small"
                    color={getSourceChipColor(listing.source_site)}
                  />
                </TableCell>
                <TableCell>
                  <Box>
                    <Typography variant="body2">{listing.building_name}</Typography>
                    {listing.listing_building_name !== listing.building_name && (
                      <Typography variant="caption" color="textSecondary">
                        掲載名: {listing.listing_building_name}
                      </Typography>
                    )}
                  </Box>
                </TableCell>
                <TableCell>{listing.floor_number ? `${listing.floor_number}階` : '-'}</TableCell>
                <TableCell>{listing.area ? `${listing.area}㎡` : '-'}</TableCell>
                <TableCell>{listing.layout || '-'}</TableCell>
                <TableCell align="right">{formatPrice(listing.current_price)}</TableCell>
                <TableCell>
                  <Chip
                    label={listing.is_active ? 'アクティブ' : '非アクティブ'}
                    size="small"
                    color={listing.is_active ? 'success' : 'default'}
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {formatDate(listing.last_confirmed_at)}
                  </Typography>
                </TableCell>
                <TableCell align="center">
                  <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <IconButton
                      size="small"
                      onClick={() => handleViewDetail(listing)}
                    >
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      href={listing.url}
                      target="_blank"
                      component="a"
                    >
                      <OpenInNewIcon fontSize="small" />
                    </IconButton>
                    <Tooltip title="最新の詳細情報を再取得">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() => handleRefreshDetail(listing.id)}
                          disabled={refreshingListings.has(listing.id)}
                        >
                          {refreshingListings.has(listing.id) ? (
                            <CircularProgress size={18} />
                          ) : (
                            <RefreshIcon fontSize="small" />
                          )}
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 詳細ダイアログ */}
      <Dialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        maxWidth="lg"
        fullWidth
        scroll="paper"
      >
        {selectedListing && (
          <>
            <DialogTitle sx={{ pb: 1 }}>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Typography variant="h6" component="span">
                    {selectedListing.building.normalized_name}
                  </Typography>
                  <Chip
                    label={selectedListing.source_site.toUpperCase()}
                    size="small"
                    color={getSourceChipColor(selectedListing.source_site)}
                  />
                  <Box sx={{ flexGrow: 1 }} />
                  <IconButton
                    href={selectedListing.url}
                    target="_blank"
                    component="a"
                    size="small"
                  >
                    <OpenInNewIcon />
                  </IconButton>
                </Box>
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  <Typography variant="body2" color="text.secondary">
                    ID: {selectedListing.id}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {selectedListing.master_property.floor_number}階 / {selectedListing.master_property.layout} / {selectedListing.master_property.area}㎡
                  </Typography>
                  <Typography variant="body2" color="primary" fontWeight="bold">
                    {formatPrice(selectedListing.current_price)}
                  </Typography>
                  <Chip
                    label={selectedListing.is_active ? 'アクティブ' : '非アクティブ'}
                    size="small"
                    color={selectedListing.is_active ? 'success' : 'default'}
                    sx={{ height: 20 }}
                  />
                </Box>
              </Box>
            </DialogTitle>
            <DialogContent>
              <Tabs value={tabIndex} onChange={(_, v) => setTabIndex(v)} sx={{ mb: 2 }}>
                <Tab label="基本情報" />
                <Tab label="掲載情報" />
                <Tab label="価格履歴" />
                <Tab label="タイムスタンプ" />
                <Tab label="詳細JSON" />
              </Tabs>

              {tabIndex === 0 && (
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          建物情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={1.5}>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">建物名</Typography>
                            <Typography variant="body2">{selectedListing.building.normalized_name}</Typography>
                          </Grid>
                          <Grid item xs={8}>
                            <Typography variant="caption" color="text.secondary">住所</Typography>
                            <Typography variant="body2">{selectedListing.building.address}</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">築年月</Typography>
                            <Typography variant="body2">
                              {selectedListing.building.built_year}年{selectedListing.building.built_month ? `${selectedListing.building.built_month}月` : ''}
                            </Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">総階数</Typography>
                            <Typography variant="body2">{selectedListing.building.total_floors}階建</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">構造</Typography>
                            <Typography variant="body2">{selectedListing.building.construction_type || '-'}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          物件情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={1.5}>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">階数</Typography>
                            <Typography variant="body2">{selectedListing.master_property.floor_number}階</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">専有面積</Typography>
                            <Typography variant="body2">{selectedListing.master_property.area}㎡</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">間取り</Typography>
                            <Typography variant="body2">{selectedListing.master_property.layout}</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">方角</Typography>
                            <Typography variant="body2">{selectedListing.master_property.direction || '-'}</Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">バルコニー</Typography>
                            <Typography variant="body2">
                              {selectedListing.master_property.balcony_area ? `${selectedListing.master_property.balcony_area}㎡` : '-'}
                            </Typography>
                          </Grid>
                          <Grid item xs={4}>
                            <Typography variant="caption" color="text.secondary">部屋番号</Typography>
                            <Typography variant="body2">{selectedListing.master_property.room_number || '-'}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          価格・費用情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={2}>
                          <Grid item xs={12} sm={3}>
                            <Paper sx={{ p: 2, bgcolor: 'primary.main', color: 'primary.contrastText', textAlign: 'center' }}>
                              <Typography variant="caption">販売価格</Typography>
                              <Typography variant="h5" fontWeight="bold">
                                {formatPrice(selectedListing.current_price)}
                              </Typography>
                            </Paper>
                          </Grid>
                          <Grid item xs={12} sm={3}>
                            <Paper sx={{ p: 2, bgcolor: 'grey.100', textAlign: 'center' }}>
                              <Typography variant="caption" color="text.secondary">管理費</Typography>
                              <Typography variant="h6">
                                {selectedListing.management_fee ? `${selectedListing.management_fee.toLocaleString()}円` : '-'}
                              </Typography>
                            </Paper>
                          </Grid>
                          <Grid item xs={12} sm={3}>
                            <Paper sx={{ p: 2, bgcolor: 'grey.100', textAlign: 'center' }}>
                              <Typography variant="caption" color="text.secondary">修繕積立金</Typography>
                              <Typography variant="h6">
                                {selectedListing.repair_fund ? `${selectedListing.repair_fund.toLocaleString()}円` : '-'}
                              </Typography>
                            </Paper>
                          </Grid>
                          <Grid item xs={12} sm={3}>
                            <Paper sx={{ p: 2, bgcolor: 'grey.100', textAlign: 'center' }}>
                              <Typography variant="caption" color="text.secondary">月額合計</Typography>
                              <Typography variant="h6">
                                {selectedListing.management_fee || selectedListing.repair_fund
                                  ? `${((selectedListing.management_fee || 0) + (selectedListing.repair_fund || 0)).toLocaleString()}円`
                                  : '-'
                                }
                              </Typography>
                            </Paper>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              )}

              {tabIndex === 1 && (
                <Grid container spacing={3}>
                  <Grid item xs={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          掲載基本情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={2}>
                          <Grid item xs={12} sm={6} md={3}>
                            <Typography variant="caption" color="text.secondary">掲載ID</Typography>
                            <Typography variant="body2">{selectedListing.id}</Typography>
                          </Grid>
                          <Grid item xs={12} sm={6} md={3}>
                            <Typography variant="caption" color="text.secondary">マスター物件ID</Typography>
                            <Typography variant="body2">{selectedListing.master_property.id}</Typography>
                          </Grid>
                          <Grid item xs={12} sm={6} md={3}>
                            <Typography variant="caption" color="text.secondary">建物ID</Typography>
                            <Typography variant="body2">{selectedListing.building.id}</Typography>
                          </Grid>
                          <Grid item xs={12} sm={6} md={3}>
                            <Typography variant="caption" color="text.secondary">サイトID</Typography>
                            <Typography variant="body2">{selectedListing.site_property_id || '-'}</Typography>
                          </Grid>
                          <Grid item xs={12}>
                            <Typography variant="caption" color="text.secondary">タイトル</Typography>
                            <Typography variant="body2">{selectedListing.title}</Typography>
                          </Grid>
                          <Grid item xs={12} sm={6}>
                            <Typography variant="caption" color="text.secondary">掲載建物名</Typography>
                            <Typography variant="body2">
                              {selectedListing.listing_building_name || '-'}
                              {selectedListing.listing_building_name !== selectedListing.building.normalized_name && (
                                <Typography variant="caption" color="text.secondary" component="span">
                                  {' '}（正規化: {selectedListing.building.normalized_name}）
                                </Typography>
                              )}
                            </Typography>
                          </Grid>
                          <Grid item xs={12} sm={6}>
                            <Typography variant="caption" color="text.secondary">ステータス</Typography>
                            <Box sx={{ mt: 0.5 }}>
                              <Chip
                                label={selectedListing.is_active ? 'アクティブ' : '非アクティブ'}
                                size="small"
                                color={selectedListing.is_active ? 'success' : 'default'}
                              />
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Typography variant="caption" color="text.secondary">掲載URL</Typography>
                            <Typography variant="body2">
                              <Link href={selectedListing.url} target="_blank" rel="noopener">
                                {selectedListing.url}
                              </Link>
                            </Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          掲載固有情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={2}>
                          <Grid item xs={12}>
                            <Typography variant="caption" color="text.secondary">駅情報</Typography>
                            <Typography variant="body2" style={{ whiteSpace: 'pre-line' }}>
                              {selectedListing.station_info || '-'}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" color="text.secondary">掲載階数</Typography>
                            <Typography variant="body2">
                              {selectedListing.listing_floor_number ? `${selectedListing.listing_floor_number}階` : '-'}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" color="text.secondary">掲載面積</Typography>
                            <Typography variant="body2">
                              {selectedListing.listing_area ? `${selectedListing.listing_area}㎡` : '-'}
                            </Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" color="text.secondary">掲載間取り</Typography>
                            <Typography variant="body2">{selectedListing.listing_layout || '-'}</Typography>
                          </Grid>
                          <Grid item xs={6}>
                            <Typography variant="caption" color="text.secondary">掲載方角</Typography>
                            <Typography variant="body2">{selectedListing.listing_direction || '-'}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          不動産会社情報
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={2}>
                          <Grid item xs={12}>
                            <Typography variant="caption" color="text.secondary">不動産会社</Typography>
                            <Typography variant="body2">{selectedListing.agency_name || '-'}</Typography>
                          </Grid>
                          <Grid item xs={12}>
                            <Typography variant="caption" color="text.secondary">電話番号</Typography>
                            <Typography variant="body2">{selectedListing.agency_tel || '-'}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          備考
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        {selectedListing.remarks ? (
                          <Box>
                            <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                              <Typography variant="body2" style={{ whiteSpace: 'pre-wrap' }}>
                                {selectedListing.remarks}
                              </Typography>
                            </Paper>
                            {selectedListing.summary_remarks && (
                              <Box sx={{ mt: 2 }}>
                                <Typography variant="caption" color="text.secondary">要約:</Typography>
                                <Typography variant="body2">{selectedListing.summary_remarks}</Typography>
                              </Box>
                            )}
                          </Box>
                        ) : (
                          <Typography color="text.secondary">備考なし</Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              )}

              {tabIndex === 2 && (
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="subtitle1" fontWeight="bold" color="primary">
                        価格履歴
                      </Typography>
                      <Chip label={`${selectedListing.price_history.length}件`} size="small" color="primary" variant="outlined" />
                    </Box>
                    <Divider sx={{ mb: 2 }} />
                    {selectedListing.price_history.length > 0 ? (
                      <TableContainer>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>記録日時</TableCell>
                              <TableCell align="right">価格</TableCell>
                              <TableCell align="center">変動</TableCell>
                              <TableCell align="center">ステータス</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {selectedListing.price_history.map((history, index) => {
                              const prevPrice = index < selectedListing.price_history.length - 1 
                                ? selectedListing.price_history[index + 1].price 
                                : null;
                              const priceChange = prevPrice ? history.price - prevPrice : 0;
                              const changePercent = prevPrice ? ((priceChange / prevPrice) * 100).toFixed(1) : null;
                              
                              return (
                                <TableRow key={history.id} hover>
                                  <TableCell>{formatDate(history.recorded_at)}</TableCell>
                                  <TableCell align="right">
                                    <Typography variant="body2" fontWeight={index === 0 ? 'bold' : 'normal'}>
                                      {formatPrice(history.price)}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="center">
                                    {prevPrice && priceChange !== 0 && (
                                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                                        <Typography 
                                          variant="caption" 
                                          color={priceChange > 0 ? 'error.main' : 'success.main'}
                                          fontWeight="bold"
                                        >
                                          {priceChange > 0 ? '+' : ''}{priceChange}万円
                                        </Typography>
                                        <Typography 
                                          variant="caption" 
                                          color={priceChange > 0 ? 'error.main' : 'success.main'}
                                        >
                                          ({changePercent}%)
                                        </Typography>
                                      </Box>
                                    )}
                                    {(!prevPrice || priceChange === 0) && '-'}
                                  </TableCell>
                                  <TableCell align="center">
                                    {index === 0 && <Chip label="最新" size="small" color="primary" />}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary" align="center">
                        価格履歴なし
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              )}

              {tabIndex === 3 && (
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          掲載関連日時
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={1.5}>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">初回確認</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.first_seen_at)}</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">最終確認</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.last_confirmed_at)}</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">初回公開</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.first_published_at)}</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">公開日時</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.published_at)}</Typography>
                            </Box>
                          </Grid>
                          {selectedListing.delisted_at && (
                            <Grid item xs={12}>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                                <Typography variant="body2" color="text.secondary">削除日時</Typography>
                                <Typography variant="body2" color="error">{formatDate(selectedListing.delisted_at)}</Typography>
                              </Box>
                            </Grid>
                          )}
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">詳細取得</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.detail_fetched_at)}</Typography>
                            </Box>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                          システム日時
                        </Typography>
                        <Divider sx={{ mb: 2 }} />
                        <Grid container spacing={1.5}>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">作成日時</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.created_at)}</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                              <Typography variant="body2" color="text.secondary">更新日時</Typography>
                              <Typography variant="body2">{formatDate(selectedListing.updated_at)}</Typography>
                            </Box>
                          </Grid>
                          {selectedListing.price_updated_at && (
                            <Grid item xs={12}>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5 }}>
                                <Typography variant="body2" color="text.secondary">価格更新</Typography>
                                <Typography variant="body2" color="warning.main">{formatDate(selectedListing.price_updated_at)}</Typography>
                              </Box>
                            </Grid>
                          )}
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12}>
                    <Alert severity="info" icon={false}>
                      <Typography variant="body2">
                        <strong>日時の説明</strong>
                      </Typography>
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="body2" component="div">
                          • <strong>初回確認:</strong> システムが初めてこの掲載を発見した日時<br/>
                          • <strong>最終確認:</strong> システムが最後にこの掲載の存在を確認した日時<br/>
                          • <strong>初回公開:</strong> 掲載サイトでの最初の公開日時（推定）<br/>
                          • <strong>詳細取得:</strong> 詳細ページから情報を取得した最新日時<br/>
                          • <strong>価格更新:</strong> 価格が最後に変更された日時
                        </Typography>
                      </Box>
                    </Alert>
                  </Grid>
                </Grid>
              )}

              {tabIndex === 4 && (
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                      詳細情報 (JSON)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    {selectedListing.detail_info && Object.keys(selectedListing.detail_info).length > 0 ? (
                      <Paper sx={{ p: 2, bgcolor: 'grey.50', maxHeight: '500px', overflow: 'auto' }}>
                        <pre style={{ 
                          margin: 0,
                          fontFamily: 'Consolas, Monaco, "Courier New", monospace',
                          fontSize: '0.875rem',
                          lineHeight: 1.5
                        }}>
                          {JSON.stringify(selectedListing.detail_info, null, 2)}
                        </pre>
                      </Paper>
                    ) : (
                      <Box sx={{ textAlign: 'center', py: 4 }}>
                        <Typography color="text.secondary">
                          詳細情報なし
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              )}
            </DialogContent>
            <DialogActions>
              <Button
                startIcon={refreshingListings.has(selectedListing.id) ? <CircularProgress size={20} /> : <RefreshIcon />}
                onClick={() => {
                  handleRefreshDetail(selectedListing.id);
                }}
                disabled={refreshingListings.has(selectedListing.id)}
              >
                詳細を再取得
              </Button>
              <Button onClick={() => setDetailOpen(false)}>閉じる</Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  );
};