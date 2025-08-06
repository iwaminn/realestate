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
  Card,
  CardContent,
  CircularProgress,
  Tooltip,
  Autocomplete,
} from '@mui/material';
import {
  Search as SearchIcon,
  Refresh as RefreshIcon,
  Visibility as VisibilityIcon,
  Edit as EditIcon,
  Clear as ClearIcon,
  Home as HomeIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import axios, { isAxiosError } from 'axios';
import { useNavigate } from 'react-router-dom';

interface Building {
  id: number;
  normalized_name: string;
  address?: string;
  total_floors?: number;
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
  // 外部建物ID
  external_ids?: Array<{
    source_site: string;
    external_id: string;
    created_at?: string;
  }>;
  // 物件一覧
  properties: Array<{
    id: number;
    room_number?: string;
    floor_number?: number;
    area?: number;
    layout?: string;
    direction?: string;
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
    built_year: '',
  });

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
  };

  const openEditDialog = () => {
    if (!selectedBuilding) return;
    setEditForm({
      normalized_name: selectedBuilding.normalized_name,
      address: selectedBuilding.address || '',
      total_floors: String(selectedBuilding.total_floors || ''),
      built_year: String(selectedBuilding.built_year || ''),
    });
    setEditDialogOpen(true);
  };

  const formatPrice = (price?: number) => {
    if (price === undefined || price === null) return '-';
    return `${price.toLocaleString()}万円`;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    return format(new Date(dateString), 'yyyy/MM/dd HH:mm');
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
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              fullWidth
              label="建物名"
              value={searchParams.name}
              onChange={(e) => setSearchParams({ ...searchParams, name: e.target.value })}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              fullWidth
              label="住所"
              value={searchParams.address}
              onChange={(e) => setSearchParams({ ...searchParams, address: e.target.value })}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
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
                <TextField {...params} label="築年数（以上）" />
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
                <TextField {...params} label="築年数（以下）" />
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
                <TextField {...params} label="総階数" />
              )}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
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
          <Grid item xs={12} md={6}>
            <Box display="flex" gap={1}>
              <Button
                variant="contained"
                startIcon={<SearchIcon />}
                onClick={handleSearch}
              >
                検索
              </Button>
              <Button
                variant="outlined"
                startIcon={<ClearIcon />}
                onClick={handleClearSearch}
              >
                クリア
              </Button>
              <Button
                variant="outlined"
                startIcon={<RefreshIcon />}
                onClick={fetchBuildings}
              >
                更新
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
            <Button
              variant="outlined"
              startIcon={<EditIcon />}
              onClick={openEditDialog}
            >
              編集
            </Button>
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
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">総階数</Typography>
                      <Typography>{selectedBuilding.total_floors ? `${selectedBuilding.total_floors}階` : '-'}</Typography>
                    </Grid>
                    <Grid item xs={3}>
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
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">物件数</Typography>
                      <Typography>{selectedBuilding.property_count}</Typography>
                    </Grid>
                    <Grid item xs={3}>
                      <Typography variant="caption" color="text.secondary">掲載中の物件数</Typography>
                      <Typography>{selectedBuilding.active_listing_count}</Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* 外部建物ID */}
              {selectedBuilding.external_ids && selectedBuilding.external_ids.length > 0 && (
                <Card sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>外部建物ID</Typography>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>サイト</TableCell>
                          <TableCell>建物ID</TableCell>
                          <TableCell>登録日時</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {selectedBuilding.external_ids.map((extId, index) => (
                          <TableRow key={index}>
                            <TableCell>
                              <Chip 
                                label={extId.source_site} 
                                size="small" 
                                color={
                                  extId.source_site === 'SUUMO' ? 'primary' :
                                  extId.source_site === 'HOMES' ? 'secondary' :
                                  extId.source_site === 'REHOUSE' ? 'success' :
                                  extId.source_site === 'NOMU' ? 'warning' :
                                  'default'
                                }
                              />
                            </TableCell>
                            <TableCell>{extId.external_id}</TableCell>
                            <TableCell>{formatDate(extId.created_at)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {/* 物件一覧 */}
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>物件一覧</Typography>
                  {selectedBuilding.properties.length > 0 ? (
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>部屋番号</TableCell>
                          <TableCell align="right">階数</TableCell>
                          <TableCell align="right">面積</TableCell>
                          <TableCell>間取り</TableCell>
                          <TableCell>方角</TableCell>
                          <TableCell align="center">掲載数</TableCell>
                          <TableCell>価格帯</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {selectedBuilding.properties.map((property) => (
                          <TableRow key={property.id}>
                            <TableCell>{property.room_number || '-'}</TableCell>
                            <TableCell align="right">
                              {property.floor_number ? `${property.floor_number}階` : '-'}
                            </TableCell>
                            <TableCell align="right">
                              {property.area ? `${property.area.toFixed(2)}㎡` : '-'}
                            </TableCell>
                            <TableCell>{property.layout || '-'}</TableCell>
                            <TableCell>{property.direction || '-'}</TableCell>
                            <TableCell align="center">
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
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
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
    </Box>
  );
};