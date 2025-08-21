import React, { useState, useEffect } from 'react';
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
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import ApartmentIcon from '@mui/icons-material/Apartment';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { propertyApi } from '../api/propertyApi';

// 東京23区のリスト
const TOKYO_WARDS = [
  { name: '港区', id: 'minato', popular: true },
  { name: '渋谷区', id: 'shibuya', popular: true },
  { name: '新宿区', id: 'shinjuku', popular: true },
  { name: '千代田区', id: 'chiyoda', popular: true },
  { name: '中央区', id: 'chuo', popular: true },
  { name: '文京区', id: 'bunkyo', popular: true },
  { name: '目黒区', id: 'meguro', popular: true },
  { name: '世田谷区', id: 'setagaya', popular: true },
  { name: '品川区', id: 'shinagawa' },
  { name: '大田区', id: 'ota' },
  { name: '杉並区', id: 'suginami' },
  { name: '中野区', id: 'nakano' },
  { name: '豊島区', id: 'toshima' },
  { name: '練馬区', id: 'nerima' },
  { name: '板橋区', id: 'itabashi' },
  { name: '北区', id: 'kita' },
  { name: '荒川区', id: 'arakawa' },
  { name: '足立区', id: 'adachi' },
  { name: '葛飾区', id: 'katsushika' },
  { name: '江戸川区', id: 'edogawa' },
  { name: '墨田区', id: 'sumida' },
  { name: '江東区', id: 'koto' },
  { name: '台東区', id: 'taito' },
];

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

  const handleAreaClick = (wardName: string) => {
    navigate(`/properties?wards=${encodeURIComponent(wardName)}`);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchText.trim()) {
      navigate(`/properties?building_name=${encodeURIComponent(searchText.trim())}`);
    }
  };

  const filteredWards = TOKYO_WARDS.filter((ward) =>
    ward.name.includes(searchText)
  );

  const popularWards = TOKYO_WARDS.filter((ward) => ward.popular);
  const otherWards = TOKYO_WARDS.filter((ward) => !ward.popular);


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
          <TextField
            fullWidth
            variant="standard"
            placeholder="建物名で検索（例：タワー、パーク）"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            InputProps={{
              disableUnderline: true,
              sx: { px: 2, py: 1 },
            }}
          />
          <IconButton type="submit" sx={{ p: '10px' }} aria-label="search">
            <SearchIcon />
          </IconButton>
        </Paper>
      </Box>

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
                23
              </Typography>
              <Typography variant="body2" color="text.secondary">
                対応エリア（区）
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

      {/* エリア選択 */}
      {searchText === '' ? (
        <>
          {/* 人気エリア */}
          <Box sx={{ mb: 6 }}>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
              <TrendingUpIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
              人気エリア
            </Typography>
            <Grid container spacing={2}>
              {popularWards.map((ward) => (
                <Grid item xs={12} sm={6} md={3} key={ward.id}>
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

          <Divider sx={{ my: 4 }} />

          {/* その他のエリア */}
          <Box>
            <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 'bold' }}>
              <LocationOnIcon sx={{ verticalAlign: 'middle', mr: 1 }} />
              その他のエリア
            </Typography>
            <Grid container spacing={2}>
              {otherWards.map((ward) => (
                <Grid item xs={6} sm={4} md={2} key={ward.id}>
                  <Card
                    sx={{
                      transition: 'all 0.3s',
                      '&:hover': {
                        transform: 'translateY(-2px)',
                        boxShadow: 3,
                        bgcolor: alpha(theme.palette.primary.main, 0.05),
                      },
                    }}
                  >
                    <CardActionArea onClick={() => handleAreaClick(ward.name)}>
                      <CardContent sx={{ textAlign: 'center', py: 2 }}>
                        <Typography variant="body1" sx={{ fontWeight: 'medium' }}>
                          {ward.name}
                        </Typography>
                        {areaStats[ward.name] && (
                          <Typography variant="caption" color="text.secondary">
                            {areaStats[ward.name]}件
                          </Typography>
                        )}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>
        </>
      ) : (
        /* 検索結果 */
        <Box>
          <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
            「{searchText}」を含むエリア
          </Typography>
          <Grid container spacing={2}>
            {filteredWards.length > 0 ? (
              filteredWards.map((ward) => (
                <Grid item xs={12} sm={6} md={3} key={ward.id}>
                  <Card>
                    <CardActionArea onClick={() => handleAreaClick(ward.name)}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          {ward.name}
                        </Typography>
                        {areaStats[ward.name] && (
                          <Typography variant="body2" color="text.secondary">
                            物件数: {areaStats[ward.name]}件
                          </Typography>
                        )}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grid>
              ))
            ) : (
              <Grid item xs={12}>
                <Typography color="text.secondary">
                  該当するエリアが見つかりませんでした
                </Typography>
              </Grid>
            )}
          </Grid>
        </Box>
      )}
    </Container>
  );
};

export default AreaSelectionPage;