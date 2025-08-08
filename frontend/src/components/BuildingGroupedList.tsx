import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  Collapse,
  IconButton,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
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
}

interface BuildingGroup {
  building: Building;
  properties: Property[];
  total_properties: number;
}

interface BuildingGroupedListProps {
  searchParams: SearchParams;
  includeInactive: boolean;
}

const BuildingGroupedList: React.FC<BuildingGroupedListProps> = ({
  searchParams,
  includeInactive,
}) => {
  const navigate = useNavigate();
  const [buildingGroups, setBuildingGroups] = useState<BuildingGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [expandedBuildings, setExpandedBuildings] = useState<Set<number>>(new Set());

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
      params.append('page', page.toString());
      params.append('per_page', '20');
      params.append('include_inactive', includeInactive.toString());
      
      const response = await fetch(`/api/v2/properties-grouped-by-buildings?${params.toString()}`);
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
  }, [page, searchParams, includeInactive]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    window.scrollTo(0, 0);
  };

  const toggleBuildingExpand = (buildingId: number) => {
    const newExpanded = new Set(expandedBuildings);
    if (newExpanded.has(buildingId)) {
      newExpanded.delete(buildingId);
    } else {
      newExpanded.add(buildingId);
    }
    setExpandedBuildings(newExpanded);
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
    if (!year) return '-';
    if (month) {
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
        <Typography variant="body1" color="text.secondary">
          検索結果: {totalCount}棟
        </Typography>
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

                <Box sx={{ display: 'flex', gap: 3, mb: 2 }}>
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
                  <Typography variant="body2" color="text.secondary">
                    {formatBuiltDate(group.building.built_year, group.building.built_month)}
                    {group.building.building_age && ` (築${group.building.building_age}年)`}
                  </Typography>
                </Box>
              </Box>

              <IconButton
                onClick={() => toggleBuildingExpand(group.building.id)}
                aria-label="expand"
              >
                {expandedBuildings.has(group.building.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </IconButton>
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
                      opacity: property.sold_at ? 0.7 : 1,
                    }}
                    onClick={() => handlePropertyClick(property.id)}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" fontWeight="bold">
                        {property.room_number || `${property.floor_number}F`}
                      </Typography>
                      {property.sold_at && (
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
            {group.total_properties > 6 && (
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