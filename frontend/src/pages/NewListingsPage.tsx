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
  Button,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import RefreshIcon from '@mui/icons-material/Refresh';
import { propertyApi, RecentUpdate } from '../api/propertyApi';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { sortWardNamesByLandPrice } from '../constants/wardOrder';

const NewListingsPage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [newListings, setNewListings] = useState<RecentUpdate[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [wards, setWards] = useState<string[]>([]);

  // URLパラメータから初期値を取得
  const selectedWard = searchParams.get('ward') || 'all';
  const selectedHours = parseInt(searchParams.get('hours') || '24');
  const page = parseInt(searchParams.get('page') || '0');
  const rowsPerPage = parseInt(searchParams.get('rowsPerPage') || '25');

  const fetchNewListings = async () => {
    setLoading(true);
    try {
      const response = await propertyApi.getRecentUpdates(selectedHours);
      
      // すべての新着物件を抽出
      const allNewListings: RecentUpdate[] = [];
      const wardSet = new Set<string>();
      
      response.updates_by_ward.forEach(ward => {
        wardSet.add(ward.ward);
        ward.new_listings.forEach(property => {
          allNewListings.push({
            ...property,
            address: property.address || ward.ward, // 区名を住所として保持
          });
        });
      });
      
      // 価格でソート（高い順）
      allNewListings.sort((a, b) => b.price - a.price);
      
      setNewListings(allNewListings);
      setWards(sortWardNamesByLandPrice(Array.from(wardSet)));
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to fetch new listings:', error);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchNewListings();
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
  const filteredListings = selectedWard === 'all' 
    ? newListings 
    : newListings.filter(property => getWard(property.address) === selectedWard);

  // ページネーション
  const paginatedListings = filteredListings.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  // 価格帯別の統計
  const priceRangeStats = {
    under5000: filteredListings.filter(p => p.price < 5000).length,
    under10000: filteredListings.filter(p => p.price >= 5000 && p.price < 10000).length,
    under20000: filteredListings.filter(p => p.price >= 10000 && p.price < 20000).length,
    over20000: filteredListings.filter(p => p.price >= 20000).length,
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* ヘッダー */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 'bold' }}>
          <NewReleasesIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
          新規掲載物件
        </Typography>
        <Typography variant="body1" color="text.secondary">
          新たに掲載された物件の一覧です（物件単位での新規掲載）
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
              onClick={fetchNewListings}
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
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">{filteredListings.length}</Typography>
            <Typography variant="body2" color="text.secondary">
              新規掲載物件数
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">{priceRangeStats.under5000}</Typography>
            <Typography variant="body2" color="text.secondary">
              5,000万円未満
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">{priceRangeStats.under10000}</Typography>
            <Typography variant="body2" color="text.secondary">
              5,000万円〜1億円
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h6">{priceRangeStats.over20000}</Typography>
            <Typography variant="body2" color="text.secondary">
              2億円以上
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
                <TableCell align="right">価格</TableCell>
                <TableCell>階数</TableCell>
                <TableCell>面積</TableCell>
                <TableCell>間取り</TableCell>
                <TableCell>方角</TableCell>
                <TableCell>築年</TableCell>
                <TableCell>掲載日</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedListings.map((property) => (
                <TableRow key={`${property.id}-${property.created_at}`}>
                  <TableCell>
                    <Link
                      component="button"
                      variant="body2"
                      onClick={() => navigate(`/properties/${property.id}`)}
                      sx={{ textAlign: 'left' }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Chip
                          icon={<NewReleasesIcon />}
                          label="NEW"
                          color="success"
                          size="small"
                        />
                        {property.building_name}
                        {property.room_number && ` ${property.room_number}号室`}
                      </Box>
                    </Link>
                  </TableCell>
                  <TableCell>{getWard(property.address)}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                      {formatPrice(property.price)}
                    </Typography>
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
                  <TableCell>{formatDate(property.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            rowsPerPageOptions={[25, 50, 100]}
            component="div"
            count={filteredListings.length}
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

export default NewListingsPage;