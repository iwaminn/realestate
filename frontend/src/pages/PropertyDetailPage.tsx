import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Chip,
  Button,
  CircularProgress,
  Alert,
  Divider,
  List,
  ListItem,
  ListItemText,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  LocationOn,
  SquareFoot,
  Apartment,
  CalendarToday,
  OpenInNew,
  ArrowBack,
  Timeline,
  Stairs,
  Explore,
  Business,
  Train,
  Home,
  Cached,
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { propertyApi } from '../api/propertyApi';
import { PropertyDetail } from '../types/property';

const PropertyDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [propertyDetail, setPropertyDetail] = useState<PropertyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      fetchPropertyDetail(parseInt(id));
    }
  }, [id]);

  const fetchPropertyDetail = async (propertyId: number) => {
    try {
      setLoading(true);
      const data = await propertyApi.getPropertyDetail(propertyId);
      console.log('Property Detail Data:', data);
      console.log('Building Name:', data.master_property?.building?.normalized_name);
      console.log('Room Number:', data.master_property?.room_number);
      setPropertyDetail(data);
    } catch (err) {
      setError('物件詳細の取得に失敗しました。');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const formatPrice = (price: number | undefined) => {
    if (!price) return '価格未定';
    
    // 1億円以上の場合
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      
      if (man === 0) {
        // ちょうど億の場合
        return `${oku}億円`;
      } else {
        // 億と万の組み合わせ
        return `${oku}億${man.toLocaleString()}万円`;
      }
    }
    
    // 1億円未満の場合
    return `${price.toLocaleString()}万円`;
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !propertyDetail) {
    return (
      <Box>
        <Alert severity="error">{error || '物件が見つかりません'}</Alert>
        <Button
          component={Link}
          to="/"
          startIcon={<ArrowBack />}
          sx={{ mt: 2 }}
        >
          物件一覧に戻る
        </Button>
      </Box>
    );
  }

  const { master_property, listings, price_histories_by_listing, price_timeline, price_consistency } = propertyDetail;
  const property = master_property;
  const building = property.building;

  // 統合価格履歴データの準備（物件単位）
  const priceChartData: any[] = [];
  
  // price_timelineがある場合はそれを使用
  if (price_timeline && price_timeline.timeline) {
    price_timeline.timeline.forEach((entry: any) => {
      const dataPoint: any = {
        date: format(new Date(entry.date), 'yyyy/MM/dd'),
        price: entry.price,
      };
      
      // ソース別の価格差がある場合は追加
      if (entry.has_discrepancy && entry.sources) {
        Object.entries(entry.sources).forEach(([source, price]) => {
          dataPoint[source] = price;
        });
      }
      
      priceChartData.push(dataPoint);
    });
  } else {
    // フォールバック：従来の方法で統合
    const dateMap = new Map<string, { prices: number[], sources: Set<string> }>();
    
    Object.entries(price_histories_by_listing).forEach(([listingId, histories]) => {
      const listing = listings.find(l => l.id === parseInt(listingId));
      if (!listing) return;
      
      histories.forEach(history => {
        const dateKey = format(new Date(history.recorded_at), 'yyyy/MM/dd');
        if (!dateMap.has(dateKey)) {
          dateMap.set(dateKey, { prices: [], sources: new Set() });
        }
        const entry = dateMap.get(dateKey)!;
        entry.prices.push(history.price);
        entry.sources.add(listing.source_site);
      });
    });
    
    // 日付ごとに代表価格を算出
    Array.from(dateMap.entries()).sort(([a], [b]) => a.localeCompare(b)).forEach(([date, data]) => {
      const uniquePrices = [...new Set(data.prices)];
      const representativePrice = uniquePrices.length === 1 ? uniquePrices[0] : Math.min(...uniquePrices);
      
      priceChartData.push({
        date,
        price: representativePrice,
        sourceCount: data.sources.size,
      });
    });
  }

  return (
    <Box>
      <Button
        component={Link}
        to="/"
        startIcon={<ArrowBack />}
        sx={{ mb: 2 }}
      >
        物件一覧に戻る
      </Button>

      <Paper elevation={1} sx={{ p: 3, mb: 3, opacity: property.has_active_listing === false ? 0.8 : 1 }}>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h4" component="h1">
                {building.normalized_name}
                {property.room_number && ` ${property.room_number}`}
              </Typography>
              <Box>
                {property.has_active_listing === false && (
                  <Chip label="掲載終了" color="error" sx={{ mr: 1 }} />
                )}
                {property.is_resale && (
                  <Chip 
                    icon={<Cached />} 
                    label="買い取り再販" 
                    color="warning" 
                    sx={{ mr: 1 }} 
                  />
                )}
                {property.source_sites.map(site => (
                  <Chip key={site} label={site} color="primary" sx={{ mr: 1 }} />
                ))}
                <Chip label={`${property.listing_count}件の掲載`} color="secondary" />
              </Box>
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Typography variant="h3" color="primary" gutterBottom>
              {property.min_price === property.max_price
                ? formatPrice(property.min_price)
                : `${formatPrice(property.min_price)} 〜 ${formatPrice(property.max_price)}`}
            </Typography>
            
            {/* 売出確認日の表示 */}
            {property.earliest_published_at && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body1" color="text.secondary">
                  売出確認日: {format(new Date(property.earliest_published_at), 'yyyy年MM月dd日', { locale: ja })}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  （販売開始から{Math.floor((new Date().getTime() - new Date(property.earliest_published_at).getTime()) / (1000 * 60 * 60 * 24))}日経過）
                </Typography>
              </Box>
            )}
            
            {/* 買い取り再販情報 */}
            {property.is_resale && property.resale_property_id && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                <Typography variant="body2">
                  この物件は買い取り再販物件です。
                  <Link to={`/properties/${property.resale_property_id}`} style={{ marginLeft: '8px' }}>
                    元の物件情報を見る
                  </Link>
                </Typography>
              </Alert>
            )}

            <List>
              <ListItem>
                <LocationOn sx={{ mr: 2 }} />
                <ListItemText primary="住所" secondary={building.address} />
              </ListItem>
              {property.station_info && (
                <ListItem>
                  <Train sx={{ mr: 2 }} />
                  <ListItemText 
                    primary="交通" 
                    secondary={
                      <Box component="div" style={{ whiteSpace: 'pre-line' }}>
                        {property.station_info}
                      </Box>
                    }
                  />
                </ListItem>
              )}
              {property.area && (
                <ListItem>
                  <SquareFoot sx={{ mr: 2 }} />
                  <ListItemText primary="専有面積" secondary={`${property.area}㎡`} />
                </ListItem>
              )}
              {property.balcony_area && (
                <ListItem>
                  <SquareFoot sx={{ mr: 2 }} />
                  <ListItemText primary="バルコニー面積" secondary={`${property.balcony_area}㎡`} />
                </ListItem>
              )}
              {property.layout && (
                <ListItem>
                  <Apartment sx={{ mr: 2 }} />
                  <ListItemText primary="間取り" secondary={property.layout} />
                </ListItem>
              )}
              {building.built_year && (
                <ListItem>
                  <CalendarToday sx={{ mr: 2 }} />
                  <ListItemText primary="築年" secondary={`${building.built_year}年（築${new Date().getFullYear() - building.built_year}年）`} />
                </ListItem>
              )}
              {property.floor_number && (
                <ListItem>
                  <Stairs sx={{ mr: 2 }} />
                  <ListItemText 
                    primary="階数" 
                    secondary={`${property.floor_number}階${building.total_floors ? ` / ${building.total_floors}階${building.basement_floors ? `地下${building.basement_floors}階建` : '建'}` : ''}`}
                  />
                </ListItem>
              )}
              {building.total_units && (
                <ListItem>
                  <Home sx={{ mr: 2 }} />
                  <ListItemText primary="総戸数" secondary={`${building.total_units}戸`} />
                </ListItem>
              )}
              {property.direction && (
                <ListItem>
                  <Explore sx={{ mr: 2 }} />
                  <ListItemText primary="方角" secondary={`${property.direction}向き`} />
                </ListItem>
              )}
              {building.land_rights && (
                <ListItem>
                  <Home sx={{ mr: 2 }} />
                  <ListItemText primary="権利形態" secondary={building.land_rights} />
                </ListItem>
              )}
              {building.parking_info && (
                <ListItem>
                  <LocationOn sx={{ mr: 2 }} />
                  <ListItemText primary="駐車場" secondary={building.parking_info} />
                </ListItem>
              )}
            </List>
          </Grid>
        </Grid>
      </Paper>

      {/* 掲載情報一覧 */}
      <Paper elevation={1} sx={{ p: 3, mb: 3 }}>
        <Typography variant="h5" gutterBottom>
          掲載情報一覧
        </Typography>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>掲載サイト</TableCell>
                <TableCell>タイトル</TableCell>
                <TableCell align="right">価格</TableCell>
                <TableCell align="right">管理費</TableCell>
                <TableCell align="right">修繕積立金</TableCell>
                <TableCell>不動産会社</TableCell>
                <TableCell>売出確認日</TableCell>
                <TableCell align="center">詳細</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listings.map((listing) => (
                <TableRow key={listing.id}>
                  <TableCell>
                    <Chip label={listing.source_site} size="small" />
                  </TableCell>
                  <TableCell>{listing.title}</TableCell>
                  <TableCell align="right">{formatPrice(listing.current_price)}</TableCell>
                  <TableCell align="right">
                    {listing.management_fee ? `${listing.management_fee.toLocaleString()}円` : '-'}
                  </TableCell>
                  <TableCell align="right">
                    {listing.repair_fund ? `${listing.repair_fund.toLocaleString()}円` : '-'}
                  </TableCell>
                  <TableCell>{listing.agency_name || '-'}</TableCell>
                  <TableCell>
                    {listing.first_published_at 
                      ? format(new Date(listing.first_published_at), 'yyyy/MM/dd', { locale: ja })
                      : listing.published_at
                      ? format(new Date(listing.published_at), 'yyyy/MM/dd', { locale: ja })
                      : format(new Date(listing.first_seen_at), 'yyyy/MM/dd', { locale: ja })}
                  </TableCell>
                  <TableCell align="center">
                    <Button
                      size="small"
                      startIcon={<OpenInNew />}
                      href={listing.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      見る
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* 価格推移グラフ */}
      {priceChartData.length > 0 && (
        <Paper elevation={1} sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
            <Timeline sx={{ mr: 1 }} />
            価格推移
          </Typography>
          
          {/* 価格一貫性情報 */}
          {price_consistency && price_consistency.consistency_score < 1 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              異なる情報源で価格差が検出されました（一貫性スコア: {(price_consistency.consistency_score * 100).toFixed(1)}%）
            </Alert>
          )}
          
          <Box sx={{ height: 400, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis
                  tickFormatter={(value) => `${value.toLocaleString()}万`}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toLocaleString()}万円`, '価格']}
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length > 0) {
                      const data = payload[0].payload;
                      return (
                        <div style={{ backgroundColor: 'white', padding: '10px', border: '1px solid #ccc' }}>
                          <p><strong>{label}</strong></p>
                          <p>価格: {data.price?.toLocaleString()}万円</p>
                          {data.sourceCount && data.sourceCount > 1 && (
                            <p style={{ fontSize: '0.9em', color: '#666' }}>
                              {data.sourceCount}つのソースから掲載
                            </p>
                          )}
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="price"
                  name="価格"
                  stroke="#1976d2"
                  strokeWidth={3}
                  dot={{ fill: '#1976d2' }}
                />
                
                {/* 価格差がある場合は各ソースの線も表示 */}
                {price_timeline && price_timeline.timeline && 
                 price_timeline.timeline.some((t: any) => t.has_discrepancy) && (
                  <>
                    {Array.from(new Set(listings.map(l => l.source_site))).map((source, index) => (
                      <Line
                        key={source}
                        type="monotone"
                        dataKey={source}
                        name={source}
                        stroke={`hsl(${(index + 1) * 120}, 70%, 50%)`}
                        strokeWidth={1}
                        strokeDasharray="5 5"
                        connectNulls
                      />
                    ))}
                  </>
                )}
              </LineChart>
            </ResponsiveContainer>
          </Box>
          
          {/* 価格変更サマリー */}
          {price_timeline && price_timeline.summary && (
            <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
              <Box>
                <Typography variant="body2" color="text.secondary">初回価格</Typography>
                <Typography variant="h6">{formatPrice(price_timeline.summary.initial_price)}</Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="text.secondary">現在価格</Typography>
                <Typography variant="h6">{formatPrice(price_timeline.summary.current_price)}</Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="text.secondary">変動額</Typography>
                <Typography variant="h6" color={price_timeline.summary.total_change > 0 ? 'error' : price_timeline.summary.total_change < 0 ? 'success' : 'inherit'}>
                  {price_timeline.summary.total_change > 0 ? '+' : ''}{price_timeline.summary.total_change}万円
                </Typography>
              </Box>
            </Box>
          )}
        </Paper>
      )}

      {/* 同じ建物の他の物件 */}
      <Button
        variant="outlined"
        startIcon={<Business />}
        onClick={() => navigate(`/buildings/${encodeURIComponent(building.normalized_name)}/properties`)}
        fullWidth
      >
        {building.normalized_name}の他の物件を見る
      </Button>
    </Box>
  );
};

export default PropertyDetailPage;