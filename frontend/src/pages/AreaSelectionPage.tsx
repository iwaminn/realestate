import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActionArea,
  Chip,
  TextField,
  InputAdornment,
  IconButton,
  Paper,
  Divider,
  useTheme,
  alpha,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  Badge,
  Link,
  Skeleton,
  Button,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import ApartmentIcon from '@mui/icons-material/Apartment';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import UpdateIcon from '@mui/icons-material/Update';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { propertyApi, RecentUpdatesResponse, WardUpdates } from '../api/propertyApi';

// 東京23区のリスト
const TOKYO_WARDS = [
  { name: '港区', id: 'minato', popular: true },
  { name: '渋谷区', id: 'shibuya', popular: true },
  { name: '新宿区', id: 'shinjuku', popular: true },
  { name: '千代田区', id: 'chiyoda', popular: true },
  { name: '中央区', id: 'chuo', popular: true },
  { name: '文京区', id: 'bunkyo', popular: true },
  { name: '目黒区', id: 'meguro', popular: true },
  { name: '世田谷区', id: 'setagaya', popular: true },
  { name: '品川区', id: 'shinagawa' },
  { name: '大田区', id: 'ota' },
  { name: '杉並区', id: 'suginami' },
  { name: '中野区', id: 'nakano' },
  { name: '豊島区', id: 'toshima' },
  { name: '練馬区', id: 'nerima' },
  { name: '板橋区', id: 'itabashi' },
  { name: '北区', id: 'kita' },
  { name: '荒川区', id: 'arakawa' },
  { name: '足立区', id: 'adachi' },
  { name: '葛飾区', id: 'katsushika' },
  { name: '江戸川区', id: 'edogawa' },
  { name: '墨田区', id: 'sumida' },
  { name: '江東区', id: 'koto' },
  { name: '台東区', id: 'taito' },
];

interface AreaStat {
  ward: string;
  count: number;
}

