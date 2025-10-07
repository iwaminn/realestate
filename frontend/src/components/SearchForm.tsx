import React, { useState, useEffect } from 'react';
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
  Collapse,
  useMediaQuery,
  useTheme,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import FilterListIcon from '@mui/icons-material/FilterList';
import { SearchParams, Area } from '../types/property';
import { propertyApi } from '../api/propertyApi';
import { debounce } from 'lodash';

interface SearchFormProps {
  onSearch: (params: SearchParams) => void;
  loading?: boolean;
  initialValues?: SearchParams;
}

const SearchForm: React.FC<SearchFormProps> = ({ onSearch, loading, initialValues }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [expandedFilters, setExpandedFilters] = useState(!isMobile);
  
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

  // Autocomplete用の状態 - エイリアス対応
  const [buildingOptions, setBuildingOptions] = useState<Array<string | { value: string; label: string }>>([]);
  const [buildingLoading, setBuildingLoading] = useState(false);
  const [buildingInputValue, setBuildingInputValue] = useState('');
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);

  // エリア一覧の状態
  const [areas, setAreas] = useState<Area[]>([]);


  // エリア一覧を取得
  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const areaList = await propertyApi.getAreas();
        setAreas(areaList);
      } catch (error) {
        console.error('Failed to fetch areas:', error);
      }
    };
    fetchAreas();
  }, []);

  // 建物名サジェストAPIを呼び出す関数（デバウンス付き）- エイリアス対応
  // 建物名サジェストAPIを呼び出す関数（デバウンス付き）
  const fetchBuildingSuggestions = React.useMemo(
    () => debounce(async (query: string) => {
      if (query.length < 1) {
        setBuildingOptions([]);
        setAutocompleteOpen(false);
        return;
      }

      setBuildingLoading(true);
      try {
        const suggestions = await propertyApi.suggestBuildings(query);
        
        // APIレスポンスの形式を判定
        if (suggestions && suggestions.length > 0) {
          if (typeof suggestions[0] === 'object' && 'value' in suggestions[0]) {
            // 新形式（オブジェクト配列）
            setBuildingOptions(suggestions as Array<{ value: string; label: string }>);
          } else {
            // 旧形式（文字列配列）
            setBuildingOptions(suggestions as string[]);
          }
          setAutocompleteOpen(true);  // 候補がある場合は自動で開く
        } else {
          setBuildingOptions([]);
          setAutocompleteOpen(false);  // 候補がない場合は閉じる
        }
      } catch (error) {
        console.error('Failed to fetch building suggestions:', error);
        setBuildingOptions([]);
        setAutocompleteOpen(false);
      } finally {
        setBuildingLoading(false);
      }
    }, 200),  // デバウンス時間を200ms
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
    
    // モバイルで検索実行後は条件フォームを自動的に折りたたむ
    if (isMobile) {
      setExpandedFilters(false);
    }
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

  // フィルター条件がアクティブかどうかを判定
  const hasActiveFilters = () => {
    return !!(
      searchParams.min_price ||
      searchParams.max_price ||
      searchParams.min_area ||
      searchParams.max_area ||
      (searchParams.layouts && searchParams.layouts.length > 0) ||
      searchParams.max_building_age ||
      (searchParams.wards && searchParams.wards.length > 0)
    );
  };

  // URLパラメータから条件が設定されている場合、モバイルでもフォームを開いた状態にする
  React.useEffect(() => {
    if (isMobile && initialValues && hasActiveFilters()) {
      // ただし、検索実行直後は折りたたむために少し遅延させる
      const timer = setTimeout(() => {
        setExpandedFilters(false);
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isMobile, initialValues]);

  // アクティブな検索条件をチップとして表示する関数
  const renderActiveFilters = () => {
    const chips = [];

    if (searchParams.wards && searchParams.wards.length > 0) {
      chips.push(
        <Chip
          key="wards"
          label={`エリア: ${searchParams.wards.join(', ')}`}
          size="small"
          onDelete={() => {
            setSearchParams({ ...searchParams, wards: [] });
          }}
          sx={{ m: 0.5 }}
        />
      );
    }

    if (searchParams.min_price || searchParams.max_price) {
      const priceLabel = searchParams.min_price && searchParams.max_price
        ? `価格: ${searchParams.min_price.toLocaleString()}万～${searchParams.max_price.toLocaleString()}万円`
        : searchParams.min_price
        ? `価格: ${searchParams.min_price.toLocaleString()}万円以上`
        : `価格: ${searchParams.max_price!.toLocaleString()}万円以下`;
      
      chips.push(
        <Chip
          key="price"
          label={priceLabel}
          size="small"
          onDelete={() => {
            setSearchParams({ ...searchParams, min_price: undefined, max_price: undefined });
          }}
          sx={{ m: 0.5 }}
        />
      );
    }

    if (searchParams.min_area || searchParams.max_area) {
      const areaLabel = searchParams.min_area && searchParams.max_area
        ? `面積: ${searchParams.min_area}㎡～${searchParams.max_area}㎡`
        : searchParams.min_area
        ? `面積: ${searchParams.min_area}㎡以上`
        : `面積: ${searchParams.max_area}㎡以下`;
      
      chips.push(
        <Chip
          key="area"
          label={areaLabel}
          size="small"
          onDelete={() => {
            setSearchParams({ ...searchParams, min_area: undefined, max_area: undefined });
          }}
          sx={{ m: 0.5 }}
        />
      );
    }

    if (searchParams.layouts && searchParams.layouts.length > 0) {
      chips.push(
        <Chip
          key="layouts"
          label={`間取り: ${searchParams.layouts.join(', ')}`}
          size="small"
          onDelete={() => {
            setSearchParams({ ...searchParams, layouts: [] });
          }}
          sx={{ m: 0.5 }}
        />
      );
    }

    if (searchParams.max_building_age) {
      chips.push(
        <Chip
          key="building_age"
          label={`築${searchParams.max_building_age}年以内`}
          size="small"
          onDelete={() => {
            setSearchParams({ ...searchParams, max_building_age: undefined });
          }}
          sx={{ m: 0.5 }}
        />
      );
    }

    return chips;
  };

  return (
    <Paper elevation={1} sx={{ p: { xs: 2, sm: 3 }, mb: 3 }}>
      <form onSubmit={handleSubmit}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Box sx={{ 
              display: 'flex', 
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: { xs: 'stretch', sm: 'center' }, 
              gap: { xs: 2, sm: 1 }
            }}>
              <Autocomplete
                sx={{ flex: 1 }}
              freeSolo
              options={buildingOptions}
              loading={buildingLoading}
              value={null}
              inputValue={buildingInputValue}
              filterOptions={(x) => x}
              open={autocompleteOpen && buildingOptions.length > 0}
              onOpen={() => {
                if (buildingOptions.length > 0) {
                  setAutocompleteOpen(true);
                }
              }}
              onClose={() => setAutocompleteOpen(false)}
              ListboxProps={{
                style: {
                  maxHeight: '400px',
                }
              }}
              slotProps={{
                popper: {
                  modifiers: [
                    {
                      name: 'offset',
                      options: {
                        offset: [0, 8],
                      },
                    },
                  ],
                  sx: {
                    width: 'calc(100% - 24px) !important',
                    marginLeft: '12px',
                    '& .MuiAutocomplete-listbox': {
                      maxHeight: '400px',
                    },
                  },
                }
              }}
              getOptionLabel={(option) => {
                // オプションがオブジェクトの場合はvalueを、文字列の場合はそのまま返す
                if (typeof option === 'object' && 'value' in option) {
                  return option.value;
                }
                return typeof option === 'string' ? option : '';
              }}
              renderOption={(props, option) => {
                // エイリアス情報を含む場合は特別な表示
                if (typeof option === 'object' && 'label' in option) {
                  return (
                    <li {...props}>
                      <Box>
                        <div>{option.label}</div>
                        {option.label !== option.value && (
                          <Box component="span" sx={{ fontSize: '0.85em', color: 'text.secondary' }}>
                            {option.label.includes('旧:') && '※ 統合された建物名で検索されました'}
                            {option.label.includes('別名:') && '※ 別名でも検索可能です'}
                          </Box>
                        )}
                      </Box>
                    </li>
                  );
                }
                return <li {...props}>{option}</li>;
              }}
              onInputChange={(_, newInputValue) => {
                setBuildingInputValue(newInputValue);
                fetchBuildingSuggestions(newInputValue);
                // input変更時にもsearchParamsを更新（prev stateを使用）
                setSearchParams(prev => ({
                  ...prev,
                  building_name: newInputValue || '',
                }));
              }}
              onChange={(_, newValue) => {
                let buildingName = '';
                if (newValue && typeof newValue === 'object' && 'value' in newValue) {
                  buildingName = newValue.value;
                } else if (typeof newValue === 'string') {
                  buildingName = newValue;
                }
                setSearchParams(prev => ({
                  ...prev,
                  building_name: buildingName || '',
                }));
                setBuildingInputValue(buildingName);
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  label="建物名"
                  placeholder="建物名で検索"
                  type="search"
                  inputProps={{
                    ...params.inputProps,
                    enterKeyHint: 'search',
                  }}
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
            {isMobile && (
              <Button
                variant={hasActiveFilters() ? "contained" : "outlined"}
                onClick={() => setExpandedFilters(!expandedFilters)}
                startIcon={<FilterListIcon />}
                endIcon={expandedFilters ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                size="medium"
                fullWidth
                sx={{ 
                  whiteSpace: 'nowrap',
                  px: 2,
                  py: 1.5,
                }}
              >
                {hasActiveFilters() ? `条件(${
                  [
                    searchParams.min_price || searchParams.max_price ? 1 : 0,
                    searchParams.min_area || searchParams.max_area ? 1 : 0,
                    searchParams.layouts?.length || 0,
                    searchParams.max_building_age ? 1 : 0,
                    searchParams.wards?.length || 0,
                  ].reduce((a, b) => a + b, 0)
                })` : '条件'}
              </Button>
            )}
            </Box>
          </Grid>

          {/* アクティブな検索条件を表示 */}
          {hasActiveFilters() && (
            <Grid item xs={12}>
              <Box sx={{ 
                display: 'flex', 
                flexWrap: 'wrap', 
                gap: 0.5,
                alignItems: 'center',
                pt: 1,
                pb: 1,
                borderBottom: '1px solid',
                borderColor: 'divider'
              }}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                  検索条件:
                </Typography>
                {renderActiveFilters()}
              </Box>
            </Grid>
          )}

          <Grid item xs={12}>
            <Collapse in={expandedFilters || !isMobile} timeout="auto">
              <Grid container spacing={2}>
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
            <FormControl fullWidth>
              <InputLabel>最低価格</InputLabel>
              <Select
                value={searchParams.min_price || ''}
                onChange={handleSelectChange('min_price')}
                label="最低価格"
              >
                <MenuItem value="">指定なし</MenuItem>
                <MenuItem value={1000}>1,000万円</MenuItem>
                <MenuItem value={2000}>2,000万円</MenuItem>
                <MenuItem value={3000}>3,000万円</MenuItem>
                <MenuItem value={4000}>4,000万円</MenuItem>
                <MenuItem value={5000}>5,000万円</MenuItem>
                <MenuItem value={6000}>6,000万円</MenuItem>
                <MenuItem value={7000}>7,000万円</MenuItem>
                <MenuItem value={8000}>8,000万円</MenuItem>
                <MenuItem value={9000}>9,000万円</MenuItem>
                <MenuItem value={10000}>1億円</MenuItem>
                <MenuItem value={15000}>1億5,000万円</MenuItem>
                <MenuItem value={20000}>2億円</MenuItem>
                <MenuItem value={30000}>3億円</MenuItem>
                <MenuItem value={40000}>4億円</MenuItem>
                <MenuItem value={50000}>5億円</MenuItem>
                <MenuItem value={60000}>6億円</MenuItem>
                <MenuItem value={70000}>7億円</MenuItem>
                <MenuItem value={80000}>8億円</MenuItem>
                <MenuItem value={90000}>9億円</MenuItem>
                <MenuItem value={100000}>10億円</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>最高価格</InputLabel>
              <Select
                value={searchParams.max_price || ''}
                onChange={handleSelectChange('max_price')}
                label="最高価格"
              >
                <MenuItem value="">指定なし</MenuItem>
                <MenuItem value={2000}>2,000万円</MenuItem>
                <MenuItem value={3000}>3,000万円</MenuItem>
                <MenuItem value={4000}>4,000万円</MenuItem>
                <MenuItem value={5000}>5,000万円</MenuItem>
                <MenuItem value={6000}>6,000万円</MenuItem>
                <MenuItem value={7000}>7,000万円</MenuItem>
                <MenuItem value={8000}>8,000万円</MenuItem>
                <MenuItem value={9000}>9,000万円</MenuItem>
                <MenuItem value={10000}>1億円</MenuItem>
                <MenuItem value={15000}>1億5,000万円</MenuItem>
                <MenuItem value={20000}>2億円</MenuItem>
                <MenuItem value={30000}>3億円</MenuItem>
                <MenuItem value={40000}>4億円</MenuItem>
                <MenuItem value={50000}>5億円</MenuItem>
                <MenuItem value={60000}>6億円</MenuItem>
                <MenuItem value={70000}>7億円</MenuItem>
                <MenuItem value={80000}>8億円</MenuItem>
                <MenuItem value={90000}>9億円</MenuItem>
                <MenuItem value={100000}>10億円</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>最低面積</InputLabel>
              <Select
                value={searchParams.min_area || ''}
                onChange={handleSelectChange('min_area')}
                label="最低面積"
              >
                <MenuItem value="">指定なし</MenuItem>
                <MenuItem value={30}>30㎡</MenuItem>
                <MenuItem value={40}>40㎡</MenuItem>
                <MenuItem value={50}>50㎡</MenuItem>
                <MenuItem value={60}>60㎡</MenuItem>
                <MenuItem value={70}>70㎡</MenuItem>
                <MenuItem value={80}>80㎡</MenuItem>
                <MenuItem value={90}>90㎡</MenuItem>
                <MenuItem value={100}>100㎡</MenuItem>
                <MenuItem value={120}>120㎡</MenuItem>
                <MenuItem value={150}>150㎡</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>最高面積</InputLabel>
              <Select
                value={searchParams.max_area || ''}
                onChange={handleSelectChange('max_area')}
                label="最高面積"
              >
                <MenuItem value="">指定なし</MenuItem>
                <MenuItem value={40}>40㎡</MenuItem>
                <MenuItem value={50}>50㎡</MenuItem>
                <MenuItem value={60}>60㎡</MenuItem>
                <MenuItem value={70}>70㎡</MenuItem>
                <MenuItem value={80}>80㎡</MenuItem>
                <MenuItem value={90}>90㎡</MenuItem>
                <MenuItem value={100}>100㎡</MenuItem>
                <MenuItem value={120}>120㎡</MenuItem>
                <MenuItem value={150}>150㎡</MenuItem>
                <MenuItem value={200}>200㎡</MenuItem>
              </Select>
            </FormControl>
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
            </Collapse>
          </Grid>
        </Grid>

        <Box sx={{ 
          mt: 3, 
          display: 'flex', 
          gap: { xs: 1, sm: 2 }, 
          justifyContent: { xs: 'stretch', sm: 'flex-end' },
          flexDirection: 'row'
        }}>
          <Button 
            variant="outlined" 
            type="button" 
            onClick={handleReset} 
            disabled={loading}
            fullWidth={isMobile}
          >
            クリア
          </Button>
          <Button
            variant="contained"
            type="submit"
            disabled={loading}
            startIcon={<SearchIcon />}
            fullWidth={isMobile}
          >
            検索
          </Button>
        </Box>
      </form>
    </Paper>
  );
};

export default SearchForm;