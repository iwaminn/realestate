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
  Tooltip,
  IconButton,
  Button,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import UpdateIcon from '@mui/icons-material/Update';
import RefreshIcon from '@mui/icons-material/Refresh';
import { propertyApi, RecentUpdate } from '../api/propertyApi';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { sortWardNamesByLandPrice } from '../constants/wardOrder';

const PriceChangesPage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [priceChanges, setPriceChanges] = useState<RecentUpdate[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [wards, setWards] = useState<string[]>([]);

  // URLパラメータから初期値を取得
  const selectedWard = searchParams.get('ward') || 'all';
  const selectedHours = parseInt(searchParams.get('hours') || '24');
  const page = parseInt(searchParams.get('page') || '0');
  const rowsPerPage = parseInt(searchParams.get('rowsPerPage') || '25');

  const fetchPriceChanges = async () => {
    setLoading(true);
    try {
      const response = await propertyApi.getRecentUpdates(selectedHours);
      
      // すべての価格改定物件を抽出
      const allPriceChanges: RecentUpdate[] = [];
      const wardSet = new Set<string>();
      
      response.updates_by_ward.forEach(ward => {
        wardSet.add(ward.ward);
        ward.price_changes.forEach(property => {
          allPriceChanges.push({
            ...property,
            address: property.address || ward.ward, // 区名を住所として保持
          });
        });
      });
      
      // 価格変動幅でソート（大きい順）
      allPriceChanges.sort((a, b) => {
        const diffA = Math.abs(a.price_diff || 0);
        const diffB = Math.abs(b.price_diff || 0);
        return diffB - diffA;
      });
      
      setPriceChanges(allPriceChanges);
      setWards(sortWardNamesByLandPrice(Array.from(wardSet)));
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to fetch price changes:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPriceChanges();
  }, [selectedHours]);

  // URLパラメータを更新するヘルパー関数
  const updateSearchParams = (updates: Record<string, string>) => {
    const newParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === '' || (key === 'ward' && value === 'all') || 
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

  const formatPrice = (price: number) => {
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      if (man === 0) {
        return `${oku}億円`;
      }
      return `${oku}億${man.toLocaleString()}万円`;
    }
    return `${price.toLocaleString()}万円`;
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
  const filteredChanges = selectedWard === 'all' 
    ? priceChanges 
    : priceChanges.filter(property => getWard(property.address) === selectedWard);

  // ページネーション
  const paginatedChanges = filteredChanges.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* ヘッダー */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 'bold' }}>
          <UpdateIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
          価格改定履歴
        </Typography>
        <Typography variant="body1" color="text.secondary">
          物件の価格変更履歴を確認できます
        </Typography>
      </Box>

      {/* フィルター */}
      <Paper sx={{ p: 3, mb: 3 }}>
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
              <Select value={selectedWard} onChange={handleWardChange} label="エリア">
                <MenuItem value="all">すべて</MenuItem>
                {wards.map(ward => (
                  <MenuItem key={ward} value={ward}>{ward}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={fetchPriceChanges}
              disabled={loading}
            >
              更新
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            {lastUpdated && (
              <Typography variant="caption" color="text.secondary">
                最終更新: {lastUpdated.toLocaleTimeString('ja-JP')}
              </Typography>
            )}
          </Grid>
        </Grid>
      </Paper>

      {/* 統計情報 */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">{filteredChanges.length}</Typography>
            <Typography variant="body2" color="text.secondary">
              価格改定物件数
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6" color="primary">
              {filteredChanges.filter(p => p.price_diff && p.price_diff < 0).length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              値下げ物件
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6" color="error">
              {filteredChanges.filter(p => p.price_diff && p.price_diff > 0).length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              値上げ物件
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* テーブル */}
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>建物名・部屋番号</TableCell>
                <TableCell>エリア</TableCell>
                <TableCell align="right">現在価格</TableCell>
                <TableCell align="right">前回価格</TableCell>
                <TableCell align="right">変動幅</TableCell>
                <TableCell align="right">変動率</TableCell>
                <TableCell>階数</TableCell>
                <TableCell>面積</TableCell>
                <TableCell>間取り</TableCell>
                <TableCell>方角</TableCell>
                <TableCell>築年</TableCell>
                <TableCell>経過日数</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedChanges.map((property) => (
                <TableRow key={`${property.id}-${property.changed_at}`}>
                  <TableCell>
                    <Link
                      component="button"
                      variant="body2"
                      onClick={() => navigate(`/properties/${property.id}`)}
                      sx={{ textAlign: 'left' }}
                    >
                      {property.building_name}
                      {property.room_number && ` ${property.room_number}号室`}
                    </Link>
                  </TableCell>
                  <TableCell>{getWard(property.address)}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                      {formatPrice(property.price)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    {property.previous_price ? (
                      <Typography variant="body2" sx={{ textDecoration: 'line-through', color: 'text.secondary' }}>
                        {formatPrice(property.previous_price)}
                      </Typography>
                    ) : '-'}
                  </TableCell>
                  <TableCell align="right">
                    {property.price_diff ? (
                      <Chip
                        icon={property.price_diff < 0 ? <TrendingDownIcon /> : <TrendingUpIcon />}
                        label={`${property.price_diff > 0 ? '+' : ''}${property.price_diff.toLocaleString()}万円`}
                        color={property.price_diff < 0 ? 'primary' : 'error'}
                        size="small"
                      />
                    ) : '-'}
                  </TableCell>
                  <TableCell align="right">
                    {property.price_diff_rate ? (
                      <Typography 
                        variant="body2" 
                        color={property.price_diff_rate < 0 ? 'primary' : 'error'}
                        sx={{ fontWeight: 'bold' }}
                      >
                        {property.price_diff_rate > 0 ? '+' : ''}{property.price_diff_rate}%
                      </Typography>
                    ) : '-'}
                  </TableCell>
                  <TableCell>{property.floor_number ? `${property.floor_number}階` : '-'}</TableCell>
                  <TableCell>{property.area ? `${property.area}㎡` : '-'}</TableCell>
                  <TableCell>{property.layout || '-'}</TableCell>
                  <TableCell>{property.direction || '-'}</TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {property.built_year ? (
                      `築${new Date().getFullYear() - property.built_year}年`
                    ) : '-'}
                  </TableCell>
                  <TableCell>
                    {property.days_on_market !== null && property.days_on_market !== undefined ? (
                      `${property.days_on_market}日`
                    ) : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            rowsPerPageOptions={[25, 50, 100]}
            component="div"
            count={filteredChanges.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
            labelRowsPerPage="表示件数:"
            labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}件`}
          />
        </TableContainer>
      )}
    </Container>
  );
};

export default PriceChangesPage;