const AreaSelectionPage: React.FC = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const [searchText, setSearchText] = useState('');
  const [areaStats, setAreaStats] = useState<{[key: string]: number}>({});
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [recentUpdates, setRecentUpdates] = useState<RecentUpdatesResponse | null>(null);
  const [updatesLoading, setUpdatesLoading] = useState(true);

  // 全体の物件数を取得（初回のみ）
  useEffect(() => {
    const fetchTotalStats = async () => {
      setLoading(true);
      try {
        const response = await propertyApi.searchProperties({
          page: 1,
          per_page: 1,
        });
        
        if (response) {
          setTotalCount(response.total || 0);
        }
      } catch (error) {
        console.error('Failed to fetch total stats:', error);
      }
      setLoading(false);
    };

    fetchTotalStats();
  }, []);

  // 価格改定・新着物件を取得
  useEffect(() => {
    const fetchRecentUpdates = async () => {
      setUpdatesLoading(true);
      try {
        const updates = await propertyApi.getRecentUpdates(24);
        setRecentUpdates(updates);
      } catch (error) {
        console.error('Failed to fetch recent updates:', error);
      }
      setUpdatesLoading(false);
    };

    fetchRecentUpdates();
    // 5分ごとに更新
    const interval = setInterval(fetchRecentUpdates, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const handleAreaClick = (wardName: string) => {
    navigate(`/properties?wards=${encodeURIComponent(wardName)}`);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchText.trim()) {
      navigate(`/properties?building_name=${encodeURIComponent(searchText.trim())}`);
    }
  };

  const filteredWards = TOKYO_WARDS.filter((ward) =>
    ward.name.includes(searchText)
  );

  const popularWards = TOKYO_WARDS.filter((ward) => ward.popular);
  const otherWards = TOKYO_WARDS.filter((ward) => !ward.popular);

  const formatPrice = (price: number) => {
    if (price >= 10000) {
      return `${(price / 10000).toFixed(1)}億円`;
    }
    return `${price.toLocaleString()}万円`;
  };

  const formatPropertyInfo = (property: any) => {
    const parts = [];
    if (property.floor_number) parts.push(`${property.floor_number}階`);
    if (property.area) parts.push(`${property.area}㎡`);
    if (property.layout) parts.push(property.layout);
    if (property.direction) parts.push(`${property.direction}向き`);
    return parts.join(' / ');
  };


  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* ヘッダーセクション */}
      <Box sx={{ textAlign: 'center', mb: 6 }}>
        <Typography
          variant="h3"
          component="h1"
          gutterBottom
          sx={{
            fontWeight: 'bold',
            background: `linear-gradient(45deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            mb: 2,
          }}
        >
          都心マンションDB
        </Typography>
        <Typography variant="h6" color="text.secondary" sx={{ mb: 4 }}>
          東京23区の中古マンション情報を検索
        </Typography>

        {/* 検索バー */}
        <Paper
          component="form"
          onSubmit={handleSearchSubmit}
          sx={{
            p: '2px 4px',
            display: 'flex',
            alignItems: 'center',
            maxWidth: 600,
            mx: 'auto',
            boxShadow: 3,
          }}
        >
          <InputAdornment position="start" sx={{ ml: 2 }}>
            <SearchIcon color="action" />
          </InputAdornment>
          <TextField
            fullWidth
            variant="standard"
            placeholder="建物名で検索（例：タワー、パーク）"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            InputProps={{
              disableUnderline: true,
              sx: { px: 2, py: 1 },
            }}
          />
          <IconButton type="submit" sx={{ p: '10px' }} aria-label="search">
            <SearchIcon />
          </IconButton>
        </Paper>
      </Box>

      {/* 価格改定・新着物件セクション */}
      {recentUpdates && recentUpdates.updates_by_ward.length > 0 && (
        <Box sx={{ mb: 6 }}>
          <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
            <UpdateIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
            直近24時間の更新情報
          </Typography>
          
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={6}>
              <Paper 
                sx={{ 
                  p: 2, 
                  bgcolor: alpha(theme.palette.error.main, 0.05),
                  cursor: 'pointer',
                  transition: 'all 0.3s',
                  '&:hover': {
                    transform: 'translateY(-2px)',
                    boxShadow: 3,
                  }
                }}
                onClick={() => navigate('/price-changes')}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center' }}>
                    <Badge badgeContent={recentUpdates.total_price_changes} color="error">
                      <UpdateIcon sx={{ mr: 1 }} />
                    </Badge>
                    価格改定物件
                  </Typography>
                  <Button size="small" color="error" endIcon={<ArrowForwardIcon />}>
                    一覧を見る
                  </Button>
                </Box>
              </Paper>
            </Grid>
            <Grid item xs={12} md={6}>
              <Paper 
                sx={{ 
                  p: 2, 
                  bgcolor: alpha(theme.palette.success.main, 0.05),
                  cursor: 'pointer',
                  transition: 'all 0.3s',
                  '&:hover': {
                    transform: 'translateY(-2px)',
                    boxShadow: 3,
                  }
                }}
                onClick={() => navigate('/new-listings')}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center' }}>
                    <Badge badgeContent={recentUpdates.total_new_listings} color="success">
                      <NewReleasesIcon sx={{ mr: 1 }} />
                    </Badge>
                    新着物件
                  </Typography>
                  <Button size="small" color="success" endIcon={<ArrowForwardIcon />}>
                    一覧を見る
                  </Button>
                </Box>
              </Paper>
            </Grid>
          </Grid>

          {/* エリア別の更新情報 */}
          <Box sx={{ maxHeight: 600, overflowY: 'auto' }}>
            {recentUpdates.updates_by_ward
              .filter(ward => ward.price_changes.length > 0 || ward.new_listings.length > 0)
              .map((ward, index) => (
                <Accordion key={ward.ward} defaultExpanded={index < 3}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', width: '100%', gap: 2 }}>
                      <Typography variant="h6">{ward.ward}</Typography>
                      <Box sx={{ display: 'flex', gap: 1, ml: 'auto', mr: 2 }}>
                        {ward.price_changes.length > 0 && (
                          <Chip
                            label={`価格改定 ${ward.price_changes.length}件`}
                            color="error"
                            size="small"
                          />
                        )}
                        {ward.new_listings.length > 0 && (
                          <Chip
                            label={`新着 ${ward.new_listings.length}件`}
                            color="success"
                            size="small"
                          />
                        )}
                      </Box>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={2}>
                      {/* 価格改定物件 */}
                      {ward.price_changes.length > 0 && (
                        <Grid item xs={12} md={6}>
                          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                            価格改定
                          </Typography>
                          <List dense>
                            {ward.price_changes.slice(0, 5).map((property) => (
                              <ListItem key={`price-${property.id}`} sx={{ pl: 0 }}>
                                <ListItemText
                                  primary={
                                    <Link
                                      href={`/properties/${property.id}`}
                                      sx={{ textDecoration: 'none', color: 'inherit', '&:hover': { textDecoration: 'underline' } }}
                                    >
                                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                                        {property.building_name} {property.room_number && `${property.room_number}号室`}
                                      </Typography>
                                    </Link>
                                  }
                                  secondary={
                                    <>
                                      <Typography variant="caption" component="span" sx={{ color: theme.palette.error.main, fontWeight: 'bold' }}>
                                        {formatPrice(property.price)}
                                        {property.previous_price && (
                                          <>
                                            {' '}
                                            <span style={{ color: 'gray', textDecoration: 'line-through' }}>
                                              {formatPrice(property.previous_price)}
                                            </span>
                                            {' '}
                                            <span style={{ color: property.price_diff && property.price_diff < 0 ? 'blue' : 'red' }}>
                                              ({property.price_diff && property.price_diff > 0 ? '+' : ''}{property.price_diff?.toLocaleString()}万円)
                                            </span>
                                          </>
                                        )}
                                      </Typography>
                                      <Typography variant="caption" component="span" sx={{ ml: 1 }}>
                                        {formatPropertyInfo(property)}
                                      </Typography>
                                    </>
                                  }
                                />
                              </ListItem>
                            ))}
                            {ward.price_changes.length > 5 && (
                              <Typography variant="caption" color="text.secondary" sx={{ pl: 2 }}>
                                他 {ward.price_changes.length - 5} 件
                              </Typography>
                            )}
                          </List>
                        </Grid>
                      )}
                      
                      {/* 新着物件 */}
                      {ward.new_listings.length > 0 && (
                        <Grid item xs={12} md={6}>
                          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                            新着
                          </Typography>
                          <List dense>
                            {ward.new_listings.slice(0, 5).map((property) => (
                              <ListItem key={`new-${property.id}`} sx={{ pl: 0 }}>
                                <ListItemText
                                  primary={
                                    <Link
                                      href={`/properties/${property.id}`}
                                      sx={{ textDecoration: 'none', color: 'inherit', '&:hover': { textDecoration: 'underline' } }}
                                    >
                                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                                        {property.building_name} {property.room_number && `${property.room_number}号室`}
                                      </Typography>
                                    </Link>
                                  }
                                  secondary={
                                    <>
                                      <Typography variant="caption" component="span" sx={{ color: theme.palette.success.main, fontWeight: 'bold' }}>
                                        {formatPrice(property.price)}
                                      </Typography>
                                      <Typography variant="caption" component="span" sx={{ ml: 1 }}>
                                        {formatPropertyInfo(property)}
                                      </Typography>
                                    </>
                                  }
                                />
                              </ListItem>
                            ))}
                            {ward.new_listings.length > 5 && (
                              <Typography variant="caption" color="text.secondary" sx={{ pl: 2 }}>
                                他 {ward.new_listings.length - 5} 件
                              </Typography>
                            )}
                          </List>
                        </Grid>
                      )}
                    </Grid>
                  </AccordionDetails>
                </Accordion>
              ))}
          </Box>
        </Box>
      )}

      {/* ローディング表示 */}
      {updatesLoading && (
        <Box sx={{ mb: 6 }}>
          <Skeleton variant="text" width={200} height={40} />
          <Grid container spacing={2}>
            {[1, 2].map((i) => (
              <Grid item xs={12} md={6} key={i}>
                <Skeleton variant="rectangular" height={80} />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      <Divider sx={{ my: 4 }} />

      {/* 統計情報 */}
      <Box sx={{ mb: 4 }}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <ApartmentIcon color="primary" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h4" gutterBottom>
                {totalCount.toLocaleString()}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                掲載中の物件数
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <LocationOnIcon color="primary" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h4" gutterBottom>
                23
              </Typography>
              <Typography variant="body2" color="text.secondary">
                対応エリア（区）
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <TrendingUpIcon color="primary" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h4" gutterBottom>
                毎日更新
              </Typography>
              <Typography variant="body2" color="text.secondary">
                最新の物件情報
              </Typography>
            </Paper>
          </Grid>
        </Grid>
      </Box>

      {/* エリア選択 */}
      {searchText === '' ? (
        <>
          {/* 人気エリア */}
          <Box sx={{ mb: 6 }}>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
              <TrendingUpIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
              人気エリア
            </Typography>
            <Grid container spacing={2}>
              {popularWards.map((ward) => (
                <Grid item xs={12} sm={6} md={3} key={ward.id}>
                  <Card
                    sx={{
                      height: '100%',
                      transition: 'all 0.3s',
                      '&:hover': {
                        transform: 'translateY(-4px)',
                        boxShadow: 6,
                      },
                    }}
                  >
                    <CardActionArea onClick={() => handleAreaClick(ward.name)}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                          {ward.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          クリックして物件を検索
                        </Typography>
                        {areaStats[ward.name] && (
                          <Chip
                            label={`${areaStats[ward.name]}件`}
                            size="small"
                            color="primary"
                            sx={{ mt: 1 }}
                          />
                        )}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>

          <Divider sx={{ my: 4 }} />

          {/* その他のエリア */}
          <Box>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
              <LocationOnIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
              その他のエリア
            </Typography>
            <Grid container spacing={2}>
              {otherWards.map((ward) => (
                <Grid item xs={6} sm={4} md={2} key={ward.id}>
                  <Card
                    sx={{
                      transition: 'all 0.3s',
                      '&:hover': {
                        transform: 'translateY(-2px)',
                        boxShadow: 3,
                        bgcolor: alpha(theme.palette.primary.main, 0.05),
                      },
                    }}
                  >
                    <CardActionArea onClick={() => handleAreaClick(ward.name)}>
                      <CardContent sx={{ textAlign: 'center', py: 2 }}>
                        <Typography variant="body1" sx={{ fontWeight: 'medium' }}>
                          {ward.name}
                        </Typography>
                        {areaStats[ward.name] && (
                          <Typography variant="caption" color="text.secondary">
                            {areaStats[ward.name]}件
                          </Typography>
                        )}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>
        </>
      ) : (
        /* 検索結果 */
        <Box>
          <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
            「{searchText}」を含むエリア
          </Typography>
          <Grid container spacing={2}>
            {filteredWards.length > 0 ? (
              filteredWards.map((ward) => (
                <Grid item xs={12} sm={6} md={3} key={ward.id}>
                  <Card>
                    <CardActionArea onClick={() => handleAreaClick(ward.name)}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          {ward.name}
                        </Typography>
                        {areaStats[ward.name] && (
                          <Typography variant="body2" color="text.secondary">
                            物件数: {areaStats[ward.name]}件
                          </Typography>
                        )}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))
            ) : (
              <Grid item xs={12}>
                <Typography color="text.secondary">
                  該当するエリアが見つかりませんでした
                </Typography>
              </Grid>
            )}
          </Grid>
        </Box>
      )}
    </Container>
  );
};

export default AreaSelectionPage;