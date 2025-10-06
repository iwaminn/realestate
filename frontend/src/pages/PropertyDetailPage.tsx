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
  useMediaQuery,
  useTheme,
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
  AccountBalanceWallet,
  Map,
  Warning,
  Shield,
  ExpandMore,
  ExpandLess,
} from '@mui/icons-material';
import { BookmarkButton } from '../components/BookmarkButton';
import { getScraperDisplayName } from '../constants/scraperConstants';
// Geocoding utilities are loaded dynamically when needed
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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [propertyDetail, setPropertyDetail] = useState<PropertyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hazardMapUrl, setHazardMapUrl] = useState<string>('https://disaportal.gsi.go.jp/hazardmap/maps/index.html');
  const [showAllListings, setShowAllListings] = useState(false);

  useEffect(() => {
    if (id) {
      fetchPropertyDetail(parseInt(id));
    }
  }, [id]);

  const fetchPropertyDetail = async (propertyId: number) => {
    try {
      setLoading(true);
      const data = await propertyApi.getPropertyDetail(propertyId);
      setPropertyDetail(data);
      
      // 建物の住所から座標を取得してハザードマップURLを生成（非同期）
      if (data?.master_property?.building?.address) {
        const address = data.master_property.building.address;
        // 非同期で座標を取得（ページ表示をブロックしない）
        import('../utils/geocoding').then(({ getHazardMapUrl }) => {
          getHazardMapUrl(address).then(url => {
            setHazardMapUrl(url);
          }).catch(() => {
            // ハザードマップURL生成エラーは無視（デフォルトURLを使用）
          });
        });
      }
    } catch (err) {
      setError('物件詳細の取得に失敗しました。');
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
          to="/properties"
          startIcon={<ArrowBack />}
          sx={{ mt: 2 }}
        >
          物件一覧を見る
        </Button>
      </Box>
    );
  }

  const { master_property, listings, price_histories_by_listing, price_timeline, price_consistency } = propertyDetail;
  const property = master_property;
  const building = property.building;
  
  // 掲載情報を分類
  const all_listings = listings || [];
  const active_listings = all_listings.filter(l => l.is_active);

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
    const dateMap = new (Map as any)();

    Object.entries(price_histories_by_listing).forEach(([listingId, histories]) => {
      const listing = listings.find(l => l.id === parseInt(listingId));
      if (!listing) return;

      histories.forEach((history: any) => {
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
    const dateEntries: Array<[string, { prices: number[], sources: Set<string> }]> = Array.from(dateMap.entries());
    dateEntries.sort((a, b) => a[0].localeCompare(b[0])).forEach(([date, data]) => {
      const uniquePrices = [...new Set(data.prices)];
      const representativePrice = uniquePrices.length === 1 ? uniquePrices[0] : Math.min(...data.prices);
      
      priceChartData.push({
        date,
        price: representativePrice,
        sourceCount: data.sources.size,
      });
    });
  }

  // 住所から区を抽出
  const extractWard = (address: string | undefined): string | null => {
    if (!address) return null;
    const match = address.match(/(.*?[都道府県])(.+?区)/);
    return match ? match[2] : null;
  };

  const ward = extractWard(building?.address);
  const backToListUrl = ward ? `/properties?wards=${encodeURIComponent(ward)}` : '/properties';

  return (
    <Box>
      <Button
        component={Link}
        to={backToListUrl}
        startIcon={<ArrowBack />}
        sx={{ mb: 2 }}
      >
        {ward ? `${ward}の物件一覧を見る` : '物件一覧を見る'}
      </Button>

      <Paper elevation={1} sx={{ 
        p: 3, 
        mb: 3, 
        opacity: property.sold_at ? 0.85 : (property.has_active_listing === false ? 0.8 : 1),
        backgroundColor: property.sold_at ? '#f5f5f5' : 'background.paper',
        border: property.sold_at ? '2px solid #e0e0e0' : '1px solid rgba(0, 0, 0, 0.12)'
      }}>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Box sx={{ 
              display: 'flex', 
              flexDirection: { xs: 'column', md: 'row' },
              justifyContent: 'space-between', 
              alignItems: { xs: 'flex-start', md: 'center' }, 
              mb: 2, 
              gap: { xs: 2, md: 0 } 
            }}>
              <Typography 
                variant={isMobile ? "h5" : "h4"} 
                component="h1" 
                sx={{ 
                  color: property.sold_at ? 'text.secondary' : 'text.primary',
                  wordBreak: 'break-word',
                  hyphens: 'auto',
                  lineHeight: { xs: 1.3, md: 1.2 },
                  flex: 1
                }}
              >
                {property.display_building_name || building.normalized_name}
                {property.room_number && ` ${property.room_number}`}
              </Typography>
              <Box sx={{ 
                display: 'flex', 
                flexWrap: 'wrap', 
                gap: 1, 
                alignSelf: { xs: 'flex-start', md: 'center' } 
              }}>
                {property.sold_at && (
                  <Chip 
                    label="販売終了" 
                    sx={{ 
                      mr: 1,
                      backgroundColor: '#d32f2f',
                      color: 'white',
                      fontWeight: 'bold'
                    }} 
                  />
                )}
                {!property.sold_at && property.has_active_listing === false && (
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

                <Chip label={`${property.listing_count}件の掲載`} color="secondary" sx={{ mr: 1 }} />
                
                {/* ブックマークボタン */}
                <BookmarkButton 
                  propertyId={property.id} 
                  size="medium"
                />
              </Box>
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Typography variant="h3" color={property.sold_at ? "text.secondary" : "primary"} gutterBottom>
              {property.sold_at && property.last_sale_price ? (
                <>
                  <Box component="span" sx={{ textDecoration: 'line-through', opacity: 0.7 }}>
                    {formatPrice(property.last_sale_price)}
                  </Box>
                  <Box component="span" sx={{ ml: 2, fontSize: '0.8em' }}>
                    販売終了
                  </Box>
                </>
              ) : (
                formatPrice(property.current_price)
              )}
            </Typography>
            
            {/* 売出確認日と販売終了日の表示 */}
            {property.earliest_published_at && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body1" color="text.secondary">
                  売出確認日: {format(new Date(property.earliest_published_at), 'yyyy年MM月dd日', { locale: ja })}
                </Typography>
                {property.sold_at ? (
                  <>
                    <Typography variant="body1" color="text.secondary">
                      販売終了日: {format(new Date(property.sold_at), 'yyyy年MM月dd日', { locale: ja })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      （販売期間: {Math.floor((new Date(property.sold_at).getTime() - new Date(property.earliest_published_at).getTime()) / (1000 * 60 * 60 * 24))}日間）
                    </Typography>
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    （販売開始から{Math.floor((new Date().getTime() - new Date(property.earliest_published_at).getTime()) / (1000 * 60 * 60 * 24))}日経過）
                  </Typography>
                )}
              </Box>
            )}
            
            {/* 販売終了からの経過日数 */}
            {property.sold_at && (
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="body2">
                  この物件は販売終了しています。
                  （販売終了から{Math.floor((new Date().getTime() - new Date(property.sold_at).getTime()) / (1000 * 60 * 60 * 24))}日経過）
                </Typography>
              </Alert>
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
                <ListItemText 
                  primary="住所" 
                  secondaryTypographyProps={{
                    component: 'div'
                  }}
                  secondary={
                    <Box sx={{ 
                      display: 'flex', 
                      flexDirection: { xs: 'column', md: 'row' },
                      alignItems: { xs: 'flex-start', md: 'center' },
                      gap: { xs: 0.5, md: 2 }
                    }}>
                      <Typography variant="body2" color="text.secondary">
                        {building.address}
                      </Typography>
                      {/* 住所がある場合、Google Mapsへのリンクを表示 */}
                      {building.address && (
                        <Box sx={{ 
                          display: 'flex', 
                          gap: { xs: 1.5, md: 1 }, 
                          flexDirection: { xs: 'column', md: 'row' },
                          mt: { xs: 2, md: 1 },
                          width: { xs: '100%', md: 'auto' }
                        }}>
                          {/* Google Mapsリンク */}
                          <Box
                            component="a"
                          href={`https://www.google.com/maps/search/${encodeURIComponent(building.address)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            padding: { xs: '12px 16px', md: '4px 8px' },
                            borderRadius: '8px',
                            border: '1px solid #dadce0',
                            textDecoration: 'none',
                            backgroundColor: 'white',
                            transition: 'all 0.2s',
                            width: { xs: '100%', md: 'auto' },
                            minHeight: { xs: '48px', md: 'auto' },
                            '&:hover': {
                              backgroundColor: '#f1f3f4',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                            },
                            '&:active': {
                              backgroundColor: '#e8eaed'
                            }
                          }}
                        >
                          {/* Google Maps公式アイコン */}
                          <Box
                            component="img"
                            src="https://www.gstatic.com/images/branding/product/1x/maps_24dp.png"
                            alt="Google Maps"
                            sx={{
                              width: { xs: 20, md: 18 },
                              height: { xs: 20, md: 18 },
                              mr: 1
                            }}
                          />
                          <Typography
                            variant="body2"
                            sx={{
                              fontSize: { xs: '0.9375rem', md: '0.8125rem' },
                              color: '#1a73e8',
                              fontWeight: 500
                            }}
                          >
                            Google Mapsで表示
                          </Typography>
                        </Box>
                        
                        {/* ハザードマップリンク */}
                        <Box
                          component="a"
                          href={hazardMapUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            padding: { xs: '12px 16px', md: '4px 8px' },
                            borderRadius: '8px',
                            border: '1px solid #ff9800',
                            textDecoration: 'none',
                            backgroundColor: '#fff3e0',
                            transition: 'all 0.2s',
                            width: { xs: '100%', md: 'auto' },
                            minHeight: { xs: '48px', md: 'auto' },
                            '&:hover': {
                              backgroundColor: '#ffe0b2',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                            },
                            '&:active': {
                              backgroundColor: '#ffcc80'
                            }
                          }}
                        >
                          <Warning
                            sx={{
                              width: { xs: 20, md: 18 },
                              height: { xs: 20, md: 18 },
                              mr: 1,
                              color: '#ff6f00'
                            }}
                          />
                          <Typography
                            variant="body2"
                            sx={{
                              fontSize: { xs: '0.9375rem', md: '0.8125rem' },
                              color: '#ff6f00',
                              fontWeight: 500
                            }}
                          >
                            ハザードマップで確認
                          </Typography>
                        </Box>
                      </Box>
                      )}
                    </Box>
                  }
                />
              </ListItem>
              {property.station_info && (
                <ListItem>
                  <Train sx={{ mr: 2 }} />
                  <ListItemText 
                    primary="交通" 
                    secondary={property.station_info}
                    secondaryTypographyProps={{ 
                      component: 'div',
                      style: { whiteSpace: 'pre-line' }
                    }}
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
              {property.management_fee && (
                <ListItem>
                  <AccountBalanceWallet sx={{ mr: 2 }} />
                  <ListItemText primary="管理費" secondary={`${property.management_fee.toLocaleString()}円/月`} />
                </ListItem>
              )}
              {property.repair_fund && (
                <ListItem>
                  <AccountBalanceWallet sx={{ mr: 2 }} />
                  <ListItemText primary="修繕積立金" secondary={`${property.repair_fund.toLocaleString()}円/月`} />
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

      {/* 同じ建物の他の物件へのリンク */}
      <Paper elevation={1} sx={{ 
        p: { xs: 2, md: 3 }, 
        mb: 3,
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        color: 'white'
      }}>
        <Box sx={{ 
          display: 'flex', 
          flexDirection: { xs: 'column', md: 'row' },
          alignItems: { xs: 'stretch', md: 'center' },
          gap: 2
        }}>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Business sx={{ fontSize: 24, mr: 1 }} />
              <Typography variant="h6" fontWeight="bold">
                同じ建物内の他の物件
              </Typography>
            </Box>
            <Typography variant="body2" sx={{ opacity: 0.9 }}>
              {building.normalized_name}
              {building.total_units && ` （総戸数: ${building.total_units}戸）`}の他の部屋も確認できます
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<Apartment />}
            onClick={() => {
              const url = `/buildings/${building.id}/properties`;
              if (property.sold_at || property.has_active_listing === false) {
                navigate(`${url}?includeInactive=true`);
              } else {
                navigate(url);
              }
            }}
            size="large"
            sx={{
              backgroundColor: 'white',
              color: 'primary.main',
              px: { xs: 3, md: 4 },
              py: 1.5,
              textTransform: 'none',
              fontSize: '1rem',
              fontWeight: 600,
              boxShadow: 2,
              '&:hover': {
                backgroundColor: '#f5f5f5',
                transform: 'translateY(-2px)',
                boxShadow: 4
              },
              minWidth: { xs: '100%', md: 'auto' }
            }}
          >
            {building.normalized_name}の全物件を見る
          </Button>
        </Box>
      </Paper>

      {/* 掲載情報一覧 - アクティブな掲載がある場合のみ表示 */}
      {active_listings.length > 0 && (
        <Paper elevation={1} sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom>
            掲載情報一覧 ({active_listings.length}件)
          </Typography>
          {isMobile && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              ← 左右にスクロールできます →
            </Typography>
          )}
          <TableContainer sx={{ overflowX: 'auto' }}>
          <Table sx={{ minWidth: { xs: 600, md: 'auto' } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ 
                  width: isMobile ? '80px' : '10%',
                  minWidth: isMobile ? '80px' : 'auto'
                }}>掲載サイト</TableCell>
                <TableCell sx={{ 
                  width: isMobile ? '250px' : '40%',
                  minWidth: isMobile ? '200px' : 'auto'
                }}>タイトル</TableCell>
                <TableCell align="right" sx={{ 
                  width: isMobile ? '120px' : '20%',
                  minWidth: isMobile ? '100px' : 'auto'
                }}>価格</TableCell>
                <TableCell sx={{ 
                  width: isMobile ? '100px' : '20%',
                  minWidth: isMobile ? '90px' : 'auto'
                }}>売出確認日</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(showAllListings ? active_listings : active_listings.slice(0, 5)).map((listing) => (
                <TableRow 
                  key={listing.id}
                  hover
                  sx={{ 
                    cursor: 'pointer',
                    '&:hover': {
                      backgroundColor: 'action.hover'
                    }
                  }}
                  onClick={() => window.open(listing.url, '_blank')}
                >
                  <TableCell>
                    <Chip label={getScraperDisplayName(listing.source_site)} size="small" />
                  </TableCell>
                  <TableCell>{listing.title}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatPrice(listing.current_price)}</TableCell>
                  <TableCell>
                    {listing.first_published_at 
                      ? format(new Date(listing.first_published_at), 'yyyy/MM/dd', { locale: ja })
                      : listing.published_at
                      ? format(new Date(listing.published_at), 'yyyy/MM/dd', { locale: ja })
                      : format(new Date(listing.first_seen_at), 'yyyy/MM/dd', { locale: ja })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        
        {/* もっと見る/閉じるボタン */}
        {active_listings.length > 5 && (
          <Box sx={{ 
            display: 'flex', 
            justifyContent: 'center', 
            mt: 2,
            pt: 2,
            borderTop: '1px solid',
            borderColor: 'divider'
          }}>
            <Button
              onClick={() => setShowAllListings(!showAllListings)}
              variant="outlined"
              size="large"
              startIcon={showAllListings ? <ExpandLess /> : <ExpandMore />}
              sx={{
                px: 4,
                py: 1,
                textTransform: 'none',
                fontSize: '1rem',
                fontWeight: 500,
                borderRadius: 2,
                '&:hover': {
                  backgroundColor: 'primary.light',
                  color: 'white',
                  borderColor: 'primary.main'
                }
              }}
            >
              {showAllListings ? 
                '閉じる' : 
                `残り${active_listings.length - 5}件をすべて表示`
              }
            </Button>
          </Box>
        )}
      </Paper>
      )}
      
      {/* 販売終了物件の場合、過去の掲載情報を表示 */}
      {property.sold_at && active_listings.length === 0 && all_listings.length > 0 && (
        <Paper elevation={1} sx={{ p: 3, mb: 3, backgroundColor: '#f5f5f5' }}>
          <Typography variant="h5" gutterBottom color="text.secondary">
            過去の掲載情報
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            この物件は販売終了のため、現在有効な掲載情報はありません。
          </Typography>
          {isMobile && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              ← 左右にスクロールできます →
            </Typography>
          )}
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table sx={{ minWidth: { xs: 600, md: 'auto' } }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ 
                    width: isMobile ? '80px' : 'auto',
                    minWidth: isMobile ? '80px' : 'auto'
                  }}>掲載サイト</TableCell>
                  <TableCell sx={{ 
                    width: isMobile ? '250px' : 'auto',
                    minWidth: isMobile ? '200px' : 'auto'
                  }}>タイトル</TableCell>
                  <TableCell align="right" sx={{ 
                    width: isMobile ? '120px' : 'auto',
                    minWidth: isMobile ? '100px' : 'auto'
                  }}>最終価格</TableCell>
                  <TableCell sx={{ 
                    width: isMobile ? '100px' : 'auto',
                    minWidth: isMobile ? '90px' : 'auto'
                  }}>最終確認日</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {all_listings.slice(0, 5).map((listing) => (
                  <TableRow 
                    key={listing.id}
                    hover
                    sx={{ 
                      cursor: 'pointer',
                      '&:hover': {
                        backgroundColor: 'action.hover'
                      }
                    }}
                    onClick={() => window.open(listing.url, '_blank')}
                  >
                    <TableCell>
                      <Chip label={getScraperDisplayName(listing.source_site)} size="small" />
                    </TableCell>
                    <TableCell>{listing.title}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatPrice(listing.current_price)}</TableCell>
                    <TableCell>
                      {/* listing.last_confirmed_at 
                        ? format(new Date(listing.last_confirmed_at), 'yyyy/MM/dd', { locale: ja })
                        : '-' */}
                      -
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      {/* 価格推移グラフ */}
      {priceChartData.length > 0 && (
        <Paper elevation={1} sx={{ p: isMobile ? 2 : 3, mb: 3 }}>
          <Typography 
            variant={isMobile ? "h6" : "h5"} 
            gutterBottom 
            sx={{ display: 'flex', alignItems: 'center' }}
          >
            <Timeline sx={{ mr: 1, fontSize: isMobile ? 20 : 24 }} />
            価格推移
          </Typography>
          
          {/* 価格一貫性情報 */}
          {price_consistency && price_consistency.consistency_score < 1 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              異なる情報源で価格差が検出されました（一貫性スコア: {(price_consistency.consistency_score * 100).toFixed(1)}%）
            </Alert>
          )}
          
          <Box sx={{ height: isMobile ? 250 : 400, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="date" 
                  tick={{ fontSize: isMobile ? 10 : 12 }}
                  angle={isMobile ? -45 : 0}
                  textAnchor={isMobile ? "end" : "middle"}
                  height={isMobile ? 60 : 30}
                />
                <YAxis
                  tickFormatter={(value) => isMobile ? `${value.toLocaleString()}` : `${value.toLocaleString()}万`}
                  tick={{ fontSize: isMobile ? 10 : 12 }}
                  width={isMobile ? 45 : 60}
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
                        name={getScraperDisplayName(source)}
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
            <Box sx={{ 
              mt: 2, 
              display: 'flex', 
              justifyContent: 'space-around', 
              textAlign: 'center',
              flexDirection: { xs: 'row', sm: 'row' },
              gap: { xs: 1, sm: 2 }
            }}>
              <Box sx={{ flex: 1 }}>
                <Typography 
                  variant={isMobile ? "caption" : "body2"} 
                  color="text.secondary"
                  sx={{ fontSize: isMobile ? '0.7rem' : '0.875rem' }}
                >
                  初回価格
                </Typography>
                <Typography 
                  variant={isMobile ? "body1" : "h6"}
                  sx={{ 
                    fontSize: isMobile ? '0.875rem' : '1.25rem',
                    fontWeight: isMobile ? 600 : 500
                  }}
                >
                  {formatPrice(price_timeline.summary.initial_price)}
                </Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography 
                  variant={isMobile ? "caption" : "body2"} 
                  color="text.secondary"
                  sx={{ fontSize: isMobile ? '0.7rem' : '0.875rem' }}
                >
                  現在価格
                </Typography>
                <Typography 
                  variant={isMobile ? "body1" : "h6"}
                  sx={{ 
                    fontSize: isMobile ? '0.875rem' : '1.25rem',
                    fontWeight: isMobile ? 600 : 500
                  }}
                >
                  {formatPrice(price_timeline.summary.current_price)}
                </Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography 
                  variant={isMobile ? "caption" : "body2"} 
                  color="text.secondary"
                  sx={{ fontSize: isMobile ? '0.7rem' : '0.875rem' }}
                >
                  変動額
                </Typography>
                <Typography 
                  variant={isMobile ? "body1" : "h6"} 
                  color={price_timeline.summary.total_change > 0 ? 'error' : price_timeline.summary.total_change < 0 ? 'success' : 'inherit'}
                  sx={{ 
                    fontSize: isMobile ? '0.875rem' : '1.25rem',
                    fontWeight: isMobile ? 600 : 500
                  }}
                >
                  {price_timeline.summary.total_change > 0 ? '+' : ''}{price_timeline.summary.total_change}万円
                </Typography>
              </Box>
            </Box>
          )}
        </Paper>
      )}
    </Box>
  );
};

export default PropertyDetailPage;