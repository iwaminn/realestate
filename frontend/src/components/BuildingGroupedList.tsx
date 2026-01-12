import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import {
  Box,
  Paper,
  Typography,
  CircularProgress,
  Pagination,
  Card,
  CardContent,
  Chip,
  Grid,
  Divider,
  Button,
  FormControlLabel,
  Checkbox,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material';
import {
  Apartment as ApartmentIcon,
  LocationOn as LocationIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';
import { SearchParams } from '../types/property';

interface Property {
  id: number;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  current_price: number | null;
  sold_at: string | null;
  has_active_listing: boolean;
}

interface Building {
  id: number;
  normalized_name: string;
  address: string | null;
  total_floors: number | null;
  built_year: number | null;
  built_month: number | null;
  construction_type: string | null;
  building_age: number | null;
  total_units?: number | null;
  avg_tsubo_price?: number | null;
}

interface BuildingGroup {
  building: Building;
  properties: Property[];
  total_properties: number;
}

interface BuildingGroupedListProps {
  searchParams: SearchParams;
  includeInactive: boolean;
  onIncludeInactiveChange?: (value: boolean) => void;
}

const BuildingGroupedList: React.FC<BuildingGroupedListProps> = ({
  searchParams,
  includeInactive,
  onIncludeInactiveChange,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [urlSearchParams, setUrlSearchParams] = useSearchParams();
  const [buildingGroups, setBuildingGroups] = useState<BuildingGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  // URLパラメータからページ番号を取得
  const initialPage = parseInt(urlSearchParams.get('page') || '1');
  const [page, setPage] = useState(initialPage);
  const [totalPages, setTotalPages] = useState(0);
  // URLパラメータから並び順を取得
  const initialSortBy = urlSearchParams.get('sort') || 'property_count_desc';
  const [sortBy, setSortBy] = useState<string>(initialSortBy);

  const fetchBuildingGroups = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      
      if (searchParams.min_price) params.append('min_price', searchParams.min_price.toString());
      if (searchParams.max_price) params.append('max_price', searchParams.max_price.toString());
      if (searchParams.min_area) params.append('min_area', searchParams.min_area.toString());
      if (searchParams.max_area) params.append('max_area', searchParams.max_area.toString());
      if (searchParams.layouts && searchParams.layouts.length > 0) {
        searchParams.layouts.forEach(layout => params.append('layouts', layout));
      }
      if (searchParams.building_name) params.append('building_name', searchParams.building_name);
      if (searchParams.max_building_age) params.append('max_building_age', searchParams.max_building_age.toString());
      if (searchParams.wards && searchParams.wards.length > 0) {
        searchParams.wards.forEach(ward => params.append('wards', ward));
      }
      if (searchParams.land_rights_types && searchParams.land_rights_types.length > 0) {
        searchParams.land_rights_types.forEach(type => params.append('land_rights_types', type));
      }
      params.append('page', page.toString());
      params.append('per_page', '20');
      params.append('include_inactive', includeInactive.toString());
      
      // 並び替えパラメータを追加
      if (sortBy !== 'property_count_desc') {
        params.append('sort_by', sortBy);
      }
      
      const response = await fetch(`/api/properties-grouped-by-buildings?${params.toString()}`);
      const data = await response.json();
      
      setBuildingGroups(data.buildings);
      setTotalCount(data.total);
      setTotalPages(data.total_pages);
    } catch (error) {
      console.error('Failed to fetch building groups:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuildingGroups();
  }, [page, searchParams, includeInactive, sortBy]);

  // URLパラメータが外部から変更された場合（ブラウザの戻る/進むボタンなど）
  useEffect(() => {
    const pageFromUrl = parseInt(urlSearchParams.get('page') || '1');
    const sortFromUrl = urlSearchParams.get('sort') || 'property_count_desc';
    
    if (pageFromUrl !== page) {
      setPage(pageFromUrl);
    }
    
    if (sortFromUrl !== sortBy) {
      setSortBy(sortFromUrl);
    }
  }, [location.search]); // URLの変更を監視

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    // URLパラメータを更新
    const newParams = new URLSearchParams(urlSearchParams);
    if (value > 1) {
      newParams.set('page', value.toString());
    } else {
      newParams.delete('page'); // 1ページ目の場合はパラメータから削除
    }
    setUrlSearchParams(newParams);
    window.scrollTo(0, 0);
  };


  const handleBuildingClick = (buildingId: number, buildingName: string) => {
    navigate(`/buildings/${buildingId}/properties`, { 
      state: { buildingName, includeInactive } 
    });
  };

  const handlePropertyClick = (propertyId: number) => {
    navigate(`/properties/${propertyId}`);
  };

  const formatPrice = (price: number | null) => {
    if (!price) return '-';
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      return man > 0 ? `${oku}億${man.toLocaleString()}万円` : `${oku}億円`;
    }
    return `${price.toLocaleString()}万円`;
  };

  const formatBuiltDate = (year: number | null, month: number | null) => {
    if (!year || year === 0) return '-';
    // monthが0の場合は表示しない（データ不正の可能性）
    if (month && month > 0 && month <= 12) {
      return `${year}年${month}月`;
    }
    return `${year}年`;
  };

  if (loading && buildingGroups.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!loading && buildingGroups.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <Typography variant="h6" color="text.secondary">
          該当する建物が見つかりません
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        {/* 上段：検索結果と並び替え */}
        <Box sx={{ 
          display: 'flex', 
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between', 
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 2,
          mb: 2
        }}>
          <Typography variant="body1" color="text.secondary">
            検索結果: {totalCount}棟
          </Typography>
          
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>並び替え</InputLabel>
            <Select
              value={sortBy}
              label="並び替え"
              onChange={(e) => {
                const newSortBy = e.target.value;
                setSortBy(newSortBy);
                
                // URLパラメータを更新
                const newParams = new URLSearchParams(urlSearchParams);
                if (newSortBy !== 'property_count_desc') {
                  newParams.set('sort', newSortBy);
                } else {
                  newParams.delete('sort');
                }
                // ページ番号をリセット
                newParams.delete('page');
                setUrlSearchParams(newParams);
                setPage(1);
              }}
            >
              <MenuItem value="property_count_desc">販売戸数（多い順）</MenuItem>
              <MenuItem value="property_count_asc">販売戸数（少ない順）</MenuItem>
              <MenuItem value="building_age_asc">築年数（新しい順）</MenuItem>
              <MenuItem value="building_age_desc">築年数（古い順）</MenuItem>
              <MenuItem value="total_units_desc">総戸数（多い順）</MenuItem>
              <MenuItem value="total_units_asc">総戸数（少ない順）</MenuItem>
              <MenuItem value="avg_tsubo_price_desc">平均坪単価（高い順）</MenuItem>
              <MenuItem value="avg_tsubo_price_asc">平均坪単価（安い順）</MenuItem>
            </Select>
          </FormControl>
        </Box>
        
        {/* 下段：販売終了物件を含むチェックボックス */}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={includeInactive}
                onChange={(e) => {
                  if (onIncludeInactiveChange) {
                    onIncludeInactiveChange(e.target.checked);
                  }
                }}
              />
            }
            label="販売終了物件を含む"
          />
        </Box>
      </Box>

      {buildingGroups.map((group) => (
        <Card key={group.building.id} sx={{ mb: 3 }}>
          <CardContent>
            {/* 建物情報ヘッダー */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <ApartmentIcon color="primary" />
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 'bold',
                      color: 'primary.main',
                      cursor: 'pointer',
                      '&:hover': { textDecoration: 'underline' },
                    }}
                    onClick={() => handleBuildingClick(group.building.id, group.building.normalized_name)}
                  >
                    {group.building.normalized_name}
                  </Typography>
                  <Chip
                    label={`${group.total_properties}件`}
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                </Box>

                <Box sx={{ display: 'flex', gap: 3, mb: 2, flexWrap: 'wrap' }}>
                  {group.building.address && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <LocationIcon fontSize="small" color="action" />
                      <Typography variant="body2" color="text.secondary">
                        {group.building.address}
                      </Typography>
                    </Box>
                  )}
                  {group.building.total_floors && (
                    <Typography variant="body2" color="text.secondary">
                      {group.building.total_floors}階建
                    </Typography>
                  )}
                  {group.building.total_units && (
                    <Typography variant="body2" color="text.secondary">
                      総戸数: {group.building.total_units}戸
                    </Typography>
                  )}
                  {group.building.avg_tsubo_price && (
                    <Typography variant="body2" color="text.secondary">
                      平均坪単価: {Math.round(group.building.avg_tsubo_price).toLocaleString()}万円
                    </Typography>
                  )}
                  <Typography variant="body2" color="text.secondary">
                    {formatBuiltDate(group.building.built_year, group.building.built_month)}
                    {group.building.building_age && group.building.building_age > 0 ? ` (築${group.building.building_age}年)` : ''}
                  </Typography>
                </Box>
              </Box>
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* 物件リスト（常に表示、最大5件） */}
            <Grid container spacing={2}>
              {group.properties.map((property) => (
                <Grid item xs={12} sm={6} md={4} key={property.id}>
                  <Paper
                    sx={{
                      p: 2,
                      cursor: 'pointer',
                      '&:hover': { bgcolor: 'action.hover' },
                      opacity: !property.has_active_listing ? 0.7 : 1,
                    }}
                    onClick={() => handlePropertyClick(property.id)}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" fontWeight="bold">
                        {property.room_number || `${property.floor_number}F`}
                      </Typography>
                      {!property.has_active_listing && (
                        <Chip label="販売終了" size="small" color="error" />
                      )}
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {property.floor_number}階 / {property.area}㎡ / {property.layout}
                      {property.direction && ` / ${property.direction}`}
                    </Typography>
                    <Typography variant="h6" color="primary" sx={{ mt: 1 }}>
                      {formatPrice(property.current_price)}
                    </Typography>
                  </Paper>
                </Grid>
              ))}
            </Grid>

            {/* 全物件を見るボタン */}
            {group.total_properties > 3 && (
              <Box sx={{ mt: 2, textAlign: 'center' }}>
                <Button
                  variant="outlined"
                  onClick={() => handleBuildingClick(group.building.id, group.building.normalized_name)}
                >
                  この建物の全{group.total_properties}件を見る
                </Button>
              </Box>
            )}
          </CardContent>
        </Card>
      ))}

      {totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={handlePageChange}
            color="primary"
            size="large"
          />
        </Box>
      )}
    </Box>
  );
};

export default BuildingGroupedList;