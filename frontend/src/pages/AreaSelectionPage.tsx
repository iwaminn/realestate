import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { APP_CONFIG } from '../config/app';
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
  Skeleton,
  Button,
  Autocomplete,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import LocationCityIcon from '@mui/icons-material/LocationCity';
import UpdateIcon from '@mui/icons-material/Update';
import NewReleasesIcon from '@mui/icons-material/NewReleases';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import { propertyApi } from '../api/propertyApi';
import { getPopularWards } from '../constants/wardOrder';
import { debounce } from 'lodash';

const AreaSelectionPage: React.FC = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const [updatesCounts, setUpdatesCounts] = useState<{
    total_price_changes: number;
    total_new_listings: number;
  } | null>(null);
  const [wardCounts, setWardCounts] = useState<{
    [key: string]: { price_changes: number; new_listings: number };
  }>({});
  const [updatesLoading, setUpdatesLoading] = useState(true);
  const [buildingOptions, setBuildingOptions] = useState<Array<string | { value: string; label: string }>>([]);
  const [loadingBuildings, setLoadingBuildings] = useState(false);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchValueRef = useRef<string>('');  // 検索値をrefで管理（レンダリングを減らす）

  // 価格改定・新着物件の件数を取得する関数（サーバーサイドキャッシュを利用・軽量版）
  const fetchUpdatesCounts = useCallback(async () => {
      setUpdatesLoading(true);
      try {
        // 件数のみを取得する軽量APIを使用
        const data = await propertyApi.getRecentUpdatesCount(24);
        
        // 状態を更新
        setUpdatesCounts({
          total_price_changes: data.total_price_changes,
          total_new_listings: data.total_new_listings
        });
        setWardCounts(data.ward_counts);
        
      } catch (error) {
        console.error('Failed to fetch updates counts:', error);
      }
      setUpdatesLoading(false);
  }, []);

  // 価格改定・新着物件の件数を取得（初回のみ）
  useEffect(() => {
    fetchUpdatesCounts();
  }, [fetchUpdatesCounts]);

  // 建物名候補を取得する関数（デバウンス付き）- SearchFormと同じ処理
  const fetchBuildingSuggestions = useCallback(
    debounce(async (query: string) => {
      if (query.length < 1) {
        setBuildingOptions([]);
        setAutocompleteOpen(false);
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
          setAutocompleteOpen(true);  // サジェストを表示
        } else {
          setBuildingOptions([]);
          setAutocompleteOpen(false);
        }
      } catch (error) {
        console.error('Failed to fetch building suggestions:', error);
        setBuildingOptions([]);
        setAutocompleteOpen(false);
      } finally {
        setLoadingBuildings(false);
      }
    }, 150),  // デバウンス時間をさらに短縮
    []
  );

  const handleAreaClick = (wardName: string) => {
    navigate(`/properties?wards=${encodeURIComponent(wardName)}`);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // refから値を取得
    const query = searchValueRef.current || inputRef.current?.value || '';
    if (query.trim()) {
      navigate(`/properties?building_name=${encodeURIComponent(query.trim())}`);
    }
  };

  const popularWards = getPopularWards();


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
{APP_CONFIG.APP_NAME}
        </Typography>
        <Typography variant="h6" color="text.secondary" sx={{ mb: 4 }}>
{APP_CONFIG.APP_DESCRIPTION}
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
            width: '100%',
            mx: 'auto',
            boxShadow: 3,
            minHeight: 56,
          }}
        >
          <Autocomplete
            freeSolo
            options={buildingOptions}
            open={autocompleteOpen && buildingOptions.length > 0}
            onOpen={() => {
              if (buildingOptions.length > 0) {
                setAutocompleteOpen(true);
              }
            }}
            onClose={() => setAutocompleteOpen(false)}
            filterOptions={(x) => x}  // 入力遅延を防ぐため、フィルタリングを無効化
            disableCloseOnSelect={false}
            // サジェストリストの幅を検索バー全体に合わせる
            slotProps={{
              popper: {
                modifiers: [
                  {
                    name: 'offset',
                    options: {
                      offset: [0, 8],  // 検索バーとの間隔
                    },
                  },
                ],
                sx: {
                  // Popperの幅を親要素（Paper）より少し狭く（左右に余白）
                  width: 'calc(100% - 24px) !important',
                  marginLeft: '12px',
                  '& .MuiAutocomplete-listbox': {
                    maxHeight: '60vh',
                  },
                },
              },
              paper: {
                sx: {
                  // Paperの幅を100%に（Popperの幅を継承）
                  width: '100%',
                  boxShadow: 3,
                },
              },
            }}
            onInputChange={(_, newInputValue, reason) => {
              // refのみ更新（状態更新しない = レンダリングを防ぐ）
              if (reason === 'input') {
                searchValueRef.current = newInputValue;
                // サジェスト取得
                fetchBuildingSuggestions(newInputValue);
              } else if (reason === 'clear') {
                searchValueRef.current = '';
                setBuildingOptions([]);
              }
            }}
            onChange={(_, newValue) => {
              if (typeof newValue === 'string') {
                searchValueRef.current = newValue;
              } else if (newValue && typeof newValue === 'object' && 'value' in newValue) {
                // オブジェクト形式の場合（エイリアス対応）
                searchValueRef.current = newValue.value;  // 検索用の値を保存
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
                inputRef={inputRef}
                variant="standard"
                placeholder="建物名で検索（例：タワー、パーク）"
                InputProps={{
                  ...params.InputProps,
                  disableUnderline: true,
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon color="action" />
                    </InputAdornment>
                  ),
                  sx: { 
                    pl: 1, 
                    pr: 2,
                    py: 0,
                    '& input': {
                      padding: '12px 0',
                      textAlign: 'left',
                    }
                  },
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
        </Paper>
      </Box>

      {/* 価格改定・新着物件セクション */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ mb: 3 }}>
          <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
            <UpdateIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
            直近24時間の更新情報
          </Typography>
        </Box>
        
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} md={6}>
            <Paper 
              sx={{ 
                p: 2, 
                bgcolor: alpha(theme.palette.error.main, 0.05),
                cursor: updatesLoading ? 'default' : 'pointer',
                transition: 'all 0.3s',
                '&:hover': updatesLoading ? {} : {
                  transform: 'translateY(-2px)',
                  boxShadow: 3,
                }
              }}
              onClick={updatesLoading ? undefined : () => navigate('/updates?tab=0')}
            >
              <Box sx={{ 
                display: 'flex', 
                flexDirection: { xs: 'column', sm: 'row' },
                justifyContent: 'space-between', 
                alignItems: { xs: 'flex-start', sm: 'center' },
                gap: { xs: 1, sm: 0 }
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <UpdateIcon color="error" />
                  <Typography variant="h6">
                    価格改定物件
                  </Typography>
                  {updatesLoading ? (
                    <Skeleton variant="rectangular" width={40} height={24} sx={{ borderRadius: 3 }} />
                  ) : (
                    <Chip 
                      label={updatesCounts?.total_price_changes || 0} 
                      color="error" 
                      size="small"
                      sx={{ fontWeight: 'bold' }}
                    />
                  )}
                </Box>
                <Button size="small" color="error" endIcon={<ArrowForwardIcon />} disabled={updatesLoading}>
                  一覧を見る
                </Button>
              </Box>
              {/* エリア別ショートカット */}
              <Divider sx={{ my: 1.5 }} />
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <LocationCityIcon sx={{ fontSize: 16 }} />
                  エリア別に見る：
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                  {popularWards.map((ward) => (
                    <Button
                      key={ward.id}
                      size="small"
                      variant="contained"
                      color="error"
                      disabled={updatesLoading}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/updates?tab=0&ward=${encodeURIComponent(ward.name)}`);
                      }}
                      sx={{ 
                        minWidth: 'auto',
                        px: 1.5,
                        py: 0.5,
                        fontSize: '0.8rem',
                        fontWeight: 'medium',
                        bgcolor: alpha(theme.palette.error.main, 0.9),
                        '&:hover': {
                          bgcolor: theme.palette.error.main,
                          transform: 'scale(1.05)',
                        }
                      }}
                    >
                      {ward.name}
                      {updatesLoading ? (
                        <Skeleton variant="circular" width={16} height={16} sx={{ ml: 0.5 }} />
                      ) : wardCounts[ward.name]?.price_changes > 0 ? (
                        <Chip 
                          label={wardCounts[ward.name].price_changes} 
                          size="small" 
                          sx={{ 
                            ml: 0.5, 
                            height: 16,
                            fontSize: '0.7rem',
                            bgcolor: 'white',
                            color: theme.palette.error.main,
                            '& .MuiChip-label': { px: 0.5 }
                          }} 
                        />
                      ) : null}
                    </Button>
                  ))}
                </Box>
              </Box>
            </Paper>
          </Grid>
          <Grid item xs={12} md={6}>
            <Paper 
              sx={{ 
                p: 2, 
                bgcolor: alpha(theme.palette.success.main, 0.05),
                cursor: updatesLoading ? 'default' : 'pointer',
                transition: 'all 0.3s',
                '&:hover': updatesLoading ? {} : {
                  transform: 'translateY(-2px)',
                  boxShadow: 3,
                }
              }}
              onClick={updatesLoading ? undefined : () => navigate('/updates?tab=1')}
            >
              <Box sx={{ 
                display: 'flex', 
                flexDirection: { xs: 'column', sm: 'row' },
                justifyContent: 'space-between', 
                alignItems: { xs: 'flex-start', sm: 'center' },
                gap: { xs: 1, sm: 0 }
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <NewReleasesIcon color="success" />
                  <Typography variant="h6">
                    新着物件
                  </Typography>
                  {updatesLoading ? (
                    <Skeleton variant="rectangular" width={40} height={24} sx={{ borderRadius: 3 }} />
                  ) : (
                    <Chip 
                      label={updatesCounts?.total_new_listings || 0} 
                      color="success" 
                      size="small"
                      sx={{ fontWeight: 'bold' }}
                    />
                  )}
                </Box>
                <Button size="small" color="success" endIcon={<ArrowForwardIcon />} disabled={updatesLoading}>
                  一覧を見る
                </Button>
              </Box>
              {/* エリア別ショートカット */}
              <Divider sx={{ my: 1.5 }} />
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <LocationCityIcon sx={{ fontSize: 16 }} />
                  エリア別に見る：
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                  {popularWards.map((ward) => (
                    <Button
                      key={ward.id}
                      size="small"
                      variant="contained"
                      color="success"
                      disabled={updatesLoading}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/updates?tab=1&ward=${encodeURIComponent(ward.name)}`);
                      }}
                      sx={{ 
                        minWidth: 'auto',
                        px: 1.5,
                        py: 0.5,
                        fontSize: '0.8rem',
                        fontWeight: 'medium',
                        bgcolor: alpha(theme.palette.success.main, 0.9),
                        '&:hover': {
                          bgcolor: theme.palette.success.main,
                          transform: 'scale(1.05)',
                        }
                      }}
                    >
                      {ward.name}
                      {updatesLoading ? (
                        <Skeleton variant="circular" width={16} height={16} sx={{ ml: 0.5 }} />
                      ) : wardCounts[ward.name]?.new_listings > 0 ? (
                        <Chip 
                          label={wardCounts[ward.name].new_listings} 
                          size="small" 
                          sx={{ 
                            ml: 0.5, 
                            height: 16,
                            fontSize: '0.7rem',
                            bgcolor: 'white',
                            color: theme.palette.success.main,
                            '& .MuiChip-label': { px: 0.5 }
                          }} 
                        />
                      ) : null}
                    </Button>
                  ))}
                </Box>
              </Box>
            </Paper>
          </Grid>
        </Grid>
      </Box>

      {/* エリア選択 */}
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
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>
      </>
    </Container>
  );
};

export default AreaSelectionPage;