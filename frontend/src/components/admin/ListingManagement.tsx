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
  previous_price?: number;
  price_updated_at?: string;
  is_new: boolean;
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
    is_initial: boolean;
  }>;
  images: Array<{
    id: number;
    image_url: string;
    image_type?: string;
    caption?: string;
    display_order?: number;
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

  const handleRefreshDetail = async (listingId: number) => {
    try {
      await listingApi.refreshListingDetail(listingId);
      alert('詳細再取得をキューに追加しました');
    } catch (err) {
      console.error('Failed to refresh listing detail:', err);
      alert('詳細再取得に失敗しました');
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
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>サイト</InputLabel>
              <Select
                value={filters.source_site}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, source_site: e.target.value })}
                label="サイト"
              >
                <MenuItem value="">全て</MenuItem>
                <MenuItem value="suumo">SUUMO</MenuItem>
                <MenuItem value="homes">LIFULL HOME'S</MenuItem>
                <MenuItem value="rehouse">三井のリハウス</MenuItem>
                <MenuItem value="nomu">ノムコム</MenuItem>
                <MenuItem value="livable">東急リバブル</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={3}>
            <TextField
              fullWidth
              size="small"
              label="建物名"
              value={filters.building_name}
              onChange={(e) => setFilters({ ...filters, building_name: e.target.value })}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>状態</InputLabel>
              <Select
                value={filters.is_active}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, is_active: e.target.value })}
                label="状態"
              >
                <MenuItem value="">全て</MenuItem>
                <MenuItem value="true">アクティブ</MenuItem>
                <MenuItem value="false">非アクティブ</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>エリア（区）</InputLabel>
              <Select
                value={filters.ward}
                onChange={(e: SelectChangeEvent) => setFilters({ ...filters, ward: e.target.value })}
                label="エリア（区）"
              >
                <MenuItem value="">全て</MenuItem>
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
          <Grid item xs={12} md={1}>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button
                variant="contained"
                onClick={handleSearch}
                startIcon={<SearchIcon />}
                disabled={loading}
              >
                検索
              </Button>
              <IconButton onClick={handleClearFilters} disabled={loading}>
                <ClearIcon />
              </IconButton>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* エラー表示 */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* 掲載一覧 */}
      <TableContainer component={Paper}>
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
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
                    <IconButton
                      size="small"
                      onClick={() => handleRefreshDetail(listing.id)}
                    >
                      <RefreshIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <TablePagination
          component="div"
          count={totalCount}
          page={page}
          onPageChange={handlePageChange}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleRowsPerPageChange}
          rowsPerPageOptions={[25, 50, 100]}
          labelRowsPerPage="表示件数:"
        />
      </TableContainer>

      {/* 詳細ダイアログ */}
      <Dialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        {selectedListing && (
          <>
            <DialogTitle>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                掲載詳細 - ID: {selectedListing.id}
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
                >
                  <OpenInNewIcon />
                </IconButton>
              </Box>
            </DialogTitle>
            <DialogContent>
              <Tabs value={tabIndex} onChange={(_, v) => setTabIndex(v)} sx={{ mb: 2 }}>
                <Tab label="基本情報" />
                <Tab label="価格履歴" />
                <Tab label="画像" />
                <Tab label="詳細情報" />
              </Tabs>

              {tabIndex === 0 && (
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" color="textSecondary">建物情報</Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography><strong>建物名:</strong> {selectedListing.building.normalized_name}</Typography>
                      <Typography><strong>住所:</strong> {selectedListing.building.address}</Typography>
                      <Typography><strong>築年:</strong> {selectedListing.building.built_year}年</Typography>
                      <Typography><strong>総階数:</strong> {selectedListing.building.total_floors}階</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" color="textSecondary">物件情報</Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography><strong>部屋番号:</strong> {selectedListing.master_property.room_number || '-'}</Typography>
                      <Typography><strong>階数:</strong> {selectedListing.master_property.floor_number}階</Typography>
                      <Typography><strong>面積:</strong> {selectedListing.master_property.area}㎡</Typography>
                      <Typography><strong>間取り:</strong> {selectedListing.master_property.layout}</Typography>
                      <Typography><strong>方角:</strong> {selectedListing.master_property.direction || '-'}</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="subtitle2" color="textSecondary">掲載情報</Typography>
                    <Box>
                      <Typography><strong>タイトル:</strong> {selectedListing.title}</Typography>
                      <Typography><strong>現在価格:</strong> {formatPrice(selectedListing.current_price)}</Typography>
                      <Typography><strong>管理費:</strong> {selectedListing.management_fee ? `${selectedListing.management_fee.toLocaleString()}円` : '-'}</Typography>
                      <Typography><strong>修繕積立金:</strong> {selectedListing.repair_fund ? `${selectedListing.repair_fund.toLocaleString()}円` : '-'}</Typography>
                      <Typography><strong>不動産会社:</strong> {selectedListing.agency_name || '-'}</Typography>
                      <Typography><strong>電話番号:</strong> {selectedListing.agency_tel || '-'}</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="subtitle2" color="textSecondary">タイムスタンプ</Typography>
                    <Box>
                      <Typography><strong>初回確認:</strong> {formatDate(selectedListing.first_seen_at)}</Typography>
                      <Typography><strong>最終確認:</strong> {formatDate(selectedListing.last_confirmed_at)}</Typography>
                      {selectedListing.delisted_at && (
                        <Typography><strong>削除日時:</strong> {formatDate(selectedListing.delisted_at)}</Typography>
                      )}
                    </Box>
                  </Grid>
                </Grid>
              )}

              {tabIndex === 1 && (
                <Box>
                  <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 2 }}>
                    価格履歴 ({selectedListing.price_history.length}件)
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>記録日時</TableCell>
                          <TableCell align="right">価格</TableCell>
                          <TableCell>初回</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {selectedListing.price_history.map((history) => (
                          <TableRow key={history.id}>
                            <TableCell>{formatDate(history.recorded_at)}</TableCell>
                            <TableCell align="right">{formatPrice(history.price)}</TableCell>
                            <TableCell>
                              {history.is_initial && <Chip label="初回" size="small" />}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              )}

              {tabIndex === 2 && (
                <Box>
                  <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 2 }}>
                    画像 ({selectedListing.images.length}件)
                  </Typography>
                  <Grid container spacing={2}>
                    {selectedListing.images.map((image) => (
                      <Grid item xs={6} md={4} key={image.id}>
                        <Box sx={{ textAlign: 'center' }}>
                          <img
                            src={image.image_url}
                            alt={image.caption || '物件画像'}
                            style={{ width: '100%', maxHeight: 200, objectFit: 'cover' }}
                          />
                          <Typography variant="caption">{image.caption}</Typography>
                        </Box>
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}

              {tabIndex === 3 && (
                <Box>
                  <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 2 }}>
                    詳細情報JSON
                  </Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.100' }}>
                    <pre style={{ overflow: 'auto', fontSize: '0.8rem' }}>
                      {JSON.stringify(selectedListing.detail_info, null, 2)}
                    </pre>
                  </Paper>
                </Box>
              )}
            </DialogContent>
          </>
        )}
      </Dialog>
    </Box>
  );
};