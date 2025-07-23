import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
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
  ToggleButtonGroup
} from '@mui/material';
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
}

type ViewMode = 'card' | 'table';
type OrderBy = 'earliest_published_at' | 'floor_number' | 'area' | 'min_price' | 'layout' | 'direction';
type Order = 'asc' | 'desc';

const BuildingPropertiesPage: React.FC = () => {
  const { buildingName } = useParams<{ buildingName: string }>();
  const [properties, setProperties] = useState<Property[]>([]);
  const [building, setBuilding] = useState<any | null>(null);
  const [stats, setStats] = useState<BuildingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [orderBy, setOrderBy] = useState<OrderBy>('earliest_published_at');
  const [order, setOrder] = useState<Order>('desc');

  useEffect(() => {
    if (buildingName) {
      fetchBuildingProperties();
    }
  }, [buildingName]);

  const fetchBuildingProperties = async () => {
    try {
      setLoading(true);
      // 建物名専用のAPIで物件を取得
      const response = await propertyApi.getBuildingProperties(decodeURIComponent(buildingName!));
      
      setProperties(response.properties);
      setBuilding(response.building);
      
      // 統計情報を計算
      if (response.properties.length > 0) {
        const prices = response.properties
          .map(p => p.min_price)
          .filter((p): p is number => p !== undefined);
        const areas = response.properties
          .map(p => p.area)
          .filter((a): a is number => a !== undefined);
        
        setStats({
          total_units: response.properties.length,
          price_range: {
            min: Math.min(...prices),
            max: Math.max(...prices),
            avg: prices.reduce((a, b) => a + b, 0) / prices.length
          },
          area_range: {
            min: areas.length > 0 ? Math.min(...areas) : 0,
            max: areas.length > 0 ? Math.max(...areas) : 0
          },
          total_floors: response.building.total_floors
        });
      }
    } catch (err) {
      setError('建物の物件情報の取得に失敗しました');
      console.error(err);
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

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
  };

  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
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
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center">
          <CircularProgress />
        </Box>
      </Container>
    );
  }
  
  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">{error}</Alert>
      </Container>
    );
  }
  
  if (!properties.length || !building) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="info">物件が見つかりません</Alert>
      </Container>
    );
  }

  const buildingInfo = building;

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
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

      {/* 建物の統計情報 */}
      {stats && (
        <Paper elevation={2} sx={{ p: 3, mb: 4 }}>
          <Typography variant="h6" gutterBottom>建物情報</Typography>
          <Grid container spacing={3}>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="primary">
                  {stats.total_units}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  販売中の戸数
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="primary">
                  {stats.total_floors || '-'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  階建て
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="body1">
                  {formatPrice(stats.price_range.min)}
                </Typography>
                <Typography variant="body1">
                  〜
                </Typography>
                <Typography variant="body1">
                  {formatPrice(stats.price_range.max)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  価格帯
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="body1">
                  {stats.area_range.min.toFixed(1)}㎡
                </Typography>
                <Typography variant="body1">
                  〜
                </Typography>
                <Typography variant="body1">
                  {stats.area_range.max.toFixed(1)}㎡
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  専有面積
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* 表示モード切替と物件一覧タイトル */}
      <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Typography variant="h5">
          販売中の物件 ({properties.length}件)
        </Typography>
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_, newMode) => newMode && setViewMode(newMode)}
          aria-label="表示モード"
        >
          <ToggleButton value="table" aria-label="表形式">
            <TableChartIcon sx={{ mr: 0.5 }} />
            表形式
          </ToggleButton>
          <ToggleButton value="card" aria-label="カード形式">
            <ViewModuleIcon sx={{ mr: 0.5 }} />
            カード形式
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {viewMode === 'table' ? (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>
                  <TableSortLabel
                    active={orderBy === 'earliest_published_at'}
                    direction={orderBy === 'earliest_published_at' ? order : 'asc'}
                    onClick={() => handleRequestSort('earliest_published_at')}
                  >
                    売出確認日
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === 'floor_number'}
                    direction={orderBy === 'floor_number' ? order : 'asc'}
                    onClick={() => handleRequestSort('floor_number')}
                  >
                    階数
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === 'area'}
                    direction={orderBy === 'area' ? order : 'asc'}
                    onClick={() => handleRequestSort('area')}
                  >
                    専有面積
                  </TableSortLabel>
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={orderBy === 'layout'}
                    direction={orderBy === 'layout' ? order : 'asc'}
                    onClick={() => handleRequestSort('layout')}
                  >
                    間取り
                  </TableSortLabel>
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={orderBy === 'direction'}
                    direction={orderBy === 'direction' ? order : 'asc'}
                    onClick={() => handleRequestSort('direction')}
                  >
                    方角
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right">
                  <TableSortLabel
                    active={orderBy === 'min_price'}
                    direction={orderBy === 'min_price' ? order : 'asc'}
                    onClick={() => handleRequestSort('min_price')}
                  >
                    価格
                  </TableSortLabel>
                </TableCell>
                <TableCell>掲載サイト</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedProperties.map((property) => (
                <TableRow key={property.id} hover>
                  <TableCell component="th" scope="row">
                    {formatDate(property.earliest_published_at)}
                  </TableCell>
                  <TableCell align="right">
                    <Box display="flex" alignItems="center" justifyContent="flex-end">
                      {property.is_resale && (
                        <CachedIcon fontSize="small" color="warning" sx={{ mr: 0.5 }} />
                      )}
                      {property.floor_number ? `${property.floor_number}階` : '-'}
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    {property.area ? `${property.area}㎡` : '-'}
                  </TableCell>
                  <TableCell>{property.layout || '-'}</TableCell>
                  <TableCell>{property.direction ? `${property.direction}向き` : '-'}</TableCell>
                  <TableCell align="right">
                    {property.min_price === property.max_price
                      ? formatPrice(property.min_price)
                      : `${formatPrice(property.min_price)} 〜 ${formatPrice(property.max_price)}`}
                  </TableCell>
                  <TableCell>
                    <Box>
                      {property.source_sites.map((site) => (
                        <Chip
                          key={site}
                          label={site}
                          size="small"
                          sx={{
                            backgroundColor: getSourceColor(site),
                            color: 'white',
                            mr: 0.5,
                            mb: 0.5
                          }}
                        />
                      ))}
                      {property.listing_count > 1 && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          {property.listing_count}件の掲載
                        </Typography>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="center">
                    <Button
                      component={Link}
                      to={`/properties/${property.id}`}
                      variant="outlined"
                      size="small"
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
                    <Box>
                      {property.source_sites.map((site) => (
                        <Chip
                          key={site}
                          label={site}
                          size="small"
                          sx={{
                            backgroundColor: getSourceColor(site),
                            color: 'white',
                            ml: 0.5
                          }}
                        />
                      ))}
                    </Box>
                  </Box>

                  <Typography variant="h5" color="primary" sx={{ mt: 1, mb: 2 }}>
                    {property.min_price === property.max_price
                      ? formatPrice(property.min_price)
                      : `${formatPrice(property.min_price)} 〜 ${formatPrice(property.max_price)}`}
                  </Typography>

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

                  {property.listing_count > 1 && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      {property.listing_count}件の掲載あり
                    </Typography>
                  )}

                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    売出確認日: {formatDate(property.earliest_published_at)}
                  </Typography>

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