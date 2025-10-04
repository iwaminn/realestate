import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  Box,
  Paper,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  CircularProgress,
  Link,
  SelectChangeEvent,
  Button,
  Tabs,
  Tab,
  Card,
  CardContent,
  CardActionArea,
  Divider,
  useMediaQuery,
  ToggleButton,
  ToggleButtonGroup,
  TableSortLabel,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import UpdateIcon from '@mui/icons-material/Update';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import RefreshIcon from '@mui/icons-material/Refresh';
import TableChartIcon from '@mui/icons-material/TableChart';
import ViewModuleIcon from '@mui/icons-material/ViewModule';
import { propertyApi, RecentUpdate } from '../api/propertyApi';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { sortWardNamesByLandPrice } from '../constants/wardOrder';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`property-updates-tabpanel-${index}`}
      aria-labelledby={`property-updates-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const PropertyUpdatesPage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [priceChanges, setPriceChanges] = useState<RecentUpdate[]>([]);
  const [newListings, setNewListings] = useState<RecentUpdate[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastScraperCompleted, setLastScraperCompleted] = useState<string | null>(null);
  const [wards, setWards] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<'table' | 'card'>('table');
  
  // 並び替えの状態管理
  type SortField = 'building_name' | 'price' | 'price_diff' | 'area' | 'floor_number' | 'built_year' | 'days_on_market' | 'changed_at' | 'created_at' | 'layout' | 'direction';
  type SortOrder = 'asc' | 'desc';
  const [sortField, setSortField] = useState<SortField>('price_diff');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // URLパラメータから初期値を取得
  const tabValue = parseInt(searchParams.get('tab') || '0');
  const selectedWard = searchParams.get('ward') || 'all';
  const selectedHours = parseInt(searchParams.get('hours') || '24');
  const page = parseInt(searchParams.get('page') || '0');
  const rowsPerPage = parseInt(searchParams.get('rowsPerPage') || '25');

  const fetchUpdates = async () => {
    setLoading(true);
    try {
      const response = await propertyApi.getRecentUpdates(selectedHours);
      
      // 価格改定物件を抽出
      const allPriceChanges: RecentUpdate[] = [];
      // 新着物件を抽出
      const allNewListings: RecentUpdate[] = [];
      const wardSet = new Set<string>();
      
      response.updates_by_ward.forEach(ward => {
        wardSet.add(ward.ward);
        
        // 価格改定物件
        ward.price_changes.forEach(property => {
          allPriceChanges.push({
            ...property,
            address: property.address || ward.ward,
          });
        });
        
        // 新着物件
        ward.new_listings.forEach(property => {
          allNewListings.push({
            ...property,
            address: property.address || ward.ward,
          });
        });
      });
      
      // 価格改定物件: 価格変動幅でソート（大きい順）
      allPriceChanges.sort((a, b) => {
        const diffA = Math.abs(a.price_diff || 0);
        const diffB = Math.abs(b.price_diff || 0);
        return diffB - diffA;
      });
      
      // 新着物件: 価格でソート（高い順）
      allNewListings.sort((a, b) => b.price - a.price);
      
      setPriceChanges(allPriceChanges);
      setNewListings(allNewListings);
      setWards(sortWardNamesByLandPrice(Array.from(wardSet)));
      setLastScraperCompleted(response.last_scraper_completed_at);
    } catch (error) {
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchUpdates();
  }, [selectedHours]);

  // URLパラメータを更新するヘルパー関数
  const updateSearchParams = (updates: Record<string, string>) => {
    const newParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === '' || 
          (key === 'tab' && value === '0') ||
          (key === 'ward' && value === 'all') || 
          (key === 'hours' && value === '24') || 
          (key === 'page' && value === '0') ||
          (key === 'rowsPerPage' && value === '25')) {
        // デフォルト値の場合はパラメータを削除
        newParams.delete(key);
      } else {
        newParams.set(key, value);
      }
    });
    setSearchParams(newParams);
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    updateSearchParams({ tab: newValue.toString(), page: '0' });
    
    // タブ変更時にデフォルトの並び替えを設定
    if (newValue === 0) {
      // 価格改定履歴タブ：価格変動幅の降順
      setSortField('price_diff');
      setSortOrder('desc');
    } else {
      // 新規掲載物件タブ：価格の降順
      setSortField('price');
      setSortOrder('desc');
    }
  };

  const handleWardChange = (event: SelectChangeEvent) => {
    updateSearchParams({ ward: event.target.value, page: '0' });
  };

  const handleHoursChange = (event: SelectChangeEvent<number>) => {
    updateSearchParams({ hours: event.target.value.toString(), page: '0' });
  };

  const handleChangePage = (event: unknown, newPage: number) => {
    updateSearchParams({ page: newPage.toString() });
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    updateSearchParams({ rowsPerPage: event.target.value, page: '0' });
  };

  // 並び替えハンドラー
  const handleSort = (field: SortField) => {
    const isCurrentField = sortField === field;
    const newOrder: SortOrder = isCurrentField && sortOrder === 'desc' ? 'asc' : 'desc';
    setSortField(field);
    setSortOrder(newOrder);
    updateSearchParams({ page: '0' }); // ページを最初に戻す
  };

  const formatPrice = (price: number, showUnit: boolean = true) => {
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      if (man === 0) {
        return `${oku}億${showUnit ? '円' : ''}`;
      }
      return `${oku}億${man.toLocaleString()}万${showUnit ? '円' : ''}`;
    }
    return `${price.toLocaleString()}万${showUnit ? '円' : ''}`;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
    });
  };

  const getWard = (address: string | null) => {
    if (!address) return '不明';
    const match = address.match(/(.*?[区市町村])/);
    if (match) {
      return match[1].replace('東京都', '');
    }
    return address;
  };

  // フィルタリング
  const filteredPriceChanges = selectedWard === 'all' 
    ? priceChanges 
    : priceChanges.filter(property => getWard(property.address) === selectedWard);
    
  const filteredNewListings = selectedWard === 'all' 
    ? newListings 
    : newListings.filter(property => getWard(property.address) === selectedWard);

  // 並び替え処理
  const sortData = (data: RecentUpdate[], field: SortField, order: SortOrder): RecentUpdate[] => {
    return [...data].sort((a, b) => {
      let aValue: any = a[field];
      let bValue: any = b[field];
      
      // 特別な処理が必要なフィールド
      if (field === 'building_name') {
        aValue = a.building_name?.toLowerCase() || '';
        bValue = b.building_name?.toLowerCase() || '';
      } else if (field === 'built_year') {
        aValue = a.built_year || 0;
        bValue = b.built_year || 0;
      } else if (field === 'price_diff') {
        // 価格改定タブでのみ有効、値下げ幅の大きさで比較
        aValue = Math.abs(a.price_diff || 0);
        bValue = Math.abs(b.price_diff || 0);
      } else if (field === 'changed_at' || field === 'created_at') {
        aValue = new Date(aValue || 0).getTime();
        bValue = new Date(bValue || 0).getTime();
      }
      
      // null/undefinedの処理
      if (aValue == null && bValue == null) return 0;
      if (aValue == null) return order === 'asc' ? -1 : 1;
      if (bValue == null) return order === 'asc' ? 1 : -1;
      
      // 比較
      if (aValue < bValue) return order === 'asc' ? -1 : 1;
      if (aValue > bValue) return order === 'asc' ? 1 : -1;
      return 0;
    });
  };

  // 現在のタブに応じたデータを選択
  const currentData = tabValue === 0 ? filteredPriceChanges : filteredNewListings;
  
  // 並び替えを適用
  const sortedData = sortData(currentData, sortField, sortOrder);

  // ページネーション
  const paginatedData = sortedData.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  // 価格帯別の統計（新着物件用）
  const priceRangeStats = {
    under5000: filteredNewListings.filter(p => p.price < 5000).length,
    under10000: filteredNewListings.filter(p => p.price >= 5000 && p.price < 10000).length,
    under20000: filteredNewListings.filter(p => p.price >= 10000 && p.price < 20000).length,
    over20000: filteredNewListings.filter(p => p.price >= 20000).length,
  };

  return (
    <Container maxWidth="xl" sx={{ 
      py: 4, 
      px: isMobile ? 0 : 3  // スマートフォンでは左右余白をゼロに
    }}>
      {/* ヘッダー */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 'bold' }}>
          <UpdateIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
          物件更新情報
        </Typography>
        <Typography variant="body1" color="text.secondary">
          価格改定や新規掲載など、最新の物件更新情報を確認できます
        </Typography>
      </Box>

      {/* タブ */}
      <Paper sx={{ mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="物件更新タブ">
          <Tab 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <UpdateIcon />
                価格改定履歴
                <Chip label={filteredPriceChanges.length} size="small" color="primary" />
              </Box>
            } 
          />
          <Tab 
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <NewReleasesIcon />
                新規掲載物件
                <Chip label={filteredNewListings.length} size="small" color="success" />
              </Box>
            } 
          />
        </Tabs>
      </Paper>

      {/* フィルター */}
      <Paper sx={{ 
        p: isMobile ? 2 : 3, 
        mb: 3 
      }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>期間</InputLabel>
              <Select value={selectedHours} onChange={handleHoursChange} label="期間">
                <MenuItem value={24}>過去24時間</MenuItem>
                <MenuItem value={48}>過去48時間</MenuItem>
                <MenuItem value={72}>過去3日間</MenuItem>
                <MenuItem value={168}>過去1週間</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>エリア</InputLabel>
              <Select 
                value={selectedWard !== 'all' && !wards.includes(selectedWard) ? 'all' : selectedWard} 
                onChange={handleWardChange} 
                label="エリア"
              >
                <MenuItem value="all">すべて</MenuItem>
                {wards.map(ward => (
                  <MenuItem key={ward} value={ward}>{ward}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={fetchUpdates}
              disabled={loading}
              fullWidth
            >
              更新
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <ToggleButtonGroup
              value={viewMode}
              exclusive
              onChange={(e, newMode) => newMode && setViewMode(newMode)}
              size="small"
              fullWidth
            >
              <ToggleButton value="table" sx={{ whiteSpace: 'nowrap' }}>
                <TableChartIcon sx={{ mr: 0.5 }} />
                表
              </ToggleButton>
              <ToggleButton value="card" sx={{ whiteSpace: 'nowrap' }}>
                <ViewModuleIcon sx={{ mr: 0.5 }} />
                カード
              </ToggleButton>
            </ToggleButtonGroup>
          </Grid>
          <Grid item xs={12} sm={6} md={2} sx={{ display: 'flex', alignItems: 'center' }}>
            {lastScraperCompleted && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: { md: 2 } }}>
                最終更新: {new Date(lastScraperCompleted).toLocaleString('ja-JP', {
                  month: 'numeric',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                })}
              </Typography>
            )}
          </Grid>
        </Grid>
      </Paper>

      {/* 価格改定履歴タブ */}
      <TabPanel value={tabValue} index={0}>
        {/* 統計情報 */}
        <Grid container spacing={isMobile ? 1 : 2} sx={{ mb: isMobile ? 2 : 3 }}>
          <Grid item xs={4} md={4}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} sx={{ fontWeight: 'bold' }}>
                {filteredPriceChanges.filter(p => p.price_diff !== null && p.price_diff !== undefined).length}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary">
                価格改定物件数
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={4} md={4}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} color="primary" sx={{ fontWeight: 'bold' }}>
                {filteredPriceChanges.filter(p => p.price_diff && p.price_diff < 0).length}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary">
                値下げ物件
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={4} md={4}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} color="error" sx={{ fontWeight: 'bold' }}>
                {filteredPriceChanges.filter(p => p.price_diff && p.price_diff > 0).length}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary">
                値上げ物件
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* モバイル時のスクロールヒント */}
        {viewMode === 'table' && (
          <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              ← 左右にスクロールできます →
            </Typography>
          </Box>
        )}

        {/* テーブルまたはカード表示 */}
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : viewMode === 'table' ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 180, sm: 250 } }}>
                    <TableSortLabel
                      active={sortField === 'building_name'}
                      direction={sortField === 'building_name' ? sortOrder : 'desc'}
                      onClick={() => handleSort('building_name')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>建物名・部屋番号・エリア</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>建物名・エリア</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ pl: { xs: 0, sm: 0.5 }, pr: { xs: 0.5, sm: 0.5 }, minWidth: { xs: 25, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'floor_number'}
                      direction={sortField === 'floor_number' ? sortOrder : 'desc'}
                      onClick={() => handleSort('floor_number')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>階数</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>階</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 35, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'area'}
                      direction={sortField === 'area' ? sortOrder : 'desc'}
                      onClick={() => handleSort('area')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>専有面積</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>㎡</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 35, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'price'}
                      direction={sortField === 'price' ? sortOrder : 'desc'}
                      onClick={() => handleSort('price')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>現在価格</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>現在</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 35, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>前回価格</Box>
                    <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>前回</Box>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 45, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'price_diff'}
                      direction={sortField === 'price_diff' ? sortOrder : 'desc'}
                      onClick={() => handleSort('price_diff')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>変動幅・率</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>変動</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 40, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'layout'}
                      direction={sortField === 'layout' ? sortOrder : 'desc'}
                      onClick={() => handleSort('layout')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>間取り</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>間取</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 20, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'direction'}
                      direction={sortField === 'direction' ? sortOrder : 'desc'}
                      onClick={() => handleSort('direction')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>方角</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>向</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 20, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'built_year'}
                      direction={sortField === 'built_year' ? sortOrder : 'desc'}
                      onClick={() => handleSort('built_year')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>築年</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>築年</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 45, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'days_on_market'}
                      direction={sortField === 'days_on_market' ? sortOrder : 'desc'}
                      onClick={() => handleSort('days_on_market')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>経過日数</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>経過</Box>
                    </TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedData.map((property) => (
                  <TableRow 
                    key={`${property.id}-${property.changed_at || property.created_at}`}
                    hover
                    onClick={() => navigate(`/properties/${property.id}`)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell sx={{ px: { xs: 1, sm: 2 } }}>
                      <Box>
                        {property.building_name}
                        {property.room_number && ` ${property.room_number}号室`}
                        <Typography variant="caption" color="text.secondary" display="block">
                          {getWard(property.address)}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right" sx={{ pl: { xs: 0, sm: 0.5 }, pr: { xs: 0.5, sm: 0.5 }, whiteSpace: 'nowrap' }}>
                      {property.floor_number ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.floor_number}</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.floor_number}階</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      {property.area ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.area}</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.area}㎡</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      <Box sx={{ fontWeight: 'bold' }}>
                        {formatPrice(property.price, !isMobile)}
                      </Box>
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      {property.previous_price ? (
                        <Box sx={{ textDecoration: 'line-through', color: 'text.secondary' }}>
                          {formatPrice(property.previous_price, !isMobile)}
                        </Box>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 } }}>
                      {property.price_diff ? (
                        <Box>
                          <Chip
                            icon={property.price_diff < 0 ? <TrendingDownIcon /> : <TrendingUpIcon />}
                            label={`${property.price_diff > 0 ? '+' : ''}${property.price_diff.toLocaleString()}万${isMobile ? '' : '円'}`}
                            color={property.price_diff < 0 ? 'primary' : 'error'}
                            size="small"
                            sx={{ height: { xs: 20, sm: 'auto' }, fontSize: { xs: '0.65rem', sm: '0.75rem' }, '& .MuiChip-icon': { fontSize: { xs: '0.8rem', sm: '1rem' } }, mb: { xs: 0, sm: 0.5 } }}
                          />
                          {property.price_diff_rate && (
                            <Typography 
                              variant="caption" 
                              display="block"
                              color={property.price_diff_rate < 0 ? 'primary' : 'error'}
                              sx={{ fontSize: { xs: '0.6rem', sm: '0.75rem' }, fontWeight: 'bold', textAlign: 'center' }}
                            >
                              ({property.price_diff_rate > 0 ? '+' : ''}{property.price_diff_rate}%)
                            </Typography>
                          )}
                        </Box>
                      ) : '-'}
                    </TableCell>
                    <TableCell sx={{ px: { xs: 1, sm: 1 } }}>{property.layout || '-'}</TableCell>
                    <TableCell sx={{ px: { xs: 1, sm: 1 } }}>{property.direction || '-'}</TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      {property.built_year ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>築{new Date().getFullYear() - property.built_year}年</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>築{new Date().getFullYear() - property.built_year}年</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, whiteSpace: 'nowrap' }}>
                      {property.days_on_market !== null && property.days_on_market !== undefined ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.days_on_market}日</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.days_on_market}日</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Grid container spacing={isMobile ? 1 : 2}>
            {paginatedData.map((property) => (
              <Grid item xs={12} sm={6} md={4} key={`${property.id}-${property.changed_at || property.created_at}`}>
                <Card>
                  <CardActionArea onClick={() => navigate(`/properties/${property.id}`)}>
                    <CardContent>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="h6">
                          {property.building_name}
                          {property.room_number && ` ${property.room_number}号室`}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {getWard(property.address)}
                        </Typography>
                      </Box>

                    <Divider sx={{ my: 1 }} />

                    {/* 価格情報 */}
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" color="text.secondary">現在価格</Typography>
                        <Typography variant="h6" color="primary">
                          {formatPrice(property.price)}
                        </Typography>
                      </Box>
                      {property.previous_price && (
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="body2" color="text.secondary">前回価格</Typography>
                          <Typography variant="body2" sx={{ textDecoration: 'line-through', color: 'text.secondary' }}>
                            {formatPrice(property.previous_price)}
                          </Typography>
                        </Box>
                      )}
                    </Box>

                    {/* 価格変動 */}
                    {property.price_diff && (
                      <Box sx={{ mb: 2, textAlign: 'center' }}>
                        <Chip
                          icon={property.price_diff < 0 ? <TrendingDownIcon /> : <TrendingUpIcon />}
                          label={`${property.price_diff > 0 ? '+' : ''}${property.price_diff.toLocaleString()}万円`}
                          color={property.price_diff < 0 ? 'primary' : 'error'}
                          sx={{ mb: 0.5 }}
                        />
                        {property.price_diff_rate && (
                          <Typography 
                            variant="caption" 
                            display="block"
                            color={property.price_diff_rate < 0 ? 'primary' : 'error'}
                            sx={{ fontWeight: 'bold' }}
                          >
                            ({property.price_diff_rate > 0 ? '+' : ''}{property.price_diff_rate}%)
                          </Typography>
                        )}
                      </Box>
                    )}

                    <Divider sx={{ my: 1 }} />

                    {/* 物件詳細 */}
                    <Grid container spacing={1}>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">階数</Typography>
                        <Typography variant="body2">{property.floor_number ? `${property.floor_number}階` : '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">面積</Typography>
                        <Typography variant="body2">{property.area ? `${property.area}㎡` : '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">間取り</Typography>
                        <Typography variant="body2">{property.layout || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">方角</Typography>
                        <Typography variant="body2">{property.direction || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">築年</Typography>
                        <Typography variant="body2">{property.built_year ? `${property.built_year}年` : '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">経過日数</Typography>
                        <Typography variant="body2">{property.days_on_market !== null && property.days_on_market !== undefined ? `${property.days_on_market}日` : '-'}</Typography>
                      </Grid>
                    </Grid>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </TabPanel>

      {/* 新規掲載物件タブ */}
      <TabPanel value={tabValue} index={1}>
        {/* 統計情報 */}
        <Grid container spacing={isMobile ? 1 : 2} sx={{ mb: isMobile ? 2 : 3 }}>
          <Grid item xs={3} md={3}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} sx={{ fontWeight: 'bold' }}>
                {filteredNewListings.length}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary" sx={{ fontSize: isMobile ? '0.6rem' : 'inherit' }}>
                新規掲載物件
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={3} md={3}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} sx={{ fontWeight: 'bold' }}>
                {priceRangeStats.under5000}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary" sx={{ fontSize: isMobile ? '0.6rem' : 'inherit' }}>
                5,000万円未満
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={3} md={3}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} sx={{ fontWeight: 'bold' }}>
                {priceRangeStats.under10000}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary" sx={{ fontSize: isMobile ? '0.6rem' : 'inherit', lineHeight: isMobile ? 1.2 : 'inherit' }}>
                {isMobile ? '5千万〜1億' : '5,000万円〜1億円'}
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={3} md={3}>
            <Paper sx={{ 
              p: isMobile ? 1 : 2, 
              textAlign: 'center' 
            }}>
              <Typography variant={isMobile ? "body1" : "h6"} sx={{ fontWeight: 'bold' }}>
                {priceRangeStats.over20000}
              </Typography>
              <Typography variant={isMobile ? "caption" : "body2"} color="text.secondary" sx={{ fontSize: isMobile ? '0.6rem' : 'inherit' }}>
                {isMobile ? '2億円以上' : '2億円以上'}
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* モバイル時のスクロールヒント */}
        {viewMode === 'table' && (
          <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 1 }}>
            <Typography variant="caption" color="text.secondary">
              ← 左右にスクロールできます →
            </Typography>
          </Box>
        )}

        {/* テーブルまたはカード表示 */}
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : viewMode === 'table' ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 180, sm: 250 } }}>
                    <TableSortLabel
                      active={sortField === 'building_name'}
                      direction={sortField === 'building_name' ? sortOrder : 'desc'}
                      onClick={() => handleSort('building_name')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>建物名・部屋番号・エリア</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>建物名・エリア</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ pl: { xs: 0, sm: 0.5 }, pr: { xs: 0.5, sm: 0.5 }, minWidth: { xs: 25, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'floor_number'}
                      direction={sortField === 'floor_number' ? sortOrder : 'desc'}
                      onClick={() => handleSort('floor_number')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>階数</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>階</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 35, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'area'}
                      direction={sortField === 'area' ? sortOrder : 'desc'}
                      onClick={() => handleSort('area')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>専有面積</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>㎡</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 35, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'price'}
                      direction={sortField === 'price' ? sortOrder : 'desc'}
                      onClick={() => handleSort('price')}
                    >
                      価格
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 40, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'layout'}
                      direction={sortField === 'layout' ? sortOrder : 'desc'}
                      onClick={() => handleSort('layout')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>間取り</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>間取</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 20, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'direction'}
                      direction={sortField === 'direction' ? sortOrder : 'desc'}
                      onClick={() => handleSort('direction')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>方角</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>向</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, minWidth: { xs: 20, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'built_year'}
                      direction={sortField === 'built_year' ? sortOrder : 'desc'}
                      onClick={() => handleSort('built_year')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>築年</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>築年</Box>
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 45, sm: 'auto' }, whiteSpace: 'nowrap' }}>
                    <TableSortLabel
                      active={sortField === 'created_at'}
                      direction={sortField === 'created_at' ? sortOrder : 'desc'}
                      onClick={() => handleSort('created_at')}
                    >
                      <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>掲載日</Box>
                      <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>掲載</Box>
                    </TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {paginatedData.map((property) => (
                  <TableRow 
                    key={`${property.id}-${property.created_at}`}
                    hover
                    onClick={() => navigate(`/properties/${property.id}`)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell sx={{ px: { xs: 1, sm: 2 } }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.5, sm: 1 } }}>
                        <Typography 
                          component="span"
                          sx={{
                            backgroundColor: theme.palette.success.main,
                            color: 'white',
                            px: 0.5,
                            py: 0.1,
                            borderRadius: 0.5,
                            fontSize: { xs: '0.6rem', sm: '0.7rem' },
                            fontWeight: 'bold',
                            display: 'inline-block',
                            lineHeight: 1.2,
                            minWidth: 28
                          }}
                        >
                          NEW
                        </Typography>
                        <Box>
                          {property.building_name}
                          {property.room_number && ` ${property.room_number}号室`}
                          <Typography variant="caption" color="text.secondary" display="block">
                            {getWard(property.address)}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell align="right" sx={{ pl: { xs: 0, sm: 0.5 }, pr: { xs: 0.5, sm: 0.5 }, whiteSpace: 'nowrap' }}>
                      {property.floor_number ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.floor_number}</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.floor_number}階</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      {property.area ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.area}</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.area}㎡</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      <Box sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                        {formatPrice(property.price, !isMobile)}
                      </Box>
                    </TableCell>
                    <TableCell sx={{ px: { xs: 1, sm: 1 } }}>{property.layout || '-'}</TableCell>
                    <TableCell sx={{ px: { xs: 1, sm: 1 } }}>{property.direction || '-'}</TableCell>
                    <TableCell align="right" sx={{ px: { xs: 1, sm: 1 }, whiteSpace: 'nowrap' }}>
                      {property.built_year ? (
                        <>
                          <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>築{new Date().getFullYear() - property.built_year}年</Box>
                          <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>築{new Date().getFullYear() - property.built_year}年</Box>
                        </>
                      ) : '-'}
                    </TableCell>
                    <TableCell sx={{ px: { xs: 1, sm: 2 } }}>{formatDate(property.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Grid container spacing={isMobile ? 1 : 2}>
            {paginatedData.map((property) => (
              <Grid item xs={12} sm={6} md={4} key={`${property.id}-${property.created_at}`}>
                <Card>
                  <CardActionArea onClick={() => navigate(`/properties/${property.id}`)}>
                    <CardContent>
                      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip
                          icon={<NewReleasesIcon />}
                          label="NEW"
                          color="success"
                          size="small"
                        />
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="h6">
                            {property.building_name}
                            {property.room_number && ` ${property.room_number}号室`}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {getWard(property.address)}
                          </Typography>
                        </Box>
                      </Box>

                    <Divider sx={{ my: 1 }} />

                    {/* 価格情報 */}
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2" color="text.secondary">価格</Typography>
                        <Typography variant="h6" color="success.main">
                          {formatPrice(property.price)}
                        </Typography>
                      </Box>
                    </Box>

                    <Divider sx={{ my: 1 }} />

                    {/* 物件詳細 */}
                    <Grid container spacing={1}>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">階数</Typography>
                        <Typography variant="body2">{property.floor_number ? `${property.floor_number}階` : '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">面積</Typography>
                        <Typography variant="body2">{property.area ? `${property.area}㎡` : '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">間取り</Typography>
                        <Typography variant="body2">{property.layout || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">方角</Typography>
                        <Typography variant="body2">{property.direction || '-'}</Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">築年</Typography>
                        <Typography variant="body2">
                          {property.built_year ? `築${new Date().getFullYear() - property.built_year}年` : '-'}
                        </Typography>
                      </Grid>
                      <Grid item xs={6}>
                        <Typography variant="caption" color="text.secondary">掲載日</Typography>
                        <Typography variant="body2">{formatDate(property.created_at)}</Typography>
                      </Grid>
                    </Grid>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </TabPanel>

      {/* ページネーション（共通） */}
      {!loading && (
        <TablePagination
          rowsPerPageOptions={[25, 50, 100]}
          component="div"
          count={sortedData.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          labelRowsPerPage="表示件数:"
          labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}件`}
        />
      )}


    </Container>
  );
};

export default PropertyUpdatesPage;