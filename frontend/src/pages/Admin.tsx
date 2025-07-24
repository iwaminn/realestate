import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Box,
  Chip,
  Alert,
  CircularProgress,
  Snackbar,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  IconButton,
  Tooltip,
  Tabs,
  Tab,
} from '@mui/material';
import {
  Merge as MergeIcon,
  Info as InfoIcon,
  Check as CheckIcon,
  Close as CloseIcon,
  Logout as LogoutIcon,
} from '@mui/icons-material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import AdminScraping from '../components/AdminScraping';
import BuildingDuplicateManager from '../components/BuildingDuplicateManager';
import BuildingMergeHistory from '../components/BuildingMergeHistory';
import PropertyMergeHistory from '../components/PropertyMergeHistory';
import ManualBuildingMerger from '../components/ManualBuildingMerger';
import ManualPropertyMerger from '../components/ManualPropertyMerger';

interface DuplicateCandidate {
  property1_id: number;
  property2_id: number;
  building_name: string;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction1: string | null;
  direction2: string | null;
  price1: number | null;
  price2: number | null;
  agency1: string | null;
  agency2: string | null;
  room_number1: string | null;
  room_number2: string | null;
  similarity_score: number;
}

interface PropertyDetail {
  id: number;
  building_id: number;
  building_name: string;
  room_number: string | null;
  floor_number: number | null;
  area: number | null;
  layout: string | null;
  direction: string | null;
  listings: Array<{
    id: number;
    source_site: string;
    url: string;
    title: string;
    current_price: number | null;
    agency_name: string | null;
    is_active: boolean;
    last_scraped_at: string | null;
  }>;
}

