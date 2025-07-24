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
} from '@mui/material';
import SearchForm from '../components/SearchForm';
import PropertyCard from '../components/PropertyCard';
import { propertyApi } from '../api/propertyApi';
import { Property, SearchParams } from '../types/property';

const PropertyListPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [includeInactive, setIncludeInactive] = useState(false);
  
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
    if (urlParams.get('layout')) params.layout = urlParams.get('layout') || undefined;
    if (urlParams.get('building_name')) params.building_name = urlParams.get('building_name') || undefined;
    if (urlParams.get('max_building_age')) params.max_building_age = Number(urlParams.get('max_building_age'));
    
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
  const updateUrlParams = (params: SearchParams, page: number) => {
    const urlParams = new URLSearchParams();
    
    // 検索条件をURLパラメータに追加
    if (params.sort_by && params.sort_by !== 'updated_at') urlParams.set('sort_by', params.sort_by);
    if (params.sort_order && params.sort_order !== 'desc') urlParams.set('sort_order', params.sort_order);
    if (params.min_price) urlParams.set('min_price', params.min_price.toString());
    if (params.max_price) urlParams.set('max_price', params.max_price.toString());
    if (params.min_area) urlParams.set('min_area', params.min_area.toString());
    if (params.max_area) urlParams.set('max_area', params.max_area.toString());
    if (params.layout) urlParams.set('layout', params.layout);
    if (params.building_name) urlParams.set('building_name', params.building_name);
    if (params.max_building_age) urlParams.set('max_building_age', params.max_building_age.toString());
    if (page > 1) urlParams.set('page', page.toString());
    
    const search = urlParams.toString();
    // 初回ロード時は履歴を置き換えない、それ以外は置き換える
    navigate({ search: search ? `?${search}` : '' }, { replace: !isInitialLoad });
    
    if (isInitialLoad) {
      setIsInitialLoad(false);
    }
  };

  const fetchProperties = async (params: SearchParams = {}, page = 1, shouldUpdateUrl = true) => {
    setLoading(true);
    setError(null);
    try {
      const response = await propertyApi.searchProperties({
        ...params,
        page,
        per_page: 12,
        sort_by: params.sort_by || 'updated_at',
        sort_order: params.sort_order || 'desc',
      });
      setProperties(response.properties);
      setTotalPages(response.total_pages);
      setTotalCount(response.total);
      setCurrentPage(page);
      
      // URLパラメータを更新（フラグがtrueの場合のみ）
      if (shouldUpdateUrl) {
        updateUrlParams(params, page);
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
    setSearchParams(params);
    // 初回ロードまたはブラウザの戻る/進むボタンでの遷移時はURLを更新しない
    fetchProperties(params, page, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

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

  return (
    <Box>
      <Typography variant="h4" component="h1" gutterBottom>
        物件検索
      </Typography>

      <SearchForm onSearch={handleSearch} loading={loading} initialValues={searchParams} />

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ mb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="body1" color="text.secondary">
            検索結果: {totalCount}件
          </Typography>
          {!loading && properties.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 200 }}>
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
                <MenuItem value="price-asc">価格（安い順）</MenuItem>
                <MenuItem value="price-desc">価格（高い順）</MenuItem>
                <MenuItem value="area-desc">面積（広い順）</MenuItem>
                <MenuItem value="area-asc">面積（狭い順）</MenuItem>
                <MenuItem value="built_year-desc">築年数（新しい順）</MenuItem>
                <MenuItem value="built_year-asc">築年数（古い順）</MenuItem>
              </Select>
            </FormControl>
          )}
        </Box>
        <FormControlLabel
          control={
            <Checkbox
              checked={includeInactive}
              onChange={(e) => {
                setIncludeInactive(e.target.checked);
                setCurrentPage(1);
                fetchProperties(searchParams, 1);
              }}
            />
          }
          label="販売終了物件を含む"
        />
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : properties.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <Typography variant="h6" color="text.secondary">
            物件が見つかりませんでした
          </Typography>
        </Box>
      ) : (
        <>
          <Grid container spacing={3}>
            {properties.map((property) => (
              <Grid item key={property.id} xs={12} sm={6} md={4}>
                <PropertyCard property={property} />
              </Grid>
            ))}
          </Grid>

          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
              <Pagination
                count={totalPages}
                page={currentPage}
                onChange={handlePageChange}
                color="primary"
                size="large"
              />
            </Box>
          )}
        </>
      )}
    </Box>
  );
};

export default PropertyListPage;