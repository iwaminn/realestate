import React, { useEffect, useState } from 'react';
import { useParams, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Card,
  CardContent,
  Grid,
  Box,
  Chip,
  CircularProgress,
  Alert,
  Paper,
  Divider,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  ToggleButton,
  ToggleButtonGroup,
  FormControlLabel,
  Checkbox,
  Tooltip,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { 
  Apartment as ApartmentIcon,
  Home as HomeIcon,
  Square as SquareIcon,
  Stairs as StairsIcon,
  Explore as ExploreIcon,
  ArrowBack as ArrowBackIcon,
  TableChart as TableChartIcon,
  ViewModule as ViewModuleIcon,
  Cached as CachedIcon
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';
import { Property } from '../types/property';

interface BuildingStats {
  total_units: number;
  price_range: {
    min: number;
    max: number;
    avg: number;
  };
  area_range: {
    min: number;
    max: number;
  };
  total_floors: number | null;
  avg_price_per_tsubo?: number;
}

type ViewMode = 'card' | 'table';
type OrderBy = 'earliest_published_at' | 'floor_number' | 'area' | 'min_price' | 'layout' | 'direction' | 'price_per_tsubo';
type Order = 'asc' | 'desc';

const BuildingPropertiesPage: React.FC = () => {
  const { buildingId } = useParams<{ buildingId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
const [properties, setProperties] = useState<Property[]>([]);
  const [building, setBuilding] = useState<any | null>(null);
  const [stats, setStats] = useState<BuildingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [maxFloorFromProperties, setMaxFloorFromProperties] = useState<number | null>(null);
  
  // URLパラメータから各種設定を取得
  const getParamsFromUrl = () => {
    const urlParams = new URLSearchParams(location.search);
    return {
      includeInactive: urlParams.get('includeInactive') === 'true',
      viewMode: (urlParams.get('viewMode') as ViewMode) || 'table',
      orderBy: (urlParams.get('orderBy') as OrderBy) || 'earliest_published_at',
      order: (urlParams.get('order') as Order) || 'desc'
    };
  };
  
  const initialParams = getParamsFromUrl();
  const [viewMode, setViewMode] = useState<ViewMode>(initialParams.viewMode);
  const [orderBy, setOrderBy] = useState<OrderBy>(initialParams.orderBy);
  const [order, setOrder] = useState<Order>(initialParams.order);
  const [includeInactive, setIncludeInactive] = useState(initialParams.includeInactive);
  
  // URLパラメータを更新する関数
  const updateUrlParams = (updates: Partial<{includeInactive: boolean, viewMode: ViewMode, orderBy: OrderBy, order: Order}>) => {
    const searchParams = new URLSearchParams(location.search);
    
    if (updates.includeInactive !== undefined) {
      if (updates.includeInactive) {
        searchParams.set('includeInactive', 'true');
      } else {
        searchParams.delete('includeInactive');
      }
    }
    
    if (updates.viewMode !== undefined) {
      searchParams.set('viewMode', updates.viewMode);
    }
    
    if (updates.orderBy !== undefined) {
      searchParams.set('orderBy', updates.orderBy);
    }
    
    if (updates.order !== undefined) {
      searchParams.set('order', updates.order);
    }
    
    navigate(`${location.pathname}?${searchParams.toString()}`, { replace: true });
  };

  useEffect(() => {
  if (buildingId) {
      fetchBuildingProperties();
    }
  }, [buildingId, includeInactive]);

  // URLパラメータが変更された時の処理
  useEffect(() => {
    const params = getParamsFromUrl();
    setIncludeInactive(params.includeInactive);
    setViewMode(params.viewMode);
    setOrderBy(params.orderBy);
    setOrder(params.order);
  }, [location.search]);

  const fetchBuildingProperties = async () => {
    try {
      setLoading(true);
      // 建物IDで物件を取得
      const response = await propertyApi.getBuildingProperties(parseInt(buildingId!), includeInactive);
      
      setProperties(response.properties);
      setBuilding(response.building);
      

      
      // 統計情報を計算
      if (response.properties.length > 0) {
        const prices = response.properties
          .map(p => p.min_price)
          .filter((p): p is number => p !== undefined && p !== null);
        const areas = response.properties
          .map(p => p.area)
          .filter((a): a is number => a !== undefined && a !== null);
        
        // 物件の階数情報から最大階数を計算
        const floors = response.properties
          .map(p => p.floor_number)
          .filter((f): f is number => f !== undefined && f !== null);
        const maxFloor = floors.length > 0 ? Math.max(...floors) : null;
        setMaxFloorFromProperties(maxFloor);
        
      if (prices.length > 0 && areas.length > 0) {
          // 各物件の坪単価を計算
          const pricePerTsubos = response.properties
            .filter(p => {
              const price = p.sold_at && p.last_sale_price 
                ? p.last_sale_price 
                : (p.majority_price || p.min_price);
              return price && p.area;
            })
            .map(p => {
              const price = p.sold_at && p.last_sale_price 
                ? p.last_sale_price 
                : (p.majority_price || p.min_price);
              const tsubo = (p.area || 0) / 3.30578;
              return tsubo > 0 && price ? price / tsubo : 0;
            });
          
          const avgPricePerTsubo = pricePerTsubos.length > 0
            ? pricePerTsubos.reduce((a, b) => a + b, 0) / pricePerTsubos.length
            : 0;
          
          setStats({
            total_units: response.properties.length,
            price_range: {
              min: Math.min(...prices),
              max: Math.max(...prices),
              avg: prices.reduce((a, b) => a + b, 0) / prices.length
            },
            area_range: {
              min: Math.min(...areas),
              max: Math.max(...areas)
            },
            total_floors: response.building.total_floors,
            avg_price_per_tsubo: avgPricePerTsubo
          });
        } else {
          // 価格や面積情報がない場合でも建物情報は表示
          setStats({
            total_units: response.properties.length,
            price_range: {
              min: 0,
              max: 0,
              avg: 0
            },
            area_range: {
              min: 0,
              max: 0
            },
            total_floors: response.building.total_floors,
            avg_price_per_tsubo: 0
          });
        }
      }
    } catch (err: any) {
      console.error('[BuildingPropertiesPage] Error:', err);
      const errorMessage = err.response?.data?.detail || err.message || '建物の物件情報の取得に失敗しました';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const getSourceColor = (source: string) => {
    switch (source.toLowerCase()) {
      case 'suumo': return '#0a9048';
      case 'athome': return '#ff6600';
      case 'homes': return '#0066cc';
      default: return '#666';
    }
  };

  const formatPrice = (price: number | undefined) => {
    if (!price) return '価格未定';
    
    // 1億円以上の場合
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      
      if (man === 0) {
        // ちょうど億の場合
        return `${oku}億円`;
      } else {
        // 億と万の組み合わせ
        return `${oku}億${man.toLocaleString()}万円`;
      }
    }
    
    // 1億円未満の場合
    return `${price.toLocaleString()}万円`;
  };

  const calculatePricePerTsubo = (price: number | undefined, area: number | undefined): string => {
    if (!price || !area) return '-';
    
    // 坪数に変換（1坪 = 3.30578㎡）
    const tsubo = area / 3.30578;
    // 坪単価を計算
    const pricePerTsubo = price / tsubo;
    
    return `${pricePerTsubo.toFixed(0)}万円/坪`;
  };

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
  };

  const calculateDaysFromPublished = (dateString: string | undefined): string => {
    if (!dateString) return '-';
    
    const publishedDate = new Date(dateString);
    const today = new Date();
    
    // 日付のみで比較（時刻を00:00:00にリセット）
    publishedDate.setHours(0, 0, 0, 0);
    today.setHours(0, 0, 0, 0);
    
    const diffTime = Math.abs(today.getTime() - publishedDate.getTime());
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      return '本日';
    } else if (diffDays === 1) {
      return '1日前';
    } else if (diffDays < 7) {
      return `${diffDays}日前`;
    } else if (diffDays < 30) {
      const weeks = Math.floor(diffDays / 7);
      return `${weeks}週間前`;
    } else if (diffDays < 365) {
      const months = Math.floor(diffDays / 30);
      return `${months}ヶ月前`;
    } else {
      const years = Math.floor(diffDays / 365);
      const remainingMonths = Math.floor((diffDays % 365) / 30);
      if (remainingMonths > 0) {
        return `${years}年${remainingMonths}ヶ月前`;
      }
      return `${years}年前`;
    }
  };

  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc';
    const newOrder = isAsc ? 'desc' : 'asc';
    setOrder(newOrder);
    setOrderBy(property);
    updateUrlParams({ orderBy: property, order: newOrder });
  };

  const sortedProperties = React.useMemo(() => {
    return [...properties].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      switch (orderBy) {
        case 'earliest_published_at':
          aValue = a.earliest_published_at || '';
          bValue = b.earliest_published_at || '';
          break;
        case 'floor_number':
          aValue = a.floor_number || 0;
          bValue = b.floor_number || 0;
          break;
        case 'area':
          aValue = a.area || 0;
          bValue = b.area || 0;
          break;
        case 'min_price':
          aValue = a.min_price || 0;
          bValue = b.min_price || 0;
          break;
        case 'layout':
          aValue = a.layout || '';
          bValue = b.layout || '';
          break;
        case 'direction':
          aValue = a.direction || '';
          bValue = b.direction || '';
          break;
        case 'price_per_tsubo':
          // 坪単価を計算（価格 / (面積 / 3.30578)）
          const aPrice = a.majority_price || a.min_price || 0;
          const bPrice = b.majority_price || b.min_price || 0;
          aValue = (a.area && aPrice) ? aPrice / (a.area / 3.30578) : 0;
          bValue = (b.area && bPrice) ? bPrice / (b.area / 3.30578) : 0;
          break;
        default:
          return 0;
      }

      if (order === 'desc') {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      } else {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      }
    });
  }, [properties, orderBy, order]);

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ 
        py: 4, 
        px: isMobile ? 1 : 3
      }}>
        <Box display="flex" justifyContent="center">
          <CircularProgress />
        </Box>
      </Container>
    );
  }
  
  if (error) {
    return (
      <Container maxWidth="xl" sx={{ 
        py: 4, 
        px: isMobile ? 1 : 3
      }}>
        <Alert severity="error">{error}</Alert>
      </Container>
    );
  }
  
  if (!building) {
    return (
      <Container maxWidth="xl" sx={{ 
        py: 4, 
        px: isMobile ? 1 : 3
      }}>
        <Alert severity="info">
          建物情報が見つかりません
        </Alert>
        <Button
          component={Link}
          to="/"
          startIcon={<ArrowBackIcon />}
          sx={{ mt: 2 }}
        >
          物件一覧に戻る
        </Button>
      </Container>
    );
  }
  
  if (!properties.length) {
    return (
      <Container maxWidth="xl" sx={{ 
        py: 4, 
        px: isMobile ? 1 : 3
      }}>
        <Alert severity="info">
          物件が見つかりません
          {!includeInactive && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2">
                販売終了物件を表示する場合は、URLに「?includeInactive=true」を追加してください。
              </Typography>
            </Box>
          )}
        </Alert>
        <Button
          component={Link}
          to="/"
          startIcon={<ArrowBackIcon />}
          sx={{ mt: 2 }}
        >
          物件一覧に戻る
        </Button>
      </Container>
    );
  }

  const buildingInfo = building;

  return (
    <Container maxWidth="xl" sx={{ 
      py: 4, 
      px: isMobile ? 1 : 3
    }}>
      <Button
        component={Link}
        to="/"
        startIcon={<ArrowBackIcon />}
        sx={{ mb: 2 }}
      >
        物件一覧に戻る
      </Button>

      <Typography variant="h4" gutterBottom>
        <ApartmentIcon sx={{ mr: 1, verticalAlign: 'bottom' }} />
        {buildingInfo.normalized_name}
      </Typography>

      {/* 建物の基本情報 */}
      {building && (
        <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  築年月
                </Typography>
                <Typography variant="h6">
                  {building.built_year ? (
                    <>
                      {building.built_year}年{building.built_month ? `${building.built_month}月` : ''}
                      <Typography component="span" variant="body1" color="text.secondary" sx={{ ml: 1 }}>
                        （築{new Date().getFullYear() - building.built_year}年）
                      </Typography>
                    </>
                  ) : '不明'}
                </Typography>
              </Box>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  総戸数
                </Typography>
                <Typography variant="h6">
                  {building.total_units ? `${building.total_units}戸` : '-'}
                </Typography>
              </Box>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  総階数
                </Typography>
                <Typography variant="h6">
                  {building.total_floors ? `${building.total_floors}階` : maxFloorFromProperties ? `${maxFloorFromProperties}階以上` : '-'}
                </Typography>
              </Box>
            </Grid>
            
            <Grid item xs={12} sm={6} md={3}>
              <Box>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  所在地
                </Typography>
                <Box sx={{ 
                  display: 'flex', 
                  flexDirection: 'column',
                  gap: 1
                }}>
                  <Typography variant="h6">
                    {building.address || '不明'}
                  </Typography>
                  {/* 住所に「号」まで含まれている場合、Google Mapsへのリンクを表示 */}
                  {building.address && building.address.match(/\d+-\d+-\d+|\d+号/) && (
                    <Box
                      component="a"
                      href={`https://www.google.com/maps/search/${encodeURIComponent(building.address)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        border: '1px solid #dadce0',
                        textDecoration: 'none',
                        backgroundColor: 'white',
                        transition: 'all 0.2s',
                        width: 'fit-content',
                        '&:hover': {
                          backgroundColor: '#f1f3f4',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
                        }
                      }}
                    >
                      {/* Google Maps公式アイコン */}
                      <Box
                        component="img"
                        src="https://www.gstatic.com/images/branding/product/1x/maps_24dp.png"
                        alt="Google Maps"
                        sx={{
                          width: 18,
                          height: 18,
                          mr: 0.75
                        }}
                      />
                      <Typography
                        variant="body2"
                        sx={{
                          fontSize: '0.8125rem',
                          color: '#1a73e8',
                          fontWeight: 500
                        }}
                      >
                        Google Mapsで表示
                      </Typography>
                    </Box>
                  )}
                </Box>
              </Box>
            </Grid>

          </Grid>
        </Paper>
      )}

      {/* 販売状況 */}
      {stats && (
        <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
          <Typography variant="h6" gutterBottom>販売状況</Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="h3" color="primary">
                  {stats.avg_price_per_tsubo 
                    ? Math.round(stats.avg_price_per_tsubo).toLocaleString()
                    : '-'}
                </Typography>
                <Typography variant="body1" color="text.secondary">
                  平均坪単価（万円）
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="h3" color="primary">
                  {stats.total_units}
                </Typography>
                <Typography variant="body1" color="text.secondary">
                  販売中の戸数
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                {stats.price_range.min === stats.price_range.max ? (
                  <Typography variant="h3" color="primary">
                    {formatPrice(stats.price_range.min)}
                  </Typography>
                ) : (
                  <>
                    <Typography variant="h5" color="primary">
                      {formatPrice(stats.price_range.min)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      〜
                    </Typography>
                    <Typography variant="h5" color="primary">
                      {formatPrice(stats.price_range.max)}
                    </Typography>
                  </>
                )}
                <Typography variant="body1" color="text.secondary">
                  価格{stats.price_range.min === stats.price_range.max ? '' : '帯'}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                {stats.area_range.min === stats.area_range.max ? (
                  <Typography variant="h3" color="primary">
                    {stats.area_range.min.toFixed(1)}
                  </Typography>
                ) : (
                  <>
                    <Typography variant="h5" color="primary">
                      {stats.area_range.min.toFixed(1)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      〜
                    </Typography>
                    <Typography variant="h5" color="primary">
                      {stats.area_range.max.toFixed(1)}
                    </Typography>
                  </>
                )}
                <Typography variant="body1" color="text.secondary">
                  専有面積（㎡）
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* 表示モード切替と物件一覧タイトル */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ 
          display: 'flex', 
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between', 
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: { xs: 2, sm: 0 },
          mb: 2 
        }}>
          <Typography variant="h5">
            {includeInactive ? '全物件' : '販売中の物件'} ({properties.length}件)
          </Typography>
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={(_, newMode) => {
              if (newMode) {
                setViewMode(newMode);
                updateUrlParams({ viewMode: newMode });
              }
            }}
            aria-label="表示モード"
            sx={{ 
              flexShrink: 0,
              '& .MuiToggleButton-root': {
                minWidth: { xs: 90, sm: 'auto' },
                whiteSpace: 'nowrap',
                fontSize: { xs: '0.875rem', sm: '0.875rem' },
                px: { xs: 1.5, sm: 2 },
                py: { xs: 1, sm: 1 }
              }
            }}
          >
            <ToggleButton value="table" aria-label="表形式">
              <TableChartIcon sx={{ mr: 0.5, fontSize: { xs: '1rem', sm: '1.25rem' } }} />
              表形式
            </ToggleButton>
            <ToggleButton value="card" aria-label="カード形式">
              <ViewModuleIcon sx={{ mr: 0.5, fontSize: { xs: '1rem', sm: '1.25rem' } }} />
              カード形式
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <FormControlLabel
          control={
            <Checkbox
              checked={includeInactive}
              onChange={(e) => {
                const newValue = e.target.checked;
                setIncludeInactive(newValue);
                updateUrlParams({ includeInactive: newValue });
              }}
            />
          }
          label="販売終了物件を含む"
        />
      </Box>

      {/* モバイル時のスクロールヒント */}
      <Box sx={{ display: { xs: 'block', md: 'none' }, mb: 1 }}>
        <Typography variant="caption" color="text.secondary">
          ← 左右にスクロールできます →
        </Typography>
      </Box>

      {viewMode === 'table' ? (
        <TableContainer 
          component={Paper} 
          sx={{ 
            overflowX: 'auto',
            // スクロールバーのスタイリング
            '&::-webkit-scrollbar': {
              height: 8,
              width: 8,
            },
            '&::-webkit-scrollbar-track': {
              backgroundColor: '#f1f1f1',
            },
            '&::-webkit-scrollbar-thumb': {
              backgroundColor: '#888',
              borderRadius: 4,
            },
            '&::-webkit-scrollbar-thumb:hover': {
              backgroundColor: '#555',
            },
            // モバイルでスクロール可能であることを示す影
            '@media (max-width: 900px)': {
              boxShadow: 'inset -1px 0 0 0 rgba(0,0,0,0.1)',
            }
          }}
        >
          <Table sx={{ minWidth: { xs: 800, md: 'auto' } }}>
            <TableHead sx={{
              position: 'sticky',
              top: 0,
              backgroundColor: 'background.paper',
              zIndex: 2,
              '& th': {
                backgroundColor: 'background.paper',
                fontWeight: 'bold'
              }
            }}>
              <TableRow>
                <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 50, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'floor_number'}
                    direction={orderBy === 'floor_number' ? order : 'asc'}
                    onClick={() => handleRequestSort('floor_number')}
                  >
                    <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>階数</Box>
                    <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>階</Box>
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 60, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'area'}
                    direction={orderBy === 'area' ? order : 'asc'}
                    onClick={() => handleRequestSort('area')}
                  >
                    <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>専有面積</Box>
                    <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>面積</Box>
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 60, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'layout'}
                    direction={orderBy === 'layout' ? order : 'asc'}
                    onClick={() => handleRequestSort('layout')}
                  >
                    間取り
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 50, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'direction'}
                    direction={orderBy === 'direction' ? order : 'asc'}
                    onClick={() => handleRequestSort('direction')}
                  >
                    方角
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 70, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'min_price'}
                    direction={orderBy === 'min_price' ? order : 'asc'}
                    onClick={() => handleRequestSort('min_price')}
                  >
                    価格
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 80, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'price_per_tsubo'}
                    direction={orderBy === 'price_per_tsubo' ? order : 'asc'}
                    onClick={() => handleRequestSort('price_per_tsubo')}
                  >
                    坪単価
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 120, sm: 'auto' } }}>
                  <TableSortLabel
                    active={orderBy === 'earliest_published_at'}
                    direction={orderBy === 'earliest_published_at' ? order : 'asc'}
                    onClick={() => handleRequestSort('earliest_published_at')}
                  >
                    <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>売出確認日</Box>
                    <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>売出日</Box>
                  </TableSortLabel>
                </TableCell>
                {includeInactive && <TableCell sx={{ px: { xs: 1, sm: 2 } }}>販売終了日</TableCell>}
                <TableCell sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 50, sm: 'auto' } }}>
                  <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>掲載情報</Box>
                  <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>掲載</Box>
                </TableCell>
                <TableCell align="center" sx={{ px: { xs: 1, sm: 2 }, minWidth: { xs: 50, sm: 'auto' } }}>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedProperties.map((property) => (
                <TableRow key={property.id} hover sx={{ opacity: property.sold_at ? 0.7 : 1 }}>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' } }}>
                    <Box display="flex" alignItems="center" justifyContent="flex-end" flexWrap="nowrap">
                      {property.sold_at && (
                        <Chip
                          label="終"
                          size="small"
                          sx={{ 
                            mr: 0.5,
                            backgroundColor: '#d32f2f',
                            color: 'white',
                            fontWeight: 'bold',
                            fontSize: { xs: '0.7rem', sm: '0.75rem' },
                            height: { xs: 18, sm: 24 },
                            display: { xs: 'inline-flex', sm: 'none' }
                          }}
                        />
                      )}
                      {property.sold_at && (
                        <Chip
                          label="販売終了"
                          size="small"
                          sx={{ 
                            mr: 0.5,
                            backgroundColor: '#d32f2f',
                            color: 'white',
                            fontWeight: 'bold',
                            display: { xs: 'none', sm: 'inline-flex' }
                          }}
                        />
                      )}
                      {property.is_resale && (
                        <CachedIcon sx={{ fontSize: { xs: 16, sm: 20 }, color: 'warning.main', mr: 0.5 }} />
                      )}
                      <Box component="span" sx={{ whiteSpace: 'nowrap' }}>
                        {property.floor_number ? `${property.floor_number}階` : '-'}
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' }, whiteSpace: 'nowrap' }}>
                    {property.area ? `${property.area}㎡` : '-'}
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' }, whiteSpace: 'nowrap' }}>{property.layout || '-'}</TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' }, whiteSpace: 'nowrap' }}>
                    <Box sx={{ display: { xs: 'none', sm: 'inline' } }}>{property.direction ? `${property.direction}向き` : '-'}</Box>
                    <Box sx={{ display: { xs: 'inline', sm: 'none' } }}>{property.direction || '-'}</Box>
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' } }}>
                    <Box sx={{ whiteSpace: 'nowrap' }}>
                      {property.sold_at && property.last_sale_price
                        ? formatPrice(property.last_sale_price)
                        : formatPrice(property.majority_price || property.min_price)}
                    </Box>
                    {property.sold_at && property.last_sale_price && (
                      <Box sx={{ fontSize: '0.7rem', color: 'text.secondary', display: { xs: 'none', sm: 'block' } }}>
                        （販売終了時）
                      </Box>
                    )}
                  </TableCell>
                  <TableCell align="right" sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' }, whiteSpace: 'nowrap' }}>
                    {property.sold_at && property.last_sale_price
                      ? calculatePricePerTsubo(property.last_sale_price, property.area)
                      : calculatePricePerTsubo(property.majority_price || property.min_price, property.area)}
                  </TableCell>
                  <TableCell sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' } }}>
                    <Box sx={{ whiteSpace: 'nowrap' }}>
                      {formatDate(property.earliest_published_at)}
                    </Box>
                    {property.earliest_published_at && (
                      <Box component="span" sx={{ fontSize: '0.75rem', color: 'text.secondary', ml: 0.5, whiteSpace: 'nowrap' }}>
                        ({calculateDaysFromPublished(property.earliest_published_at)})
                      </Box>
                    )}
                  </TableCell>
                  {includeInactive && (
                    <TableCell sx={{ px: { xs: 1, sm: 2 }, fontSize: { xs: '0.85rem', sm: '0.875rem' }, whiteSpace: 'nowrap' }}>
                      {property.sold_at ? formatDate(property.sold_at) : '-'}
                    </TableCell>
                  )}
                  <TableCell sx={{ px: { xs: 1, sm: 2 } }}>
                    <Tooltip 
                      title={
                        <Box>
                          {property.source_sites.map((site) => (
                            <Box key={site} sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                              <Box 
                                sx={{ 
                                  width: 8, 
                                  height: 8, 
                                  borderRadius: '50%',
                                  backgroundColor: getSourceColor(site),
                                  mr: 1
                                }} 
                              />
                              <Typography variant="body2">{site}</Typography>
                            </Box>
                          ))}
                        </Box>
                      }
                      arrow
                      placement="left"
                    >
                      <Chip
                        label={`${property.listing_count || property.source_sites.length}件`}
                        size="small"
                        variant="outlined"
                        sx={{ 
                          cursor: 'pointer',
                          fontSize: { xs: '0.7rem', sm: '0.75rem' },
                          height: { xs: 20, sm: 24 }
                        }}
                      />
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ px: { xs: 1, sm: 2 } }}>
                    <Button
                      component={Link}
                      to={`/properties/${property.id}`}
                      variant="outlined"
                      size="small"
                      sx={{
                        fontSize: { xs: '0.7rem', sm: '0.875rem' },
                        px: { xs: 1, sm: 2 },
                        py: { xs: 0.5, sm: 1 },
                        minWidth: { xs: 40, sm: 64 }
                      }}
                    >
                      詳細
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : (
        <Grid container spacing={3}>
          {sortedProperties.map((property) => (
            <Grid item xs={12} md={6} key={property.id}>
              <Card>
                <CardContent>
                  <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                    <Box display="flex" alignItems="center">
                      <Typography variant="h6" component="div">
                        {property.floor_number ? `${property.floor_number}階` : '物件'}
                      </Typography>
                      {property.sold_at && (
                        <Chip
                          label="販売終了"
                          size="small"
                          color="error"
                          sx={{ ml: 1 }}
                        />
                      )}
                      {property.is_resale && (
                        <Chip
                          icon={<CachedIcon />}
                          label="買い取り再販"
                          size="small"
                          color="warning"
                          sx={{ ml: 1 }}
                        />
                      )}
                    </Box>
                    <Tooltip 
                      title={
                        <Box>
                          {property.source_sites.map((site) => (
                            <Box key={site} sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                              <Box 
                                sx={{ 
                                  width: 8, 
                                  height: 8, 
                                  borderRadius: '50%',
                                  backgroundColor: getSourceColor(site),
                                  mr: 1
                                }} 
                              />
                              <Typography variant="body2">{site}</Typography>
                            </Box>
                          ))}
                        </Box>
                      }
                      arrow
                      placement="left"
                    >
                      <Chip
                        label={`掲載${property.listing_count || property.source_sites.length}件`}
                        size="small"
                        variant="outlined"
                        sx={{ cursor: 'pointer' }}
                      />
                    </Tooltip>
                  </Box>

                  <Box sx={{ mt: 2, mb: 2 }}>
                    <Typography variant="h5" color={property.sold_at ? "text.secondary" : "primary"}>
                      {property.sold_at && property.last_sale_price
                        ? formatPrice(property.last_sale_price)
                        : formatPrice(property.majority_price || property.min_price)}
                    </Typography>
                    {property.sold_at && property.last_sale_price && (
                      <Typography variant="body2" color="text.secondary">
                        （販売終了時）
                      </Typography>
                    )}
                    <Typography variant="body1" color="text.secondary" sx={{ mt: 0.5 }}>
                      坪単価: {property.sold_at && property.last_sale_price
                        ? calculatePricePerTsubo(property.last_sale_price, property.area)
                        : calculatePricePerTsubo(property.majority_price || property.min_price, property.area)}
                    </Typography>
                  </Box>

                  <Grid container spacing={2}>
                    {property.layout && (
                      <Grid item xs={6}>
                        <Box display="flex" alignItems="center">
                          <HomeIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="body2">{property.layout}</Typography>
                        </Box>
                      </Grid>
                    )}
                    {property.area && (
                      <Grid item xs={6}>
                        <Box display="flex" alignItems="center">
                          <SquareIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="body2">{property.area}㎡</Typography>
                        </Box>
                      </Grid>
                    )}
                    {property.floor_number && (
                      <Grid item xs={6}>
                        <Box display="flex" alignItems="center">
                          <StairsIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="body2">
                            {property.floor_number}階
                          </Typography>
                        </Box>
                      </Grid>
                    )}
                    {property.direction && (
                      <Grid item xs={6}>
                        <Box display="flex" alignItems="center">
                          <ExploreIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="body2">
                            {property.direction}向き
                          </Typography>
                        </Box>
                      </Grid>
                    )}
                  </Grid>

                  <Box sx={{ mt: 2, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                    <Grid container spacing={1}>
                      <Grid item xs={12}>
                        <Typography variant="body2" color="text.secondary">
                          売出確認日: {formatDate(property.earliest_published_at)}
                          {property.earliest_published_at && (
                            <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                              ({calculateDaysFromPublished(property.earliest_published_at)})
                            </Typography>
                          )}
                        </Typography>
                      </Grid>
                      {property.sold_at && (
                        <Grid item xs={12}>
                          <Typography variant="body2" color="text.secondary">
                            販売終了日: {formatDate(property.sold_at)}
                          </Typography>
                        </Grid>
                      )}
                    </Grid>
                  </Box>

                  <Divider sx={{ my: 2 }} />

                  <Box display="flex" justifyContent="center">
                    <Button
                      component={Link}
                      to={`/properties/${property.id}`}
                      variant="contained"
                      size="small"
                      fullWidth
                    >
                      詳細を見る
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Container>
  );
};

export default BuildingPropertiesPage;