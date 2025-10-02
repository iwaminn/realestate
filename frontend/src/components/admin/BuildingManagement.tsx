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
  InputAdornment,
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
  Tabs,
  Tab,
  Collapse,
} from '@mui/material';
import {
  Search as SearchIcon,
  Refresh as RefreshIcon,
  Visibility as VisibilityIcon,
  Edit as EditIcon,
  Clear as ClearIcon,
  Home as HomeIcon,
  CallSplit as CallSplitIcon,
  Delete as DeleteIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import axios, { isAxiosError } from 'axios';
import { useNavigate } from 'react-router-dom';

interface Building {
  id: number;
  normalized_name: string;
  address?: string;
  total_floors?: number;
  total_units?: number;  // 総戸数を追加
  built_year?: number;
  created_at: string;
  updated_at: string;
  // 統計情報
  property_count: number;
  active_listing_count: number;
  min_price?: number;
  max_price?: number;
}

interface BuildingDetail extends Building {
  // 掲載情報の建物名（別名）
  listing_names?: Array<{
    name: string;
    source_sites: string[];
    occurrence_count: number;
    first_seen_at?: string;
    last_seen_at?: string;
  }>;
  // 物件一覧
  properties: Array<{
    id: number;
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
    display_building_name?: string;  // 物件毎の建物名を追加
    active_listing_count: number;
    min_price?: number;
    max_price?: number;
  }>;
}

// 築年数の選択肢
const buildingAgeOptions = [
  '新築',
  '5年以内',
  '10年以内',
  '15年以内',
  '20年以内',
  '25年以内',
  '30年以内',
  '30年超',
];

// 総階数の選択肢
const totalFloorsOptions = [
  '～5階',
  '6～10階',
  '11～15階',
  '16～20階',
  '21～30階',
  '31階～',
];

export const BuildingManagement: React.FC = () => {
  const navigate = useNavigate();
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);
  const [totalCount, setTotalCount] = useState(0);
  const [searchParams, setSearchParams] = useState({
    name: '',
    address: '',
    minBuiltYear: '',
    maxBuiltYear: '',
    minTotalFloors: '',
    maxTotalFloors: '',
    hasActiveListings: '',
  });
  const [selectedBuilding, setSelectedBuilding] = useState<BuildingDetail | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editForm, setEditForm] = useState({
    normalized_name: '',
    address: '',
    total_floors: '',
    total_units: '',
    built_year: '',
  });
  const [detachingPropertyId, setDetachingPropertyId] = useState<number | null>(null);
  const [detachTargetPropertyId, setDetachTargetPropertyId] = useState<number | null>(null);  // 分離対象の物件ID
  const [detachDialogOpen, setDetachDialogOpen] = useState(false);
  const [detachCandidates, setDetachCandidates] = useState<any>(null);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [createNewBuilding, setCreateNewBuilding] = useState(false);
  const [buildingSearchQuery, setBuildingSearchQuery] = useState('');
  const [buildingSearchResults, setBuildingSearchResults] = useState<any[]>([]);
  const [searchingBuildings, setSearchingBuildings] = useState(false);
  const [newBuildingForm, setNewBuildingForm] = useState({
    name: '',
    address: '',
    built_year: '',
    built_month: '',
    total_floors: '',
  });
  const [expandedPropertyId, setExpandedPropertyId] = useState<number | null>(null);

  // 建物一覧を取得
  const fetchBuildings = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('offset', String(page * rowsPerPage));
      params.append('limit', String(rowsPerPage));
      
      if (searchParams.name) params.append('name', searchParams.name);
      if (searchParams.address) params.append('address', searchParams.address);
      if (searchParams.minBuiltYear) params.append('min_built_year', searchParams.minBuiltYear);
      if (searchParams.maxBuiltYear) params.append('max_built_year', searchParams.maxBuiltYear);
      if (searchParams.minTotalFloors) params.append('min_total_floors', searchParams.minTotalFloors);
      if (searchParams.maxTotalFloors) params.append('max_total_floors', searchParams.maxTotalFloors);
      if (searchParams.hasActiveListings) params.append('has_active_listings', searchParams.hasActiveListings);

      const response = await axios.get(`/api/admin/buildings?${params}`);
      setBuildings(response.data.items);
      setTotalCount(response.data.total);
    } catch (error) {
      console.error('建物一覧の取得に失敗しました:', error);
    } finally {
      setLoading(false);
    }
  };

  // 建物詳細を取得
  const fetchBuildingDetail = async (buildingId: number) => {
    setDetailLoading(true);
    try {
      const response = await axios.get(`/api/admin/buildings/${buildingId}`);
      setSelectedBuilding(response.data);
      setDetailDialogOpen(true);
    } catch (error) {
      console.error('建物詳細の取得に失敗しました:', error);
    } finally {
      setDetailLoading(false);
    }
  };

  // 建物情報を更新
  const updateBuilding = async () => {
    if (!selectedBuilding) return;
    
    try {
      const data: any = {};
      if (editForm.normalized_name !== selectedBuilding.normalized_name) {
        data.normalized_name = editForm.normalized_name;
      }
      if (editForm.address !== selectedBuilding.address) {
        data.address = editForm.address || null;
      }
      if (editForm.total_floors !== String(selectedBuilding.total_floors || '')) {
        data.total_floors = editForm.total_floors ? Number(editForm.total_floors) : null;
      }
      if (editForm.total_units !== String(selectedBuilding.total_units || '')) {
        data.total_units = editForm.total_units ? Number(editForm.total_units) : null;
      }
      if (editForm.built_year !== String(selectedBuilding.built_year || '')) {
        data.built_year = editForm.built_year ? Number(editForm.built_year) : null;
      }

      await axios.patch(`/api/admin/buildings/${selectedBuilding.id}`, data);
      setEditDialogOpen(false);
      fetchBuildingDetail(selectedBuilding.id); // 詳細を再取得
      fetchBuildings(); // 一覧も更新
    } catch (error) {
      console.error('建物情報の更新に失敗しました:', error);
    }
  };

  useEffect(() => {
    fetchBuildings();
  }, [page, rowsPerPage]);

  const handleSearch = () => {
    setPage(0);
    fetchBuildings();
  };

  const handleClearSearch = () => {
    setSearchParams({
      name: '',
      address: '',
      minBuiltYear: '',
      maxBuiltYear: '',
      minTotalFloors: '',
      maxTotalFloors: '',
      hasActiveListings: '',
    });
    setPage(0);
    // クリア後に再検索を実行
    setTimeout(() => fetchBuildings(), 0);
  };

  const openEditDialog = () => {
    if (!selectedBuilding) return;
    setEditForm({
      normalized_name: selectedBuilding.normalized_name,
      address: selectedBuilding.address || '',
      total_floors: String(selectedBuilding.total_floors || ''),
      total_units: String(selectedBuilding.total_units || ''),
      built_year: String(selectedBuilding.built_year || ''),
    });
    setEditDialogOpen(true);
  };

  // 建物を削除
  const deleteBuilding = async (buildingId: number) => {
    if (!window.confirm('この建物を削除してもよろしいですか？\n削除後は元に戻せません。')) {
      return;
    }

    try {
      const response = await axios.delete(`/api/admin/buildings/${buildingId}`);
      console.log('Delete response:', response);
      
      // 削除成功（axiosのtryブロック内なら成功）
      alert('建物を削除しました');
      await fetchBuildings(); // 一覧を更新
      if (detailDialogOpen) {
        setDetailDialogOpen(false); // 詳細ダイアログを閉じる
      }
    } catch (error) {
      console.error('建物削除エラー:', error);
      if (isAxiosError(error)) {
        if (error.response?.status === 404) {
          // 404の場合は既に削除されている
          alert('建物は既に削除されています');
          await fetchBuildings(); // 一覧を更新
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

  // 建物統合を復元
  // 建物検索（物件分離用）
  const searchBuildingsForDetach = async () => {
    if (!buildingSearchQuery.trim()) return;
    
    setSearchingBuildings(true);
    try {
      const response = await axios.get('/admin/buildings/search', {
        params: { query: buildingSearchQuery, limit: 20 }
      });
      setBuildingSearchResults(response.data.buildings || []);
    } catch (error) {
      console.error('建物検索エラー:', error);
      alert('建物の検索に失敗しました');
    } finally {
      setSearchingBuildings(false);
    }
  };

  // 物件を建物から分離
  // 物件分離候補を取得
  const fetchDetachCandidates = async (propertyId: number) => {
    setDetachingPropertyId(propertyId);
    setDetachTargetPropertyId(propertyId);  // 分離対象の物件IDを保存
    try {
      const response = await axios.post(`/api/admin/properties/${propertyId}/detach-candidates`);
      setDetachCandidates(response.data);
      setDetachDialogOpen(true);
      
      // デフォルト値を設定
      if (response.data.property_attributes) {
        setNewBuildingForm({
          name: response.data.property_building_name || '',
          address: response.data.property_attributes.address || '',
          built_year: response.data.property_attributes.built_year ? String(response.data.property_attributes.built_year) : '',
          built_month: response.data.property_attributes.built_month ? String(response.data.property_attributes.built_month) : '',
          total_floors: response.data.property_attributes.total_floors ? String(response.data.property_attributes.total_floors) : '',
        });
      }
      
      // 候補がない場合は新規建物作成タブを選択
      if (!response.data.candidates || response.data.candidates.length === 0) {
        setCreateNewBuilding(true);
      } else {
        setCreateNewBuilding(false);
        // デフォルトでは何も選択しない
        setSelectedBuildingId(null);
      }
    } catch (error: any) {
      console.error('候補取得に失敗しました:', error);
      const errorMessage = error.response?.data?.detail || '候補取得に失敗しました';
      alert(errorMessage);
      setDetachingPropertyId(null);  // エラー時のみクリア
    }
  };

  // 物件を建物に紐付け
  const attachPropertyToBuilding = async () => {
    console.log('attachPropertyToBuilding called');
    console.log('detachCandidates:', detachCandidates);
    console.log('detachTargetPropertyId:', detachTargetPropertyId);
    
    if (!detachCandidates || !detachTargetPropertyId) {
      alert(`物件情報が不足しています\ndetachCandidates: ${!!detachCandidates}\ndetachTargetPropertyId: ${detachTargetPropertyId}`);
      return;
    }
    
    const propertyId = detachTargetPropertyId;
    
    try {
      const requestData: any = {
        create_new: createNewBuilding
      };
      
      if (createNewBuilding) {
        // 新規建物作成
        requestData.new_building_name = newBuildingForm.name;
        requestData.new_building_address = newBuildingForm.address || null;
        requestData.new_building_built_year = newBuildingForm.built_year ? Number(newBuildingForm.built_year) : null;
        requestData.new_building_built_month = newBuildingForm.built_month ? Number(newBuildingForm.built_month) : null;
        requestData.new_building_total_floors = newBuildingForm.total_floors ? Number(newBuildingForm.total_floors) : null;
      } else {
        // 既存建物に紐付け
        if (!selectedBuildingId) {
          alert('紐付け先の建物を選択してください');
          return;
        }
        requestData.building_id = selectedBuildingId;
      }
      
      const response = await axios.post(
        `/api/admin/properties/${propertyId}/attach-to-building`,
        requestData
      );
      
      console.log('紐付けAPIレスポンス:', response.data);
      
      // 成功メッセージを表示
      const successMessage = response.data?.message || '物件を建物に紐付けました';
      alert(successMessage);
      
      // ダイアログを閉じる
      setDetachDialogOpen(false);
      setDetachCandidates(null);
      setDetachingPropertyId(null);
      setDetachTargetPropertyId(null);
      setBuildingSearchQuery('');
      setBuildingSearchResults([]);
      
      // 詳細を再取得
      if (selectedBuilding) {
        await fetchBuildingDetail(selectedBuilding.id);
      }
      // 一覧も更新
      await fetchBuildings();
      
    } catch (error: any) {
      console.error('紐付けに失敗しました:', error);
      // エラーメッセージの取得を改善
      let errorMessage = '紐付けに失敗しました';
      if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.response?.data?.message) {
        errorMessage = error.response.data.message;
      } else if (error.message) {
        errorMessage = error.message;
      }
      alert(errorMessage);
    }
  };

  const formatPrice = (price?: number) => {
    if (price === undefined || price === null) return '-';
    return `${price.toLocaleString()}万円`;
  };

  const calculateBuildingAge = (builtYear?: number) => {
    if (!builtYear) return '-';
    const currentYear = new Date().getFullYear();
    const age = currentYear - builtYear;
    return `${age}年`;
  };

  // 築年数選択肢から年を計算
  const getYearFromBuildingAge = (ageOption: string): string => {
    const currentYear = new Date().getFullYear();
    switch (ageOption) {
      case '新築': return String(currentYear);
      case '5年以内': return String(currentYear - 5);
      case '10年以内': return String(currentYear - 10);
      case '15年以内': return String(currentYear - 15);
      case '20年以内': return String(currentYear - 20);
      case '25年以内': return String(currentYear - 25);
      case '30年以内': return String(currentYear - 30);
      case '30年超': return '1900';
      default: return '';
    }
  };

  // 総階数選択肢から階数を計算
  const getFloorsFromOption = (floorsOption: string): { min: string, max: string } => {
    switch (floorsOption) {
      case '～5階': return { min: '1', max: '5' };
      case '6～10階': return { min: '6', max: '10' };
      case '11～15階': return { min: '11', max: '15' };
      case '16～20階': return { min: '16', max: '20' };
      case '21～30階': return { min: '21', max: '30' };
      case '31階～': return { min: '31', max: '999' };
      default: return { min: '', max: '' };
    }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        建物管理
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
              value={searchParams.name}
              onChange={(e) => setSearchParams({ ...searchParams, name: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="建物名または建物ID"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
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
              options={buildingAgeOptions}
              value={null}
              onChange={(_, value) => {
                if (value) {
                  const year = getYearFromBuildingAge(value);
                  setSearchParams({ ...searchParams, minBuiltYear: year });
                }
              }}
              renderInput={(params) => (
                <TextField {...params} label="築年数（以上）" size="small" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Autocomplete
              options={buildingAgeOptions}
              value={null}
              onChange={(_, value) => {
                if (value) {
                  const year = getYearFromBuildingAge(value);
                  setSearchParams({ ...searchParams, maxBuiltYear: year });
                }
              }}
              renderInput={(params) => (
                <TextField {...params} label="築年数（以下）" size="small" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Autocomplete
              options={totalFloorsOptions}
              value={null}
              onChange={(_, value) => {
                if (value) {
                  const { min, max } = getFloorsFromOption(value);
                  setSearchParams({ 
                    ...searchParams, 
                    minTotalFloors: min,
                    maxTotalFloors: max 
                  });
                }
              }}
              renderInput={(params) => (
                <TextField {...params} label="総階数" size="small" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>掲載状態</InputLabel>
              <Select
                value={searchParams.hasActiveListings}
                onChange={(e) => setSearchParams({ ...searchParams, hasActiveListings: e.target.value })}
                label="掲載状態"
              >
                <MenuItem value="">すべて</MenuItem>
                <MenuItem value="true">掲載中の物件あり</MenuItem>
                <MenuItem value="false">掲載中の物件なし</MenuItem>
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

      {/* 建物一覧 */}
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
                  <TableCell align="center">総階数</TableCell>
                  <TableCell align="center">総戸数</TableCell>
                  <TableCell align="center">築年数</TableCell>
                  <TableCell align="center">物件数</TableCell>
                  <TableCell align="center">掲載中</TableCell>
                  <TableCell>価格帯</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {buildings.map((building) => (
                  <TableRow key={building.id}>
                    <TableCell>{building.id}</TableCell>
                    <TableCell>{building.normalized_name}</TableCell>
                    <TableCell>{building.address || '-'}</TableCell>
                    <TableCell align="center">
                      {building.total_floors ? `${building.total_floors}階` : '-'}
                    </TableCell>
                    <TableCell align="center">
                      {building.total_units ? `${building.total_units}戸` : '-'}
                    </TableCell>
                    <TableCell align="center">
                      {building.built_year ? (
                        <>
                          {building.built_year}年築
                          <Typography variant="caption" display="block" color="text.secondary">
                            （築{calculateBuildingAge(building.built_year)}）
                          </Typography>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="center">{building.property_count}</TableCell>
                    <TableCell align="center">
                      {building.active_listing_count > 0 ? (
                        <Chip
                          label={building.active_listing_count}
                          color="primary"
                          size="small"
                        />
                      ) : (
                        <Chip
                          label="0"
                          size="small"
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      {building.min_price && building.max_price ? (
                        building.min_price === building.max_price ? (
                          formatPrice(building.min_price)
                        ) : (
                          `${formatPrice(building.min_price)} - ${formatPrice(building.max_price)}`
                        )
                      ) : (
                        '-'
                      )}
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="詳細表示">
                        <IconButton
                          size="small"
                          onClick={() => fetchBuildingDetail(building.id)}
                        >
                          <VisibilityIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="物件一覧">
                        <IconButton
                          size="small"
                          onClick={() => navigate(`/buildings/${building.id}/properties`)}
                        >
                          <HomeIcon />
                        </IconButton>
                      </Tooltip>
                      {building.property_count === 0 && (
                        <Tooltip title="建物を削除">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => deleteBuilding(building.id)}
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

      {/* 建物詳細ダイアログ */}
      <Dialog
        open={detailDialogOpen}
        onClose={() => setDetailDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              建物詳細 (ID: {selectedBuilding?.id})
            </Typography>
            <Box>
              {selectedBuilding && selectedBuilding.property_count === 0 && (
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteIcon />}
                  onClick={() => deleteBuilding(selectedBuilding.id)}
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
          ) : selectedBuilding ? (
            <Box>
              {/* 基本情報 */}
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>基本情報</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">建物名</Typography>
                      <Typography>{selectedBuilding.normalized_name}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">住所</Typography>
                      <Typography>{selectedBuilding.address || '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={4} md={2.4}>
                      <Typography variant="caption" color="text.secondary">総階数</Typography>
                      <Typography>{selectedBuilding.total_floors ? `${selectedBuilding.total_floors}階` : '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={4} md={2.4}>
                      <Typography variant="caption" color="text.secondary">総戸数</Typography>
                      <Typography>{selectedBuilding.total_units ? `${selectedBuilding.total_units}戸` : '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={4} md={2.4}>
                      <Typography variant="caption" color="text.secondary">築年数</Typography>
                      <Typography>
                        {selectedBuilding.built_year ? (
                          <>
                            {selectedBuilding.built_year}年築
                            （築{calculateBuildingAge(selectedBuilding.built_year)}）
                          </>
                        ) : '-'}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={2.4}>
                      <Typography variant="caption" color="text.secondary">物件数</Typography>
                      <Typography>{selectedBuilding.property_count}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6} md={2.4}>
                      <Typography variant="caption" color="text.secondary">掲載中の物件数</Typography>
                      <Typography>{selectedBuilding.active_listing_count}</Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* 掲載情報の建物名（別名） */}
              {selectedBuilding.listing_names && selectedBuilding.listing_names.length > 0 && (
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>掲載情報の建物名（別名）</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      各不動産サイトで使用されている建物名の一覧です
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                      {selectedBuilding.listing_names.map((listingName, index) => (
                        <Chip
                          key={index}
                          label={`${listingName.name} (${listingName.occurrence_count}件)`}
                          variant="outlined"
                          color="secondary"
                          sx={{ 
                            fontSize: '0.9rem',
                            '& .MuiChip-label': { px: 2, py: 1 }
                          }}
                          title={`サイト: ${listingName.source_sites.join(', ')}`}
                        />
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              )}

              {/* 物件一覧 */}
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>物件一覧</Typography>
                  {selectedBuilding.properties.length > 0 ? (
                    <TableContainer sx={{ maxHeight: 600 }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            <TableCell>物件ID</TableCell>
                            <TableCell>部屋番号</TableCell>
                            <TableCell align="right">階数</TableCell>
                            <TableCell align="right">面積</TableCell>
                            <TableCell>間取り</TableCell>
                            <TableCell>方角</TableCell>
                            <TableCell>物件表示名</TableCell>
                            <TableCell align="center">掲載数</TableCell>
                            <TableCell>価格帯</TableCell>
                            <TableCell align="center">操作</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {selectedBuilding.properties.map((property) => (
                            <React.Fragment key={property.id}>
                              <TableRow>
                                <TableCell>{property.id}</TableCell>
                                <TableCell>{property.room_number || '-'}</TableCell>
                                <TableCell align="right">
                                  {property.floor_number ? `${property.floor_number}階` : '-'}
                                </TableCell>
                                <TableCell align="right">
                                  {property.area ? `${property.area.toFixed(2)}㎡` : '-'}
                                </TableCell>
                                <TableCell>{property.layout || '-'}</TableCell>
                                <TableCell>{property.direction || '-'}</TableCell>
                                <TableCell>
                                  {property.display_building_name ? (
                                    property.display_building_name !== selectedBuilding.normalized_name ? (
                                      <Tooltip title="建物名とは異なる表示名が設定されています">
                                        <Chip
                                          label={property.display_building_name}
                                          size="small"
                                          color="warning"
                                          variant="outlined"
                                        />
                                      </Tooltip>
                                    ) : (
                                      <Typography variant="body2" color="text.secondary">
                                        {property.display_building_name}
                                      </Typography>
                                    )
                                  ) : (
                                    '-'
                                  )}
                                </TableCell>
                                <TableCell align="center">
                                  <Box display="flex" alignItems="center" gap={1}>
                                    {property.active_listing_count > 0 ? (
                                      <Chip
                                        label={property.active_listing_count}
                                        color="primary"
                                        size="small"
                                      />
                                    ) : (
                                      <Chip
                                        label="0"
                                        size="small"
                                      />
                                    )}
                                    {(property as any).listings && (property as any).listings.length > 0 && (
                                      <IconButton
                                        size="small"
                                        onClick={() => setExpandedPropertyId(
                                          expandedPropertyId === property.id ? null : property.id
                                        )}
                                      >
                                        {expandedPropertyId === property.id ? 
                                          <ExpandLessIcon /> : <ExpandMoreIcon />}
                                      </IconButton>
                                    )}
                                  </Box>
                                </TableCell>
                                <TableCell>
                                  {property.min_price && property.max_price ? (
                                    property.min_price === property.max_price ? (
                                      formatPrice(property.min_price)
                                    ) : (
                                      `${formatPrice(property.min_price)} - ${formatPrice(property.max_price)}`
                                    )
                                  ) : (
                                    '-'
                                  )}
                                </TableCell>
                                <TableCell align="center">
                                  <Tooltip title="この物件を建物から分離">
                                    <IconButton
                                      size="small"
                                      color="warning"
                                      onClick={() => fetchDetachCandidates(property.id)}
                                      disabled={detachingPropertyId === property.id}
                                    >
                                      {detachingPropertyId === property.id ? (
                                        <CircularProgress size={20} />
                                      ) : (
                                        <CallSplitIcon />
                                      )}
                                    </IconButton>
                                  </Tooltip>
                                </TableCell>
                              </TableRow>
                              {/* 掲載情報の折り畳み行 */}
                              {expandedPropertyId === property.id && (property as any).listings && (property as any).listings.length > 0 && (
                                <TableRow>
                                  <TableCell colSpan={10} sx={{ bgcolor: 'grey.50', py: 0 }}>
                                    <Collapse in={expandedPropertyId === property.id}>
                                      <Box sx={{ p: 2 }}>
                                        <Typography variant="subtitle2" gutterBottom>
                                          掲載情報 ({(property as any).listings?.length || 0}件)
                                        </Typography>
                                        <Table size="small">
                                          <TableHead>
                                            <TableRow>
                                              <TableCell>ID</TableCell>
                                              <TableCell>サイト</TableCell>
                                              <TableCell>建物名</TableCell>
                                              <TableCell align="right">価格</TableCell>
                                              <TableCell>住所</TableCell>
                                              <TableCell align="center">所在階</TableCell>
                                              <TableCell align="center">総階数</TableCell>
                                              <TableCell align="center">総戸数</TableCell>
                                              <TableCell>初回掲載日</TableCell>
                                              <TableCell>最終確認日</TableCell>
                                            </TableRow>
                                          </TableHead>
                                          <TableBody>
                                            {((property as any).listings || []).map((listing: any) => (
                                              <TableRow key={listing.id}>
                                                <TableCell>{listing.id}</TableCell>
                                                <TableCell>
                                                  <Chip
                                                    label={listing.source_site}
                                                    size="small"
                                                    color={
                                                      listing.source_site === 'SUUMO' ? 'primary' :
                                                      listing.source_site === 'HOMES' ? 'secondary' :
                                                      listing.source_site === 'REHOUSE' ? 'success' :
                                                      listing.source_site === 'NOMU' ? 'warning' :
                                                      'default'
                                                    }
                                                  />
                                                </TableCell>
                                                <TableCell>
                                                  {listing.listing_building_name || '-'}
                                                </TableCell>
                                                <TableCell align="right">
                                                  {formatPrice(listing.current_price)}
                                                </TableCell>
                                                <TableCell>
                                                  {listing.listing_address || '-'}
                                                </TableCell>
                                                <TableCell align="center">
                                                  {listing.listing_floor_number ? `${listing.listing_floor_number}階` : '-'}
                                                </TableCell>
                                                <TableCell align="center">
                                                  {listing.listing_total_floors ? `${listing.listing_total_floors}階` : '-'}
                                                </TableCell>
                                                <TableCell align="center">
                                                  {listing.listing_total_units ? `${listing.listing_total_units}戸` : '-'}
                                                </TableCell>
                                                <TableCell>
                                                  {listing.first_seen_at ? 
                                                    format(new Date(listing.first_seen_at), 'yyyy/MM/dd') : '-'}
                                                </TableCell>
                                                <TableCell>
                                                  {listing.last_scraped_at ? 
                                                    format(new Date(listing.last_scraped_at), 'yyyy/MM/dd') : '-'}
                                                </TableCell>
                                              </TableRow>
                                            ))}
                                          </TableBody>
                                        </Table>
                                      </Box>
                                    </Collapse>
                                  </TableCell>
                                </TableRow>
                              )}
                            </React.Fragment>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  ) : (
                    <Typography color="text.secondary">物件がありません</Typography>
                  )}
                </CardContent>
              </Card>
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
        <DialogTitle>建物情報の編集</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="建物名"
                value={editForm.normalized_name}
                onChange={(e) => setEditForm({ ...editForm, normalized_name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="住所"
                value={editForm.address}
                onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="総階数"
                type="number"
                value={editForm.total_floors}
                onChange={(e) => setEditForm({ ...editForm, total_floors: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="総戸数"
                type="number"
                value={editForm.total_units}
                onChange={(e) => setEditForm({ ...editForm, total_units: e.target.value })}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="築年"
                type="number"
                value={editForm.built_year}
                onChange={(e) => setEditForm({ ...editForm, built_year: e.target.value })}
                helperText="西暦で入力（例：1995）"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={updateBuilding}>保存</Button>
        </DialogActions>
      </Dialog>

      {/* 物件分離・建物選択ダイアログ */}
      <Dialog
        open={detachDialogOpen}
        onClose={() => {
          setDetachDialogOpen(false);
          setDetachingPropertyId(null);  // ローディング状態をクリア
          setDetachCandidates(null);
          setBuildingSearchQuery('');
          setBuildingSearchResults([]);
        }}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          物件の分離と再紐付け先の選択
        </DialogTitle>
        <DialogContent>
          {detachCandidates && (
            <Box>
              {/* 現在の状況 */}
              <Card sx={{ mb: 2, bgcolor: 'grey.50' }}>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    現在の建物
                  </Typography>
                  <Typography variant="body1">
                    {detachCandidates.current_building.normalized_name} (ID: {detachCandidates.current_building.id})
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {detachCandidates.current_building.address || '住所未設定'}
                  </Typography>
                </CardContent>
              </Card>

              {/* 物件情報 */}
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    物件の掲載情報
                  </Typography>
                  <Typography variant="body1" gutterBottom>
                    建物名: <strong>{detachCandidates.property_building_name}</strong>
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2">
                        住所: {detachCandidates.property_attributes.address || '-'}
                      </Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="body2">
                        築年月: {detachCandidates.property_attributes.built_year ? 
                          `${detachCandidates.property_attributes.built_year}年${detachCandidates.property_attributes.built_month ? detachCandidates.property_attributes.built_month + '月' : ''}` 
                          : '-'}
                      </Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="body2">
                        総階数: {detachCandidates.property_attributes.total_floors || '-'}階
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* 紐付け先の選択 */}
              <Typography variant="h6" gutterBottom>
                紐付け先を選択
              </Typography>

              <FormControl component="fieldset" sx={{ mb: 2, width: '100%' }}>
                <Tabs
                  value={createNewBuilding ? 1 : 0}
                  onChange={(_, value) => setCreateNewBuilding(value === 1)}
                  sx={{ mb: 2 }}
                >
                  <Tab label="既存の建物から選択" />
                  <Tab label="新規建物を作成" />
                </Tabs>

                {!createNewBuilding ? (
                  // 既存建物の選択
                  <Box>
                    {/* 建物検索フィールド */}
                    <Box sx={{ mb: 2 }}>
                      <TextField
                        fullWidth
                        placeholder="建物名または建物IDで検索"
                        value={buildingSearchQuery}
                        onChange={(e) => {
                          setBuildingSearchQuery(e.target.value);
                          // 入力テキストが空になったら検索結果もクリア
                          if (e.target.value === '') {
                            setBuildingSearchResults([]);
                          }
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            searchBuildingsForDetach();
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
                              {buildingSearchQuery && (
                                <IconButton
                                  size="small"
                                  onClick={() => {
                                    setBuildingSearchQuery('');
                                    setBuildingSearchResults([]);
                                  }}
                                  sx={{ mr: 1 }}
                                >
                                  <ClearIcon />
                                </IconButton>
                              )}
                              <Button
                                variant="contained"
                                size="small"
                                onClick={searchBuildingsForDetach}
                                disabled={searchingBuildings || !buildingSearchQuery.trim()}
                              >
                                検索
                              </Button>
                            </InputAdornment>
                          ),
                        }}
                      />
                    </Box>

                    {searchingBuildings && (
                      <Box display="flex" justifyContent="center" p={2}>
                        <CircularProgress size={24} />
                      </Box>
                    )}

                    {/* 検索結果または候補の表示 */}
                    {(buildingSearchResults.length > 0 || detachCandidates.candidates.length > 0) ? (
                      <TableContainer sx={{ maxHeight: 300 }}>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell padding="checkbox"></TableCell>
                              <TableCell>建物名</TableCell>
                              <TableCell>住所</TableCell>
                              <TableCell align="center">築年</TableCell>
                              <TableCell align="center">階数</TableCell>
                              {buildingSearchResults.length === 0 && (
                                <>
                                  <TableCell align="center">スコア</TableCell>
                                  <TableCell>一致項目</TableCell>
                                </>
                              )}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {/* 検索結果を優先表示 */}
                            {(buildingSearchResults.length > 0 ? buildingSearchResults : detachCandidates.candidates).map((candidate: any) => (
                              <TableRow 
                                key={candidate.id}
                                selected={selectedBuildingId === candidate.id}
                                onClick={() => setSelectedBuildingId(candidate.id)}
                                sx={{ cursor: 'pointer' }}
                              >
                                <TableCell padding="checkbox">
                                  <input
                                    type="radio"
                                    checked={selectedBuildingId === candidate.id}
                                    onChange={() => setSelectedBuildingId(candidate.id)}
                                  />
                                </TableCell>
                                <TableCell>
                                  {candidate.normalized_name}
                                  {buildingSearchResults.length > 0 && (
                                    <Chip 
                                      label={`ID: ${candidate.id}`} 
                                      size="small" 
                                      sx={{ ml: 1 }}
                                    />
                                  )}
                                  {buildingSearchResults.length === 0 && (candidate.match_type === 'alias' || candidate.match_type === 'listing') && (
                                    <Chip
                                      label={`別名: ${candidate.alias_name || candidate.matched_alias}`}
                                      size="small"
                                      color="info"
                                      sx={{ ml: 1 }}
                                    />
                                  )}
                                </TableCell>
                                <TableCell>{candidate.address || '-'}</TableCell>
                                <TableCell align="center">{candidate.built_year || '-'}</TableCell>
                                <TableCell align="center">{candidate.total_floors || '-'}</TableCell>
                                {buildingSearchResults.length === 0 && (
                                  <>
                                    <TableCell align="center">
                                      <Chip
                                        label={candidate.score}
                                        size="small"
                                        color={candidate.score >= 20 ? 'success' : candidate.score >= 15 ? 'warning' : 'default'}
                                      />
                                    </TableCell>
                                    <TableCell>
                                      {candidate.match_details.join(', ')}
                                    </TableCell>
                                  </>
                                )}
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary" sx={{ p: 2, textAlign: 'center' }}>
                        {buildingSearchQuery ? 
                          '検索結果がありません。別のキーワードで検索するか、新規建物を作成してください。' :
                          '候補となる建物が見つかりません。建物を検索するか、新規建物を作成してください。'
                        }
                      </Typography>
                    )}
                  </Box>
                ) : (
                  // 新規建物作成フォーム
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      以下の情報で新規建物が作成されます（掲載情報の多数決から自動決定）
                    </Typography>
                    
                    <Box sx={{ bgcolor: 'grey.50', p: 2, borderRadius: 1 }}>
                      <Grid container spacing={2}>
                        <Grid item xs={12}>
                          <Typography variant="caption" color="text.secondary">建物名</Typography>
                          <Typography variant="body1" sx={{ fontWeight: 'medium' }}>
                            {newBuildingForm.name || '（未設定）'}
                          </Typography>
                        </Grid>
                        <Grid item xs={12}>
                          <Typography variant="caption" color="text.secondary">住所</Typography>
                          <Typography variant="body1">
                            {newBuildingForm.address || '（未設定）'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">築年月</Typography>
                          <Typography variant="body1">
                            {newBuildingForm.built_year ? 
                              `${newBuildingForm.built_year}年${newBuildingForm.built_month ? newBuildingForm.built_month + '月' : ''}` 
                              : '（未設定）'}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">総階数</Typography>
                          <Typography variant="body1">
                            {newBuildingForm.total_floors ? `${newBuildingForm.total_floors}階` : '（未設定）'}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>
                  </Box>
                )}
              </FormControl>

              {/* 推奨事項の表示 */}
              {detachCandidates.can_create_new && !createNewBuilding && (
                <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>
                  ※ 一致度が低いため、新規建物の作成も検討してください
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setDetachDialogOpen(false);
            setDetachingPropertyId(null);  // ローディング状態をクリア
            setDetachTargetPropertyId(null);  // 分離対象IDもクリア
            setDetachCandidates(null);
            setBuildingSearchQuery('');
            setBuildingSearchResults([]);
          }}>キャンセル</Button>
          <Button
            variant="contained"
            onClick={attachPropertyToBuilding}
            disabled={!createNewBuilding && !selectedBuildingId}
          >
            実行
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};