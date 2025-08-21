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
  List,
  ListItem,
  ListItemText,
  Badge,
  Link,
  Skeleton,
  Button,
  Tabs,
  Tab,
  TabScrollButton,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import ApartmentIcon from '@mui/icons-material/Apartment';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import UpdateIcon from '@mui/icons-material/Update';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { propertyApi, RecentUpdatesResponse, WardUpdates } from '../api/propertyApi';
import { TOKYO_WARDS, sortWardsByLandPrice, getPopularWards, getOtherWards } from '../constants/wardOrder';

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
  const [selectedWardTab, setSelectedWardTab] = useState(0);
  const [updateType, setUpdateType] = useState<'price_changes' | 'new_listings'>('price_changes');

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

  const popularWards = getPopularWards();
  const otherWards = getOtherWards();

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

          {/* タブで価格改定/新着を切り替え */}
          <Paper sx={{ p: 2 }}>
            <Tabs 
              value={updateType} 
              onChange={(e, newValue) => {
                setUpdateType(newValue);
                setSelectedWardTab(0); // タブ切り替え時にエリアタブをリセット
              }}
              sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
            >
              <Tab 
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <UpdateIcon />
                    価格改定物件
                    <Chip label={recentUpdates.total_price_changes} size="small" color="error" />
                  </Box>
                } 
                value="price_changes" 
              />
              <Tab 
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <NewReleasesIcon />
                    新着物件
                    <Chip label={recentUpdates.total_new_listings} size="small" color="success" />
                  </Box>
                } 
                value="new_listings" 
              />
            </Tabs>

            {/* エリア別タブ */}
            {sortWardsByLandPrice(
              recentUpdates.updates_by_ward
                .filter(ward => 
                  updateType === 'price_changes' 
                    ? ward.price_changes.length > 0 
                    : ward.new_listings.length > 0
                )
            ).length > 0 && (
              <>
                <Tabs
                  value={selectedWardTab}
                  onChange={(e, newValue) => setSelectedWardTab(newValue)}
                  variant="scrollable"
                  scrollButtons="auto"
                  sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
                >
                  {sortWardsByLandPrice(
                    recentUpdates.updates_by_ward
                      .filter(ward => 
                        updateType === 'price_changes' 
                          ? ward.price_changes.length > 0 
                          : ward.new_listings.length > 0
                      )
                  )
                    .map((ward, index) => (
                      <Tab 
                        key={ward.ward} 
                        label={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {ward.ward}
                            <Chip 
                              label={
                                updateType === 'price_changes' 
                                  ? ward.price_changes.length 
                                  : ward.new_listings.length
                              } 
                              size="small" 
                              color={updateType === 'price_changes' ? 'error' : 'success'}
                            />
                          </Box>
                        }
                      />
                    ))}
                </Tabs>

                {/* タブコンテンツ */}
                <Box sx={{ minHeight: 300, maxHeight: 500, overflowY: 'auto' }}>
                  {sortWardsByLandPrice(
                    recentUpdates.updates_by_ward
                      .filter(ward => 
                        updateType === 'price_changes' 
                          ? ward.price_changes.length > 0 
                          : ward.new_listings.length > 0
                      )
                  )
                    .map((ward, index) => (
                      <Box
                        key={ward.ward}
                        hidden={selectedWardTab !== index}
                        sx={{ p: 2 }}
                      >
                        {updateType === 'price_changes' ? (
                          <List>
                            {ward.price_changes.map((property) => (
                              <ListItem key={`price-${property.id}`} sx={{ pl: 0 }}>
                                <ListItemText
                                  primary={
                                    <Link
                                      href={`/properties/${property.id}`}
                                      sx={{ textDecoration: 'none', color: 'inherit', '&:hover': { textDecoration: 'underline' } }}
                                    >
                                      <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                                        {property.building_name} {property.room_number && `${property.room_number}号室`}
                                      </Typography>
                                    </Link>
                                  }
                                  secondary={
                                    <Box sx={{ mt: 1 }}>
                                      <Typography variant="body2" component="span" sx={{ color: theme.palette.error.main, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        {formatPrice(property.price)}
                                        {property.previous_price && (
                                          <>
                                            {' '}
                                            <span style={{ color: 'gray', textDecoration: 'line-through', fontSize: '0.9rem' }}>
                                              {formatPrice(property.previous_price)}
                                            </span>
                                            {' '}
                                            <Chip
                                              label={`${property.price_diff && property.price_diff > 0 ? '+' : ''}${property.price_diff?.toLocaleString()}万円`}
                                              size="small"
                                              color={property.price_diff && property.price_diff < 0 ? 'primary' : 'error'}
                                              sx={{ ml: 1 }}
                                            />
                                            <Chip
                                              label={`${property.price_diff_rate && property.price_diff_rate > 0 ? '+' : ''}${property.price_diff_rate}%`}
                                              size="small"
                                              variant="outlined"
                                              color={property.price_diff && property.price_diff < 0 ? 'primary' : 'error'}
                                              sx={{ ml: 1 }}
                                            />
                                          </>
                                        )}
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 0.5, color: 'text.secondary' }}>
                                        {formatPropertyInfo(property)}
                                      </Typography>
                                    </Box>
                                  }
                                />
                                <Divider />
                              </ListItem>
                            ))}
                          </List>
                        ) : (
                          <List>
                            {ward.new_listings.map((property) => (
                              <ListItem key={`new-${property.id}`} sx={{ pl: 0 }}>
                                <ListItemText
                                  primary={
                                    <Link
                                      href={`/properties/${property.id}`}
                                      sx={{ textDecoration: 'none', color: 'inherit', '&:hover': { textDecoration: 'underline' } }}
                                    >
                                      <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                                        <Chip
                                          icon={<NewReleasesIcon />}
                                          label="NEW"
                                          color="success"
                                          size="small"
                                          sx={{ mr: 1 }}
                                        />
                                        {property.building_name} {property.room_number && `${property.room_number}号室`}
                                      </Typography>
                                    </Link>
                                  }
                                  secondary={
                                    <Box sx={{ mt: 1 }}>
                                      <Typography variant="body2" component="span" sx={{ color: theme.palette.success.main, fontWeight: 'bold', fontSize: '1.1rem' }}>
                                        {formatPrice(property.price)}
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 0.5, color: 'text.secondary' }}>
                                        {formatPropertyInfo(property)}
                                      </Typography>
                                    </Box>
                                  }
                                />
                                <Divider />
                              </ListItem>
                            ))}
                          </List>
                        )}
                      </Box>
                    ))}
                </Box>
              </>
            )}
          </Paper>
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