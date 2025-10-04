import React, { useState, useEffect } from 'react';
import '../../utils/axiosConfig';
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
  Card,
  CardContent,
  CircularProgress,
  Tooltip,
  Autocomplete,
  Checkbox,
  ListItemText,
  Tabs,
  Tab,
  FormControlLabel,
  Alert,
  Collapse,
} from '@mui/material';
import {
  Search as SearchIcon,
  Refresh as RefreshIcon,
  Visibility as VisibilityIcon,
  Edit as EditIcon,
  Clear as ClearIcon,
  Home as HomeIcon,
  OpenInNew as OpenInNewIcon,
  CallSplit as CallSplitIcon,
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import axios, { isAxiosError } from 'axios';
import { useNavigate } from 'react-router-dom';

interface Property {
  id: number;
  building_id: number;
  room_number?: string;
  floor_number?: number;
  area?: number;
  layout?: string;
  direction?: string;
  property_hash: string;
  display_building_name?: string;
  created_at: string;
  updated_at: string;
  // 建物情報
  building: {
    id: number;
    normalized_name: string;
    address?: string;
    total_floors?: number;
    built_year?: number;
  };
  // 掲載情報のサマリー
  listing_summary: {
    active_count: number;
    total_count: number;
    min_price?: number;
    max_price?: number;
    sources: string[];
  };
}

interface PropertyDetail extends Property {
  // 現在の掲載情報
  active_listings: Array<{
    id: number;
    source_site: string;
    url: string;
    current_price?: number;
    station_info?: string;
    listing_building_name?: string;
    listing_address?: string;
    last_confirmed_at?: string;
    listing_area?: number;
    listing_floor_number?: number;
    listing_layout?: string;
    listing_direction?: string;
    listing_built_year?: number;
    listing_built_month?: number;
    listing_total_floors?: number;
    listing_total_units?: number;
    management_fee?: number;
    repair_fund?: number;
    agency_name?: string;
    agency_tel?: string;
    first_seen_at?: string;
    detail_fetched_at?: string;
  }>;
  // 過去の掲載情報
  inactive_listings: Array<{
    id: number;
    source_site: string;
    url: string;
    current_price?: number;
    listing_building_name?: string;
    listing_address?: string;
    delisted_at?: string;
  }>;
  // 価格履歴
  price_history: Array<{
    price: number;
    recorded_at: string;
    source_site: string;
  }>;
}

interface DetachCandidatesResponse {
  current_property: {
    id: number;
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
  };
  listing_info: {
    id: number;
    source_site: string;
    url: string;
    current_price?: number;
    building_name?: string;
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
  };
  candidates: Array<{
    id: number;
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
    display_building_name?: string;
    score: number;
    match_details: string[];
  }>;
  new_property_defaults: {
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
    display_building_name?: string;
  };
  can_create_new: boolean;
}

// 面積の選択肢（数値のみ）
const areaOptions = [
  '20',
  '30',
  '40',
  '50',
  '60',
  '70',
  '80',
  '90',
  '100',
];

// 間取りの選択肢
const layoutOptions = [
  'ワンルーム',
  '1K',
  '1DK',
  '1LDK',
  '2K',
  '2DK',
  '2LDK',
  '3K',
  '3DK',
  '3LDK',
  '4K',
  '4DK',
  '4LDK',
  '5K以上',
];

// 方角の選択肢
const directionOptions = [
  '北',
  '北東',
  '東',
  '南東',
  '南',
  '南西',
  '西',
  '北西',
];

export const PropertyManagement: React.FC = () => {
  const navigate = useNavigate();
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [totalCount, setTotalCount] = useState(0);
  const [searchParams, setSearchParams] = useState({
    buildingQuery: '',  // 建物名または建物ID
    propertyId: '',     // 物件ID
    address: '',
    minArea: '',
    maxArea: '',
    layouts: [] as string[],
    directions: [] as string[],
    hasActiveListings: '',
  });
  const [selectedProperty, setSelectedProperty] = useState<PropertyDetail | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    display_building_name: '',
    room_number: '',
    floor_number: '',
    area: '',
    layout: '',
    direction: '',
  });
  
  // 掲載情報分離用の状態
  const [detachListingDialogOpen, setDetachListingDialogOpen] = useState(false);
  const [detachingListingId, setDetachingListingId] = useState<number | null>(null);
  const [detachCandidates, setDetachCandidates] = useState<DetachCandidatesResponse | null>(null);
  const [selectedDetachPropertyId, setSelectedDetachPropertyId] = useState<number | null>(null);
  const [detachTabValue, setDetachTabValue] = useState(0);
  const [deleteOriginalProperty, setDeleteOriginalProperty] = useState(false);
  const [remainingListingsCount, setRemainingListingsCount] = useState(0);
  const [newPropertyForm, setNewPropertyForm] = useState({
    room_number: '',
    floor_number: '',
    area: '',
    layout: '',
    direction: '',
    display_building_name: '',
  });
  const [expandedListingId, setExpandedListingId] = useState<number | null>(null);

  // 物件一覧を取得
  const fetchProperties = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('offset', String(page * rowsPerPage));
      params.append('limit', String(rowsPerPage));
      
      // 物件ID検索
      if (searchParams.propertyId) {
        const id = searchParams.propertyId.trim();
        if (id.match(/^\d+$/)) {
          params.append('property_id', id);
        }
      }

      // 建物名または建物ID検索
      if (searchParams.buildingQuery) {
        const query = searchParams.buildingQuery.trim();
        if (query.match(/^\d+$/)) {
          // 数値のみの場合は建物IDとして検索
          params.append('building_id', query);
        } else {
          // それ以外は建物名として検索
          params.append('building_name', query);
        }
      }
      if (searchParams.address) params.append('address', searchParams.address);
      if (searchParams.minArea) params.append('min_area', searchParams.minArea);
      if (searchParams.maxArea) params.append('max_area', searchParams.maxArea);
      if (searchParams.layouts.length > 0) params.append('layouts', searchParams.layouts.join(','));
      if (searchParams.directions.length > 0) params.append('directions', searchParams.directions.join(','));
      if (searchParams.hasActiveListings) params.append('has_active_listings', searchParams.hasActiveListings);

      const response = await axios.get(`/admin/properties?${params}`);
      setProperties(response.data.items);
      setTotalCount(response.data.total);
    } catch (error) {
      console.error('物件一覧の取得に失敗しました:', error);
      if (isAxiosError(error)) {
        console.error('Response data:', error.response?.data);
        console.error('Response status:', error.response?.status);
      }
    } finally {
      setLoading(false);
    }
  };

  // 物件詳細を取得
  const fetchPropertyDetail = async (propertyId: number) => {
    setDetailLoading(true);
    try {
      const response = await axios.get(`/admin/properties/${propertyId}`);
      setSelectedProperty(response.data);
      setDetailDialogOpen(true);
    } catch (error) {
      console.error('物件詳細の取得に失敗しました:', error);
      if (isAxiosError(error)) {
        console.error('Response data:', error.response?.data);
        console.error('Response status:', error.response?.status);
      }
    } finally {
      setDetailLoading(false);
    }
  };

  // 物件情報を更新
  const updateProperty = async () => {
    if (!selectedProperty) return;
    
    try {
      const data: any = {};
      if (editForm.display_building_name !== selectedProperty.display_building_name) {
        data.display_building_name = editForm.display_building_name || null;
      }
      if (editForm.room_number !== selectedProperty.room_number) {
        data.room_number = editForm.room_number || null;
      }
      if (editForm.floor_number !== String(selectedProperty.floor_number || '')) {
        data.floor_number = editForm.floor_number ? Number(editForm.floor_number) : null;
      }
      if (editForm.area !== String(selectedProperty.area || '')) {
        data.area = editForm.area ? Number(editForm.area) : null;
      }
      if (editForm.layout !== selectedProperty.layout) {
        data.layout = editForm.layout || null;
      }
      if (editForm.direction !== selectedProperty.direction) {
        data.direction = editForm.direction || null;
      }

      await axios.patch(`/admin/properties/${selectedProperty.id}`, data);
      setEditDialogOpen(false);
      fetchPropertyDetail(selectedProperty.id); // 詳細を再取得
      fetchProperties(); // 一覧も更新
    } catch (error) {
      console.error('物件情報の更新に失敗しました:', error);
    }
  };

  useEffect(() => {
    fetchProperties();
  }, [page, rowsPerPage]);

  const handleSearch = () => {
    setPage(0);
    fetchProperties();
  };

  const handleClearSearch = () => {
    setSearchParams({
      buildingQuery: '',
      propertyId: '',
      address: '',
      minArea: '',
      maxArea: '',
      layouts: [],
      directions: [],
      hasActiveListings: '',
    });
    setPage(0);
  };

  const openEditDialog = () => {
    if (!selectedProperty) return;
    setEditForm({
      display_building_name: selectedProperty.display_building_name || '',
      room_number: selectedProperty.room_number || '',
      floor_number: String(selectedProperty.floor_number || ''),
      area: String(selectedProperty.area || ''),
      layout: selectedProperty.layout || '',
      direction: selectedProperty.direction || '',
    });
    setEditDialogOpen(true);
  };

  // 物件を削除
  const deleteProperty = async (propertyId: number) => {
    if (!window.confirm('この物件を削除してもよろしいですか？\n削除後は元に戻せません。')) {
      return;
    }

    try {
      const response = await axios.delete(`/admin/properties/${propertyId}`);
      console.log('Delete response:', response);
      
      // 削除成功（axiosのtryブロック内なら成功）
      alert('物件を削除しました');
      await fetchProperties(); // 一覧を更新
      if (detailDialogOpen) {
        setDetailDialogOpen(false); // 詳細ダイアログを閉じる
      }
    } catch (error) {
      console.error('物件削除エラー:', error);
      if (isAxiosError(error)) {
        if (error.response?.status === 404) {
          // 404の場合は既に削除されている
          alert('物件は既に削除されています');
          await fetchProperties(); // 一覧を更新
        } else if (error.response) {
          console.error('Error response:', error.response);
          alert(`削除に失敗しました: ${error.response.data.detail || 'エラーが発生しました'}`);
        } else {
          alert('削除に失敗しました（ネットワークエラー）');
        }
      } else {
        alert('削除に失敗しました');
      }
    }
  };

  // 掲載情報分離の候補を取得
  const fetchDetachCandidates = async (listingId: number) => {
    try {
      const response = await axios.post(`/admin/listings/${listingId}/detach-candidates`);
      setDetachCandidates(response.data);
      setDetachingListingId(listingId);
      setDetachListingDialogOpen(true);
      setDetachTabValue(0);
      setSelectedDetachPropertyId(null);
      setDeleteOriginalProperty(false);
      
      // 元の物件に残る掲載情報の数を計算
      if (selectedProperty) {
        const totalListings = selectedProperty.active_listings.length + selectedProperty.inactive_listings.length;
        setRemainingListingsCount(totalListings - 1); // 分離する1件を除く
      }
      
      // 新規物件フォームにデフォルト値を設定
      const defaults = response.data.new_property_defaults;
      setNewPropertyForm({
        room_number: defaults.room_number || '',
        floor_number: String(defaults.floor_number || ''),
        area: String(defaults.area || ''),
        layout: defaults.layout || '',
        direction: defaults.direction || '',
        display_building_name: defaults.display_building_name || '',
      });
    } catch (error: any) {
      console.error('分離候補の取得に失敗しました:', error);
      const errorMessage = error.response?.data?.detail || error.message || '分離候補の取得に失敗しました';
      console.error('Error details:', {
        status: error.response?.status,
        data: error.response?.data,
        url: error.config?.url
      });
      alert(errorMessage);
    }
  };

  // 掲載情報を分離実行
  const executeDetachListing = async () => {
    if (!detachingListingId) return;

    try {
      let requestData: any = {};
      
      if (detachTabValue === 0) {
        // 既存の物件から選択
        if (!selectedDetachPropertyId) {
          alert('紐付け先の物件を選択してください');
          return;
        }
        requestData = {
          property_id: selectedDetachPropertyId,
          create_new: false,
          delete_original: deleteOriginalProperty,
        };
      } else {
        // 新規物件を作成
        requestData = {
          create_new: true,
          room_number: newPropertyForm.room_number || null,
          floor_number: newPropertyForm.floor_number ? Number(newPropertyForm.floor_number) : null,
          area: newPropertyForm.area ? Number(newPropertyForm.area) : null,
          layout: newPropertyForm.layout || null,
          direction: newPropertyForm.direction || null,
          display_building_name: newPropertyForm.display_building_name || null,
          delete_original: deleteOriginalProperty,
        };
      }

      const response = await axios.post(
        `/admin/listings/${detachingListingId}/attach-to-property`,
        requestData
      );
      
      alert(response.data.message);
      setDetachListingDialogOpen(false);
      
      // 詳細を再取得（元の物件が削除されていない場合のみ）
      if (selectedProperty && !deleteOriginalProperty) {
        await fetchPropertyDetail(selectedProperty.id);
      } else if (deleteOriginalProperty) {
        // 元の物件が削除された場合はダイアログを閉じる
        setDetailDialogOpen(false);
      }
      // 一覧も更新
      await fetchProperties();
    } catch (error: any) {
      console.error('掲載情報の分離に失敗しました:', error);
      const errorMessage = error.response?.data?.detail || '掲載情報の分離に失敗しました';
      alert(errorMessage);
    }
  };



  const formatPrice = (price?: number) => {
    if (price === undefined || price === null) return '-';
    // 価格は既に万円単位で保存されている
    return `${price.toLocaleString()}万円`;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    return format(new Date(dateString), 'yyyy/MM/dd HH:mm');
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        物件管理
      </Typography>

      {/* 検索フォーム */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 500, fontSize: '1.1rem' }}>
            検索フィルター
          </Typography>
        </Box>
        <Grid container spacing={2} alignItems="flex-start">
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              fullWidth
              size="small"
              label="建物名または建物ID"
              value={searchParams.buildingQuery}
              onChange={(e) => setSearchParams({ ...searchParams, buildingQuery: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="建物名または建物ID"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              fullWidth
              size="small"
              label="物件ID"
              value={searchParams.propertyId}
              onChange={(e) => setSearchParams({ ...searchParams, propertyId: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="例: 5428"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              fullWidth
              size="small"
              label="住所"
              value={searchParams.address}
              onChange={(e) => setSearchParams({ ...searchParams, address: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Autocomplete
              options={areaOptions}
              value={searchParams.minArea || null}
              onChange={(_, value) => {
                setSearchParams({ ...searchParams, minArea: value || '' });
              }}
              renderInput={(params) => (
                <TextField {...params} label="最小面積（㎡）" size="small" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Autocomplete
              options={areaOptions}
              value={searchParams.maxArea || null}
              onChange={(_, value) => {
                setSearchParams({ ...searchParams, maxArea: value || '' });
              }}
              renderInput={(params) => (
                <TextField {...params} label="最大面積（㎡）" size="small" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>間取り</InputLabel>
              <Select
                multiple
                value={searchParams.layouts}
                onChange={(e) => setSearchParams({ ...searchParams, layouts: e.target.value as string[] })}
                label="間取り"
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Box>
                )}
              >
                {layoutOptions.map((layout) => (
                  <MenuItem key={layout} value={layout}>
                    <Checkbox checked={searchParams.layouts.indexOf(layout) > -1} />
                    <ListItemText primary={layout} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={1.5}>
            <FormControl fullWidth size="small">
              <InputLabel>方角</InputLabel>
              <Select
                multiple
                value={searchParams.directions}
                onChange={(e) => setSearchParams({ ...searchParams, directions: e.target.value as string[] })}
                label="方角"
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Box>
                )}
              >
                {directionOptions.map((direction) => (
                  <MenuItem key={direction} value={direction}>
                    <Checkbox checked={searchParams.directions.indexOf(direction) > -1} />
                    <ListItemText primary={direction} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={1.5}>
            <FormControl fullWidth size="small">
              <InputLabel>掲載状態</InputLabel>
              <Select
                value={searchParams.hasActiveListings}
                onChange={(e) => setSearchParams({ ...searchParams, hasActiveListings: e.target.value })}
                label="掲載状態"
              >
                <MenuItem value="">すべて</MenuItem>
                <MenuItem value="true">掲載中のみ</MenuItem>
                <MenuItem value="false">掲載終了のみ</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={12} md={2}>
            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end', alignItems: 'center' }}>
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
                onClick={handleClearSearch}
                disabled={loading}
                sx={{ minWidth: 'auto', px: 2 }}
              >
                <ClearIcon />
              </Button>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* 物件一覧 */}
      <TableContainer component={Paper}>
        {loading ? (
          <Box display="flex" justifyContent="center" p={3}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>建物名</TableCell>
                  <TableCell>住所</TableCell>
                  <TableCell align="right">階数</TableCell>
                  <TableCell align="right">面積</TableCell>
                  <TableCell>間取り</TableCell>
                  <TableCell>方角</TableCell>
                  <TableCell align="center">掲載数</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {properties.map((property) => (
                  <TableRow key={property.id}>
                    <TableCell>{property.id}</TableCell>
                    <TableCell>
                      <Box>
                        <Typography variant="body2">
                          {property.display_building_name || property.building.normalized_name}
                        </Typography>
                        {property.display_building_name && property.display_building_name !== property.building.normalized_name && (
                          <Typography variant="caption" color="text.secondary">
                            (建物: {property.building.normalized_name})
                          </Typography>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>{property.building.address || '-'}</TableCell>
                    <TableCell align="right">
                      {property.floor_number ? `${property.floor_number}階` : '-'}
                      {property.building.total_floors && ` / ${property.building.total_floors}階`}
                    </TableCell>
                    <TableCell align="right">
                      {property.area ? `${property.area.toFixed(2)}㎡` : '-'}
                    </TableCell>
                    <TableCell>{property.layout || '-'}</TableCell>
                    <TableCell>{property.direction || '-'}</TableCell>
                    <TableCell align="center">
                      <Box>
                        {property.listing_summary.active_count > 0 ? (
                          <Chip
                            label={`掲載中 ${property.listing_summary.active_count}`}
                            color="primary"
                            size="small"
                          />
                        ) : (
                          <Chip
                            label="掲載終了"
                            size="small"
                          />
                        )}
                        <Typography variant="caption" display="block" color="text.secondary">
                          全{property.listing_summary.total_count}件
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="詳細表示">
                        <IconButton
                          size="small"
                          onClick={() => fetchPropertyDetail(property.id)}
                        >
                          <VisibilityIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="建物の物件一覧">
                        <IconButton
                          size="small"
                          onClick={() => navigate(`/buildings/${property.building_id}/properties`)}
                        >
                          <HomeIcon />
                        </IconButton>
                      </Tooltip>
                      {property.listing_summary.total_count === 0 && (
                        <Tooltip title="物件を削除">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => deleteProperty(property.id)}
                          >
                            <DeleteIcon />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              component="div"
              count={totalCount}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={(_, newPage) => setPage(newPage)}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value, 10));
                setPage(0);
              }}
              rowsPerPageOptions={[25, 50, 100]}
              labelRowsPerPage="表示件数:"
            />
          </>
        )}
      </TableContainer>

      {/* 物件詳細ダイアログ */}
      <Dialog
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              物件詳細 (ID: {selectedProperty?.id})
            </Typography>
            <Box>
              {selectedProperty && selectedProperty.active_listings.length === 0 && selectedProperty.inactive_listings.length === 0 && (
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteIcon />}
                  onClick={() => deleteProperty(selectedProperty.id)}
                  sx={{ mr: 1 }}
                >
                  削除
                </Button>
              )}
              <Button
                variant="outlined"
                startIcon={<EditIcon />}
                onClick={openEditDialog}
              >
                編集
              </Button>
            </Box>
          </Box>
        </DialogTitle>
        <DialogContent>
          {detailLoading ? (
            <Box display="flex" justifyContent="center" p={3}>
              <CircularProgress />
            </Box>
          ) : selectedProperty ? (
            <Box>
              {/* 基本情報 */}
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>基本情報</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">建物名</Typography>
                      <Typography>{selectedProperty.display_building_name || selectedProperty.building.normalized_name}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">住所</Typography>
                      <Typography>{selectedProperty.building.address || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">部屋番号</Typography>
                      <Typography>{selectedProperty.room_number || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">階数</Typography>
                      <Typography>
                        {selectedProperty.floor_number ? `${selectedProperty.floor_number}階` : '-'}
                        {selectedProperty.building.total_floors && ` / ${selectedProperty.building.total_floors}階`}
                      </Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">面積</Typography>
                      <Typography>{selectedProperty.area ? `${selectedProperty.area.toFixed(2)}㎡` : '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">間取り</Typography>
                      <Typography>{selectedProperty.layout || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">方角</Typography>
                      <Typography>{selectedProperty.direction || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">築年</Typography>
                      <Typography>{selectedProperty.building.built_year ? `${selectedProperty.building.built_year}年` : '-'}</Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* 掲載中の情報 */}
              {selectedProperty.active_listings.length > 0 && (
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>掲載中の情報</Typography>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>ID</TableCell>
                          <TableCell>サイト</TableCell>
                          <TableCell align="right">価格</TableCell>
                          <TableCell>建物名</TableCell>
                          <TableCell>住所</TableCell>
                          <TableCell>最終確認</TableCell>
                          <TableCell align="center">詳細</TableCell>
                          <TableCell align="center">リンク</TableCell>
                          <TableCell align="center">操作</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {selectedProperty.active_listings.map((listing) => (
                          <React.Fragment key={listing.id}>
                            <TableRow>
                              <TableCell>{listing.id}</TableCell>
                              <TableCell>{listing.source_site}</TableCell>
                              <TableCell align="right">{formatPrice(listing.current_price)}</TableCell>
                              <TableCell>{listing.listing_building_name || '-'}</TableCell>
                              <TableCell>{listing.listing_address || '-'}</TableCell>
                              <TableCell>{formatDate(listing.last_confirmed_at)}</TableCell>
                              <TableCell align="center">
                                <IconButton
                                  size="small"
                                  onClick={() => setExpandedListingId(
                                    expandedListingId === listing.id ? null : listing.id
                                  )}
                                >
                                  {expandedListingId === listing.id ? 
                                    <ExpandLessIcon fontSize="small" /> : 
                                    <ExpandMoreIcon fontSize="small" />}
                                </IconButton>
                              </TableCell>
                              <TableCell align="center">
                                <IconButton
                                  size="small"
                                  href={listing.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  <OpenInNewIcon fontSize="small" />
                                </IconButton>
                              </TableCell>
                              <TableCell align="center">
                                <Tooltip title="この掲載情報を別物件として分離">
                                  <IconButton
                                    size="small"
                                    color="warning"
                                    onClick={() => fetchDetachCandidates(listing.id)}
                                  >
                                    <CallSplitIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </TableCell>
                            </TableRow>
                            {/* 詳細情報の折り畳み行 */}
                            {expandedListingId === listing.id && (
                              <TableRow>
                                <TableCell colSpan={9} sx={{ bgcolor: 'grey.50', py: 0 }}>
                                  <Collapse in={expandedListingId === listing.id}>
                                    <Box sx={{ p: 2 }}>
                                      <Typography variant="subtitle2" gutterBottom>
                                        掲載情報詳細
                                      </Typography>
                                      <Grid container spacing={2}>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            総階数
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_total_floors ? `${listing.listing_total_floors}階` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            総戸数
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_total_units ? `${listing.listing_total_units}戸` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            所在階
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_floor_number ? `${listing.listing_floor_number}階` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            専有面積
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_area ? `${listing.listing_area}㎡` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            間取り
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_layout || '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            方角
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_direction || '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            築年月
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.listing_built_year ? 
                                              `${listing.listing_built_year}年${listing.listing_built_month ? listing.listing_built_month + '月' : ''}` 
                                              : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            管理費
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.management_fee ? `${listing.management_fee.toLocaleString()}円/月` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            修繕積立金
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.repair_fund ? `${listing.repair_fund.toLocaleString()}円/月` : '-'}
                                          </Typography>
                                        </Grid>
                                        <Grid item xs={12} md={6}>
                                          <Typography variant="caption" color="text.secondary">
                                            不動産会社
                                          </Typography>
                                          <Typography variant="body2">
                                            {listing.agency_name || '-'}
                                          </Typography>
                                        </Grid>
                                        {listing.agency_tel && (
                                          <Grid item xs={12} md={6}>
                                            <Typography variant="caption" color="text.secondary">
                                              電話番号
                                            </Typography>
                                            <Typography variant="body2">
                                              {listing.agency_tel}
                                            </Typography>
                                          </Grid>
                                        )}
                                        <Grid item xs={12}>
                                          <Typography variant="caption" color="text.secondary">
                                            初回掲載日
                                          </Typography>
                                          <Typography variant="body2">
                                            {formatDate(listing.first_seen_at)}
                                          </Typography>
                                        </Grid>
                                        {listing.detail_fetched_at && (
                                          <Grid item xs={12}>
                                            <Typography variant="caption" color="text.secondary">
                                              詳細取得日時
                                            </Typography>
                                            <Typography variant="body2">
                                              {formatDate(listing.detail_fetched_at)}
                                            </Typography>
                                          </Grid>
                                        )}
                                      </Grid>
                                    </Box>
                                  </Collapse>
                                </TableCell>
                              </TableRow>
                            )}
                          </React.Fragment>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {/* 過去の掲載情報 */}
              {selectedProperty.inactive_listings.length > 0 && (
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>過去の掲載情報</Typography>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>サイト</TableCell>
                          <TableCell align="right">最終価格</TableCell>
                          <TableCell>建物名</TableCell>
                          <TableCell>住所</TableCell>
                          <TableCell>掲載終了日</TableCell>
                          <TableCell align="center">リンク</TableCell>
                          <TableCell align="center">操作</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {selectedProperty.inactive_listings.map((listing) => (
                          <TableRow key={listing.id}>
                            <TableCell>{listing.source_site}</TableCell>
                            <TableCell align="right">{formatPrice(listing.current_price)}</TableCell>
                            <TableCell>{listing.listing_building_name || '-'}</TableCell>
                            <TableCell>{listing.listing_address || '-'}</TableCell>
                            <TableCell>{formatDate(listing.delisted_at)}</TableCell>
                            <TableCell align="center">
                              <IconButton
                                size="small"
                                href={listing.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <OpenInNewIcon fontSize="small" />
                              </IconButton>
                            </TableCell>
                            <TableCell align="center">
                              <Tooltip title="この掲載情報を別物件として分離">
                                <IconButton
                                  size="small"
                                  color="warning"
                                  onClick={() => fetchDetachCandidates(listing.id)}
                                >
                                  <CallSplitIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>

                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </Box>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailDialogOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>

      {/* 編集ダイアログ */}
      <Dialog
        open={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>物件情報の編集</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="建物名（表示用）"
                value={editForm.display_building_name}
                onChange={(e) => setEditForm({ ...editForm, display_building_name: e.target.value })}
                helperText="空欄の場合は建物マスターの名前を使用"
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="部屋番号"
                value={editForm.room_number}
                onChange={(e) => setEditForm({ ...editForm, room_number: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="階数"
                type="number"
                value={editForm.floor_number}
                onChange={(e) => setEditForm({ ...editForm, floor_number: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="面積（㎡）"
                type="number"
                value={editForm.area}
                onChange={(e) => setEditForm({ ...editForm, area: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="間取り"
                value={editForm.layout}
                onChange={(e) => setEditForm({ ...editForm, layout: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>方角</InputLabel>
                <Select
                  value={editForm.direction}
                  onChange={(e) => setEditForm({ ...editForm, direction: e.target.value })}
                  label="方角"
                >
                  <MenuItem value="">未設定</MenuItem>
                  <MenuItem value="北">北</MenuItem>
                  <MenuItem value="北東">北東</MenuItem>
                  <MenuItem value="東">東</MenuItem>
                  <MenuItem value="南東">南東</MenuItem>
                  <MenuItem value="南">南</MenuItem>
                  <MenuItem value="南西">南西</MenuItem>
                  <MenuItem value="西">西</MenuItem>
                  <MenuItem value="北西">北西</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={updateProperty}>保存</Button>
        </DialogActions>
      </Dialog>

      {/* 掲載情報分離ダイアログ */}
      <Dialog
        open={detachListingDialogOpen}
        onClose={() => setDetachListingDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>掲載情報の分離と再紐付け先の選択</DialogTitle>
        <DialogContent>
          {detachCandidates && (
            <Box>
              {/* 現在の掲載情報 */}
              <Card sx={{ mb: 2, bgcolor: 'grey.100' }}>
                <CardContent>
                  <Typography variant="subtitle2" gutterBottom>掲載情報</Typography>
                  <Grid container spacing={1}>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">サイト</Typography>
                      <Typography variant="body2">{detachCandidates.listing_info.source_site}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">価格</Typography>
                      <Typography variant="body2">{formatPrice(detachCandidates.listing_info.current_price)}</Typography>
                    </Grid>
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">建物名</Typography>
                      <Typography variant="body2">{detachCandidates.listing_info.building_name || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">階数</Typography>
                      <Typography variant="body2">
                        {detachCandidates.listing_info.floor_number ? `${detachCandidates.listing_info.floor_number}階` : '-'}
                      </Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">面積</Typography>
                      <Typography variant="body2">
                        {detachCandidates.listing_info.area ? `${detachCandidates.listing_info.area.toFixed(2)}㎡` : '-'}
                      </Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">間取り</Typography>
                      <Typography variant="body2">{detachCandidates.listing_info.layout || '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">方角</Typography>
                      <Typography variant="body2">{detachCandidates.listing_info.direction || '-'}</Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* 元の物件削除オプション（掲載情報が1件の場合のみ表示） */}
              {remainingListingsCount === 0 && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Typography variant="body2" gutterBottom>
                    この掲載情報を分離すると、元の物件には掲載情報が残りません。
                  </Typography>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={deleteOriginalProperty}
                        onChange={(e) => setDeleteOriginalProperty(e.target.checked)}
                      />
                    }
                    label="元の物件を自動的に削除する"
                  />
                </Alert>
              )}

              {/* タブ選択 */}
              <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                <Tabs value={detachTabValue} onChange={(_, newValue) => setDetachTabValue(newValue)}>
                  <Tab label="既存の物件から選択" />
                  <Tab label="新規物件を作成" />
                </Tabs>
              </Box>

              {/* 既存物件から選択 */}
              {detachTabValue === 0 && (
                <Box sx={{ mt: 2 }}>
                  {detachCandidates.candidates.length > 0 ? (
                    <>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        以下の候補から選択してください（スコアが高い順）
                      </Typography>
                      <TableContainer>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell padding="checkbox"></TableCell>
                              <TableCell>物件ID</TableCell>
                              <TableCell>建物名</TableCell>
                              <TableCell>階数</TableCell>
                              <TableCell>面積</TableCell>
                              <TableCell>間取り</TableCell>
                              <TableCell>方角</TableCell>
                              <TableCell>スコア</TableCell>
                              <TableCell>一致項目</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {detachCandidates.candidates.map((candidate: any) => (
                              <TableRow
                                key={candidate.id}
                                selected={selectedDetachPropertyId === candidate.id}
                                onClick={() => setSelectedDetachPropertyId(candidate.id)}
                                sx={{ cursor: 'pointer' }}
                              >
                                <TableCell padding="checkbox">
                                  <Checkbox checked={selectedDetachPropertyId === candidate.id} />
                                </TableCell>
                                <TableCell>{candidate.id}</TableCell>
                                <TableCell>{candidate.display_building_name || '-'}</TableCell>
                                <TableCell>
                                  {candidate.floor_number ? `${candidate.floor_number}階` : '-'}
                                </TableCell>
                                <TableCell>
                                  {candidate.area ? `${candidate.area.toFixed(2)}㎡` : '-'}
                                </TableCell>
                                <TableCell>{candidate.layout || '-'}</TableCell>
                                <TableCell>{candidate.direction || '-'}</TableCell>
                                <TableCell>
                                  <Chip label={candidate.score} size="small" color="primary" />
                                </TableCell>
                                <TableCell>
                                  <Typography variant="caption">
                                    {candidate.match_details.join(', ')}
                                  </Typography>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </>
                  ) : (
                    <Typography color="text.secondary">
                      候補となる物件が見つかりませんでした。新規物件を作成してください。
                    </Typography>
                  )}
                </Box>
              )}

              {/* 新規物件作成 */}
              {detachTabValue === 1 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    新しい物件を作成して掲載情報を紐付けます
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mt: 1 }}>
                    以下の内容で新規物件を作成します（掲載情報から自動決定）：
                  </Typography>
                  <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                    <Grid container spacing={2}>
                      <Grid item xs={12}>
                        <Typography variant="caption" color="text.secondary">建物名（表示用）</Typography>
                        <Typography variant="body1">{newPropertyForm.display_building_name || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">部屋番号</Typography>
                        <Typography variant="body1">{newPropertyForm.room_number || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">階数</Typography>
                        <Typography variant="body1">
                          {newPropertyForm.floor_number ? `${newPropertyForm.floor_number}階` : '-'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">面積</Typography>
                        <Typography variant="body1">
                          {newPropertyForm.area ? `${newPropertyForm.area}㎡` : '-'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">間取り</Typography>
                        <Typography variant="body1">{newPropertyForm.layout || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">方角</Typography>
                        <Typography variant="body1">{newPropertyForm.direction || '-'}</Typography>
                      </Grid>
                    </Grid>
                  </Box>
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetachListingDialogOpen(false)}>キャンセル</Button>
          <Button
            variant="contained"
            onClick={executeDetachListing}
            disabled={detachTabValue === 0 && !selectedDetachPropertyId}
          >
            実行
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};