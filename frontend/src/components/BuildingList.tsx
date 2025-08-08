import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Typography,
  TextField,
  InputAdornment,
  IconButton,
  Chip,
  Button,
  CircularProgress,
  Tooltip,
} from '@mui/material';
import {
  Search as SearchIcon,
  Clear as ClearIcon,
  Home as HomeIcon,
  Apartment as ApartmentIcon,
} from '@mui/icons-material';
import { propertyApi } from '../api/propertyApi';

interface Building {
  id: number;
  normalized_name: string;
  address: string | null;
  total_floors: number | null;
  built_year: number | null;
  built_month: number | null;
  construction_type: string | null;
  station_info: string | null;
  property_count: number;
  active_listings: number;
  price_range: {
    min: number | null;
    max: number | null;
    avg: number | null;
  };
  building_age: number | null;
}

interface BuildingListProps {
  selectedWards?: string[];
  minPrice?: number;
  maxPrice?: number;
  maxBuildingAge?: number;
}

const BuildingList: React.FC<BuildingListProps> = ({
  selectedWards = [],
  minPrice,
  maxPrice,
  maxBuildingAge,
}) => {
  const navigate = useNavigate();
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [searchQuery, setSearchQuery] = useState('');
  const [tempSearchQuery, setTempSearchQuery] = useState('');

  const fetchBuildings = async () => {
    setLoading(true);
    try {
      const response = await propertyApi.searchBuildings({
        wards: selectedWards.length > 0 ? selectedWards : undefined,
        search: searchQuery || undefined,
        min_price: minPrice,
        max_price: maxPrice,
        max_building_age: maxBuildingAge,
        page: page + 1,
        per_page: rowsPerPage,
        sort_by: 'property_count',
        sort_order: 'desc',
      });

      setBuildings(response.buildings);
      setTotalCount(response.total);
    } catch (error) {
      console.error('Failed to fetch buildings:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBuildings();
  }, [page, rowsPerPage, searchQuery, selectedWards, minPrice, maxPrice, maxBuildingAge]);

  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSearch = () => {
    setSearchQuery(tempSearchQuery);
    setPage(0);
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      handleSearch();
    }
  };

  const handleBuildingClick = (buildingId: number, buildingName: string) => {
    navigate(`/buildings/${buildingId}`, { 
      state: { buildingName } 
    });
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

  return (
    <Box>
      <Box sx={{ mb: 3, display: 'flex', gap: 2, alignItems: 'center' }}>
        <TextField
          fullWidth
          variant="outlined"
          placeholder="建物名で検索..."
          value={tempSearchQuery}
          onChange={(e) => setTempSearchQuery(e.target.value)}
          onKeyPress={handleKeyPress}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
            endAdornment: tempSearchQuery && (
              <InputAdornment position="end">
                <IconButton
                  size="small"
                  onClick={() => {
                    setTempSearchQuery('');
                    setSearchQuery('');
                    setPage(0);
                  }}
                >
                  <ClearIcon />
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
        <Button
          variant="contained"
          onClick={handleSearch}
          disabled={loading}
        >
          検索
        </Button>
      </Box>

      <Paper sx={{ width: '100%', overflow: 'hidden' }}>
        <TableContainer sx={{ maxHeight: 'calc(100vh - 300px)' }}>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>建物名</TableCell>
                <TableCell>住所</TableCell>
                <TableCell align="center">階数</TableCell>
                <TableCell align="center">築年月</TableCell>
                <TableCell align="center">築年数</TableCell>
                <TableCell align="center">物件数</TableCell>
                <TableCell align="center">掲載数</TableCell>
                <TableCell align="center">価格帯</TableCell>
                <TableCell align="center">平均価格</TableCell>
                <TableCell align="center">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={10} align="center">
                    <CircularProgress />
                  </TableCell>
                </TableRow>
              ) : buildings.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={10} align="center">
                    <Typography color="textSecondary">
                      建物が見つかりません
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                buildings.map((building) => (
                  <TableRow
                    key={building.id}
                    hover
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 'bold',
                          color: 'primary.main',
                          '&:hover': { textDecoration: 'underline' },
                        }}
                        onClick={() => handleBuildingClick(building.id, building.normalized_name)}
                      >
                        {building.normalized_name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {building.address || '-'}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      {building.total_floors ? `${building.total_floors}F` : '-'}
                    </TableCell>
                    <TableCell align="center">
                      {formatBuiltDate(building.built_year, building.built_month)}
                    </TableCell>
                    <TableCell align="center">
                      {building.building_age ? `${building.building_age}年` : '-'}
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={building.property_count}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={building.active_listings}
                        size="small"
                        color={building.active_listings > 0 ? 'success' : 'default'}
                      />
                    </TableCell>
                    <TableCell align="center">
                      {building.price_range.min && building.price_range.max ? (
                        <Typography variant="body2">
                          {formatPrice(building.price_range.min)}
                          {building.price_range.min !== building.price_range.max && (
                            <>
                              <br />
                              〜{formatPrice(building.price_range.max)}
                            </>
                          )}
                        </Typography>
                      ) : (
                        '-'
                      )}
                    </TableCell>
                    <TableCell align="center">
                      {building.price_range.avg ? formatPrice(building.price_range.avg) : '-'}
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="建物内の物件を見る">
                        <IconButton
                          size="small"
                          color="primary"
                          onClick={() => handleBuildingClick(building.id, building.normalized_name)}
                        >
                          <ApartmentIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          rowsPerPageOptions={[20, 50, 100]}
          component="div"
          count={totalCount}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          labelRowsPerPage="表示件数:"
          labelDisplayedRows={({ from, to, count }) =>
            `${from}-${to} / 全${count}件`
          }
        />
      </Paper>
    </Box>
  );
};

export default BuildingList;