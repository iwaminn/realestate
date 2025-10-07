import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Grid,
  Typography,
  CircularProgress,
  Box,
  Alert,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
  FormControlLabel,
  Checkbox,
  ToggleButton,
  ToggleButtonGroup,
  useTheme,
  useMediaQuery,
  Container,
} from '@mui/material';
import {
  ViewList as ViewListIcon,
  Apartment as ApartmentIcon,
} from '@mui/icons-material';
import SearchForm from '../components/SearchForm';
import PropertyCard from '../components/PropertyCard';
import BuildingGroupedList from '../components/BuildingGroupedList';
import { propertyApi } from '../api/propertyApi';
import { Property, SearchParams } from '../types/property';
import { BookmarkService } from '../services/bookmarkService';
import { useUserAuth } from '../contexts/UserAuthContext';

const PropertyListPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [soldCount, setSoldCount] = useState(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [bookmarkStatuses, setBookmarkStatuses] = useState<{ [key: string]: boolean }>({});
  const { isAuthenticated, isLoading: authLoading } = useUserAuth();
  // URLパラメータからviewModeを取得
  const getViewModeFromUrl = (): 'properties' | 'buildings' => {
    const urlParams = new URLSearchParams(location.search);
    return urlParams.get('view') === 'buildings' ? 'buildings' : 'properties';
  };
  
  const [viewMode, setViewMode] = useState<'properties' | 'buildings'>(getViewModeFromUrl());
  
  // URLパラメータから初期状態を取得
  const getInitialParams = (): SearchParams => {
    const urlParams = new URLSearchParams(location.search);
    const params: SearchParams = {
      sort_by: urlParams.get('sort_by') || 'updated_at',
      sort_order: urlParams.get('sort_order') || 'desc',
    };
    
    // その他の検索条件も復元
    if (urlParams.get('min_price')) params.min_price = Number(urlParams.get('min_price'));
    if (urlParams.get('max_price')) params.max_price = Number(urlParams.get('max_price'));
    if (urlParams.get('min_area')) params.min_area = Number(urlParams.get('min_area'));
    if (urlParams.get('max_area')) params.max_area = Number(urlParams.get('max_area'));
    if (urlParams.get('layouts')) params.layouts = urlParams.get('layouts')?.split(',') || undefined;
    if (urlParams.get('building_name')) params.building_name = urlParams.get('building_name') || undefined;
    if (urlParams.get('max_building_age')) params.max_building_age = Number(urlParams.get('max_building_age'));
    if (urlParams.get('wards')) params.wards = urlParams.get('wards')?.split(',') || undefined;
    
    return params;
  };
  
  // URLパラメータからinclude_inactiveを取得
  const getIncludeInactiveFromUrl = (): boolean => {
    const urlParams = new URLSearchParams(location.search);
    return urlParams.get('include_inactive') === 'true';
  };
  
  const [searchParams, setSearchParams] = useState<SearchParams>(getInitialParams());
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  
  // URLからinclude_inactiveを初期化
  useEffect(() => {
    setIncludeInactive(getIncludeInactiveFromUrl());
  }, []);

  // URLパラメータを更新
  const updateUrlParams = (params: SearchParams, page: number, includeInactiveValue?: boolean) => {
    const urlParams = new URLSearchParams();
    
    // viewモードを保持
    if (viewMode === 'buildings') {
      urlParams.set('view', 'buildings');
    }
    
    // 検索条件をURLパラメータに追加
    if (params.sort_by && params.sort_by !== 'updated_at') urlParams.set('sort_by', params.sort_by);
    if (params.sort_order && params.sort_order !== 'desc') urlParams.set('sort_order', params.sort_order);
    if (params.min_price) urlParams.set('min_price', params.min_price.toString());
    if (params.max_price) urlParams.set('max_price', params.max_price.toString());
    if (params.min_area) urlParams.set('min_area', params.min_area.toString());
    if (params.max_area) urlParams.set('max_area', params.max_area.toString());
    if (params.layouts && params.layouts.length > 0) urlParams.set('layouts', params.layouts.join(','));
    if (params.building_name) urlParams.set('building_name', params.building_name);
    if (params.max_building_age) urlParams.set('max_building_age', params.max_building_age.toString());
    if (params.wards && params.wards.length > 0) urlParams.set('wards', params.wards.join(','));
    if (page > 1) urlParams.set('page', page.toString());
    
    // include_inactiveパラメータを追加
    const includeInactiveToUse = includeInactiveValue !== undefined ? includeInactiveValue : includeInactive;
    if (includeInactiveToUse) {
      urlParams.set('include_inactive', 'true');
    }
    
    const search = urlParams.toString();
    // 初回ロード時は履歴を置き換えない、それ以外は置き換える
    navigate({ search: search ? `?${search}` : '' }, { replace: !isInitialLoad });
    
    if (isInitialLoad) {
      setIsInitialLoad(false);
    }
  };

  const fetchProperties = async (params: SearchParams = {}, page = 1, shouldUpdateUrl = true) => {
    return fetchPropertiesWithIncludeInactive(params, page, shouldUpdateUrl, includeInactive);
  };

  const fetchPropertiesWithIncludeInactive = async (
    params: SearchParams = {}, 
    page = 1, 
    shouldUpdateUrl = true,
    includeInactiveParam?: boolean
  ) => {
    // 初回ロード時のみローディング表示、それ以外は既存の表示を維持
    if (initialLoading) {
      setLoading(true);
    }
    setError(null);
    try {
      const includeInactiveValue = includeInactiveParam !== undefined ? includeInactiveParam : includeInactive;
      
      const response = await propertyApi.searchProperties({
        ...params,
        page,
        per_page: 12,
        sort_by: params.sort_by || 'updated_at',
        sort_order: params.sort_order || 'desc',
        include_inactive: includeInactiveValue,
      });
      
      setProperties(response.properties);
      setTotalPages(response.total_pages);
      setTotalCount(response.total);
      setCurrentPage(page);
      
      // 販売終了物件の数をカウント
      const soldPropertiesCount = response.properties.filter((p: Property) => p.sold_at).length;
      setSoldCount(soldPropertiesCount);
      
      // URLパラメータを更新（フラグがtrueの場合のみ）
      if (shouldUpdateUrl) {
        updateUrlParams(params, page, includeInactiveValue);
      }
      
      // 初回ロード完了
      if (initialLoading) {
        setInitialLoading(false);
      }
    } catch (err) {
      setError('物件の取得に失敗しました。');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // URLパラメータからページ番号も復元
    const urlParams = new URLSearchParams(location.search);
    const page = Number(urlParams.get('page')) || 1;
    const params = getInitialParams();
    const includeInactiveFromUrl = getIncludeInactiveFromUrl();
    const viewModeFromUrl = getViewModeFromUrl();

    setSearchParams(params);
    setIncludeInactive(includeInactiveFromUrl);
    setViewMode(viewModeFromUrl);

    // 初回ロードまたはブラウザの戻る/進むボタンでの遷移時はURLを更新しない
    fetchPropertiesWithIncludeInactive(params, page, false, includeInactiveFromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // 物件一覧が更新されたらブックマーク状態を一括チェック
  useEffect(() => {
    const fetchBookmarkStatuses = async () => {
      // 認証チェック中または未認証の場合はスキップ
      if (authLoading || !isAuthenticated) {
        setBookmarkStatuses({});
        return;
      }

      // 物件がない場合はスキップ
      if (properties.length === 0) {
        return;
      }

      try {
        const propertyIds = properties.map(p => p.id);
        const result = await BookmarkService.checkBookmarkStatusBulk(propertyIds);
        setBookmarkStatuses(result.bookmarks);
      } catch (error) {
        console.error('ブックマーク状態の一括取得に失敗:', error);
        setBookmarkStatuses({});
      }
    };

    fetchBookmarkStatuses();
  }, [properties, isAuthenticated, authLoading]);

  const handleSearch = (params: SearchParams) => {
    // クリアボタンから空のオブジェクトが渡された場合は、完全にリセット
    const newParams = Object.keys(params).length === 0 ? {} : { ...searchParams, ...params };
    setSearchParams(newParams);
    fetchProperties(newParams, 1);
  };

  const handleSortChange = (event: SelectChangeEvent<string>) => {
    const value = event.target.value;
    const [sortBy, sortOrder] = value.split('-');
    const newParams = { ...searchParams, sort_by: sortBy, sort_order: sortOrder };
    setSearchParams(newParams);
    fetchProperties(newParams, 1);
  };

  const handlePageChange = (_: React.ChangeEvent<unknown>, page: number) => {
    fetchProperties(searchParams, page);
    window.scrollTo(0, 0);
  };

  const handleViewModeChange = (_: React.MouseEvent<HTMLElement>, newMode: 'properties' | 'buildings' | null) => {
    if (newMode !== null && newMode !== viewMode) {
      setViewMode(newMode);
      
      // URLパラメータを更新
      const urlParams = new URLSearchParams(location.search);
      if (newMode === 'buildings') {
        urlParams.set('view', 'buildings');
      } else {
        urlParams.delete('view');
      }
      
      // 履歴に追加（replaceではなくpushを使用）
      navigate({ search: urlParams.toString() ? `?${urlParams.toString()}` : '' }, { replace: false });
    }
  };

  return (
    <Container maxWidth="xl" sx={{ 
      py: 4, 
      px: isMobile ? 1 : 3
    }}>
      <Box sx={{ 
        display: 'flex', 
        flexDirection: { xs: 'column', sm: 'row' },
        justifyContent: 'space-between', 
        alignItems: { xs: 'flex-start', sm: 'center' },
        gap: { xs: 2, sm: 0 },
        mb: 3 
      }}>
        <Typography variant={isMobile ? "h5" : "h4"} component="h1">
          物件検索
        </Typography>
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={handleViewModeChange}
          aria-label="表示モード"
          sx={{ 
            flexShrink: 0,
            '& .MuiToggleButton-root': {
              minWidth: { xs: 85, sm: 'auto' },
              whiteSpace: 'nowrap',
              fontSize: { xs: '0.875rem', sm: '0.875rem' },
              px: { xs: 1.5, sm: 2 },
              py: { xs: 1, sm: 1 }
            }
          }}
        >
          <ToggleButton value="properties" aria-label="物件一覧">
            <ViewListIcon sx={{ mr: { xs: 0.5, sm: 1 }, fontSize: { xs: '1rem', sm: '1.25rem' } }} />
            物件一覧
          </ToggleButton>
          <ToggleButton value="buildings" aria-label="建物一覧">
            <ApartmentIcon sx={{ mr: { xs: 0.5, sm: 1 }, fontSize: { xs: '1rem', sm: '1.25rem' } }} />
            建物一覧
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      <SearchForm onSearch={handleSearch} loading={loading && !initialLoading} initialValues={searchParams} />

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {viewMode === 'buildings' ? (
        // 建物一覧表示
        <BuildingGroupedList
          searchParams={searchParams}
          includeInactive={includeInactive}
          onIncludeInactiveChange={(newValue) => {
            setIncludeInactive(newValue);
            setCurrentPage(1);
            // 新しい値を直接渡す
            fetchPropertiesWithIncludeInactive(searchParams, 1, true, newValue);
          }}
        />
      ) : (
        // 物件一覧表示
        <>
          <Box sx={{ mb: 2 }}>
            <Box sx={{ 
              display: 'flex', 
              flexDirection: { xs: 'column', sm: 'row' },
              justifyContent: 'space-between', 
              alignItems: { xs: 'flex-start', sm: 'center' },
              gap: { xs: 2, sm: 0 },
              mb: 1 
            }}>
              <Box sx={{ 
                display: 'flex', 
                flexDirection: { xs: 'column', sm: 'row' },
                alignItems: { xs: 'flex-start', sm: 'center' }, 
                gap: { xs: 1, sm: 2 }
              }}>
                <Typography variant="body1" color="text.secondary">
                  検索結果: {totalCount}件
                </Typography>
                {includeInactive && soldCount > 0 && (
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      backgroundColor: '#f5f5f5',
                      px: 1.5,
                      py: 0.5,
                      borderRadius: 1,
                      border: '1px solid #e0e0e0'
                    }}
                  >
                    <Box
                      sx={{
                        width: 12,
                        height: 12,
                        backgroundColor: '#d32f2f',
                        borderRadius: '50%'
                      }}
                    />
                    <Typography variant="body2" color="text.secondary">
                      販売終了: {soldCount}件
                    </Typography>
                  </Box>
                )}
              </Box>
              {!loading && properties.length > 0 && (
                <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 200 } }}>
                  <InputLabel id="sort-select-label">並び替え</InputLabel>
                  <Select
                    labelId="sort-select-label"
                    id="sort-select"
                    value={`${searchParams.sort_by || 'updated_at'}-${searchParams.sort_order || 'desc'}`}
                    label="並び替え"
                    onChange={handleSortChange}
                  >
                    <MenuItem value="updated_at-desc">更新日（新しい順）</MenuItem>
                    <MenuItem value="updated_at-asc">更新日（古い順）</MenuItem>
                    <MenuItem value="price-desc">価格（高い順）</MenuItem>
                    <MenuItem value="price-asc">価格（安い順）</MenuItem>
                    <MenuItem value="area-desc">面積（広い順）</MenuItem>
                    <MenuItem value="area-asc">面積（狭い順）</MenuItem>
                    <MenuItem value="built_year-desc">築年数（新しい順）</MenuItem>
                    <MenuItem value="built_year-asc">築年数（古い順）</MenuItem>
                    <MenuItem value="tsubo_price-desc">坪単価（高い順）</MenuItem>
                    <MenuItem value="tsubo_price-asc">坪単価（安い順）</MenuItem>
                  </Select>
                </FormControl>
              )}
            </Box>
            <FormControlLabel
              control={
                <Checkbox
                  checked={includeInactive}
                  onChange={(e) => {
                    const newIncludeInactive = e.target.checked;
                    setIncludeInactive(newIncludeInactive);
                    setCurrentPage(1);
                    // 新しい値を直接渡す
                    fetchPropertiesWithIncludeInactive(searchParams, 1, true, newIncludeInactive);
                  }}
                />
              }
              label="販売終了物件を含む"
            />
          </Box>

          {initialLoading && loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
              <CircularProgress />
            </Box>
          ) : properties.length === 0 && !loading ? (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <Typography variant="h6" color="text.secondary">
                物件が見つかりませんでした
              </Typography>
            </Box>
          ) : (
            <>
              <Box sx={{ position: 'relative' }}>
                {/* ページ遷移中は半透明のオーバーレイを表示 */}
                {!initialLoading && loading && (
                  <Box
                    sx={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      backgroundColor: 'rgba(255, 255, 255, 0.7)',
                      zIndex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <CircularProgress />
                  </Box>
                )}
                
                <Grid container spacing={{ xs: 2, sm: 3 }} sx={{ opacity: !initialLoading && loading ? 0.5 : 1, transition: 'opacity 0.2s' }}>
                  {properties.map((property) => (
                    <Grid item key={property.id} xs={12} sm={6} md={4}>
                      <PropertyCard
                        property={property}
                        initialBookmarked={bookmarkStatuses[property.id.toString()] || false}
                      />
                    </Grid>
                  ))}
                </Grid>
              </Box>

              {totalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
                  <Pagination
                    count={totalPages}
                    page={currentPage}
                    onChange={handlePageChange}
                    color="primary"
                    size="large"
                    disabled={loading}
                  />
                </Box>
              )}
            </>
          )}
        </>
      )}
    </Container>
  );
};

export default PropertyListPage;