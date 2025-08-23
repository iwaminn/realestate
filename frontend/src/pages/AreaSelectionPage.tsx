import React, { useState, useEffect, useCallback } from 'react';
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
  Autocomplete,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import ApartmentIcon from '@mui/icons-material/Apartment';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import UpdateIcon from '@mui/icons-material/Update';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { propertyApi, RecentUpdatesResponse, WardUpdates } from '../api/propertyApi';
import { TOKYO_WARDS, sortWardsByLandPrice, getPopularWards, getOtherWards } from '../constants/wardOrder';
import { debounce } from 'lodash';

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
  const [selectedWardName, setSelectedWardName] = useState<string | null>(null);
  const [updateType, setUpdateType] = useState<'price_changes' | 'new_listings'>('price_changes');
  const [buildingOptions, setBuildingOptions] = useState<Array<string | { value: string; label: string }>>([]);
  const [loadingBuildings, setLoadingBuildings] = useState(false);
  const [buildingInputValue, setBuildingInputValue] = useState(searchText);

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

  // 建物名候補を取得する関数（デバウンス付き）- SearchFormと同じ処理
  const fetchBuildingSuggestions = useCallback(
    debounce(async (query: string) => {
      if (query.length < 1) {
        setBuildingOptions([]);
        return;
      }
      
      setLoadingBuildings(true);
      try {
        const suggestions = await propertyApi.suggestBuildings(query);
        // APIレスポンスの形式を判定（SearchFormと同じ処理）
        if (suggestions && suggestions.length > 0) {
          if (typeof suggestions[0] === 'object' && 'value' in suggestions[0]) {
            // 新形式（オブジェクト配列）
            setBuildingOptions(suggestions as Array<{ value: string; label: string }>);
          } else {
            // 旧形式（文字列配列）
            setBuildingOptions(suggestions as string[]);
          }
        } else {
          setBuildingOptions([]);
        }
      } catch (error) {
        console.error('Failed to fetch building suggestions:', error);
        setBuildingOptions([]);
      } finally {
        setLoadingBuildings(false);
      }
    }, 300),
    []
  );

  const handleAreaClick = (wardName: string) => {
    navigate(`/properties?wards=${encodeURIComponent(wardName)}`);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchText.trim()) {
      navigate(`/properties?building_name=${encodeURIComponent(searchText.trim())}`);
    }
  };

  // エリアフィルタリングは建物名検索とは独立して処理
  const filteredWards = TOKYO_WARDS.filter((ward) =>
    ward.name.includes('')  // 建物名検索時はエリア選択を表示しない
  );

  const popularWards = getPopularWards();
  const otherWards = getOtherWards();

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
          <Autocomplete
            freeSolo
            options={buildingOptions}
            value={searchText}
            inputValue={buildingInputValue}
            onInputChange={(event, newInputValue, reason) => {
              setBuildingInputValue(newInputValue);
              if (reason === 'input') {
                setSearchText(newInputValue);
                fetchBuildingSuggestions(newInputValue);
              } else if (reason === 'clear') {
                setSearchText('');
                setBuildingInputValue('');
                setBuildingOptions([]);
              }
            }}
            onChange={(event, newValue) => {
              if (typeof newValue === 'string') {
                setSearchText(newValue);
                setBuildingInputValue(newValue);
              } else if (newValue && typeof newValue === 'object' && 'value' in newValue) {
                // オブジェクト形式の場合（エイリアス対応）
                setSearchText(newValue.value);
                setBuildingInputValue(newValue.label);
              }
            }}
            getOptionLabel={(option) => {
              // オプションのラベル表示方法
              if (typeof option === 'string') {
                return option;
              } else if (typeof option === 'object' && 'label' in option) {
                return option.label;
              }
              return '';
            }}
            isOptionEqualToValue={(option, value) => {
              if (typeof option === 'string' && typeof value === 'string') {
                return option === value;
              } else if (typeof option === 'object' && typeof value === 'object') {
                return option.value === value.value;
              }
              return false;
            }}
            loading={loadingBuildings}
            loadingText="読み込み中..."
            noOptionsText="候補が見つかりません"
            sx={{ flex: 1 }}
            renderInput={(params) => (
              <TextField
                {...params}
                variant="standard"
                placeholder="建物名で検索（例：タワー、パーク）"
                InputProps={{
                  ...params.InputProps,
                  disableUnderline: true,
                  sx: { px: 2, py: 1 },
                  endAdornment: (
                    <>
                      {loadingBuildings ? <CircularProgress color="inherit" size={20} /> : null}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                }}
              />
            )}
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
                onClick={() => navigate('/updates?tab=0')}
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
                onClick={() => navigate('/updates?tab=1')}
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
                // 選択中のエリアを保持して、新しいタブでそのエリアを探す
                if (selectedWardName && recentUpdates) {
                  const newWards = sortWardsByLandPrice(
                    recentUpdates.updates_by_ward.filter(ward => 
                      newValue === 'price_changes' 
                        ? ward.price_changes.length > 0 
                        : ward.new_listings.length > 0
                    )
                  );
                  const wardIndex = newWards.findIndex(w => w.ward === selectedWardName);
                  setSelectedWardTab(wardIndex >= 0 ? wardIndex : 0);
                } else {
                  setSelectedWardTab(0);
                }
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
                  onChange={(e, newValue) => {
                    setSelectedWardTab(newValue);
                    // 選択されたエリア名を保存
                    const wards = sortWardsByLandPrice(
                      recentUpdates.updates_by_ward.filter(ward => 
                        updateType === 'price_changes' 
                          ? ward.price_changes.length > 0 
                          : ward.new_listings.length > 0
                      )
                    );
                    if (wards[newValue]) {
                      setSelectedWardName(wards[newValue].ward);
                    }
                  }}
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
                          <Box>
                            {ward.price_changes.map((property, index) => (
                              <Paper 
                                key={`price-${property.id}`} 
                                component={Link}
                                href={`/properties/${property.id}`}
                                sx={{ 
                                  p: 2, 
                                  mb: 2, 
                                  border: 1,
                                  borderColor: 'divider',
                                  display: 'block',
                                  textDecoration: 'none',
                                  color: 'inherit',
                                  cursor: 'pointer',
                                  transition: 'all 0.3s',
                                  '&:hover': { 
                                    boxShadow: 3,
                                    bgcolor: alpha(theme.palette.primary.main, 0.02),
                                    transform: 'translateY(-2px)'
                                  }
                                }}
                              >
                                <Grid container spacing={2}>
                                  <Grid item xs={12} md={8}>
                                    <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1 }}>
                                      {property.building_name}
                                      {property.room_number && (
                                        <Chip label={`${property.room_number}号室`} size="small" sx={{ ml: 1 }} />
                                      )}
                                    </Typography>
                                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                                      {property.floor_number && (
                                        <Chip icon={<LocationOnIcon />} label={`${property.floor_number}階`} size="small" variant="outlined" />
                                      )}
                                      {property.area && (
                                        <Chip label={`${property.area}㎡`} size="small" variant="outlined" />
                                      )}
                                      {property.layout && (
                                        <Chip label={property.layout} size="small" variant="outlined" />
                                      )}
                                      {property.direction && (
                                        <Chip label={`${property.direction}向き`} size="small" variant="outlined" />
                                      )}
                                    </Box>
                                  </Grid>
                                  <Grid item xs={12} md={4}>
                                    <Box sx={{ textAlign: { xs: 'left', md: 'right' } }}>
                                      <Typography variant="h5" sx={{ color: theme.palette.error.main, fontWeight: 'bold' }}>
                                        {formatPrice(property.price)}
                                      </Typography>
                                      {property.previous_price && (
                                        <Box sx={{ mt: 1 }}>
                                          <Typography variant="body2" sx={{ color: 'text.secondary', textDecoration: 'line-through' }}>
                                            {formatPrice(property.previous_price)}
                                          </Typography>
                                          <Box sx={{ display: 'flex', gap: 1, justifyContent: { xs: 'flex-start', md: 'flex-end' }, mt: 0.5 }}>
                                            <Chip
                                              icon={property.price_diff && property.price_diff < 0 ? <TrendingDownIcon /> : <TrendingUpIcon />}
                                              label={`${property.price_diff && property.price_diff > 0 ? '+' : ''}${property.price_diff?.toLocaleString()}万円`}
                                              size="small"
                                              color={property.price_diff && property.price_diff < 0 ? 'primary' : 'error'}
                                            />
                                            <Chip
                                              label={`${property.price_diff_rate && property.price_diff_rate > 0 ? '+' : ''}${property.price_diff_rate}%`}
                                              size="small"
                                              variant="outlined"
                                              color={property.price_diff && property.price_diff < 0 ? 'primary' : 'error'}
                                            />
                                          </Box>
                                        </Box>
                                      )}
                                    </Box>
                                  </Grid>
                                </Grid>
                              </Paper>
                            ))}
                          </Box>
                        ) : (
                          <Box>
                            {ward.new_listings.map((property, index) => (
                              <Paper 
                                key={`new-${property.id}`} 
                                component={Link}
                                href={`/properties/${property.id}`}
                                sx={{ 
                                  p: 2, 
                                  mb: 2,
                                  border: 1,
                                  borderColor: 'divider',
                                  display: 'block',
                                  textDecoration: 'none',
                                  color: 'inherit',
                                  cursor: 'pointer',
                                  transition: 'all 0.3s',
                                  background: `linear-gradient(to right, ${alpha(theme.palette.success.main, 0.03)} 0%, transparent 100%)`,
                                  '&:hover': { 
                                    boxShadow: 3,
                                    bgcolor: alpha(theme.palette.success.main, 0.05),
                                    transform: 'translateY(-2px)'
                                  }
                                }}
                              >
                                <Grid container spacing={2}>
                                  <Grid item xs={12} md={8}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                                      <Chip
                                        icon={<NewReleasesIcon />}
                                        label="NEW"
                                        color="success"
                                        size="small"
                                        sx={{ mr: 2 }}
                                      />
                                      <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                                        {property.building_name}
                                        {property.room_number && (
                                          <Chip label={`${property.room_number}号室`} size="small" sx={{ ml: 1 }} />
                                        )}
                                      </Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                      {property.floor_number && (
                                        <Chip icon={<LocationOnIcon />} label={`${property.floor_number}階`} size="small" variant="outlined" />
                                      )}
                                      {property.area && (
                                        <Chip label={`${property.area}㎡`} size="small" variant="outlined" />
                                      )}
                                      {property.layout && (
                                        <Chip label={property.layout} size="small" variant="outlined" />
                                      )}
                                      {property.direction && (
                                        <Chip label={`${property.direction}向き`} size="small" variant="outlined" />
                                      )}
                                    </Box>
                                  </Grid>
                                  <Grid item xs={12} md={4}>
                                    <Box sx={{ textAlign: { xs: 'left', md: 'right' } }}>
                                      <Typography variant="h5" sx={{ color: theme.palette.success.main, fontWeight: 'bold' }}>
                                        {formatPrice(property.price)}
                                      </Typography>
                                      <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
                                        {property.created_at && `掲載: ${new Date(property.created_at).toLocaleDateString('ja-JP')}`}
                                      </Typography>
                                    </Box>
                                  </Grid>
                                </Grid>
                              </Paper>
                            ))}
                          </Box>
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
                6
              </Typography>
              <Typography variant="body2" color="text.secondary">
                対応エリア（都心6区）
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

      {/* エリア選択 - 建物名検索中は表示しない */}
      {(buildingInputValue === '') && (
        <>
          {/* 対象エリア（都心6区） */}
          <Box sx={{ mb: 6 }}>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
              <LocationOnIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
              対象エリア
            </Typography>
            <Grid container spacing={2}>
              {popularWards.map((ward) => (
                <Grid item xs={12} sm={6} md={4} key={ward.id}>
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
        </>
      )}
    </Container>
  );
};

export default AreaSelectionPage;