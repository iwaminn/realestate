import React, { useState, useCallback } from 'react';
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
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { SearchParams } from '../types/property';
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
    layout: initialValues?.layout || '',
    building_name: initialValues?.building_name || '',
    max_building_age: initialValues?.max_building_age || undefined,
  });

  // Autocomplete用の状態
  const [buildingOptions, setBuildingOptions] = useState<string[]>([]);
  const [buildingLoading, setBuildingLoading] = useState(false);
  const [buildingInputValue, setBuildingInputValue] = useState('');

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
        layout: initialValues.layout || '',
        building_name: initialValues.building_name || '',
        max_building_age: initialValues.max_building_age || undefined,
      });
      setBuildingInputValue(initialValues.building_name || '');
    }
  }, [initialValues]);

  const handleChange = (field: keyof SearchParams) => (
    event: React.ChangeEvent<HTMLInputElement | { value: unknown }>
  ) => {
    const value = event.target.value;
    setSearchParams({
      ...searchParams,
      [field]: value === '' ? undefined : value,
    });
  };

  const handleSelectChange = (field: keyof SearchParams) => (
    event: SelectChangeEvent<string | number>
  ) => {
    const value = event.target.value;
    setSearchParams({
      ...searchParams,
      [field]: value === '' ? undefined : value,
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
      layout: '',
      building_name: '',
      max_building_age: undefined,
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

          <Grid item xs={12} sm={6} md={3}>
            <TextField
              fullWidth
              label="最低価格"
              type="number"
              value={searchParams.min_price || ''}
              onChange={handleChange('min_price')}
              InputProps={{
                endAdornment: <InputAdornment position="end">万円</InputAdornment>,
              }}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <TextField
              fullWidth
              label="最高価格"
              type="number"
              value={searchParams.max_price || ''}
              onChange={handleChange('max_price')}
              InputProps={{
                endAdornment: <InputAdornment position="end">万円</InputAdornment>,
              }}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <TextField
              fullWidth
              label="最低面積"
              type="number"
              value={searchParams.min_area || ''}
              onChange={handleChange('min_area')}
              InputProps={{
                endAdornment: <InputAdornment position="end">㎡</InputAdornment>,
              }}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <TextField
              fullWidth
              label="最高面積"
              type="number"
              value={searchParams.max_area || ''}
              onChange={handleChange('max_area')}
              InputProps={{
                endAdornment: <InputAdornment position="end">㎡</InputAdornment>,
              }}
            />
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>間取り</InputLabel>
              <Select
                value={searchParams.layout || ''}
                onChange={handleSelectChange('layout')}
                label="間取り"
              >
                <MenuItem value="">すべて</MenuItem>
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
                <MenuItem value="4LDK">4LDK以上</MenuItem>
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