const Admin: React.FC = () => {
  const { isAuthenticated, username, isLoading, logout } = useAuth();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState(0);
  const [propertySubTab, setPropertySubTab] = useState(0);
  const [buildingSubTab, setBuildingSubTab] = useState(0);
  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPair, setSelectedPair] = useState<DuplicateCandidate | null>(null);
  const [property1Detail, setProperty1Detail] = useState<PropertyDetail | null>(null);
  const [property2Detail, setProperty2Detail] = useState<PropertyDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [primaryProperty, setPrimaryProperty] = useState<number | null>(null);
  const [merging, setMerging] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' });
  const [minSimilarity, setMinSimilarity] = useState(0.8);
  const [limit, setLimit] = useState(50);

  useEffect(() => {
    // 認証チェック完了後にのみリダイレクト
    if (!isLoading && !isAuthenticated) {
      navigate('/admin/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  useEffect(() => {
    fetchDuplicates();
  }, [minSimilarity, limit]);

  const fetchDuplicates = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/api/admin/duplicate-candidates', {
        params: { min_similarity: minSimilarity, limit }
      });
      setDuplicates(response.data);
    } catch (error) {
      console.error('Failed to fetch duplicates:', error);
      setSnackbar({ open: true, message: '重複候補の取得に失敗しました', severity: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const fetchPropertyDetail = async (propertyId: number): Promise<PropertyDetail | null> => {
    try {
      const response = await axios.get(`/api/admin/properties/${propertyId}`);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch property detail:', error);
      return null;
    }
  };

  const handleShowDetail = async (candidate: DuplicateCandidate) => {
    setSelectedPair(candidate);
    setDetailLoading(true);
    setPrimaryProperty(null);

    const [detail1, detail2] = await Promise.all([
      fetchPropertyDetail(candidate.property1_id),
      fetchPropertyDetail(candidate.property2_id)
    ]);

    setProperty1Detail(detail1);
    setProperty2Detail(detail2);
    setDetailLoading(false);
  };

  const handleMerge = async () => {
    if (!selectedPair || !primaryProperty) return;

    const secondaryProperty = primaryProperty === selectedPair.property1_id 
      ? selectedPair.property2_id 
      : selectedPair.property1_id;

    setMerging(true);
    try {
      await axios.post('/api/admin/merge-properties', {
        primary_property_id: primaryProperty,
        secondary_property_id: secondaryProperty
      });

      setSnackbar({ 
        open: true, 
        message: `物件ID ${secondaryProperty} を ${primaryProperty} に統合しました`, 
        severity: 'success' 
      });
      
      // リストから削除
      setDuplicates(prev => prev.filter(d => 
        !(d.property1_id === selectedPair.property1_id && d.property2_id === selectedPair.property2_id)
      ));
      
      setSelectedPair(null);
      setProperty1Detail(null);
      setProperty2Detail(null);
    } catch (error) {
      console.error('Failed to merge properties:', error);
      setSnackbar({ open: true, message: '物件の統合に失敗しました', severity: 'error' });
    } finally {
      setMerging(false);
    }
  };

  const handleExclude = async () => {
    if (!selectedPair) return;

    try {
      await axios.post('/api/admin/exclude-properties', {
        property1_id: selectedPair.property1_id,
        property2_id: selectedPair.property2_id,
        reason: '方角が異なる別物件として維持'
      });

      setSnackbar({ 
        open: true, 
        message: '物件を別物件として維持します', 
        severity: 'success' 
      });
      
      // リストから削除
      setDuplicates(prev => prev.filter(d => 
        !(d.property1_id === selectedPair.property1_id && d.property2_id === selectedPair.property2_id)
      ));
      
      setSelectedPair(null);
      setProperty1Detail(null);
      setProperty2Detail(null);
    } catch (error) {
      console.error('Failed to exclude properties:', error);
      setSnackbar({ open: true, message: '物件の除外に失敗しました', severity: 'error' });
    }
  };

  const getSimilarityColor = (score: number) => {
    if (score >= 0.95) return 'error';
    if (score >= 0.9) return 'warning';
    return 'info';
  };

  const renderPropertyCard = (property: PropertyDetail | null, isSelected: boolean, onSelect: () => void) => {
    if (!property) return null;

    return (
      <Paper 
        elevation={isSelected ? 8 : 3} 
        sx={{ 
          p: 2, 
          border: isSelected ? 2 : 0,
          borderColor: 'primary.main',
          cursor: 'pointer',
          '&:hover': { boxShadow: 6 }
        }}
        onClick={onSelect}
      >
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">物件ID: {property.id}</Typography>
          {isSelected && <Chip label="統合先" color="primary" />}
        </Box>
        
        <Grid container spacing={1}>
          <Grid item xs={12}>
            <Typography variant="body2" color="textSecondary">建物</Typography>
            <Typography>{property.building_name}</Typography>
          </Grid>
          {property.room_number && (
            <Grid item xs={6}>
              <Typography variant="body2" color="textSecondary">部屋番号</Typography>
              <Typography>{property.room_number}</Typography>
            </Grid>
          )}
          <Grid item xs={6}>
            <Typography variant="body2" color="textSecondary">階数</Typography>
            <Typography>{property.floor_number}階</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2" color="textSecondary">面積</Typography>
            <Typography>{property.area}㎡</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2" color="textSecondary">間取り</Typography>
            <Typography>{property.layout}</Typography>
          </Grid>
          <Grid item xs={6}>
            <Typography variant="body2" color="textSecondary">方角</Typography>
            <Typography>{property.direction || '-'}</Typography>
          </Grid>
        </Grid>

        <Box mt={2}>
          <Typography variant="body2" color="textSecondary" gutterBottom>
            掲載情報 ({property.listings.length}件)
          </Typography>
          {property.listings.length === 0 && (
            <Alert severity="warning" sx={{ mb: 1 }}>
              この物件には有効な掲載情報がありません
            </Alert>
          )}
          {property.listings.map(listing => (
            <Box key={listing.id} display="flex" alignItems="center" gap={1} mb={0.5}>
              <Chip 
                label={listing.source_site} 
                size="small" 
                color={listing.is_active ? 'success' : 'default'}
              />
              <Typography variant="body2">
                {listing.current_price ? `${listing.current_price}万円` : '価格不明'}
              </Typography>
              {listing.agency_name && (
                <Typography variant="caption" color="textSecondary">
                  {listing.agency_name}
                </Typography>
              )}
            </Box>
          ))}
        </Box>
      </Paper>
    );
  };

  // 認証チェック中はローディング表示
  if (isLoading) {
    return (
      <Container>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">
          管理画面
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <Typography variant="body1" color="text.secondary">
            ログイン中: {username}
          </Typography>
          <Button
            variant="outlined"
            startIcon={<LogoutIcon />}
            onClick={() => {
              logout();
              navigate('/');
            }}
          >
            ログアウト
          </Button>
        </Box>
      </Box>

      <Paper sx={{ mb: 3 }}>
        <Tabs value={activeTab} onChange={(_, value) => setActiveTab(value)}>
          <Tab label="物件重複管理" />
          <Tab label="建物重複管理" />
          <Tab label="スクレイピング" />
        </Tabs>
      </Paper>

      {activeTab === 0 && (
        <Box>
          <Paper sx={{ mb: 2 }}>
            <Tabs value={propertySubTab} onChange={(_, value) => setPropertySubTab(value)}>
              <Tab label="重複候補" />
              <Tab label="統合履歴" />
            </Tabs>
          </Paper>

          {propertySubTab === 0 && (
            <>
              <ManualPropertyMerger />
              <Paper sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={3} alignItems="center">
          <Grid item xs={12} md={6}>
            <Typography gutterBottom>類似度しきい値: {minSimilarity}</Typography>
            <Slider
              value={minSimilarity}
              onChange={(_, value) => setMinSimilarity(value as number)}
              min={0.5}
              max={1}
              step={0.05}
              marks
              valueLabelDisplay="auto"
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>表示件数</InputLabel>
              <Select value={limit} onChange={(e) => setLimit(e.target.value as number)}>
                <MenuItem value={20}>20件</MenuItem>
                <MenuItem value={50}>50件</MenuItem>
                <MenuItem value={100}>100件</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <Button 
              variant="contained" 
              fullWidth 
              onClick={fetchDuplicates}
              disabled={loading}
            >
              再検索
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {loading ? (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <Alert severity="info" sx={{ mb: 2 }}>
            {duplicates.length}件の重複候補が見つかりました
          </Alert>

          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>建物名</TableCell>
                  <TableCell align="center">階</TableCell>
                  <TableCell align="center">面積</TableCell>
                  <TableCell align="center">間取り</TableCell>
                  <TableCell align="center">方角</TableCell>
                  <TableCell align="center">価格</TableCell>
                  <TableCell align="center">類似度</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {duplicates.map((dup, index) => (
                  <TableRow key={index}>
                    <TableCell>{dup.building_name}</TableCell>
                    <TableCell align="center">{dup.floor_number}階</TableCell>
                    <TableCell align="center">{dup.area}㎡</TableCell>
                    <TableCell align="center">{dup.layout}</TableCell>
                    <TableCell align="center">
                      <Box>
                        <Typography variant="body2">{dup.direction1 || '-'}</Typography>
                        <Typography variant="body2" color="textSecondary">{dup.direction2 || '-'}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box>
                        <Typography variant="body2">{dup.price1 ? `${dup.price1}万円` : '-'}</Typography>
                        <Typography variant="body2" color="textSecondary">{dup.price2 ? `${dup.price2}万円` : '-'}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Chip 
                        label={`${(dup.similarity_score * 100).toFixed(0)}%`}
                        color={getSimilarityColor(dup.similarity_score)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="詳細を表示">
                        <IconButton 
                          size="small" 
                          onClick={() => handleShowDetail(dup)}
                          color="primary"
                        >
                          <InfoIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}

      <Dialog open={!!selectedPair} onClose={() => setSelectedPair(null)} maxWidth="lg" fullWidth>
        <DialogTitle>
          物件詳細比較
          {selectedPair && (
            <Chip 
              label={`類似度: ${(selectedPair.similarity_score * 100).toFixed(0)}%`}
              color={getSimilarityColor(selectedPair.similarity_score)}
              sx={{ ml: 2 }}
            />
          )}
        </DialogTitle>
        <DialogContent>
          {detailLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : (
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                {renderPropertyCard(
                  property1Detail,
                  primaryProperty === selectedPair?.property1_id,
                  () => setPrimaryProperty(selectedPair?.property1_id || null)
                )}
              </Grid>
              <Grid item xs={12} md={6}>
                {renderPropertyCard(
                  property2Detail,
                  primaryProperty === selectedPair?.property2_id,
                  () => setPrimaryProperty(selectedPair?.property2_id || null)
                )}
              </Grid>
            </Grid>
          )}
          
          {!detailLoading && primaryProperty && (
            <>
              <Alert severity="info" sx={{ mt: 2 }}>
                物件ID {primaryProperty} を統合先として選択しました。
                もう一方の物件の掲載情報がこの物件に統合されます。
              </Alert>
              {/* 統合先の物件に掲載情報がない場合の警告 */}
              {((primaryProperty === property1Detail?.id && property1Detail?.listings.length === 0) ||
                (primaryProperty === property2Detail?.id && property2Detail?.listings.length === 0)) && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  注意: 統合先の物件には有効な掲載情報がありません。
                  通常は掲載情報がある物件を統合先として選択することを推奨します。
                </Alert>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedPair(null)}>キャンセル</Button>
          <Button 
            onClick={handleExclude}
            variant="outlined"
            startIcon={<CloseIcon />}
          >
            別物件として維持
          </Button>
          <Button 
            onClick={handleMerge} 
            variant="contained" 
            startIcon={<MergeIcon />}
            disabled={!primaryProperty || merging}
          >
            {merging ? '統合中...' : '統合実行'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
            </>
          )}

          {propertySubTab === 1 && (
            <PropertyMergeHistory />
          )}
        </Box>
      )}

      {activeTab === 1 && (
        <Box>
          <Paper sx={{ mb: 2 }}>
            <Tabs value={buildingSubTab} onChange={(_, value) => setBuildingSubTab(value)}>
              <Tab label="重複候補" />
              <Tab label="統合履歴" />
            </Tabs>
          </Paper>

          {buildingSubTab === 0 && (
            <>
              <ManualBuildingMerger />
              <BuildingDuplicateManager />
            </>
          )}

          {buildingSubTab === 1 && (
            <BuildingMergeHistory />
          )}
        </Box>
      )}

      {activeTab === 2 && (
        <Box>
          <AdminScraping />
        </Box>
      )}
    </Container>
  );
};

export default Admin;