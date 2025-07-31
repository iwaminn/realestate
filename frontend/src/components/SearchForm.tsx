import React, { useState, useCallback, useEffect } from 'react';
import {
  Paper,
  Grid,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Box,
  InputAdornment,
  Autocomplete,
  CircularProgress,
  SelectChangeEvent,
  Chip,
  OutlinedInput,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { SearchParams, Area } from '../types/property';
import { propertyApi } from '../api/propertyApi';
import { debounce } from 'lodash';

interface SearchFormProps {
  onSearch: (params: SearchParams) => void;
  loading?: boolean;
  initialValues?: SearchParams;
}

const SearchForm: React.FC<SearchFormProps> = ({ onSearch, loading, initialValues }) => {
  const [searchParams, setSearchParams] = useState<SearchParams>({
    min_price: initialValues?.min_price || undefined,
    max_price: initialValues?.max_price || undefined,
    min_area: initialValues?.min_area || undefined,
    max_area: initialValues?.max_area || undefined,
    layouts: initialValues?.layouts || [],
    building_name: initialValues?.building_name || '',
    max_building_age: initialValues?.max_building_age || undefined,
    wards: initialValues?.wards || [],
  });

  // Autocomplete用の状態
  const [buildingOptions, setBuildingOptions] = useState<string[]>([]);
  const [buildingLoading, setBuildingLoading] = useState(false);
  const [buildingInputValue, setBuildingInputValue] = useState('');

  // エリア一覧の状態
  const [areas, setAreas] = useState<Area[]>([]);

  // エリア一覧を取得
  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const areaList = await propertyApi.getAreas();
        console.log('Fetched areas:', areaList);
        setAreas(areaList);
      } catch (error) {
        console.error('Failed to fetch areas:', error);
      }
    };
    fetchAreas();
  }, []);

  // 建物名サジェストAPIを呼び出す関数（デバウンス付き）
  const fetchBuildingSuggestions = useCallback(
    debounce(async (query: string) => {
      if (query.length < 1) {
        setBuildingOptions([]);
        return;
      }

      setBuildingLoading(true);
      try {
        const suggestions = await propertyApi.suggestBuildings(query);
        setBuildingOptions(suggestions);
      } catch (error) {
        console.error('Failed to fetch building suggestions:', error);
        setBuildingOptions([]);
      } finally {
        setBuildingLoading(false);
      }
    }, 300),
    []
  );

  // Update form when initialValues change (e.g., when navigating back)
  React.useEffect(() => {
    if (initialValues) {
      setSearchParams({
        min_price: initialValues.min_price || undefined,
        max_price: initialValues.max_price || undefined,
        min_area: initialValues.min_area || undefined,
        max_area: initialValues.max_area || undefined,
        layouts: initialValues.layouts || [],
        building_name: initialValues.building_name || '',
        max_building_age: initialValues.max_building_age || undefined,
        wards: initialValues.wards || [],
      });
      setBuildingInputValue(initialValues.building_name || '');
    }
  }, [initialValues]);


  const handleSelectChange = (field: keyof SearchParams) => (
    event: SelectChangeEvent<string | number>
  ) => {
    const value = event.target.value;
    setSearchParams({
      ...searchParams,
      [field]: value === '' ? undefined : value,
    });
  };

  const handleMultiSelectChange = (field: keyof SearchParams) => (
    event: SelectChangeEvent<string[]>
  ) => {
    const value = event.target.value;
    // On autofill we get a string of comma separated values
    const values = typeof value === 'string' ? value.split(',') : value;
    setSearchParams({
      ...searchParams,
      [field]: values,
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchParams);
  };

  const handleReset = () => {
    setSearchParams({
      min_price: undefined,
      max_price: undefined,
      min_area: undefined,
      max_area: undefined,
      layouts: [],
      building_name: '',
      max_building_age: undefined,
      wards: [],
    });
    setBuildingInputValue('');
    setBuildingOptions([]);
    onSearch({});
  };

  return (
    <Paper elevation={1} sx={{ p: 3, mb: 3 }}>
      <form onSubmit={handleSubmit}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Autocomplete
              freeSolo
              options={buildingOptions}
              loading={buildingLoading}
              inputValue={buildingInputValue}
              onInputChange={(_, newInputValue) => {
                setBuildingInputValue(newInputValue);
                fetchBuildingSuggestions(newInputValue);
                // input変更時にもsearchParamsを更新
                setSearchParams({
                  ...searchParams,
                  building_name: newInputValue || undefined,
                });
              }}
              onChange={(_, newValue) => {
                setSearchParams({
                  ...searchParams,
                  building_name: newValue || undefined,
                });
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="建物名"
                  placeholder="建物名で検索"
                  InputProps={{
                    ...params.InputProps,
                    startAdornment: (
                      <>
                        <InputAdornment position="start">
                          <SearchIcon />
                        </InputAdornment>
                        {params.InputProps.startAdornment}
                      </>
                    ),
                    endAdornment: (
                      <>
                        {buildingLoading ? <CircularProgress color="inherit" size={20} /> : null}
                        {params.InputProps.endAdornment}
                      </>
                    ),
                  }}
                />
              )}
            />
          </Grid>

          <Grid item xs={12} sm={12} md={6}>
            <FormControl fullWidth>
              <InputLabel id="area-multiple-chip-label">エリア</InputLabel>
              <Select
                labelId="area-multiple-chip-label"
                id="area-multiple-chip"
                multiple
                value={searchParams.wards || []}
                onChange={handleMultiSelectChange('wards')}
                input={<OutlinedInput id="select-multiple-chip" label="エリア" />}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Box>
                )}
                MenuProps={{
                  PaperProps: {
                    style: {
                      maxHeight: 48 * 4.5 + 8,
                      width: 250,
                    },
                  },
                }}
              >
                {areas.map((area) => (
                  <MenuItem key={area.name} value={area.name}>
                    {area.name} ({area.property_count}件)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Autocomplete
              freeSolo
              options={[1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 15000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, 100000]}
              value={searchParams.min_price || null}
              onChange={(_, newValue) => {
                setSearchParams({
                  ...searchParams,
                  min_price: typeof newValue === 'number' ? newValue : newValue ? parseInt(newValue) : undefined,
                });
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="最低価格"
                  type="number"
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {params.InputProps.endAdornment}
                        <InputAdornment position="end">万円</InputAdornment>
                      </>
                    ),
                  }}
                />
              )}
              getOptionLabel={(option) => option.toString()}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Autocomplete
              freeSolo
              options={[2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 15000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, 100000]}
              value={searchParams.max_price || null}
              onChange={(_, newValue) => {
                setSearchParams({
                  ...searchParams,
                  max_price: typeof newValue === 'number' ? newValue : newValue ? parseInt(newValue) : undefined,
                });
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="最高価格"
                  type="number"
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {params.InputProps.endAdornment}
                        <InputAdornment position="end">万円</InputAdornment>
                      </>
                    ),
                  }}
                />
              )}
              getOptionLabel={(option) => option.toString()}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Autocomplete
              freeSolo
              options={[30, 40, 50, 60, 70, 80, 90, 100, 120]}
              value={searchParams.min_area || null}
              onChange={(_, newValue) => {
                setSearchParams({
                  ...searchParams,
                  min_area: typeof newValue === 'number' ? newValue : newValue ? parseFloat(newValue) : undefined,
                });
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="最低面積"
                  type="number"
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {params.InputProps.endAdornment}
                        <InputAdornment position="end">㎡</InputAdornment>
                      </>
                    ),
                  }}
                />
              )}
              getOptionLabel={(option) => option.toString()}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Autocomplete
              freeSolo
              options={[40, 50, 60, 70, 80, 90, 100, 120, 150]}
              value={searchParams.max_area || null}
              onChange={(_, newValue) => {
                setSearchParams({
                  ...searchParams,
                  max_area: typeof newValue === 'number' ? newValue : newValue ? parseFloat(newValue) : undefined,
                });
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="最高面積"
                  type="number"
                  InputProps={{
                    ...params.InputProps,
                    endAdornment: (
                      <>
                        {params.InputProps.endAdornment}
                        <InputAdornment position="end">㎡</InputAdornment>
                      </>
                    ),
                  }}
                />
              )}
              getOptionLabel={(option) => option.toString()}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={6}>
            <FormControl fullWidth>
              <InputLabel id="layout-multiple-chip-label">間取り</InputLabel>
              <Select
                labelId="layout-multiple-chip-label"
                id="layout-multiple-chip"
                multiple
                value={searchParams.layouts || []}
                onChange={handleMultiSelectChange('layouts')}
                input={<OutlinedInput id="select-multiple-layout-chip" label="間取り" />}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Box>
                )}
                MenuProps={{
                  PaperProps: {
                    style: {
                      maxHeight: 48 * 4.5 + 8,
                      width: 250,
                    },
                  },
                }}
              >
                <MenuItem value="1R">1R</MenuItem>
                <MenuItem value="1K">1K</MenuItem>
                <MenuItem value="1DK">1DK</MenuItem>
                <MenuItem value="1LDK">1LDK</MenuItem>
                <MenuItem value="2K">2K</MenuItem>
                <MenuItem value="2DK">2DK</MenuItem>
                <MenuItem value="2LDK">2LDK</MenuItem>
                <MenuItem value="3K">3K</MenuItem>
                <MenuItem value="3DK">3DK</MenuItem>
                <MenuItem value="3LDK">3LDK</MenuItem>
                <MenuItem value="4LDK">4LDK</MenuItem>
                <MenuItem value="4LDK以上">4LDK以上</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>築年数</InputLabel>
              <Select
                value={searchParams.max_building_age || ''}
                onChange={handleSelectChange('max_building_age')}
                label="築年数"
              >
                <MenuItem value="">すべて</MenuItem>
                <MenuItem value={5}>5年以内</MenuItem>
                <MenuItem value={10}>10年以内</MenuItem>
                <MenuItem value={15}>15年以内</MenuItem>
                <MenuItem value={20}>20年以内</MenuItem>
                <MenuItem value={25}>25年以内</MenuItem>
                <MenuItem value={30}>30年以内</MenuItem>
              </Select>
            </FormControl>
          </Grid>

        </Grid>

        <Box sx={{ mt: 3, display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
          <Button variant="outlined" type="button" onClick={handleReset} disabled={loading}>
            クリア
          </Button>
          <Button
            variant="contained"
            type="submit"
            disabled={loading}
            startIcon={<SearchIcon />}
          >
            検索
          </Button>
        </Box>
      </form>
    </Paper>
  );
};

export default SearchForm;